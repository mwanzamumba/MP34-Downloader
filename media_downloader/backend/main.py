import os
import re
import time
import uuid
import shutil
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import yt_dlp


# ============================================================
# APP CONFIGURATION
# ============================================================

APP_VERSION = "3.3.0"

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FILE_TTL = int(
    os.getenv(
        "FILE_TTL",
        "1800",
    )
)

YOUTUBE_COOKIES = os.getenv(
    "YOUTUBE_COOKIES",
    ""
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(
    "mp34-downloader"
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    version=APP_VERSION,
    description=(
        "Media analysis and download API "
        "powered by yt-dlp."
    ),
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
        hostname = (
            urlparse(url)
            .hostname
            or ""
        ).lower()

    except Exception:
        return "Unknown"

    if (
        "youtube.com" in hostname
        or hostname == "youtu.be"
    ):
        return "YouTube"

    if (
        "tiktok.com" in hostname
    ):
        return "TikTok"

    if (
        "instagram.com" in hostname
        or "instagr.am" in hostname
    ):
        return "Instagram"

    if (
        "facebook.com" in hostname
        or hostname == "fb.watch"
    ):
        return "Facebook"

    if (
        "twitter.com" in hostname
        or "x.com" in hostname
    ):
        return "X"

    return "Unknown"


# ============================================================
# YOUTUBE URL NORMALIZATION
# ============================================================

def normalize_youtube_url(
    url: str,
) -> str:
    """
    Convert YouTube URLs into a clean single-video URL.

    Example:

    Input:
    https://www.youtube.com/watch?v=ABC123&list=RDXYZ&feature=youtu.be

    Output:
    https://www.youtube.com/watch?v=ABC123

    This is important because YouTube Mix/playlist URLs
    can cause yt-dlp to invoke the youtube:tab extractor,
    which can result in HTTP 403 errors.
    """

    try:
        parsed = urlparse(url)

        hostname = (
            parsed.hostname
            or ""
        ).lower()

        # ----------------------------------------------------
        # youtu.be
        # ----------------------------------------------------

        if hostname == "youtu.be":

            video_id = (
                parsed.path
                .strip("/")
            )

            if video_id:

                return (
                    "https://www.youtube.com/"
                    f"watch?v={video_id}"
                )

            return url

        # ----------------------------------------------------
        # YouTube domains
        # ----------------------------------------------------

        if (
            "youtube.com" in hostname
            or "youtube-nocookie.com" in hostname
        ):

            query = parse_qs(
                parsed.query
            )

            video_id = query.get(
                "v",
                [None],
            )[0]

            if video_id:

                return (
                    "https://www.youtube.com/"
                    f"watch?v={video_id}"
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

def validate_url(
    url: str,
) -> str:

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL is required.",
        )

    url = url.strip()

    if not re.match(
        r"^https?://",
        url,
        re.IGNORECASE,
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Please provide a valid "
                "HTTP or HTTPS URL."
            ),
        )

    platform = detect_platform(
        url
    )

    logger.info(
        "[URL] Platform detected: %s",
        platform,
    )

    # --------------------------------------------------------
    # Normalize YouTube URLs
    # --------------------------------------------------------

    if platform == "YouTube":

        original_url = url

        url = normalize_youtube_url(
            url
        )

        if url != original_url:

            logger.info(
                "[YOUTUBE] URL normalized successfully."
            )

            logger.info(
                "[YOUTUBE] Playlist/mix parameters removed."
            )

    return url


# ============================================================
# COOKIE FILE
# ============================================================

def create_cookie_file():
    """
    Creates a temporary Netscape cookie file from the
    YOUTUBE_COOKIES environment variable.

    Cookie contents are never logged.
    """

    if not YOUTUBE_COOKIES.strip():

        return None

    cookie_file = (
        DOWNLOAD_DIR
        / f".youtube_cookies_{uuid.uuid4().hex}.txt"
    )

    try:

        cookie_file.write_text(
            YOUTUBE_COOKIES,
            encoding="utf-8",
        )

        return cookie_file

    except Exception as exc:

        logger.error(
            "[COOKIES] Failed to create cookie file: %s",
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

        # ----------------------------------------------------
        # Do not download playlists.
        # ----------------------------------------------------

        "noplaylist": True,

        # ----------------------------------------------------
        # Quiet output is disabled because we want useful
        # logging in Render.
        # ----------------------------------------------------

        "quiet": False,
        "no_warnings": False,

        # ----------------------------------------------------
        # Retry configuration
        # ----------------------------------------------------

        "retries": 3,
        "fragment_retries": 3,

        # ----------------------------------------------------
        # Continue/resume
        # ----------------------------------------------------

        "continuedl": True,
        "overwrites": True,

        # ----------------------------------------------------
        # Network
        # ----------------------------------------------------

        "socket_timeout": 30,

        # ----------------------------------------------------
        # Extractor configuration
        #
        # default + web_embedded gives yt-dlp alternatives
        # when YouTube blocks one client.
        # ----------------------------------------------------

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "default",
                    "web_embedded",
                ]
            }
        },

        # ----------------------------------------------------
        # User agent
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
            "Accept-Language": (
                "en-US,en;q=0.9"
            ),
        },

        # ----------------------------------------------------
        # Download settings
        # ----------------------------------------------------

        "restrictfilenames": True,

    }

    # ========================================================
    # COOKIES
    # ========================================================

    cookie_file = create_cookie_file()

    if cookie_file:

        options[
            "cookiefile"
        ] = str(cookie_file)

        logger.info(
            "[YOUTUBE] Cookie authentication enabled."
        )

    # ========================================================
    # ACTUAL DOWNLOAD
    # ========================================================

    if download:

        options.update({

            "format": "best",

            "merge_output_format": "mp4",

        })

        if output_template:

            options[
                "outtmpl"
            ] = output_template

    return options


