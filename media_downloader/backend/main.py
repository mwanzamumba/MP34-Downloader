from pathlib import Path
from urllib.parse import urlparse
import tempfile

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


app = FastAPI(title="MP34 Downloader API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# URL VALIDATION
# ---------------------------------------------------------

def validate_url(value: str) -> str:
    value = value.strip()

    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Provide a valid http or https URL."
        )

    return value


# ---------------------------------------------------------
# PLATFORM DETECTION
# ---------------------------------------------------------

def platform_for(url: str) -> str:
    host = urlparse(url).netloc.lower()

    for domain, name in [
        ("tiktok.com", "TikTok"),
        ("youtube.com", "YouTube"),
        ("youtu.be", "YouTube"),
        ("instagram.com", "Instagram"),
        ("facebook.com", "Facebook"),
        ("fb.watch", "Facebook"),
        ("x.com", "X / Twitter"),
        ("twitter.com", "X / Twitter"),
    ]:
        if domain in host:
            return name

    return "Other"


# ---------------------------------------------------------
# FIND A DIRECT DOWNLOADABLE FORMAT
# ---------------------------------------------------------

def pick_direct_format(info: dict):
    """
    Find a direct HTTP/HTTPS media URL.

    We prefer progressive formats containing BOTH:
        - video
        - audio

    This is important because a video-only stream cannot
    simply be saved as a normal MP4 without merging audio.
    """

    formats = info.get("formats") or []

    direct_formats = []

    for fmt in formats:
        media_url = fmt.get("url")
        protocol = (fmt.get("protocol") or "").lower()

        if not media_url:
            continue

        if protocol not in ("http", "https"):
            continue

        direct_formats.append(fmt)

    if not direct_formats:
        return None

    # -----------------------------------------------------
    # 1. Prefer progressive video + audio
    # -----------------------------------------------------

    progressive = []

    for fmt in direct_formats:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")

        has_video = vcodec and vcodec != "none"
        has_audio = acodec and acodec != "none"

        if has_video and has_audio:
            progressive.append(fmt)

    if progressive:

        def progressive_score(fmt):
            height = fmt.get("height") or 0
            bitrate = fmt.get("tbr") or 0
            fps = fmt.get("fps") or 0

            # Prefer MP4 when possible.
            ext_bonus = 1 if fmt.get("ext") == "mp4" else 0

            return (
                ext_bonus,
                height,
                bitrate,
                fps,
            )

        progressive.sort(
            key=progressive_score,
            reverse=True,
        )

        return progressive[0]

    # -----------------------------------------------------
    # 2. No progressive video.
    #
    # Do NOT blindly return a video-only stream because
    # it would normally have no audio.
    # -----------------------------------------------------

    return None


# ---------------------------------------------------------
# ANALYZE
# ---------------------------------------------------------

@app.post("/analyze")
async def analyze_link(data: dict):

    url = validate_url(
        str(data.get("url", "")).strip()
    )

    platform = platform_for(url)

    if yt_dlp is None:
        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed."
        )

    try:

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,

            # Ask yt-dlp to prefer a normal video+audio
            # format when the website provides one.
            "format": "best",
        }

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False,
            )

        if not info:
            raise HTTPException(
                status_code=422,
                detail="No media information was returned."
            )

        selected_format = pick_direct_format(info)

        if selected_format is None:

            formats = info.get("formats") or []

            if formats:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "The media was found, but this source does "
                        "not provide a single direct video+audio "
                        "download URL. It may use separate video "
                        "and audio streams or a streaming manifest."
                    )
                )

            raise HTTPException(
                status_code=422,
                detail="No downloadable media formats were found."
            )

        download_url = selected_format.get("url")

        if not download_url:
            raise HTTPException(
                status_code=422,
                detail="The selected media format has no download URL."
            )

        extension = (
            selected_format.get("ext")
            or info.get("ext")
            or "mp4"
        )

        protocol = (
            selected_format.get("protocol")
            or ""
        ).lower()

        return {
            "title": (
                info.get("title")
                or urlparse(url).netloc
            ),

            "thumbnail": (
                info.get("thumbnail")
                or ""
            ),

            "platform": (
                info.get("extractor_key")
                or platform
            ),

            "source_url": url,

            "download_url": download_url,

            "extension": extension,

            "supports_resume": protocol in (
                "http",
                "https",
            ),

            "format_id": selected_format.get(
                "format_id",
                ""
            ),

            "format_note": selected_format.get(
                "format_note",
                ""
            ),

            "filesize": (
                selected_format.get("filesize")
                or selected_format.get("filesize_approx")
                or 0
            ),
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not analyse this link: {error}"
            ),
        ) from error


# ---------------------------------------------------------
# OLD DOWNLOAD ENDPOINT
# ---------------------------------------------------------

@app.post("/download")
async def download_link(
    data: dict,
    background_tasks: BackgroundTasks,
):

    url = validate_url(
        str(data.get("url", "")).strip()
    )

    if yt_dlp is None:
        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed."
        )

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="media_download_"
        )
    )

    try:

        output_template = str(
            temp_dir / "%(title).150s.%(ext)s"
        )

        options = {
            "quiet": True,
            "noplaylist": True,
            "format": "best",
            "outtmpl": output_template,
        }

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=True,
            )

            file_path = Path(
                downloader.prepare_filename(info)
            )

        if not file_path.exists():

            raise HTTPException(
                status_code=500,
                detail="The media file was not created."
            )

        background_tasks.add_task(
            cleanup_download,
            temp_dir,
        )

        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/octet-stream",
        )

    except HTTPException:

        cleanup_download(temp_dir)

        raise

    except Exception as error:

        cleanup_download(temp_dir)

        raise HTTPException(
            status_code=422,
            detail=f"Download failed: {error}"
        ) from error


# ---------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------

def cleanup_download(directory: Path):

    try:

        if directory.exists():

            for file in directory.iterdir():

                if file.is_file():
                    file.unlink()

            directory.rmdir()

    except Exception:
        pass


# ---------------------------------------------------------
# VERSION
# ---------------------------------------------------------

@app.get("/version")
async def version():

    return {
        "yt_dlp": (
            yt_dlp.version.__version__
            if yt_dlp
            else "not installed"
        )
    }