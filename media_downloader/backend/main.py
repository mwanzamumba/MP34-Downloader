import os
import time
import uuid
import shutil
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# APP CONFIGURATION
# ============================================================

APP_VERSION = "4.0.0"

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FILE_TTL = 1800

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    version=APP_VERSION,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class AnalyzeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    media_type: str = "video"
    audio_format: str | None = None


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str) -> str:

    hostname = urlparse(url).hostname

    if not hostname:
        return "unknown"

    hostname = hostname.lower()

    if "youtube.com" in hostname or "youtu.be" in hostname:
        return "youtube"

    if "tiktok.com" in hostname:
        return "tiktok"

    if "instagram.com" in hostname:
        return "instagram"

    if "facebook.com" in hostname or "fb.watch" in hostname:
        return "facebook"

    if "twitter.com" in hostname or "x.com" in hostname:
        return "x"

    return "unknown"


# ============================================================
# URL VALIDATION
# ============================================================

def validate_url(url: str) -> str:

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required.",
        )

    url = url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are supported.",
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL.",
        )

    return url


# ============================================================
# YOUTUBE NORMALIZATION
# ============================================================

def normalize_youtube_url(url: str) -> str:

    try:
        parsed = urlparse(url)

        hostname = (
            parsed.hostname or ""
        ).lower()

        if "youtu.be" in hostname:

            video_id = (
                parsed.path
                .strip("/")
                .split("/")[0]
            )

            if video_id:
                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

        if "youtube.com" in hostname:

            query = parse_qs(
                parsed.query
            )

            video_id = query.get("v")

            if video_id:
                return (
                    "https://www.youtube.com/watch?v="
                    + video_id[0]
                )

    except Exception:
        pass

    return url


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_string(value):

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.lower() in (
        "none",
        "null",
    ):
        return None

    return text


def safe_int(value):

    if value is None:
        return None

    try:
        return int(value)
    except Exception:
        return None


def safe_float(value):

    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    download: bool = False,
    output_template: str | None = None,
):

    options = {
        "quiet": True,
        "no_warnings": True,

        "noplaylist": True,

        "retries": 3,
        "fragment_retries": 3,

        "continuedl": True,
        "overwrites": True,

        "socket_timeout": 30,

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),
        },

        "restrictfilenames": True,

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "default",
                    "web_embedded",
                ],
            },
        },
    }

    if output_template:
        options["outtmpl"] = output_template

    return options


# ============================================================
# PUBLIC FORMAT CONVERSION
# ============================================================

def format_to_public(fmt):

    if not isinstance(
        fmt,
        dict,
    ):
        return None

    vcodec = safe_string(
        fmt.get("vcodec")
    )

    acodec = safe_string(
        fmt.get("acodec")
    )

    has_video = (
        vcodec is not None
        and vcodec != "none"
    )

    has_audio = (
        acodec is not None
        and acodec != "none"
    )

    return {
        "format_id": safe_string(
            fmt.get("format_id")
        ),

        "ext": safe_string(
            fmt.get("ext")
        ),

        "format_note": safe_string(
            fmt.get("format_note")
        ),

        "width": safe_int(
            fmt.get("width")
        ),

        "height": safe_int(
            fmt.get("height")
        ),

        "fps": safe_float(
            fmt.get("fps")
        ),

        "vcodec": vcodec,

        "acodec": acodec,

        "filesize": safe_int(
            fmt.get("filesize")
        ),

        "filesize_approx": safe_int(
            fmt.get("filesize_approx")
        ),

        "abr": safe_float(
            fmt.get("abr")
        ),

        "url": safe_string(
            fmt.get("url")
        ),

        "has_video": has_video,

        "has_audio": has_audio,
    }


# ============================================================
# FORMAT SELECTION
# ============================================================

def choose_recommended_video(formats):

    candidates = [
        fmt
        for fmt in formats
        if (
            fmt.get("vcodec") not in (
                None,
                "none",
            )
        )
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("height") or 0,
            x.get("width") or 0,
            x.get("fps") or 0,
        ),
        reverse=True,
    )

    return candidates[0]


def choose_recommended_audio(formats):

    candidates = [
        fmt
        for fmt in formats
        if (
            fmt.get("acodec") not in (
                None,
                "none",
            )
            and
            fmt.get("vcodec") in (
                None,
                "none",
            )
        )
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("abr") or 0
        ),
        reverse=True,
    )

    return candidates[0]


def choose_audio_for_video(
    formats,
    selected_video,
):

    audio_formats = [
        fmt
        for fmt in formats
        if (
            fmt.get("acodec") not in (
                None,
                "none",
            )
            and
            fmt.get("vcodec") in (
                None,
                "none",
            )
        )
    ]

    if not audio_formats:
        return None

    audio_formats.sort(
        key=lambda x: (
            x.get("abr") or 0
        ),
        reverse=True,
    )

    return audio_formats[0]


