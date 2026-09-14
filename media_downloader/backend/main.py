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


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="MP34 Downloader API",
    version="1.0.0",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# URL VALIDATION
# =========================================================

def validate_url(value: str) -> str:
    value = value.strip()

    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail="URL must start with http:// or https://."
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Invalid URL."
        )

    return value


# =========================================================
# PLATFORM DETECTION
# =========================================================

def platform_for(url: str) -> str:

    host = urlparse(url).netloc.lower()

    platforms = [
        ("tiktok.com", "TikTok"),
        ("youtube.com", "YouTube"),
        ("youtu.be", "YouTube"),
        ("instagram.com", "Instagram"),
        ("facebook.com", "Facebook"),
        ("fb.watch", "Facebook"),
        ("x.com", "X / Twitter"),
        ("twitter.com", "X / Twitter"),
    ]

    for domain, name in platforms:

        if domain in host:
            return name

    return "Other"


# =========================================================
# FORMAT INFORMATION
# =========================================================

def format_summary(fmt: dict) -> dict:

    return {
        "format_id": fmt.get("format_id"),
        "ext": fmt.get("ext"),
        "protocol": fmt.get("protocol"),
        "vcodec": fmt.get("vcodec"),
        "acodec": fmt.get("acodec"),
        "height": fmt.get("height"),
        "width": fmt.get("width"),
        "fps": fmt.get("fps"),
        "tbr": fmt.get("tbr"),
        "abr": fmt.get("abr"),
        "filesize": (
            fmt.get("filesize")
            or fmt.get("filesize_approx")
            or 0
        ),
    }


# =========================================================
# FIND DIRECT PROGRESSIVE FORMAT
# =========================================================

def find_progressive_format(info: dict):

    formats = info.get("formats") or []

    candidates = []

    for fmt in formats:

        media_url = fmt.get("url")

        protocol = (
            fmt.get("protocol")
            or ""
        ).lower()

        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")

        # Must have a real URL.
        if not media_url:
            continue

        # We need an ordinary HTTP/HTTPS URL.
        if protocol not in ("http", "https"):
            continue

        # Must contain video.
        if not vcodec or vcodec == "none":
            continue

        # Must contain audio.
        if not acodec or acodec == "none":
            continue

        candidates.append(fmt)

    if not candidates:
        return None

    # Prefer MP4.
    # Then prefer higher resolution.
    # Then higher bitrate.

    candidates.sort(
        key=lambda fmt: (
            1 if fmt.get("ext") == "mp4" else 0,
            fmt.get("height") or 0,
            fmt.get("tbr") or 0,
        ),
        reverse=True,
    )

    return candidates[0]


# =========================================================
# FIND AUDIO FORMAT
# =========================================================

def find_audio_format(info: dict):

    formats = info.get("formats") or []

    candidates = []

    for fmt in formats:

        media_url = fmt.get("url")

        protocol = (
            fmt.get("protocol")
            or ""
        ).lower()

        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")

        if not media_url:
            continue

        if protocol not in ("http", "https"):
            continue

        if vcodec not in (None, "none"):
            continue

        if not acodec or acodec == "none":
            continue

        candidates.append(fmt)

    if not candidates:
        return None

    candidates.sort(
        key=lambda fmt: (
            fmt.get("abr") or 0,
            fmt.get("tbr") or 0,
        ),
        reverse=True,
    )

    return candidates[0]


# =========================================================
# ANALYZE MEDIA
# =========================================================

