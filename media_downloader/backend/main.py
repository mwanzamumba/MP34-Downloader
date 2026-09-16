import os
import re
import time
import uuid
import shutil
import logging
import subprocess

from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# CONFIGURATION
# ============================================================

APP_VERSION = "3.5.0"

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

FILE_TTL = int(os.getenv("FILE_TTL", "1800"))

# IMPORTANT:
# Never print this value to logs.
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("media-downloader")


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
    try:
        parsed = urlparse(url)

        hostname = (parsed.hostname or "").lower()

        if "youtube.com" in hostname or hostname == "youtu.be":
            return "YouTube"

        if "tiktok.com" in hostname:
            return "TikTok"

        if "instagram.com" in hostname:
            return "Instagram"

        if "facebook.com" in hostname or hostname == "fb.watch":
            return "Facebook"

        if "twitter.com" in hostname or "x.com" in hostname:
            return "X"

        return "Unknown"

    except Exception:
        return "Unknown"


# ============================================================
# YOUTUBE URL NORMALIZATION
# ============================================================

def normalize_youtube_url(url: str) -> str:
    """
    Converts YouTube URLs such as:

    https://www.youtube.com/watch?v=VIDEO&list=RD...
    
    into:

    https://www.youtube.com/watch?v=VIDEO

    This prevents yt-dlp from accidentally treating a YouTube
    Mix/playlist URL as a playlist.
    """

    try:
        parsed = urlparse(url)

        hostname = (parsed.hostname or "").lower()

        # youtu.be/VIDEO_ID
        if hostname == "youtu.be":
            video_id = parsed.path.strip("/")

            if video_id:
                return (
                    f"https://www.youtube.com/watch?v="
                    f"{video_id}"
                )

            return url

        # youtube.com
        if (
            "youtube.com" in hostname
            or "youtube-nocookie.com" in hostname
        ):
            query = parse_qs(parsed.query)

            video_id = query.get("v", [None])[0]

            if video_id:
                return (
                    f"https://www.youtube.com/watch?v="
                    f"{video_id}"
                )

    except Exception as exc:
        logger.warning(
            "[YOUTUBE] URL normalization failed: %s",
            exc,
        )

    return url


# ============================================================
# URL VALIDATION
# ============================================================

def validate_url(url: str) -> str:
    url = (url or "").strip()

    if not url:
        raise ValueError("URL cannot be empty.")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Please provide a valid HTTP or HTTPS URL.")

    platform = detect_platform(url)

    if platform == "Unknown":
        raise ValueError(
            "This platform is not currently supported."
        )

    if platform == "YouTube":
        url = normalize_youtube_url(url)

    return url


# ============================================================
# COOKIE FILE
# ============================================================

def create_cookie_file():
    """
    Creates a temporary Netscape cookie file if the
    YOUTUBE_COOKIES environment variable exists.

    The cookie contents are NEVER logged.
    """

    if not YOUTUBE_COOKIES:
        return None

    cookie_file = DOWNLOAD_DIR / "youtube_cookies.txt"

    try:
        cookie_file.write_text(
            YOUTUBE_COOKIES,
            encoding="utf-8",
        )

        return cookie_file

    except Exception as exc:
        logger.error(
            "[YOUTUBE] Failed to create cookie file: %s",
            exc,
        )

        return None


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    *,
    download: bool = False,
    output_template: str | None = None,
):
    options = {
        "noplaylist": True,

        "quiet": False,
        "no_warnings": False,

        "retries": 3,
        "fragment_retries": 3,

        "continuedl": True,
        "overwrites": True,

        "socket_timeout": 30,

        # ----------------------------------------------------
        # JavaScript runtime for YouTube challenge solving
        # ----------------------------------------------------

        "js_runtimes": {
            "node": None,
        },

        # ----------------------------------------------------
        # YouTube clients
        # ----------------------------------------------------

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "default",
                    "web_embedded",
                ],
            },
        },

        # ----------------------------------------------------
        # Browser-like headers
        # ----------------------------------------------------

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),

            "Accept-Language": "en-US,en;q=0.9",
        },

        "restrictfilenames": True,
    }

    # --------------------------------------------------------
    # Cookies
    # --------------------------------------------------------

    cookie_file = create_cookie_file()

    if cookie_file:
        options["cookiefile"] = str(cookie_file)

        logger.info(
            "[YOUTUBE] Cookie authentication enabled."
        )

    # --------------------------------------------------------
    # Download settings
    # --------------------------------------------------------

    if download:
        options.update({
            "format": "best",
            "merge_output_format": "mp4",
        })

        if output_template:
            options["outtmpl"] = output_template

    return options


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_dict(value):
    """
    Guarantees that a value is a dictionary.
    """

    if isinstance(value, dict):
        return value

    return {}