# ============================================================
# SAFE INTEGER
# ============================================================

def safe_int(
    value,
):
    try:

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# SAFE STRING
# ============================================================

def safe_string(
    value,
):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return value


# ============================================================
# FORMAT CONVERSION
# ============================================================

def format_to_public(
    fmt: dict,
) -> dict:

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

        "format_id":
            safe_string(
                fmt.get("format_id")
            ) or "",

        "ext":
            safe_string(
                fmt.get("ext")
            ),

        "format_note":
            safe_string(
                fmt.get("format_note")
            ),

        "width":
            safe_int(
                fmt.get("width")
            ),

        "height":
            safe_int(
                fmt.get("height")
            ),

        "fps":
            fmt.get("fps"),

        "vcodec":
            vcodec,

        "acodec":
            acodec,

        "filesize":
            safe_int(
                fmt.get("filesize")
                or fmt.get(
                    "filesize_approx"
                )
            ),

        "filesize_approx":
            safe_int(
                fmt.get(
                    "filesize_approx"
                )
            ),

        "abr":
            safe_int(
                fmt.get("abr")
            ),

        "url":
            safe_string(
                fmt.get("url")
            ),

        "has_video":
            has_video,

        "has_audio":
            has_audio,
    }


# ============================================================
# FORMAT SELECTION
# ============================================================

def select_recommended_video(
    formats: list[dict],
):

    progressive = [
        f
        for f in formats
        if f.get("has_video")
        and f.get("has_audio")
    ]

    video_only = [
        f
        for f in formats
        if f.get("has_video")
    ]

    candidates = (
        progressive
        if progressive
        else video_only
    )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("height")
            or 0,
            x.get("filesize")
            or 0,
        ),
        reverse=True,
    )

    return candidates[0]


def select_recommended_audio(
    formats: list[dict],
):

    audio_only = [
        f
        for f in formats
        if f.get("has_audio")
        and not f.get("has_video")
    ]

    progressive = [
        f
        for f in formats
        if f.get("has_audio")
        and f.get("has_video")
    ]

    candidates = (
        audio_only
        if audio_only
        else progressive
    )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("abr")
            or 0,
            x.get("filesize")
            or 0,
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# CLEANUP
# ============================================================

