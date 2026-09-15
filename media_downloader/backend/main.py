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


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# URL VALIDATION
# ============================================================

def validate_url(value: str) -> str:
    value = value.strip()

    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail="Please provide a valid http or https URL."
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Invalid media URL."
        )

    return value


# ============================================================
# PLATFORM DETECTION
# ============================================================

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


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():
    return {
        "status": "online",
        "service": "MP34 Downloader API"
    }


# ============================================================
# ANALYZE
# ============================================================
@app.post("/analyze")
async def analyze_link(data: dict):
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON."
        )

    raw_url = data.get("url")

    if not raw_url:
        raise HTTPException(
            status_code=422,
            detail="Please provide a media URL."
        )

    url = validate_url(str(raw_url))

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
        }

        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(
                url,
                download=False,
            )

        if not info:
            raise HTTPException(
                status_code=422,
                detail="Could not find media information."
            )

        formats = info.get("formats", [])

        video_formats = []
        audio_formats = []

        for fmt in formats:
            stream_url = fmt.get("url")

            if not stream_url:
                continue

            video_ext = fmt.get("video_ext")
            audio_ext = fmt.get("audio_ext")

            if video_ext and video_ext != "none":
                video_formats.append(fmt)

            if audio_ext and audio_ext != "none":
                audio_formats.append(fmt)

        if not video_formats:
            raise HTTPException(
                status_code=422,
                detail="No downloadable video stream was found."
            )

        if not audio_formats:
            raise HTTPException(
                status_code=422,
                detail="No downloadable audio stream was found."
            )

        # Prefer progressive MP4 video streams.
        progressive_video = [
            fmt for fmt in video_formats
            if fmt.get("ext") == "mp4"
            and fmt.get("format_id") in {"hd", "sd"}
        ]

        if progressive_video:
            video_formats = progressive_video

        # Prefer HD over SD.
        def video_score(fmt):
            width = fmt.get("width") or 0
            height = fmt.get("height") or 0
            return (
                width * height,
                fmt.get("tbr") or 0,
            )

        best_video = max(
            video_formats,
            key=video_score,
        )

        # Prefer M4A audio.
        m4a_audio = [
            fmt for fmt in audio_formats
            if fmt.get("ext") == "m4a"
        ]

        if m4a_audio:
            audio_formats = m4a_audio

        def audio_score(fmt):
            return (
                fmt.get("abr") or 0,
                fmt.get("tbr") or 0,
            )

        best_audio = max(
            audio_formats,
            key=audio_score,
        )

        return {
            "title": info.get("title") or "Untitled media",
            "thumbnail": info.get("thumbnail") or "",
            "platform": info.get("extractor_key")
                or platform_for(url),
            "source_url": url,

            "video": {
                "url": best_video.get("url"),
                "format_id": best_video.get("format_id"),
                "extension": best_video.get("ext") or "mp4",
                "width": best_video.get("width"),
                "height": best_video.get("height"),
                "resolution": best_video.get("resolution"),
            },

            "audio": {
                "url": best_audio.get("url"),
                "format_id": best_audio.get("format_id"),
                "extension": best_audio.get("ext") or "m4a",
                "abr": best_audio.get("abr"),
            },
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Could not analyse this link: {error}"
        ) from error
# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
async def download_link(
    data: dict,
    background_tasks: BackgroundTasks
):

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON."
        )

    raw_url = data.get("url")

    if not raw_url:
        raise HTTPException(
            status_code=422,
            detail="Please provide a media URL."
        )

    url = validate_url(str(raw_url))

    if yt_dlp is None:
        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed."
        )

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="mp34_download_"
        )
    )

    try:

        # ----------------------------------------------------
        # Predictable output filename
        # ----------------------------------------------------

        output_template = str(
            temp_dir / "download.%(ext)s"
        )

        options = {
            "quiet": False,
            "no_warnings": False,

            "noplaylist": True,

            # Use one complete downloadable format.
            "format": "best",

            "outtmpl": output_template,

            "continuedl": True,

            "merge_output_format": "mp4",
        }

        print("=" * 60)
        print("MP34 DOWNLOAD START")
        print("URL:", url)
        print("TEMP DIRECTORY:", temp_dir)
        print("=" * 60)

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=True
               
            )
        print(info.key())

        print("=" * 60)
        print("YT-DLP FINISHED")
        print(
            "TITLE:",
            info.get("title") if info else "unknown"
        )
        print("=" * 60)

        # ----------------------------------------------------
        # FIND ACTUAL CREATED FILE
        # ----------------------------------------------------

        files = []

        for file in temp_dir.rglob("*"):

            if not file.is_file():
                continue

            if file.name.endswith(".part"):
                continue

            if file.name.endswith(".ytdl"):
                continue

            try:

                if file.stat().st_size <= 0:
                    continue

            except Exception:

                continue

            files.append(file)

        # ----------------------------------------------------
        # PRINT CREATED FILES
        # ----------------------------------------------------

        print("FILES CREATED:")

        for file in files:

            try:

                print(
                    " -",
                    file.name,
                    file.stat().st_size,
                    "bytes"
                )

            except Exception:

                print(
                    " -",
                    file.name
                )

        # ----------------------------------------------------
        # NO FILE
        # ----------------------------------------------------

        if not files:

            all_items = []

            for item in temp_dir.rglob("*"):
                all_items.append(str(item))

            print(
                "NO USABLE MEDIA FILE WAS CREATED."
            )

            print(
                "DIRECTORY CONTENT:"
            )

            print(all_items)

            raise HTTPException(
                status_code=500,
                detail=(
                    "yt-dlp finished but no media "
                    "file was created."
                )
            )

        # ----------------------------------------------------
        # SELECT LARGEST FILE
        # ----------------------------------------------------

        file_path = max(
            files,
            key=lambda file: file.stat().st_size
        )

        file_size = file_path.stat().st_size

        print("=" * 60)
        print("FILE READY")
        print("FILE:", file_path)
        print("SIZE:", file_size, "bytes")
        print("=" * 60)

        if file_size <= 0:

            raise HTTPException(
                status_code=500,
                detail="Downloaded media file is empty."
            )

        # ----------------------------------------------------
        # MIME TYPE
        # ----------------------------------------------------

        extension = file_path.suffix.lower()

        mime_types = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",

            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }

        media_type = mime_types.get(
            extension,
            "application/octet-stream"
        )

        # ----------------------------------------------------
        # RETURN FILE
        # ----------------------------------------------------

        background_tasks.add_task(
            cleanup_download,
            temp_dir
        )

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type=media_type,
        )

    except HTTPException:

        cleanup_download(temp_dir)

        raise

    except Exception as error:

        print("=" * 60)
        print("DOWNLOAD ERROR")
        print(str(error))
        print("=" * 60)

        cleanup_download(temp_dir)

        raise HTTPException(
            status_code=422,
            detail={
                "message": "Download failed.",
                "error": str(error),
            }
        ) from error


# ============================================================
# CLEANUP
# ============================================================

def cleanup_download(
    directory: Path
):

    try:

        if not directory.exists():
            return

        for file in directory.rglob("*"):

            try:

                if file.is_file():
                    file.unlink()

            except Exception:
                pass

        directories = sorted(
            [
                item
                for item in directory.rglob("*")
                if item.is_dir()
            ],
            key=lambda item: len(item.parts),
            reverse=True,
        )

        for folder in directories:

            try:
                folder.rmdir()

            except Exception:
                pass

        try:
            directory.rmdir()

        except Exception:
            pass

    except Exception:
        pass


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
async def version():

    return {
        "yt_dlp":
            yt_dlp.version.__version__
            if yt_dlp
            else "not installed"
    }