def safe_string(value, default=None):
    """
    Converts a value to a string safely.
    """

    if value is None:
        return default

    try:
        value = str(value).strip()

        if not value:
            return default

        return value

    except Exception:
        return default


def safe_int(value, default=None):
    """
    Safely converts a value to int.
    """

    if value is None:
        return default

    try:
        return int(value)

    except Exception:
        return default


def safe_float(value, default=None):
    """
    Safely converts a value to float.
    """

    if value is None:
        return default

    try:
        return float(value)

    except Exception:
        return default


# ============================================================
# FORMAT HELPERS
# ============================================================

def format_to_public(fmt):
    """
    Converts yt-dlp format information into a safe JSON object.

    IMPORTANT:
    yt-dlp can sometimes return unexpected/null format entries,
    so this function checks everything before using .get().
    """

    if not isinstance(fmt, dict):
        return None

    vcodec = fmt.get("vcodec")
    acodec = fmt.get("acodec")

    has_video = (
        vcodec is not None
        and vcodec != "none"
    )

    has_audio = (
        acodec is not None
        and acodec != "none"
    )

    filesize = fmt.get("filesize")

    if filesize is not None:
        filesize = safe_int(filesize)

    filesize_approx = fmt.get("filesize_approx")

    if filesize_approx is not None:
        filesize_approx = safe_int(filesize_approx)

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

        "vcodec": safe_string(
            vcodec
        ),

        "acodec": safe_string(
            acodec
        ),

        "filesize": filesize,

        "filesize_approx": filesize_approx,

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
    candidates = []

    for fmt in formats or []:

        if not isinstance(fmt, dict):
            continue

        vcodec = fmt.get("vcodec")
        height = safe_int(fmt.get("height"), 0)
        width = safe_int(fmt.get("width"), 0)
        fps = safe_float(fmt.get("fps"), 0)

        if (
            vcodec
            and vcodec != "none"
            and height
            and height > 0
        ):
            candidates.append(fmt)

    if not candidates:
        return None

    # Prefer formats with both video and audio.
    candidates.sort(
        key=lambda x: (
            1
            if (
                x.get("acodec")
                and x.get("acodec") != "none"
            )
            else 0,

            safe_int(x.get("height"), 0),

            safe_int(x.get("width"), 0),

            safe_float(x.get("fps"), 0),
        ),
        reverse=True,
    )

    return candidates[0]


def choose_recommended_audio(formats):
    candidates = []

    for fmt in formats or []:

        if not isinstance(fmt, dict):
            continue

        acodec = fmt.get("acodec")

        abr = safe_float(
            fmt.get("abr"),
            0,
        )

        if (
            acodec
            and acodec != "none"
        ):
            candidates.append(fmt)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            safe_float(
                x.get("abr"),
                0,
            ),
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# CLEANUP
# ============================================================

def cleanup_old_files():
    now = time.time()

    if not DOWNLOAD_DIR.exists():
        return

    for item in DOWNLOAD_DIR.iterdir():

        # Don't delete the cookie file here.
        if item.name == "youtube_cookies.txt":
            continue

        try:

            age = now - item.stat().st_mtime

            if age > FILE_TTL:

                if item.is_dir():
                    shutil.rmtree(
                        item,
                        ignore_errors=True,
                    )

                else:
                    item.unlink(
                        missing_ok=True
                    )

        except Exception as exc:
            logger.warning(
                "[CLEANUP] Failed to remove %s: %s",
                item,
                exc,
            )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "success": True,
        "name": "Media Downloader API",
        "version": APP_VERSION,
        "status": "online",
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
        "yt_dlp": yt_dlp.version.__version__,
    }


# ============================================================
# DEBUG RUNTIME
# ============================================================

