import os
import time
import uuid
import shutil
import logging
import base64

from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# CONFIGURATION
# ============================================================

APP_VERSION = "5.0.0"

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FILE_TTL = 1800


# ============================================================
# YOUTUBE CONFIGURATION
# ============================================================

BGUTIL_PROVIDER_URL = os.getenv(
    "BGUTIL_PROVIDER_URL",
    "http://127.0.0.1:4416",
)

YOUTUBE_COOKIES_BASE64 = os.getenv(
    "YOUTUBE_COOKIES_BASE64",
    "",
)

YOUTUBE_COOKIES_FILE = DOWNLOAD_DIR / "youtube_cookies.txt"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    version=APP_VERSION,
)


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

        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        if host.startswith("m."):
            host = host[2:]

        if (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtu.be"
        ):
            return "youtube"

        if (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        ):
            return "tiktok"

        if (
            host == "instagram.com"
            or host.endswith(".instagram.com")
        ):
            return "instagram"

        if (
            host == "facebook.com"
            or host.endswith(".facebook.com")
            or host == "fb.watch"
        ):
            return "facebook"

        if (
            host == "twitter.com"
            or host.endswith(".twitter.com")
            or host == "x.com"
            or host.endswith(".x.com")
        ):
            return "twitter"

        return "unknown"

    except Exception:

        return "unknown"


# ============================================================
# URL VALIDATION
# ============================================================

def validate_url(url: str):

    if not url:
        raise HTTPException(
            status_code=400,
            detail="URL is required.",
        )

    url = url.strip()

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid HTTP or HTTPS URL.",
        )

    return url


# ============================================================
# YOUTUBE URL NORMALIZATION
# ============================================================

def normalize_youtube_url(url: str) -> str:

    try:

        parsed = urlparse(url)

        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        # ----------------------------------------------------
        # youtu.be/<id>
        # ----------------------------------------------------

        if host == "youtu.be":

            video_id = parsed.path.strip("/")

            if video_id:

                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

        # ----------------------------------------------------
        # youtube.com/shorts/<id>
        # ----------------------------------------------------

        if host.endswith("youtube.com"):

            path_parts = [
                part
                for part in parsed.path.split("/")
                if part
            ]

            if (
                len(path_parts) >= 2
                and path_parts[0].lower() == "shorts"
            ):

                video_id = path_parts[1]

                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

            # ------------------------------------------------
            # youtube.com/watch?v=<id>
            # ------------------------------------------------

            query = parse_qs(
                parsed.query
            )

            video_id_list = query.get("v")

            if video_id_list:

                video_id = video_id_list[0]

                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

        return url

    except Exception:

        return url


# ============================================================
# YOUTUBE COOKIES
# ============================================================

def setup_youtube_cookies():

    """
    Creates a Netscape-format cookie file from the
    YOUTUBE_COOKIES_BASE64 environment variable.

    Cookies are optional.

    The server will continue working without cookies.
    """

    if not YOUTUBE_COOKIES_BASE64:

        return None

    try:

        cookie_data = base64.b64decode(
            YOUTUBE_COOKIES_BASE64
        )

        YOUTUBE_COOKIES_FILE.write_bytes(
            cookie_data
        )

        logger.info(
            "YouTube cookies loaded."
        )

        return str(
            YOUTUBE_COOKIES_FILE
        )

    except Exception as exc:

        logger.error(
            "Failed to decode YouTube cookies: %s",
            exc,
        )

        return None


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    download=False,
    output_template=None,
    platform=None,
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

        "restrictfilenames": True,

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

    }

    # --------------------------------------------------------
    # Output template
    # --------------------------------------------------------

    if output_template:

        options["outtmpl"] = output_template

    # --------------------------------------------------------
    # YouTube-specific configuration
    # --------------------------------------------------------

    if platform == "youtube":

        options["extractor_args"] = {

            "youtube": [
                "player_client=mweb,web_embedded"
            ],

            "youtubepot-bgutilhttp": [
                f"base_url={BGUTIL_PROVIDER_URL}"
            ],

        }

        # ----------------------------------------------------
        # Optional cookies
        # ----------------------------------------------------

        cookie_file = setup_youtube_cookies()

        if cookie_file:

            options["cookiefile"] = cookie_file

    return options


# ============================================================
# FORMAT CONVERSION
# ============================================================

