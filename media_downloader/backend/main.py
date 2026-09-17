import os
import re
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
# APPLICATION CONFIGURATION
# ============================================================

APP_VERSION = "6.0.0"

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

# Files older than this are deleted.
FILE_TTL = 1800

# Maximum final filename stem length.
# The extension is added separately by yt-dlp.
MAX_FILENAME_LENGTH = 80


# ============================================================
# YOUTUBE CONFIGURATION
# ============================================================

# bgutil-ytdlp-pot-provider HTTP server
#
# Default provider address:
# http://127.0.0.1:4416
#
# Can be changed through Render environment variables.
BGUTIL_PROVIDER_URL = os.getenv(
    "BGUTIL_PROVIDER_URL",
    "http://127.0.0.1:4416",
).rstrip("/")


# Optional Base64 encoded Netscape cookie file.
#
# This is NOT required for normal public videos.
#
# If you configure this in Render:
#
# YOUTUBE_COOKIES_BASE64=<base64-cookie-file>
#
YOUTUBE_COOKIES_BASE64 = os.getenv(
    "YOUTUBE_COOKIES_BASE64",
    "",
).strip()


YOUTUBE_COOKIES_FILE = (
    DOWNLOAD_DIR / "youtube_cookies.txt"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# FASTAPI
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

        # ----------------------------------------------------
        # YouTube
        # ----------------------------------------------------

        if (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtu.be"
        ):
            return "youtube"

        # ----------------------------------------------------
        # TikTok
        # ----------------------------------------------------

        if (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        ):
            return "tiktok"

        # ----------------------------------------------------
        # Instagram
        # ----------------------------------------------------

        if (
            host == "instagram.com"
            or host.endswith(".instagram.com")
        ):
            return "instagram"

        # ----------------------------------------------------
        # Facebook
        # ----------------------------------------------------

        if (
            host == "facebook.com"
            or host.endswith(".facebook.com")
            or host == "fb.watch"
        ):
            return "facebook"

        # ----------------------------------------------------
        # Twitter / X
        # ----------------------------------------------------

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

def validate_url(
    url: str,
) -> str:

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
            detail=(
                "Please provide a valid "
                "HTTP or HTTPS URL."
            ),
        )

    return url


# ============================================================
# YOUTUBE URL NORMALIZATION
# ============================================================