@app.post("/analyze")
async def analyze_link(data: dict):

    # -----------------------------------------------------
    # Validate request
    # -----------------------------------------------------

    if not isinstance(data, dict):

        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON."
        )

    raw_url = data.get("url")

    if raw_url is None:

        raise HTTPException(
            status_code=422,
            detail="Missing 'url' field."
        )

    url = validate_url(str(raw_url))

    platform = platform_for(url)

    # -----------------------------------------------------
    # Check yt-dlp
    # -----------------------------------------------------

    if yt_dlp is None:

        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed on the server."
        )

    # -----------------------------------------------------
    # yt-dlp extraction
    # -----------------------------------------------------

    try:

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,

            # We intentionally don't force a format here.
            # We want to inspect what the website actually
            # provides.
        }

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False,
            )

        # -------------------------------------------------
        # Validate extraction result
        # -------------------------------------------------

        if not info:

            raise HTTPException(
                status_code=422,
                detail="yt-dlp returned no media information."
            )

        # -------------------------------------------------
        # Basic information
        # -------------------------------------------------

        title = (
            info.get("title")
            or urlparse(url).netloc
        )

        thumbnail = (
            info.get("thumbnail")
            or ""
        )

        extractor = (
            info.get("extractor_key")
            or platform
        )

        formats = info.get("formats") or []

        # -------------------------------------------------
        # Find progressive video
        # -------------------------------------------------

        selected = find_progressive_format(info)

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        if selected:

            download_url = selected.get("url")

            if download_url:

                return {
                    "success": True,

                    "title": title,

                    "thumbnail": thumbnail,

                    "platform": extractor,

                    "source_url": url,

                    "download_url": download_url,

                    "extension": (
                        selected.get("ext")
                        or "mp4"
                    ),

                    "supports_resume": True,

                    "format_id": (
                        selected.get("format_id")
                        or ""
                    ),

                    "format_note": (
                        selected.get("format_note")
                        or ""
                    ),

                    "width": (
                        selected.get("width")
                        or 0
                    ),

                    "height": (
                        selected.get("height")
                        or 0
                    ),

                    "filesize": (
                        selected.get("filesize")
                        or selected.get("filesize_approx")
                        or 0
                    ),
                }

        # =================================================
        # NO PROGRESSIVE FORMAT
        # =================================================

        audio_format = find_audio_format(info)

        # Count different types of formats.

        http_formats = []
        video_only_formats = []
        audio_only_formats = []
        manifest_formats = []

        for fmt in formats:

            protocol = (
                fmt.get("protocol")
                or ""
            ).lower()

            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")

            if protocol in ("m3u8", "m3u8_native"):
                manifest_formats.append(
                    format_summary(fmt)
                )
                continue

            if protocol not in ("http", "https"):
                continue

            summary = format_summary(fmt)

            http_formats.append(summary)

            if (
                vcodec
                and vcodec != "none"
                and (
                    not acodec
                    or acodec == "none"
                )
            ):
                video_only_formats.append(summary)

            if (
                acodec
                and acodec != "none"
                and (
                    not vcodec
                    or vcodec == "none"
                )
            ):
                audio_only_formats.append(summary)

        # -------------------------------------------------
        # Return diagnostic response
        # -------------------------------------------------

        return {
            "success": False,

            "title": title,

            "thumbnail": thumbnail,

            "platform": extractor,

            "source_url": url,

            "download_url": "",

            "extension": (
                info.get("ext")
                or "mp4"
            ),

            "supports_resume": False,

            "message": (
                "The media was successfully detected, "
                "but no single direct video+audio URL "
                "was found."
            ),

            "debug": {
                "total_formats": len(formats),

                "http_formats": http_formats,

                "video_only_formats": video_only_formats,

                "audio_only_formats": audio_only_formats,

                "manifest_formats": manifest_formats,

                "has_audio_stream": (
                    audio_format is not None
                ),
            },
        }

    # -----------------------------------------------------
    # Extraction failed
    # -----------------------------------------------------

    except HTTPException:
        raise

    except Exception as error:

        error_message = str(error)

        raise HTTPException(
            status_code=422,
            detail={
                "message": "yt-dlp could not analyse this URL.",
                "platform": platform,
                "error": error_message,
            },
        ) from error


# =========================================================
# OLD SERVER-SIDE DOWNLOAD ENDPOINT
# =========================================================

@app.post("/download")
async def download_link(
    data: dict,
    background_tasks: BackgroundTasks,
):

    if not isinstance(data, dict):

        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON."
        )

    raw_url = data.get("url")

    if raw_url is None:

        raise HTTPException(
            status_code=422,
            detail="Missing 'url' field."
        )

    url = validate_url(str(raw_url))

    if yt_dlp is None:

        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed."
        )

    # -----------------------------------------------------
    # Temporary directory
    # -----------------------------------------------------

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="media_download_"
        )
    )

    try:

        output_template = str(
            temp_dir
            / "%(title).150s.%(ext)s"
        )

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,

            # Let yt-dlp choose the best available format.
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

        # -------------------------------------------------
        # Check file
        # -------------------------------------------------

        if not file_path.exists():

            raise HTTPException(
                status_code=500,
                detail="The media file was not created."
            )

        # -------------------------------------------------
        # Cleanup after response
        # -------------------------------------------------

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
            detail={
                "message": "Download failed.",
                "error": str(error),
            },
        ) from error


# =========================================================
# CLEANUP
# =========================================================

def cleanup_download(directory: Path):

    try:

        if directory.exists():

            for file in directory.iterdir():

                try:

                    if file.is_file():
                        file.unlink()

                except Exception:
                    pass

            try:
                directory.rmdir()

            except Exception:
                pass

    except Exception:
        pass


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def home():

    return {
        "status": "online",
        "service": "MP34 Downloader API",
        "message": "API is running."
    }


# =========================================================
# VERSION
# =========================================================

@app.get("/version")
async def version():

    return {
        "yt_dlp": (
            yt_dlp.version.__version__
            if yt_dlp
            else "not installed"
        )
    }