# ============================================================
# CLEANUP
# ============================================================

def cleanup_old_files():

    now = time.time()

    try:

        for item in DOWNLOAD_DIR.iterdir():

            if not item.is_dir():
                continue

            try:

                age = (
                    now
                    - item.stat().st_mtime
                )

                if age > FILE_TTL:

                    shutil.rmtree(
                        item,
                        ignore_errors=True,
                    )

                    logger.info(
                        "Deleted old job: %s",
                        item.name,
                    )

            except Exception:
                continue

    except Exception:
        pass


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "success": True,
        "message": "Media Downloader API is running.",
        "version": APP_VERSION,
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "success": True,
        "status": "healthy",
        "version": APP_VERSION,
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {
        "success": True,
        "version": APP_VERSION,
    }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(
    request: AnalyzeRequest,
):

    cleanup_old_files()

    url = validate_url(
        request.url
    )

    url = normalize_youtube_url(
        url
    )

    platform = detect_platform(
        url
    )

    logger.info(
        "Analyzing %s URL: %s",
        platform,
        url,
    )

    options = get_ytdlp_options()

    try:

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

    except Exception as e:

        logger.exception(
            "Analysis failed"
        )

        return {
            "success": False,
            "error": str(e),
        }

    if not info:

        return {
            "success": False,
            "error": "No media information was returned.",
        }

    raw_formats = info.get(
        "formats",
        [],
    )

    public_formats = []

    for fmt in raw_formats:

        public_format = (
            format_to_public(fmt)
        )

        if public_format:

            if public_format.get(
                "format_id"
            ):

                public_formats.append(
                    public_format
                )

    video_formats = [
        fmt
        for fmt in public_formats
        if fmt.get("has_video")
    ]

    audio_formats = [
        fmt
        for fmt in public_formats
        if (
            fmt.get("has_audio")
            and not fmt.get("has_video")
        )
    ]

    progressive_formats = [
        fmt
        for fmt in public_formats
        if (
            fmt.get("has_video")
            and fmt.get("has_audio")
        )
    ]

    recommended_video = (
        choose_recommended_video(
            raw_formats
        )
    )

    recommended_audio = (
        choose_recommended_audio(
            raw_formats
        )
    )

    return {
        "success": True,

        "title": info.get(
            "title",
            "Unknown title",
        ),

        "thumbnail": info.get(
            "thumbnail"
        ),

        "duration": info.get(
            "duration"
        ),

        "platform": platform,

        "formats": public_formats,

        "video_formats": video_formats,

        "audio_formats": audio_formats,

        "progressive_formats":
            progressive_formats,

        "recommended_video":
            format_to_public(
                recommended_video
            )
            if recommended_video
            else None,

        "recommended_audio":
            format_to_public(
                recommended_audio
            )
            if recommended_audio
            else None,
    }


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
def download(
    request: DownloadRequest,
):

    cleanup_old_files()

    url = validate_url(
        request.url
    )

    url = normalize_youtube_url(
        url
    )

    if not request.format_id:

        return {
            "success": False,
            "error": "format_id is required.",
        }

    logger.info(
        "Download request: %s",
        request.format_id,
    )

    # --------------------------------------------------------
    # RE-EXTRACT INFORMATION
    # --------------------------------------------------------

    extract_options = (
        get_ytdlp_options()
    )

    try:

        with yt_dlp.YoutubeDL(
            extract_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

    except Exception as e:

        logger.exception(
            "Download extraction failed"
        )

        return {
            "success": False,
            "error": str(e),
        }

    raw_formats = info.get(
        "formats",
        [],
    )

    # --------------------------------------------------------
    # FIND REQUESTED FORMAT
    # --------------------------------------------------------

    selected_format = None

    for fmt in raw_formats:

        if str(
            fmt.get("format_id")
        ) == str(
            request.format_id
        ):

            selected_format = fmt
            break

    if selected_format is None:

        return {
            "success": False,
            "error": (
                "The selected format is no longer "
                "available. Please analyze the link again."
            ),
        }

    # --------------------------------------------------------
    # CREATE JOB
    # --------------------------------------------------------

    job_id = uuid.uuid4().hex

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_template = str(
        job_dir
        / "%(title).150s.%(ext)s"
    )

    # --------------------------------------------------------
    # DOWNLOAD OPTIONS
    # --------------------------------------------------------

    download_options = get_ytdlp_options(
        download=True,
        output_template=output_template,
    )

    # ========================================================
    # AUDIO DOWNLOAD
    # ========================================================

    if request.media_type == "audio":

        download_options["format"] = (
            request.format_id
        )

        output_audio_format = (
            request.audio_format
            or "mp3"
        )

        download_options[
            "postprocessors"
        ] = [
            {
                "key":
                    "FFmpegExtractAudio",

                "preferredcodec":
                    output_audio_format,

                "preferredquality":
                    "192",
            }
        ]

    # ========================================================
    # VIDEO DOWNLOAD
    # ========================================================

    else:

        vcodec = selected_format.get(
            "vcodec"
        )

        acodec = selected_format.get(
            "acodec"
        )

        has_video = (
            vcodec not in (
                None,
                "none",
            )
        )

        has_audio = (
            acodec not in (
                None,
                "none",
            )
        )

        if not has_video:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            return {
                "success": False,
                "error": (
                    "The selected format does not "
                    "contain video."
                ),
            }

        # ----------------------------------------------------
        # PROGRESSIVE VIDEO
        # ----------------------------------------------------

        if has_audio:

            download_options[
                "format"
            ] = request.format_id

        # ----------------------------------------------------
        # VIDEO-ONLY FORMAT
        # ----------------------------------------------------

        else:

            audio_format = (
                choose_audio_for_video(
                    raw_formats,
                    selected_format,
                )
            )

            if audio_format is None:

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True,
                )

                return {
                    "success": False,
                    "error": (
                        "This video has no compatible "
                        "audio stream."
                    ),
                }

            video_id = (
                request.format_id
            )

            audio_id = str(
                audio_format.get(
                    "format_id"
                )
            )

            logger.info(
                "Merging video %s + audio %s",
                video_id,
                audio_id,
            )

            download_options[
                "format"
            ] = (
                f"{video_id}+{audio_id}"
            )

            download_options[
                "merge_output_format"
            ] = "mp4"

    # ========================================================
    # RUN YT-DLP
    # ========================================================

    try:

        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download(
                [url]
            )

    except Exception as e:

        logger.exception(
            "Download failed"
        )

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        return {
            "success": False,
            "error": str(e),
        }

    # ========================================================
    # FIND OUTPUT FILE
    # ========================================================

    output_files = []

    for file in job_dir.rglob("*"):

        if not file.is_file():
            continue

        if file.suffix in (
            ".part",
            ".ytdl",
        ):
            continue

        if file.stat().st_size <= 0:
            continue

        output_files.append(
            file
        )

    if not output_files:

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        return {
            "success": False,
            "error": (
                "Download completed but no output "
                "file was created."
            ),
        }

    # --------------------------------------------------------
    # LARGEST FILE
    # --------------------------------------------------------

    output_file = max(
        output_files,
        key=lambda file:
            file.stat().st_size,
    )

    filename = output_file.name

    download_url = (
        f"/files/{job_id}/{filename}"
    )

    file_size = (
        output_file.stat().st_size
    )

    logger.info(
        "Download complete: %s",
        output_file,
    )

    # ========================================================
    # IMPORTANT RESPONSE
    # ========================================================

    return {
        "success": True,

        "job_id": job_id,

        "filename": filename,

        "downloadUrl": download_url,

        "media_type": request.media_type,

        "format_id": request.format_id,

        "size": file_size,
    }