def cleanup_old_files():

    now = time.time()

    try:

        for path in DOWNLOAD_DIR.iterdir():

            try:

                if not path.is_file():
                    continue

                age = (
                    now
                    - path.stat().st_mtime
                )

                if age > FILE_TTL:

                    path.unlink(
                        missing_ok=True
                    )

                    logger.info(
                        "[CLEANUP] Deleted: %s",
                        path.name,
                    )

            except Exception as exc:

                logger.warning(
                    "[CLEANUP] Could not remove %s: %s",
                    path.name,
                    exc,
                )

    except Exception as exc:

        logger.warning(
            "[CLEANUP] Failed: %s",
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
        "yt_dlp": yt_dlp.version.__version__,
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {
        "success": True,
        "api_version": APP_VERSION,
        "yt_dlp": yt_dlp.version.__version__,
        "cookies_enabled": bool(
            YOUTUBE_COOKIES.strip()
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

    logger.info(
        "=================================================="
    )

    logger.info(
        "[ANALYZE] Platform: %s",
        platform,
    )

    logger.info(
        "[ANALYZE] URL received."
    )

    logger.info(
        "[ANALYZE] Starting yt-dlp extraction..."
    )

    options = get_ytdlp_options(
        download=False
    )

    try:

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        if not info:

            raise HTTPException(
                status_code=422,
                detail=(
                    "Unable to extract media "
                    "information."
                ),
            )

        # ----------------------------------------------------
        # If yt-dlp returns playlist information, try to use
        # the first video only.
        # ----------------------------------------------------

        if (
            info.get("_type") == "playlist"
        ):

            entries = info.get(
                "entries"
            ) or []

            first_entry = next(
                (
                    entry
                    for entry in entries
                    if entry
                ),
                None,
            )

            if first_entry:

                info = first_entry

        title = (
            info.get("title")
            or "Unknown title"
        )

        thumbnail = (
            info.get("thumbnail")
        )

        duration = safe_int(
            info.get("duration")
        )

        raw_formats = (
            info.get("formats")
            or []
        )

        public_formats = []

        for fmt in raw_formats:

            try:

                converted = (
                    format_to_public(
                        fmt
                    )
                )

                if converted[
                    "format_id"
                ]:

                    public_formats.append(
                        converted
                    )

            except Exception as exc:

                logger.warning(
                    "[ANALYZE] Skipping invalid format: %s",
                    exc,
                )

        # ----------------------------------------------------
        # Remove duplicate format IDs.
        # ----------------------------------------------------

        unique_formats = {}

        for fmt in public_formats:

            format_id = fmt[
                "format_id"
            ]

            unique_formats[
                format_id
            ] = fmt

        public_formats = list(
            unique_formats.values()
        )

        # ----------------------------------------------------
        # Recommended formats
        # ----------------------------------------------------

        recommended_video = (
            select_recommended_video(
                public_formats
            )
        )

        recommended_audio = (
            select_recommended_audio(
                public_formats
            )
        )

        logger.info(
            "[ANALYZE] Title: %s",
            title,
        )

        logger.info(
            "[ANALYZE] Formats found: %d",
            len(public_formats),
        )

        logger.info(
            "[ANALYZE] Recommended video: %s",
            (
                recommended_video.get(
                    "format_id"
                )
                if recommended_video
                else "None"
            ),
        )

        logger.info(
            "[ANALYZE] Recommended audio: %s",
            (
                recommended_audio.get(
                    "format_id"
                )
                if recommended_audio
                else "None"
            ),
        )

        logger.info(
            "=================================================="
        )

        return {

            "success": True,

            "title": title,

            "platform": platform,

            "thumbnail": thumbnail,

            "duration": duration,

            "formats": public_formats,

            "recommended_video":
                recommended_video,

            "recommended_audio":
                recommended_audio,
        }

    except HTTPException:

        raise

    except yt_dlp.utils.DownloadError as exc:

        logger.error(
            "[ANALYZE] yt-dlp error: %s",
            exc,
        )

        error_message = str(
            exc
        )

        # ----------------------------------------------------
        # Friendlier error messages
        # ----------------------------------------------------

        if (
            "403"
            in error_message
        ):

            detail = (
                "The media platform "
                "blocked the request (HTTP 403). "
                "Please try another link."
            )

        elif (
            "Sign in"
            in error_message
            or "login"
            in error_message.lower()
        ):

            detail = (
                "This media requires authentication "
                "and could not be accessed."
            )

        else:

            detail = (
                "Unable to analyze this media link."
            )

        raise HTTPException(
            status_code=422,
            detail=detail,
        )

    except Exception as exc:

        logger.exception(
            "[ANALYZE] Unexpected error"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected server error "
                "while analyzing the media."
            ),
        )


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

    requested_format_id = (
        request.format_id.strip()
    )

    if not requested_format_id:

        raise HTTPException(
            status_code=400,
            detail="format_id is required.",
        )

    logger.info(
        "=================================================="
    )

    logger.info(
        "[DOWNLOAD] Platform: %s",
        platform,
    )

    logger.info(
        "[DOWNLOAD] Requested format: %s",
        requested_format_id,
    )

    logger.info(
        "[DOWNLOAD] Media type: %s",
        request.media_type,
    )

    # ========================================================
    # FIRST: EXTRACT MEDIA INFORMATION
    # ========================================================

    analyze_options = get_ytdlp_options(
        download=False
    )

    try:

        with yt_dlp.YoutubeDL(
            analyze_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

    except yt_dlp.utils.DownloadError as exc:

        logger.error(
            "[DOWNLOAD] Extraction failed: %s",
            exc,
        )

        raise HTTPException(
            status_code=422,
            detail=(
                "Unable to access the media "
                "for downloading."
            ),
        )

    except Exception as exc:

        logger.exception(
            "[DOWNLOAD] Unexpected extraction error"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected error while preparing "
                "the download."
            ),
        )

    # ========================================================
    # PLAYLIST PROTECTION
    # ========================================================

    if (
        info.get("_type") == "playlist"
    ):

        entries = info.get(
            "entries"
        ) or []

        first_entry = next(
            (
                entry
                for entry in entries
                if entry
            ),
            None,
        )

        if first_entry:

            info = first_entry

    # ========================================================
    # FIND REQUESTED FORMAT
    # ========================================================

    formats = (
        info.get("formats")
        or []
    )

    selected_format = None

    for fmt in formats:

        if str(
            fmt.get("format_id")
        ) == requested_format_id:

            selected_format = fmt

            break

    if selected_format is None:

        logger.error(
            "[DOWNLOAD] Requested format not found: %s",
            requested_format_id,
        )

        available_ids = [
            str(
                fmt.get("format_id")
            )
            for fmt in formats
            if fmt.get("format_id")
        ]

        logger.info(
            "[DOWNLOAD] Available formats: %s",
            ", ".join(
                available_ids[:30]
            ),
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "The requested format is "
                "no longer available. "
                "Please analyze the link again."
            ),
        )

    logger.info(
        "[DOWNLOAD] Requested format found."
    )

    logger.info(
        "[DOWNLOAD] Selected format: %s",
        selected_format.get(
            "format_id"
        ),
    )

    logger.info(
        "[DOWNLOAD] Extension: %s",
        selected_format.get(
            "ext"
        ),
    )

    logger.info(
        "[DOWNLOAD] Video codec: %s",
        selected_format.get(
            "vcodec"
        ),
    )

    logger.info(
        "[DOWNLOAD] Audio codec: %s",
        selected_format.get(
            "acodec"
        ),
    )

    # ========================================================
    # OUTPUT DIRECTORY
    # ========================================================

    job_id = uuid.uuid4().hex

    job_dir = (
        DOWNLOAD_DIR
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # OUTPUT FILE
    # ========================================================

    media_type = (
        request.media_type.lower()
    )

    if media_type == "audio":

        extension = (
            request.audio_format
            or "mp3"
        )

        extension = extension.lower()

        if extension not in {
            "mp3",
            "m4a",
            "opus",
            "wav",
        }:

            extension = "mp3"

    else:

        extension = (
            selected_format.get(
                "ext"
            )
            or "mp4"
        )

        extension = str(
            extension
        ).lower()

        if extension == "webm":

            extension = "mp4"

    output_template = str(
        job_dir
        / "media.%(ext)s"
    )

    # ========================================================
    # DOWNLOAD OPTIONS
    # ========================================================

    download_options = get_ytdlp_options(
        download=True,
        output_template=output_template,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Download EXACTLY the format selected by the Flutter app.
    # --------------------------------------------------------

    if media_type == "audio":

        download_options[
            "format"
        ] = requested_format_id

        download_options[
            "postprocessors"
        ] = [
            {
                "key":
                    "FFmpegExtractAudio",

                "preferredcodec":
                    extension,

                "preferredquality":
                    "192",
            }
        ]

    else:

        download_options[
            "format"
        ] = requested_format_id

    # ========================================================
    # ACTUAL DOWNLOAD
    # ========================================================

    logger.info(
        "[DOWNLOAD] STARTING ACTUAL DOWNLOAD"
    )

    try:

        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download(
                [url]
            )

    except yt_dlp.utils.DownloadError as exc:

        logger.error(
            "[DOWNLOAD] DOWNLOAD FAILED"
        )

        logger.error(
            "[DOWNLOAD] %s",
            exc,
        )

        # ----------------------------------------------------
        # Remove failed job directory
        # ----------------------------------------------------

        try:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

        except Exception:
            pass

        error_message = str(
            exc
        )

        if "403" in error_message:

            detail = (
                "The media server returned "
                "HTTP 403 while downloading. "
                "Please try analyzing the link again "
                "or try another media link."
            )

        elif (
            "Sign in"
            in error_message
        ):

            detail = (
                "This media requires authentication "
                "and could not be downloaded."
            )

        else:

            detail = (
                "The media download failed."
            )

        raise HTTPException(
            status_code=422,
            detail=detail,
        )

    except Exception as exc:

        logger.exception(
            "[DOWNLOAD] Unexpected download error"
        )

        try:

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected server error "
                "during download."
            ),
        )

    # ========================================================
    # FIND RESULT FILE
    # ========================================================

    downloaded_files = [
        file
        for file in job_dir.iterdir()
        if file.is_file()
        and not file.name.endswith(
            ".part"
        )
    ]

    if not downloaded_files:

        logger.error(
            "[DOWNLOAD] No output file was created."
        )

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Download completed but "
                "no output file was found."
            ),
        )

    output_file = max(
        downloaded_files,
        key=lambda file:
            file.stat().st_mtime,
    )

    filename = output_file.name

    logger.info(
        "[DOWNLOAD] Download completed."
    )

    logger.info(
        "[DOWNLOAD] File: %s",
        filename,
    )

    logger.info(
        "[DOWNLOAD] Job ID: %s",
        job_id,
    )

    logger.info(
        "=================================================="
    )

    return {

        "success": True,

        "job_id": job_id,

        "filename": filename,

        "download_url":
            f"/files/{job_id}/{filename}",

        "title":
            info.get(
                "title"
            )
            or "Downloaded media",

        "platform":
            platform,
    }