@app.get("/debug-runtime")
def debug_runtime():

    result = {
        "success": True,
        "yt_dlp": yt_dlp.version.__version__,
        "node_path": shutil.which("node"),
        "node_version": None,
        "ejs_package": None,
    }

    # --------------------------------------------------------
    # Node
    # --------------------------------------------------------

    try:

        node_result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        result["node_version"] = (
            node_result.stdout.strip()
            or node_result.stderr.strip()
        )

    except Exception as exc:

        result["node_version"] = (
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # yt-dlp-ejs
    # --------------------------------------------------------

    try:

        import yt_dlp_ejs

        result["ejs_package"] = "installed"

    except Exception as exc:

        result["ejs_package"] = (
            f"NOT AVAILABLE: {exc}"
        )

    return result


# ============================================================
# DEBUG YOUTUBE
# ============================================================

@app.get("/debug-youtube")
def debug_youtube():

    test_url = (
        "https://www.youtube.com/watch?v=L5aSgl7HKBA"
    )

    test_url = normalize_youtube_url(
        test_url
    )

    logger.info(
        "[DEBUG] Testing YouTube URL: %s",
        test_url,
    )

    options = get_ytdlp_options(
        download=False
    )

    options["skip_download"] = True

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                test_url,
                download=False,
            )

        # ----------------------------------------------------
        # VERY IMPORTANT
        # info itself may be None
        # ----------------------------------------------------

        if not isinstance(info, dict):

            return {
                "success": False,
                "error": (
                    "yt-dlp returned no video information."
                ),
            }

        formats = info.get("formats") or []

        if not isinstance(formats, list):
            formats = []

        video_formats = []
        audio_formats = []

        public_formats = []

        for fmt in formats:

            if not isinstance(fmt, dict):
                continue

            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")

            if (
                vcodec
                and vcodec != "none"
            ):
                video_formats.append(fmt)

            if (
                acodec
                and acodec != "none"
            ):
                audio_formats.append(fmt)

            public = format_to_public(fmt)

            if public is not None:
                public_formats.append(
                    public
                )

        return {
            "success": True,

            "message": (
                "YouTube extraction succeeded."
            ),

            "title": safe_string(
                info.get("title"),
                "Unknown",
            ),

            "id": safe_string(
                info.get("id")
            ),

            "duration": safe_int(
                info.get("duration")
            ),

            "total_formats": len(
                public_formats
            ),

            "video_formats": len(
                video_formats
            ),

            "audio_formats": len(
                audio_formats
            ),

            "formats": public_formats[:30],
        }

    except Exception as exc:

        logger.exception(
            "[DEBUG] YouTube test failed."
        )

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(request: AnalyzeRequest):

    cleanup_old_files()

    try:

        original_url = request.url

        url = validate_url(
            original_url
        )

        platform = detect_platform(
            url
        )

        logger.info(
            "[ANALYZE] Platform: %s",
            platform,
        )

        logger.info(
            "[ANALYZE] URL: %s",
            url,
        )

        options = get_ytdlp_options(
            download=False
        )

        options["skip_download"] = True

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        # ----------------------------------------------------
        # Protect against None
        # ----------------------------------------------------

        if not isinstance(info, dict):

            raise ValueError(
                "yt-dlp returned no media information."
            )

        # ----------------------------------------------------
        # Protect against playlists
        # ----------------------------------------------------

        if info.get("_type") == "playlist":

            entries = info.get("entries")

            if entries:
                raise ValueError(
                    "Playlist URLs are not supported. "
                    "Please provide a direct video URL."
                )

        # ----------------------------------------------------
        # Basic information
        # ----------------------------------------------------

        title = safe_string(
            info.get("title"),
            "Untitled Media",
        )

        thumbnail = safe_string(
            info.get("thumbnail")
        )

        duration = safe_int(
            info.get("duration")
        )

        # ----------------------------------------------------
        # Formats
        # ----------------------------------------------------

        raw_formats = info.get("formats") or []

        if not isinstance(
            raw_formats,
            list,
        ):
            raw_formats = []

        formats = []
        video_formats = []
        audio_formats = []
        progressive_formats = []

        seen_ids = set()

        for fmt in raw_formats:

            if not isinstance(fmt, dict):
                continue

            format_id = safe_string(
                fmt.get("format_id")
            )

            if not format_id:
                continue

            # Avoid duplicates
            if format_id in seen_ids:
                continue

            seen_ids.add(
                format_id
            )

            public = format_to_public(
                fmt
            )

            if public is None:
                continue

            formats.append(
                public
            )

            vcodec = fmt.get(
                "vcodec"
            )

            acodec = fmt.get(
                "acodec"
            )

            has_video = (
                vcodec
                and vcodec != "none"
            )

            has_audio = (
                acodec
                and acodec != "none"
            )

            if has_video:
                video_formats.append(
                    public
                )

            if has_audio:
                audio_formats.append(
                    public
                )

            if (
                has_video
                and has_audio
            ):
                progressive_formats.append(
                    public
                )

        # ----------------------------------------------------
        # Recommended formats
        # ----------------------------------------------------

        recommended_video_raw = (
            choose_recommended_video(
                raw_formats
            )
        )

        recommended_audio_raw = (
            choose_recommended_audio(
                raw_formats
            )
        )

        recommended_video = None

        if recommended_video_raw:

            recommended_video = (
                format_to_public(
                    recommended_video_raw
                )
            )

        recommended_audio = None

        if recommended_audio_raw:

            recommended_audio = (
                format_to_public(
                    recommended_audio_raw
                )
            )

        logger.info(
            "[ANALYZE] Title: %s",
            title,
        )

        logger.info(
            "[ANALYZE] Formats: %d",
            len(formats),
        )

        logger.info(
            "[ANALYZE] Video formats: %d",
            len(video_formats),
        )

        logger.info(
            "[ANALYZE] Audio formats: %d",
            len(audio_formats),
        )

        return {
            "success": True,

            "title": title,

            "platform": platform,

            "thumbnail": thumbnail,

            "duration": duration,

            "formats": formats,

            "video_formats": video_formats,

            "audio_formats": audio_formats,

            "progressive_formats": (
                progressive_formats
            ),

            "recommended_video": (
                recommended_video
            ),

            "recommended_audio": (
                recommended_audio
            ),
        }

    except Exception as exc:

        logger.exception(
            "[ANALYZE] Failed."
        )

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
def download(request: DownloadRequest):

    cleanup_old_files()

    job_id = str(
        uuid.uuid4()
    )

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

    try:

        # ----------------------------------------------------
        # Validate URL
        # ----------------------------------------------------

        url = validate_url(
            request.url
        )

        platform = detect_platform(
            url
        )

        logger.info(
            "[DOWNLOAD] Platform: %s",
            platform,
        )

        logger.info(
            "[DOWNLOAD] Requested format: %s",
            request.format_id,
        )

        # ----------------------------------------------------
        # Extract information
        # ----------------------------------------------------

        extract_options = (
            get_ytdlp_options(
                download=False
            )
        )

        extract_options[
            "skip_download"
        ] = True

        with yt_dlp.YoutubeDL(
            extract_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        if not isinstance(
            info,
            dict,
        ):

            raise ValueError(
                "yt-dlp returned no media information."
            )

        # ----------------------------------------------------
        # Playlist protection
        # ----------------------------------------------------

        if info.get("_type") == "playlist":

            raise ValueError(
                "Playlist URLs are not supported. "
                "Please provide a direct video URL."
            )

        # ----------------------------------------------------
        # Find requested format
        # ----------------------------------------------------

        raw_formats = (
            info.get("formats") or []
        )

        if not isinstance(
            raw_formats,
            list,
        ):
            raw_formats = []

        selected_format = None

        for fmt in raw_formats:

            if not isinstance(
                fmt,
                dict,
            ):
                continue

            format_id = safe_string(
                fmt.get("format_id")
            )

            if (
                format_id
                == request.format_id
            ):
                selected_format = fmt
                break

        if selected_format is None:

            raise ValueError(
                "Requested format was not found."
            )

        logger.info(
            "[DOWNLOAD] Requested format found."
        )

        # ----------------------------------------------------
        # Prepare output directory
        # ----------------------------------------------------

        job_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_template = str(
            job_dir / "%(title).150s.%(ext)s"
        )

        # ----------------------------------------------------
        # Download options
        # ----------------------------------------------------

        download_options = (
            get_ytdlp_options(
                download=True,
                output_template=(
                    output_template
                ),
            )
        )

        # ----------------------------------------------------
        # Media type
        # ----------------------------------------------------

        media_type = (
            request.media_type
            or "video"
        ).lower()

        if media_type not in (
            "video",
            "audio",
        ):
            media_type = "video"

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        if media_type == "audio":

            requested_audio_format = (
                request.audio_format
                or "mp3"
            ).lower()

            if requested_audio_format not in (
                "mp3",
                "m4a",
                "wav",
                "aac",
                "opus",
            ):
                requested_audio_format = "mp3"

            download_options[
                "format"
            ] = request.format_id

            download_options[
                "postprocessors"
            ] = [
                {
                    "key": (
                        "FFmpegExtractAudio"
                    ),

                    "preferredcodec": (
                        requested_audio_format
                    ),

                    "preferredquality": (
                        "192"
                    ),
                }
            ]

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        else:

            download_options[
                "format"
            ] = request.format_id

            download_options[
                "merge_output_format"
            ] = "mp4"

        logger.info(
            "[DOWNLOAD] Selected format: %s",
            request.format_id,
        )

        logger.info(
            "[DOWNLOAD] Media type: %s",
            media_type,
        )

        logger.info(
            "[DOWNLOAD] STARTING ACTUAL DOWNLOAD"
        )

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download(
                [url]
            )

        logger.info(
            "[DOWNLOAD] Download completed."
        )

        # ----------------------------------------------------
        # Find downloaded file
        # ----------------------------------------------------

        downloaded_files = []

        for file in job_dir.iterdir():

            if not file.is_file():
                continue

            if file.name.endswith(
                ".part"
            ):
                continue

            if file.name.endswith(
                ".ytdl"
            ):
                continue

            downloaded_files.append(
                file
            )

        if not downloaded_files:

            raise FileNotFoundError(
                "Download completed but no output file was found."
            )

        # ----------------------------------------------------
        # Choose largest output file
        # ----------------------------------------------------

        downloaded_files.sort(
            key=lambda x: x.stat().st_size,
            reverse=True,
        )

        output_file = (
            downloaded_files[0]
        )

        filename = output_file.name

        logger.info(
            "[DOWNLOAD] File: %s",
            filename,
        )

        return {
            "success": True,

            "job_id": job_id,

            "filename": filename,

            "download_url": (
                f"/files/"
                f"{job_id}/"
                f"{filename}"
            ),

            "title": safe_string(
                info.get("title"),
                "Media",
            ),

            "platform": platform,
        }

    except Exception as exc:

        logger.exception(
            "[DOWNLOAD] DOWNLOAD FAILED"
        )

        # Remove incomplete job directory
        try:

            if job_dir.exists():

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True,
                )

        except Exception:
            pass

        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# FILE DOWNLOAD
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def get_file(
    job_id: str,
    filename: str,
):

    # --------------------------------------------------------
    # Security validation
    # --------------------------------------------------------

    if (
        ".." in job_id
        or "/" in job_id
        or "\\" in job_id
    ):
        return {
            "success": False,
            "error": "Invalid job ID.",
        }

    if (
        ".." in filename
        or "/" in filename
        or "\\" in filename
    ):
        return {
            "success": False,
            "error": "Invalid filename.",
        }

    file_path = (
        DOWNLOAD_DIR
        / job_id
        / filename
    )

    if not file_path.exists():
        return {
            "success": False,
            "error": "File not found.",
        }

    if not file_path.is_file():
        return {
            "success": False,
            "error": "Invalid file.",
        }

    return FileResponse(
        path=file_path,
        filename=filename,
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_event():

    logger.info(
        "========================================"
    )

    logger.info(
        "MEDIA DOWNLOADER API"
    )

    logger.info(
        "Version: %s",
        APP_VERSION,
    )

    logger.info(
        "yt-dlp: %s",
        yt_dlp.version.__version__,
    )

    logger.info(
        "Node path: %s",
        shutil.which("node"),
    )

    logger.info(
        "========================================"
    )


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event("shutdown")
def shutdown_event():

    logger.info(
        "Media Downloader API shutting down."
    )