def format_to_public(
    fmt,
):

    if not isinstance(
        fmt,
        dict,
    ):
        return None

    vcodec = fmt.get(
        "vcodec"
    )

    acodec = fmt.get(
        "acodec"
    )

    has_video = (
        vcodec is not None
        and vcodec != "none"
    )

    has_audio = (
        acodec is not None
        and acodec != "none"
    )

    width = fmt.get(
        "width"
    )

    height = fmt.get(
        "height"
    )

    filesize = fmt.get(
        "filesize"
    )

    filesize_approx = fmt.get(
        "filesize_approx"
    )

    return {

        "format_id": str(
            fmt.get(
                "format_id",
                "",
            )
        ),

        "ext": fmt.get(
            "ext"
        ),

        "format_note": fmt.get(
            "format_note"
        ),

        "width": width,

        "height": height,

        "fps": fmt.get(
            "fps"
        ),

        "vcodec": vcodec,

        "acodec": acodec,

        "filesize": filesize,

        "filesize_approx": filesize_approx,

        "abr": fmt.get(
            "abr"
        ),

        "tbr": fmt.get(
            "tbr"
        ),

        "url": fmt.get(
            "url"
        ),

        "has_video": has_video,

        "has_audio": has_audio,

    }


# ============================================================
# FORMAT HELPERS
# ============================================================

def choose_recommended_video(
    formats,
):

    candidates = []

    for fmt in formats:

        if not isinstance(
            fmt,
            dict,
        ):
            continue

        vcodec = fmt.get(
            "vcodec"
        )

        if (
            not vcodec
            or vcodec == "none"
        ):
            continue

        height = fmt.get(
            "height"
        ) or 0

        width = fmt.get(
            "width"
        ) or 0

        filesize = (
            fmt.get("filesize")
            or fmt.get("filesize_approx")
            or 0
        )

        candidates.append(
            (
                height,
                width,
                filesize,
                fmt,
            )
        )

    if not candidates:

        return None

    # Prefer highest resolution,
    # then larger width,
    # then a known filesize.

    candidates.sort(
        key=lambda x: (
            x[0],
            x[1],
            x[2],
        ),
        reverse=True,
    )

    return candidates[0][3]


def choose_recommended_audio(
    formats,
):

    candidates = []

    for fmt in formats:

        if not isinstance(
            fmt,
            dict,
        ):
            continue

        acodec = fmt.get(
            "acodec"
        )

        if (
            not acodec
            or acodec == "none"
        ):
            continue

        vcodec = fmt.get(
            "vcodec"
        )

        # Audio-only preferred.

        if (
            vcodec
            and vcodec != "none"
        ):
            continue

        abr = fmt.get(
            "abr"
        ) or 0

        filesize = (
            fmt.get("filesize")
            or fmt.get("filesize_approx")
            or 0
        )

        candidates.append(
            (
                abr,
                filesize,
                fmt,
            )
        )

    if not candidates:

        return None

    candidates.sort(
        key=lambda x: (
            x[0],
            x[1],
        ),
        reverse=True,
    )

    return candidates[0][2]


def choose_audio_for_video(
    formats,
):

    return choose_recommended_audio(
        formats
    )


# ============================================================
# FILE CLEANUP
# ============================================================

