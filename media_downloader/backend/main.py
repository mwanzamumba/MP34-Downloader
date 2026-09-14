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
    title="MP34 Downloader API"
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
            detail="Please provide a valid http or https URL."
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Invalid media URL."
        )

    return value


# =========================================================
# PLATFORM
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
# ROOT
# =========================================================

@app.get("/")
async def home():

    return {
        "status": "online",
        "service": "MP34 Downloader API"
    }


# =========================================================
# ANALYZE
# =========================================================

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

    url = validate_url(
        str(raw_url)
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
        }

        with yt_dlp.YoutubeDL(
            options
        ) as downloader:

            info = downloader.extract_info(
                url,
                download=False
            )

        if not info:

            raise HTTPException(
                status_code=422,
                detail="Could not find media information."
            )

        return {
            "title": (
                info.get("title")
                or "Untitled media"
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
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not analyse this link: "
                f"{error}"
            )
        ) from error


# =========================================================
# DOWNLOAD
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

    if not raw_url:

        raise HTTPException(
            status_code=422,
            detail="Please provide a media URL."
        )

    url = validate_url(
        str(raw_url)
    )

    if yt_dlp is None:

        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed."
        )

    # -----------------------------------------------------
    # CREATE TEMP DIRECTORY
    # -----------------------------------------------------

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="media_download_"
        )
    )

    try:

        output_template = str(
            temp_dir /
            "%(title).150s.%(ext)s"
        )

        options = {

            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,

            # Let yt-dlp select the best available media.
            "format": "best",

            "outtmpl": output_template,

            # Do not keep partial files after an error.
            "continuedl": True,

            # Allow yt-dlp to merge streams if necessary.
            "merge_output_format": "mp4",
        }

        # -------------------------------------------------
        # DOWNLOAD
        # -------------------------------------------------

        with yt_dlp.YoutubeDL(
            options
        ) as downloader:

            info = downloader.extract_info(
                url,
                download=True
            )

        # -------------------------------------------------
        # FIND ACTUAL CREATED FILE
        # -------------------------------------------------

        created_files = []

        for file in temp_dir.rglob("*"):

            if not file.is_file():
                continue

            # Ignore yt-dlp temporary/partial files.
            if file.name.endswith(".part"):
                continue

            if file.name.endswith(".ytdl"):
                continue

            created_files.append(file)

        # -------------------------------------------------
        # NO FILE
        # -------------------------------------------------

        if not created_files:

            raise HTTPException(
                status_code=500,
                detail=(
                    "yt-dlp completed but did not create "
                    "a media file. The source may provide "
                    "only a streaming format or require "
                    "additional processing."
                )
            )

        # -------------------------------------------------
        # PICK LARGEST FILE
        # -------------------------------------------------

        file_path = max(
            created_files,
            key=lambda file: file.stat().st_size
        )

        # -------------------------------------------------
        # VERIFY SIZE
        # -------------------------------------------------

        file_size = file_path.stat().st_size

        if file_size <= 0:

            raise HTTPException(
                status_code=500,
                detail="The downloaded media file is empty."
            )

        # -------------------------------------------------
        # CLEANUP AFTER RESPONSE
        # -------------------------------------------------

        background_tasks.add_task(
            cleanup_download,
            temp_dir
        )

        # -------------------------------------------------
        # RETURN FILE
        # -------------------------------------------------

        return FileResponse(
            path=str(file_path),

            filename=file_path.name,

            media_type="application/octet-stream"
        )

    except HTTPException:

        cleanup_download(
            temp_dir
        )

        raise

    except Exception as error:

        cleanup_download(
            temp_dir
        )

        raise HTTPException(
            status_code=422,
            detail={
                "message": "Download failed.",
                "error": str(error),
            }
        ) from error


# =========================================================
# CLEANUP
# =========================================================

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

        # Remove directories from deepest level.
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