# ============================================================
# SERVE FILE
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def serve_file(
    job_id: str,
    filename: str,
):

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

    requested_file = (
        job_dir / filename
    )

    # --------------------------------------------------------
    # SECURITY
    # --------------------------------------------------------

    try:

        requested_file.resolve().relative_to(
            job_dir.resolve()
        )

    except ValueError:

        raise HTTPException(
            status_code=403,
            detail="Invalid file path.",
        )

    if not requested_file.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    if not requested_file.is_file():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    # --------------------------------------------------------
    # MIME TYPE
    # --------------------------------------------------------

    extension = (
        requested_file.suffix.lower()
    )

    media_type = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
    }.get(
        extension,
        "application/octet-stream",
    )

    return FileResponse(
        path=str(requested_file),
        media_type=media_type,
        filename=requested_file.name,
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    logger.info(
        "========================================"
    )

    logger.info(
        "Media Downloader API"
    )

    logger.info(
        "Version: %s",
        APP_VERSION,
    )

    logger.info(
        "Python: %s",
        os.sys.version,
    )

    logger.info(
        "yt-dlp: %s",
        yt_dlp.version.__version__,
    )

    logger.info(
        "FFmpeg: %s",
        shutil.which("ffmpeg"),
    )

    logger.info(
        "FFprobe: %s",
        shutil.which("ffprobe"),
    )

    logger.info(
        "========================================"
    )