def cleanup_old_files():

    now = time.time()

    if not DOWNLOAD_DIR.exists():

        return

    for item in DOWNLOAD_DIR.iterdir():

        try:

            if item.name == "youtube_cookies.txt":

                continue

            age = (
                now
                - item.stat().st_mtime
            )

            if age <= FILE_TTL:

                continue

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
                "Cleanup failed for %s: %s",
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

        "endpoints": {

            "analyze": "/analyze",

            "download": "/download",

            "health": "/health",

            "version": "/version",

        },

    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    cleanup_old_files()

    return {

        "success": True,

        "status": "healthy",

        "version": APP_VERSION,

        "youtube_pot_provider": (
            BGUTIL_PROVIDER_URL
        ),

        "youtube_cookies": bool(
            YOUTUBE_COOKIES_BASE64
        ),

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

    platform = detect_platform(
        url
    )

    if platform == "youtube":

        url = normalize_youtube_url(
            url
        )

    logger.info(
        "Analyzing %s URL: %s",
        platform,
        url,
    )

    try:

        options = get_ytdlp_options(
            download=False,
            platform=platform,
        )

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        if not info:

            return {

                "success": False,

                "error": (
                    "Unable to extract media information."
                ),

            }

        formats = info.get(
            "formats",
            []
        )

        public_formats = []

        video_formats = []

        audio_formats = []

        progressive_formats = []

        for fmt in formats:

            public_fmt = format_to_public(
                fmt
            )

            if not public_fmt:

                continue

            public_formats.append(
                public_fmt
            )

            if public_fmt["has_video"]:

                video_formats.append(
                    public_fmt
                )

            if public_fmt["has_audio"]:

                audio_formats.append(
                    public_fmt
                )

            if (
                public_fmt["has_video"]
                and public_fmt["has_audio"]
            ):

                progressive_formats.append(
                    public_fmt
                )

        recommended_video_raw = (
            choose_recommended_video(
                formats
            )
        )

        recommended_audio_raw = (
            choose_recommended_audio(
                formats
            )
        )

        recommended_video = None

        recommended_audio = None

        if recommended_video_raw:

            recommended_video = (
                format_to_public(
                    recommended_video_raw
                )
            )

        if recommended_audio_raw:

            recommended_audio = (
                format_to_public(
                    recommended_audio_raw
                )
            )

        return {

            "success": True,

            "platform": platform,

            "id": info.get(
                "id"
            ),

            "title": info.get(
                "title"
            ),

            "thumbnail": info.get(
                "thumbnail"
            ),

            "duration": info.get(
                "duration"
            ),

            "uploader": info.get(
                "uploader"
            ),

            "webpage_url": info.get(
                "webpage_url"
            ),

            "formats": public_formats,

            "video_formats": video_formats,

            "audio_formats": audio_formats,

            "progressive_formats": progressive_formats,

            "recommended_video": (
                recommended_video
            ),

            "recommended_audio": (
                recommended_audio
            ),

        }

    except Exception as exc:

        logger.exception(
            "Analysis failed."
        )

        error_message = str(
            exc
        )

        return {

            "success": False,

            "platform": platform,

            "error": error_message,

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

    platform = detect_platform(
        url
    )

    if platform == "youtube":

        url = normalize_youtube_url(
            url
        )

    media_type = (
        request.media_type
        .strip()
        .lower()
    )

    if media_type not in (
        "video",
        "audio",
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "media_type must be "
                "'video' or 'audio'."
            ),
        )

    logger.info(
        "Download request | platform=%s | "
        "media_type=%s | format=%s",
        platform,
        media_type,
        request.format_id,
    )

    # ========================================================
    # EXTRACT MEDIA INFORMATION AGAIN
    # ========================================================

    try:

        extraction_options = (
            get_ytdlp_options(
                download=False,
                platform=platform,
            )
        )

        with yt_dlp.YoutubeDL(
            extraction_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

    except Exception as exc:

        logger.exception(
            "Could not extract media information."
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    formats = info.get(
        "formats",
        []
    )

    # ========================================================
    # FIND REQUESTED FORMAT
    # ========================================================

    selected_format = None

    for fmt in formats:

        if str(
            fmt.get("format_id")
        ) == str(
            request.format_id
        ):

            selected_format = fmt

            break

    if selected_format is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Requested format was not found."
            ),
        )

    # ========================================================
    # CREATE JOB
    # ========================================================

    job_id = uuid.uuid4().hex

    job_dir = DOWNLOAD_DIR / job_id

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    title = (
        info.get("title")
        or "download"
    )

    safe_title = "".join(
        char
        for char in title
        if char.isalnum()
        or char in (
            " ",
            "-",
            "_",
            ".",
        )
    ).strip()

    if not safe_title:

        safe_title = "download"

    output_template = str(
        job_dir
        / f"{safe_title}.%(ext)s"
    )

    # ========================================================
    # AUDIO DOWNLOAD
    # ========================================================

    if media_type == "audio":

        audio_format = (
            request.audio_format
            or "mp3"
        ).lower()

        allowed_audio_formats = {
            "mp3",
            "m4a",
            "wav",
            "aac",
            "flac",
            "opus",
        }

        if (
            audio_format
            not in allowed_audio_formats
        ):

            audio_format = "mp3"

        download_options = (
            get_ytdlp_options(
                download=True,
                output_template=output_template,
                platform=platform,
            )
        )

        download_options["format"] = (
            request.format_id
        )

        download_options[
            "postprocessors"
        ] = [

            {

                "key": (
                    "FFmpegExtractAudio"
                ),

                "preferredcodec": (
                    audio_format
                ),

                "preferredquality": (
                    "192"
                ),

            }

        ]

        try:

            with yt_dlp.YoutubeDL(
                download_options
            ) as ydl:

                ydl.download(
                    [url]
                )

        except Exception as exc:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            logger.exception(
                "Audio download failed."
            )

            raise HTTPException(
                status_code=500,
                detail=str(exc),
            )

        # ----------------------------------------------------
        # Find resulting audio file
        # ----------------------------------------------------

        output_files = [
            file
            for file in job_dir.iterdir()
            if file.is_file()
        ]

        if not output_files:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Audio download completed "
                    "but no output file was found."
                ),
            )

        output_file = max(
            output_files,
            key=lambda file: file.stat().st_size,
        )

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
            vcodec
            and vcodec != "none"
        )

        has_audio = (
            acodec
            and acodec != "none"
        )

        if not has_video:

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected format "
                    "does not contain video."
                ),
            )

        download_options = (
            get_ytdlp_options(
                download=True,
                output_template=output_template,
                platform=platform,
            )
        )

        # ----------------------------------------------------
        # Progressive format
        # ----------------------------------------------------

        if has_audio:

            download_options[
                "format"
            ] = request.format_id

        # ----------------------------------------------------
        # Video-only format
        # ----------------------------------------------------

        else:

            audio_format = (
                choose_audio_for_video(
                    formats
                )
            )

            if not audio_format:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No compatible audio "
                        "format was found."
                    ),
                )

            video_id = str(
                selected_format.get(
                    "format_id"
                )
            )

            audio_id = str(
                audio_format.get(
                    "format_id"
                )
            )

            download_options[
                "format"
            ] = (
                f"{video_id}+{audio_id}"
            )

            download_options[
                "merge_output_format"
            ] = "mp4"

        # ----------------------------------------------------
        # Download video
        # ----------------------------------------------------

        try:

            with yt_dlp.YoutubeDL(
                download_options
            ) as ydl:

                ydl.download(
                    [url]
                )

        except Exception as exc:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            logger.exception(
                "Video download failed."
            )

            raise HTTPException(
                status_code=500,
                detail=str(exc),
            )

        # ----------------------------------------------------
        # Find resulting video
        # ----------------------------------------------------

        output_files = [
            file
            for file in job_dir.iterdir()
            if file.is_file()
        ]

        if not output_files:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Video download completed "
                    "but no output file was found."
                ),
            )

        output_file = max(
            output_files,
            key=lambda file: file.stat().st_size,
        )

    # ========================================================
    # FINAL RESPONSE
    # ========================================================

    file_size = output_file.stat().st_size

    download_url = (
        f"/files/{job_id}/"
        f"{output_file.name}"
    )

    logger.info(
        "Download completed | file=%s | size=%s",
        output_file.name,
        file_size,
    )

    return {

        "success": True,

        "job_id": job_id,

        "filename": output_file.name,

        "downloadUrl": download_url,

        "media_type": media_type,

        "format_id": request.format_id,

        "size": file_size,

    }