# ============================================================
# SERVE DOWNLOADED FILE
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def get_file(
    job_id: str,
    filename: str,
):

    # --------------------------------------------------------
    # Basic security validation
    # --------------------------------------------------------

    if (
        "/" in job_id
        or "\\" in job_id
        or ".." in job_id
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid job ID.",
        )

    if (
        "/" in filename
        or "\\" in filename
        or ".." in filename
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    file_path = (
        DOWNLOAD_DIR
        / job_id
        / filename
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found or expired.",
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    return FileResponse(
        path=str(
            file_path
        ),
        filename=filename,
    )


# ============================================================
# DEBUG YOUTUBE
# ============================================================

@app.get(
    "/debug-youtube"
)
def debug_youtube():

    """
    Simple diagnostic endpoint.

    It uses a public test video.
    """

    test_url = (
        "https://www.youtube.com/"
        "watch?v=L5aSgl7HKBA"
    )

    test_url = normalize_youtube_url(
        test_url
    )

    logger.info(
        "[DEBUG] Testing YouTube."
    )

    options = get_ytdlp_options(
        download=False
    )

    try:

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                test_url,
                download=False,
            )

        return {

            "success": True,

            "message":
                "YouTube extraction succeeded.",

            "title":
                info.get(
                    "title"
                ),

            "id":
                info.get(
                    "id"
                ),

            "duration":
                info.get(
                    "duration"
                ),

            "formats":
                len(
                    info.get(
                        "formats"
                    )
                    or []
                ),
        }

    except Exception as exc:

        logger.exception(
            "[DEBUG] YouTube test failed."
        )

        raise HTTPException(
            status_code=422,
            detail=(
                "YouTube debug test failed."
            ),
        )


# ============================================================
# STARTUP
# ============================================================

@app.on_event(
    "startup"
)
def startup_event():

    logger.info(
        "=================================================="
    )

    logger.info(
        "Media Downloader API starting..."
    )

    logger.info(
        "API version: %s",
        APP_VERSION,
    )

    logger.info(
        "yt-dlp version: %s",
        yt_dlp.version.__version__,
    )

    logger.info(
        "Download directory: %s",
        DOWNLOAD_DIR,
    )

    logger.info(
        "File TTL: %s seconds",
        FILE_TTL,
    )

    logger.info(
        "YouTube cookies configured: %s",
        bool(
            YOUTUBE_COOKIES.strip()
        ),
    )

    logger.info(
        "=================================================="
    )


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event(
    "shutdown"
)
def shutdown_event():

    logger.info(
        "Media Downloader API shutting down."
    )