def normalize_youtube_url(
    url: str,
) -> str:

    try:

        parsed = urlparse(url)

        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        # ----------------------------------------------------
        # youtu.be/<id>
        # ----------------------------------------------------

        if host == "youtu.be":

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

        # ----------------------------------------------------
        # YouTube
        # ----------------------------------------------------

        if host.endswith(
            "youtube.com"
        ):

            path_parts = [
                part
                for part in parsed.path.split("/")
                if part
            ]

            # ------------------------------------------------
            # /shorts/<id>
            # ------------------------------------------------

            if (
                len(path_parts) >= 2
                and path_parts[0].lower()
                == "shorts"
            ):

                video_id = path_parts[1]

                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

            # ------------------------------------------------
            # /live/<id>
            # ------------------------------------------------

            if (
                len(path_parts) >= 2
                and path_parts[0].lower()
                == "live"
            ):

                video_id = path_parts[1]

                return (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

            # ------------------------------------------------
            # /watch?v=<id>
            # ------------------------------------------------

            query = parse_qs(
                parsed.query
            )

            video_ids = query.get(
                "v"
            )

            if video_ids:

                video_id = (
                    video_ids[0]
                )

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
    Creates the YouTube cookie file from the
    YOUTUBE_COOKIES_BASE64 environment variable.

    Cookies are optional.

    The cookie file is deliberately stored inside
    DOWNLOAD_DIR and excluded from cleanup.
    """

    if not YOUTUBE_COOKIES_BASE64:

        return None

    try:

        cookie_data = base64.b64decode(
            YOUTUBE_COOKIES_BASE64
        )

        if not cookie_data:

            logger.warning(
                "YouTube cookie data is empty."
            )

            return None

        YOUTUBE_COOKIES_FILE.write_bytes(
            cookie_data
        )

        logger.info(
            "YouTube cookies loaded successfully."
        )

        return str(
            YOUTUBE_COOKIES_FILE
        )

    except Exception as exc:

        logger.error(
            "Unable to decode YouTube cookies: %s",
            exc,
        )

        return None


# ============================================================
# SAFE FILENAME
# ============================================================

def make_safe_filename(
    title: str,
    media_id: str | None = None,
) -> str:

    """
    Creates a Windows-safe, short filename stem.

    Example:

        Original:
        My Very Long YouTube Video Title That Goes On And On...

        Result:
        My_Very_Long_YouTube_Video_Title_That_Goes_On-abc12345

    Maximum:
        MAX_FILENAME_LENGTH characters
    """

    # --------------------------------------------------------
    # Basic fallback
    # --------------------------------------------------------

    if not title:

        title = "download"

    title = str(title)

    # --------------------------------------------------------
    # Replace Windows-invalid characters
    #
    # < > : " / \ | ? *
    # --------------------------------------------------------

    title = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        title,
    )

    # --------------------------------------------------------
    # Remove control characters
    # --------------------------------------------------------

    title = re.sub(
        r"[\x00-\x1f\x7f]",
        "",
        title,
    )

    # --------------------------------------------------------
    # Collapse whitespace
    # --------------------------------------------------------

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    # --------------------------------------------------------
    # Replace problematic dots/spaces at the end
    # --------------------------------------------------------

    title = title.rstrip(
        " ."
    )

    # --------------------------------------------------------
    # Fallback if nothing remains
    # --------------------------------------------------------

    if not title:

        title = "download"

    # --------------------------------------------------------
    # Windows reserved filenames
    # --------------------------------------------------------

    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    if title.upper() in reserved_names:

        title = (
            "download_"
            + title
        )

    # --------------------------------------------------------
    # Short unique identifier
    # --------------------------------------------------------

    if media_id:

        media_id = re.sub(
            r"[^A-Za-z0-9_-]",
            "",
            str(media_id),
        )

        media_id = media_id[:8]

    else:

        media_id = uuid.uuid4().hex[:8]

    suffix = (
        "-"
        + media_id
    )

    # --------------------------------------------------------
    # Calculate maximum title portion
    # --------------------------------------------------------

    available_length = (
        MAX_FILENAME_LENGTH
        - len(suffix)
    )

    if available_length < 10:

        available_length = 10

    # --------------------------------------------------------
    # Trim title
    # --------------------------------------------------------

    title = title[
        :available_length
    ]

    title = title.rstrip(
        " ."
    )

    # --------------------------------------------------------
    # Final stem
    # --------------------------------------------------------

    final_name = (
        title
        + suffix
    )

    # --------------------------------------------------------
    # Final safety check
    # --------------------------------------------------------

    final_name = final_name.rstrip(
        " ."
    )

    if not final_name:

        final_name = (
            "download-"
            + uuid.uuid4().hex[:8]
        )

    return final_name


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    download: bool = False,
    output_template: str | None = None,
    platform: str | None = None,
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

        options[
            "outtmpl"
        ] = output_template

    # ========================================================
    # YOUTUBE
    # ========================================================

    if platform == "youtube":

        # Current documented strategy:
        #
        # mweb:
        #   Current recommended client when using a PO token.
        #
        # default:
        #   Provides a fallback to yt-dlp's normal
        #   client handling.
        #
        # bgutil HTTP provider:
        #   Automatically supplies PO tokens.
        #
        options[
            "extractor_args"
        ] = {

            "youtube": {

                "player_client": [
                    "mweb",
                    "default",
                ],

            },

            "youtubepot-bgutilhttp": {

                "base_url": [
                    BGUTIL_PROVIDER_URL,
                ],

            },

        }

        # ----------------------------------------------------
        # Optional cookies
        # ----------------------------------------------------

        cookie_file = (
            setup_youtube_cookies()
        )

        if cookie_file:

            options[
                "cookiefile"
            ] = cookie_file

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

        "width": fmt.get(
            "width"
        ),

        "height": fmt.get(
            "height"
        ),

        "fps": fmt.get(
            "fps"
        ),

        "vcodec": vcodec,

        "acodec": acodec,

        "filesize": fmt.get(
            "filesize"
        ),

        "filesize_approx": fmt.get(
            "filesize_approx"
        ),

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
# CHOOSE RECOMMENDED VIDEO
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

        height = (
            fmt.get("height")
            or 0
        )

        width = (
            fmt.get("width")
            or 0
        )

        filesize = (
            fmt.get("filesize")
            or fmt.get(
                "filesize_approx"
            )
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

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        ),
        reverse=True,
    )

    return candidates[0][3]


# ============================================================
# CHOOSE RECOMMENDED AUDIO
# ============================================================

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

        abr = (
            fmt.get("abr")
            or 0
        )

        filesize = (
            fmt.get("filesize")
            or fmt.get(
                "filesize_approx"
            )
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
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    return candidates[0][2]


# ============================================================
# CHOOSE AUDIO FOR VIDEO
# ============================================================

def choose_audio_for_video(
    formats,
):

    return choose_recommended_audio(
        formats
    )


# ============================================================
# CLEANUP OLD FILES
# ============================================================

def cleanup_old_files():

    now = time.time()

    if not DOWNLOAD_DIR.exists():

        return

    for item in DOWNLOAD_DIR.iterdir():

        try:

            # Never delete the persistent cookie file.

            if (
                item.name
                == "youtube_cookies.txt"
            ):

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

        "youtube": {

            "pot_provider": (
                BGUTIL_PROVIDER_URL
            ),

            "cookies_configured": bool(
                YOUTUBE_COOKIES_BASE64
            ),

        },

    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {

        "success": True,

        "version": APP_VERSION,

        "yt_dlp": (
            yt_dlp.version.__version__
        ),

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

    # --------------------------------------------------------
    # Normalize YouTube URLs
    # --------------------------------------------------------

    if platform == "youtube":

        url = normalize_youtube_url(
            url
        )

    logger.info(
        "Analyzing media | platform=%s | url=%s",
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
                    "Unable to extract "
                    "media information."
                ),

            }

        formats = info.get(
            "formats",
            [],
        )

        public_formats = []

        video_formats = []

        audio_formats = []

        progressive_formats = []

        # ----------------------------------------------------
        # Convert formats
        # ----------------------------------------------------

        for fmt in formats:

            public_fmt = (
                format_to_public(
                    fmt
                )
            )

            if not public_fmt:

                continue

            public_formats.append(
                public_fmt
            )

            if public_fmt[
                "has_video"
            ]:

                video_formats.append(
                    public_fmt
                )

            if public_fmt[
                "has_audio"
            ]:

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

        # ----------------------------------------------------
        # Recommended formats
        # ----------------------------------------------------

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
            "Media analysis failed."
        )

        return {

            "success": False,

            "platform": platform,

            "error": str(exc),

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

    # --------------------------------------------------------
    # Normalize YouTube
    # --------------------------------------------------------

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
        "Download request | "
        "platform=%s | "
        "type=%s | "
        "format=%s",
        platform,
        media_type,
        request.format_id,
    )

    # ========================================================
    # EXTRACT INFORMATION
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
            "Unable to extract media "
            "before download."
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # ========================================================
    # FIND FORMAT
    # ========================================================

    formats = info.get(
        "formats",
        [],
    )

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
                "Requested format "
                "was not found."
            ),
        )

    # ========================================================
    # CREATE JOB DIRECTORY
    # ========================================================

    job_id = uuid.uuid4().hex

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # SAFE FILENAME
    # ========================================================

    original_title = (
        info.get("title")
        or "download"
    )

    media_id = (
        info.get("id")
        or uuid.uuid4().hex
    )

    safe_stem = make_safe_filename(
        title=original_title,
        media_id=media_id,
    )

    logger.info(
        "Original title: %s",
        original_title,
    )

    logger.info(
        "Safe filename stem: %s",
        safe_stem,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We NEVER put %(title)s directly into the output
    # template.
    #
    # This is what prevents long Windows filenames.
    # --------------------------------------------------------

    output_template = str(
        job_dir
        / f"{safe_stem}.%(ext)s"
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
                output_template=(
                    output_template
                ),
                platform=platform,
            )
        )

        download_options[
            "format"
        ] = request.format_id

        download_options[
            "postprocessors"
        ] = [

            {

                "key":
                    "FFmpegExtractAudio",

                "preferredcodec":
                    audio_format,

                "preferredquality":
                    "192",

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
        # Find output
        # ----------------------------------------------------

        output_files = [
            file
            for file in job_dir.iterdir()
            if file.is_file()
        ]

        if not output_files:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Audio download completed "
                    "but no output file was found."
                ),
            )

        output_file = max(
            output_files,
            key=lambda file: (
                file.stat().st_size
            ),
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

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

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
                output_template=(
                    output_template
                ),
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

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True,
                )

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
        # Execute download
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
        # Find output file
        # ----------------------------------------------------

        output_files = [
            file
            for file in job_dir.iterdir()
            if file.is_file()
        ]

        if not output_files:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Video download completed "
                    "but no output file was found."
                ),
            )

        output_file = max(
            output_files,
            key=lambda file: (
                file.stat().st_size
            ),
        )

    # ========================================================
    # FINAL FILE CHECK
    # ========================================================

    if not output_file.exists():

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=500,
            detail="Output file was not found.",
        )

    file_size = output_file.stat().st_size

    # ========================================================
    # FINAL FILENAME SAFETY CHECK
    # ========================================================

    # This should already be safe because we controlled
    # the output template. This second check protects us
    # if a postprocessor changes the filename.

    final_name = output_file.name

    if len(final_name) > (
        MAX_FILENAME_LENGTH + 10
    ):

        extension = (
            output_file.suffix
        )

        final_stem = (
            output_file.stem
        )

        final_stem = make_safe_filename(
            title=final_stem,
            media_id=media_id,
        )

        new_name = (
            final_stem
            + extension
        )

        new_path = (
            job_dir / new_name
        )

        try:

            output_file.rename(
                new_path
            )

            output_file = new_path

            final_name = (
                output_file.name
            )

        except Exception as exc:

            logger.warning(
                "Unable to rename final file: %s",
                exc,
            )

    # ========================================================
    # DOWNLOAD URL
    # ========================================================

    download_url = (
        f"/files/"
        f"{job_id}/"
        f"{output_file.name}"
    )

    logger.info(
        "Download completed."
    )

    logger.info(
        "Final filename: %s",
        output_file.name,
    )

    logger.info(
        "Final filename length: %d",
        len(output_file.name),
    )

    logger.info(
        "File size: %d bytes",
        file_size,
    )

    # ========================================================
    # RESPONSE
    # ========================================================

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
# SERVE FILE
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def serve_file(
    job_id: str,
    filename: str,
):

    # ========================================================
    # PATH SECURITY
    # ========================================================

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

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

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

    # ========================================================
    # VERIFY PATH STAYS INSIDE DOWNLOAD DIRECTORY
    # ========================================================

    try:

        file_path.resolve().relative_to(
            DOWNLOAD_DIR.resolve()
        )

    except ValueError:

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    # ========================================================
    # MIME TYPES
    # ========================================================

    extension = (
        file_path.suffix.lower()
    )

    media_types = {

        ".mp4":
            "video/mp4",

        ".webm":
            "video/webm",

        ".mkv":
            "video/x-matroska",

        ".mov":
            "video/quicktime",

        ".avi":
            "video/x-msvideo",

        ".flv":
            "video/x-flv",

        ".mp3":
            "audio/mpeg",

        ".m4a":
            "audio/mp4",

        ".aac":
            "audio/aac",

        ".wav":
            "audio/wav",

        ".flac":
            "audio/flac",

        ".ogg":
            "audio/ogg",

        ".opus":
            "audio/opus",

    }

    media_type = media_types.get(
        extension,
        "application/octet-stream",
    )

    # ========================================================
    # RETURN FILE
    # ========================================================

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event(
    "startup"
)
def startup_event():

    logger.info(
        "=========================================="
    )

    logger.info(
        "Media Downloader API starting..."
    )

    logger.info(
        "Application version: %s",
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

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------

    logger.info(
        "YouTube PO Token provider: %s",
        BGUTIL_PROVIDER_URL,
    )

    logger.info(
        "YouTube cookies configured: %s",
        bool(
            YOUTUBE_COOKIES_BASE64
        ),
    )

    # --------------------------------------------------------
    # Load cookies if configured
    # --------------------------------------------------------

    if YOUTUBE_COOKIES_BASE64:

        setup_youtube_cookies()

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    cleanup_old_files()

    logger.info(
        "Maximum filename length: %d",
        MAX_FILENAME_LENGTH,
    )

    logger.info(
        "Media Downloader API ready."
    )

    logger.info(
        "=========================================="
    )
    