# ============================================================
# SERVE DOWNLOADED FILE
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def serve_file(
    job_id: str,
    filename: str,
):

    # --------------------------------------------------------
    # Prevent path traversal
    # --------------------------------------------------------

    if (
        ".." in job_id
        or ".." in filename
        or "/" in job_id
        or "\\" in job_id
        or "/" in filename
        or "\\" in filename
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid file path.",
        )

    job_dir = DOWNLOAD_DIR / job_id

    file_path = (
        job_dir / filename
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    # --------------------------------------------------------
    # Security check
    # --------------------------------------------------------

    try:

        file_path.resolve().relative_to(
            DOWNLOAD_DIR.resolve()
        )

    except ValueError:

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    # --------------------------------------------------------
    # MIME type
    # --------------------------------------------------------

    extension = (
        file_path.suffix.lower()
    )

    media_types = {

        ".mp4": "video/mp4",

        ".webm": "video/webm",

        ".mkv": "video/x-matroska",

        ".mov": "video/quicktime",

        ".avi": "video/x-msvideo",

        ".mp3": "audio/mpeg",

        ".m4a": "audio/mp4",

        ".aac": "audio/aac",

        ".wav": "audio/wav",

        ".flac": "audio/flac",

        ".ogg": "audio/ogg",

        ".opus": "audio/opus",

    }

    media_type = media_types.get(
        extension,
        "application/octet-stream",
    )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_event():

    logger.info(
        "=========================================="
    )

    logger.info(
        "Media Downloader API starting..."
    )

    logger.info(
        "App version: %s",
        APP_VERSION,
    )

    logger.info(
        "Python executable: %s",
        os.sys.executable,
    )

    logger.info(
        "yt-dlp version: %s",
        yt_dlp.version.__version__,
    )

    ffmpeg_path = shutil.which(
        "ffmpeg"
    )

    ffprobe_path = shutil.which(
        "ffprobe"
    )

    logger.info(
        "FFmpeg: %s",
        ffmpeg_path or "NOT FOUND",
    )

    logger.info(
        "FFprobe: %s",
        ffprobe_path or "NOT FOUND",
    )

    logger.info(
        "YouTube POT provider: %s",
        BGUTIL_PROVIDER_URL,
    )

    logger.info(
        "YouTube cookies configured: %s",
        bool(
            YOUTUBE_COOKIES_BASE64
        ),
    )

    if YOUTUBE_COOKIES_BASE64:

        setup_youtube_cookies()

    cleanup_old_files()

    logger.info(
        "Media Downloader API ready."
    )

    logger.info(
        "=========================================="
    )