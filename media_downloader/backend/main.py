import os
import re
import time
import uuid
import shutil
import socket
import logging
import base64
import importlib.util
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import yt_dlp

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_VERSION = "6.2.0"

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

MAX_FILENAME_LENGTH = int(
    os.getenv(
        "MAX_FILENAME_LENGTH",
        "80",
    )
)

# ------------------------------------------------------------
# BGUTIL PO TOKEN PROVIDER
# ------------------------------------------------------------

BGUTIL_PROVIDER_URL = os.getenv(
    "BGUTIL_PROVIDER_URL",
    "http://127.0.0.1:4416",
).rstrip("/")


# ------------------------------------------------------------
# OPTIONAL YOUTUBE COOKIES
# ------------------------------------------------------------

YOUTUBE_COOKIES_BASE64 = os.getenv(
    "YOUTUBE_COOKIES_BASE64",
    "",
).strip()

YOUTUBE_COOKIES_FILE = (
    DOWNLOAD_DIR / "youtube_cookies.txt"
)


# ------------------------------------------------------------
# DEBUGGING
# ------------------------------------------------------------

YTDLP_DEBUG = os.getenv(
    "YTDLP_DEBUG",
    "1",
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.DEBUG if YTDLP_DEBUG else logging.INFO,
    format=(
        "%(asctime)s "
        "[%(levelname)s] "
        "%(name)s: "
        "%(message)s"
    ),
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


from pydantic import BaseModel, Field, field_validator

class DownloadRequest(BaseModel):
    url: str
    format_id: str | None = None
    media_type: str = "video"

    # Accept null safely
    audio_format: str | None = Field(default="mp3")

    @field_validator("audio_format", mode="before")
    @classmethod
    def fix_audio_format(cls, value):

        if value is None:
            return "mp3"

        if not isinstance(value, str):
            return "mp3"

        value = value.strip().lower()

        allowed = {
            "mp3",
            "m4a",
            "aac",
            "wav",
            "flac",
            "opus",
            "dash"
        }

        if value not in allowed:
            return "mp3"

        return value

    @field_validator("media_type", mode="before")
    @classmethod
    def fix_media_type(cls, value):

        if value is None:
            return "video"

        value = str(value).strip().lower()

        if value not in {"video", "audio"}:
            return "video"

        return value


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str) -> str:

    try:

        parsed = urlparse(
            url.strip()
        )

        hostname = (
            parsed.hostname or ""
        ).lower()

    except Exception:

        return "unknown"

    hostname = hostname.replace(
        "www.",
        "",
    )

    if (
        "youtube.com" in hostname
        or hostname == "youtu.be"
        or "youtube-nocookie.com" in hostname
    ):
        return "youtube"

    if (
        "facebook.com" in hostname
        or "fb.watch" in hostname
    ):
        return "facebook"

    if (
        "tiktok.com" in hostname
        or hostname == "vm.tiktok.com"
    ):
        return "tiktok"

    if (
        "instagram.com" in hostname
    ):
        return "instagram"

    if (
        "twitter.com" in hostname
        or "x.com" in hostname
    ):
        return "twitter"

    return "generic"


# ============================================================
# YOUTUBE VIDEO ID
# ============================================================

def get_youtube_video_id(
    url: str,
) -> str | None:

    try:

        parsed = urlparse(
            url.strip()
        )

        hostname = (
            parsed.hostname or ""
        ).lower()

        if hostname == "youtu.be":

            return (
                parsed.path
                .strip("/")
                .split("/")[0]
                or None
            )

        query = parse_qs(
            parsed.query
        )

        if query.get("v"):

            return query["v"][0]

        match = re.search(
            r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{6,})",
            parsed.path,
        )

        if match:

            return match.group(1)

    except Exception as exc:

        logger.debug(
            "Could not extract YouTube video ID: %s",
            exc,
        )

    return None


# ============================================================
# BGUTIL PROVIDER HOST/PORТ
# ============================================================

def get_provider_host_port():

    try:

        parsed = urlparse(
            BGUTIL_PROVIDER_URL
        )

        if not parsed.hostname:

            return None

        if parsed.port:

            port = parsed.port

        elif parsed.scheme == "https":

            port = 443

        else:

            port = 80

        return (
            parsed.hostname,
            port,
        )

    except Exception as exc:

        logger.error(
            "Could not parse BGUTIL_PROVIDER_URL: %s",
            exc,
        )

        return None


# ============================================================
# CHECK BGUTIL TCP CONNECTIVITY
# ============================================================

def is_bgutil_provider_reachable(
    timeout: float = 2.0,
) -> bool:

    target = get_provider_host_port()

    if not target:

        return False

    host, port = target

    try:

        with socket.create_connection(
            (
                host,
                port,
            ),
            timeout=timeout,
        ):

            return True

    except Exception:

        return False


# ============================================================
# WAIT FOR BGUTIL PROVIDER
# ============================================================

def wait_for_bgutil_provider(
    attempts: int = 30,
    delay: float = 0.5,
) -> bool:

    logger.info(
        "Waiting for BGUTIL provider at %s",
        BGUTIL_PROVIDER_URL,
    )

    for attempt in range(
        1,
        attempts + 1,
    ):

        if is_bgutil_provider_reachable():

            logger.info(
                "BGUTIL provider is reachable "
                "after attempt %s.",
                attempt,
            )

            return True

        logger.warning(
            "BGUTIL provider not reachable "
            "(attempt %s/%s).",
            attempt,
            attempts,
        )

        time.sleep(delay)

    logger.error(
        "BGUTIL provider could not be reached "
        "after %s attempts.",
        attempts,
    )

    return False


# ============================================================
# FIND BGUTIL PLUGIN FILES
# ============================================================

def find_bgutil_plugin_files():

    results = []

    try:

        yt_dlp_location = Path(
            yt_dlp.__file__
        ).resolve()

        site_packages = (
            yt_dlp_location.parent.parent
        )

        search_roots = [
            site_packages,
            Path(
                "/usr/local/lib"
            ),
        ]

        seen = set()

        for root in search_roots:

            if not root.exists():

                continue

            try:

                for path in root.rglob(
                    "*bgutil*"
                ):

                    if not path.is_file():

                        continue

                    text = str(
                        path
                    )

                    if text in seen:

                        continue

                    seen.add(text)

                    results.append(
                        text
                    )

            except Exception:

                continue

    except Exception as exc:

        logger.debug(
            "Plugin scan failed: %s",
            exc,
        )

    return results[:30]


# ============================================================
# YT-DLP VERSION
# ============================================================

def get_ytdlp_version():

    try:

        return yt_dlp.version.__version__

    except Exception:

        return "unknown"


# ============================================================
# YOUTUBE COOKIES
# ============================================================

def setup_youtube_cookies():

    if not YOUTUBE_COOKIES_BASE64:

        return None

    try:

        decoded = base64.b64decode(
            YOUTUBE_COOKIES_BASE64,
            validate=True,
        )

        if not decoded:

            logger.warning(
                "YOUTUBE_COOKIES_BASE64 is empty."
            )

            return None

        YOUTUBE_COOKIES_FILE.write_bytes(
            decoded
        )

        logger.info(
            "YouTube cookies configured."
        )

        return str(
            YOUTUBE_COOKIES_FILE
        )

    except Exception as exc:

        logger.error(
            "Could not decode YouTube cookies: %s",
            exc,
        )

        return None


# ============================================================
# SAFE FILENAME
# ============================================================

def make_safe_filename(
    title: str | None,
    extension: str,
    media_id: str | None = None,
) -> str:

    title = (
        title
        or "download"
    )

    media_id = (
        media_id
        or uuid.uuid4().hex[:8]
    )

    # Remove Windows/Linux forbidden characters.
    title = re.sub(
        r'[<>:"/\\|?*]',
        "",
        title,
    )

    title = re.sub(
        r"[\x00-\x1f\x7f]",
        "",
        title,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    # Prevent repeated punctuation.
    title = re.sub(
        r"[. ]+$",
        "",
        title,
    )

    if not title:

        title = "download"

    # Keep filenames short.
    suffix = (
        "-"
        + re.sub(
            r"[^A-Za-z0-9_-]",
            "",
            media_id,
        )[:10]
    )

    if not suffix.strip("-"):

        suffix = (
            "-"
            + uuid.uuid4().hex[:8]
        )

    available = (
        MAX_FILENAME_LENGTH
        - len(suffix)
    )

    if available < 10:

        available = 10

    title = title[:available].rstrip(
        ". "
    )

    return (
        f"{title}"
        f"{suffix}"
        f".{extension.lstrip('.')}"
    )


# ============================================================
# CLEAN OLD FILES
# ============================================================

def cleanup_old_files():

    now = time.time()

    try:

        for path in DOWNLOAD_DIR.iterdir():

            if not path.is_file():

                continue

            # Do not delete cookies.
            if path == YOUTUBE_COOKIES_FILE:

                continue

            try:

                age = (
                    now
                    - path.stat().st_mtime
                )

                if age > FILE_TTL:

                    path.unlink(
                        missing_ok=True
                    )

                    logger.info(
                        "Deleted expired file: %s",
                        path.name,
                    )

            except Exception as exc:

                logger.warning(
                    "Could not remove %s: %s",
                    path,
                    exc,
                )

    except Exception as exc:

        logger.warning(
            "Cleanup failed: %s",
            exc,
        )


# ============================================================
# FFmpeg CHECK
# ============================================================

def get_ffmpeg_path():

    return shutil.which(
        "ffmpeg"
    )


def get_ffprobe_path():

    return shutil.which(
        "ffprobe"
    )


# ============================================================
# BASE YT-DLP OPTIONS
# ============================================================

def get_base_ytdlp_options():

    options = {

        "quiet": not YTDLP_DEBUG,

        "no_warnings": not YTDLP_DEBUG,

        "noplaylist": True,

        "restrictfilenames": True,

        "nocheckcertificate": True,

        "ignoreerrors": False,

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        "concurrent_fragment_downloads": 4,

    }

    if YTDLP_DEBUG:

        options["verbose"] = True

    return options


# ============================================================
# YOUTUBE OPTIONS
# ============================================================

def get_youtube_options(
    output_template: str | None = None,
):

    options = get_base_ytdlp_options()

    if output_template:

        options["outtmpl"] = (
            output_template
        )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Current yt-dlp guidance recommends mweb + a PO-token
    # provider.
    #
    # We deliberately do NOT put "default" here.
    # Otherwise yt-dlp can fall back to another client which
    # may immediately trigger the bot check.
    # --------------------------------------------------------

    options["extractor_args"] = {

        "youtube": {

            "player_client": [
                "mweb",
            ],

        },

        "youtubepot-bgutilhttp": {

            "base_url": [
                BGUTIL_PROVIDER_URL,
            ],

        },

    }

    # --------------------------------------------------------
    # OPTIONAL COOKIES
    # --------------------------------------------------------

    cookie_file = (
        setup_youtube_cookies()
    )

    if cookie_file:

        options["cookiefile"] = (
            cookie_file
        )

    return options


# ============================================================
# YOUTUBE FALLBACK OPTIONS
# ============================================================

def get_youtube_fallback_options(
    client: str,
    output_template: str | None = None,
):

    options = get_base_ytdlp_options()

    if output_template:

        options["outtmpl"] = (
            output_template
        )

    options["extractor_args"] = {

        "youtube": {

            "player_client": [
                client,
            ],

        },

    }

    cookie_file = (
        setup_youtube_cookies()
    )

    if cookie_file:

        options["cookiefile"] = (
            cookie_file
        )

    return options


# ============================================================
# GENERIC OPTIONS
# ============================================================

def get_generic_options(
    output_template: str | None = None,
):

    options = get_base_ytdlp_options()

    if output_template:

        options["outtmpl"] = (
            output_template
        )

    return options


# ============================================================
# YOUTUBE EXTRACTION STRATEGIES
# ============================================================

def get_youtube_strategies():

    return [

        (
            "mweb-bgutil",
            lambda output=None:
                get_youtube_options(
                    output
                ),
        ),

        # ----------------------------------------------------
        # Fallbacks.
        #
        # These are NOT guaranteed to work. They are here so
        # that a temporary YouTube client change does not
        # automatically kill every possible extraction path.
        # ----------------------------------------------------

        (
            "web-embedded",
            lambda output=None:
                get_youtube_fallback_options(
                    "web_embedded",
                    output,
                ),
        ),

        (
            "tv",
            lambda output=None:
                get_youtube_fallback_options(
                    "tv",
                    output,
                ),
        ),

        
            "android-vr",
            lambda output=None:
                get_youtube_fallback_options(
                    "android_vr",
                    output,
                ),

    ]


# ============================================================
# EXTRACT INFO
# ============================================================

def extract_info(
    url: str,
    platform: str,
):

    cleanup_old_files()

    # --------------------------------------------------------
    # YOUTUBE
    # --------------------------------------------------------

    if platform == "youtube":

        provider_reachable = (
            is_bgutil_provider_reachable()
        )

        if not provider_reachable:

            logger.warning(
                "BGUTIL provider is not reachable. "
                "Attempting fallback YouTube clients."
            )

        last_error = None

        for strategy_name, options_factory in (
            get_youtube_strategies()
        ):

            logger.info(
                "Trying YouTube strategy: %s",
                strategy_name,
            )

            try:

                options = (
                    options_factory()
                )

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    info = ydl.extract_info(
                        url,
                        download=False,
                    )

                if info:

                    logger.info(
                        "YouTube strategy succeeded: %s",
                        strategy_name,
                    )

                    return info

            except Exception as exc:

                last_error = str(
                    exc
                )

                logger.warning(
                    "YouTube strategy '%s' failed: %s",
                    strategy_name,
                    last_error,
                )

        raise RuntimeError(
            "All YouTube extraction strategies failed. "
            f"BGUTIL reachable={provider_reachable}. "
            f"Last error: {last_error}"
        )

    # --------------------------------------------------------
    # OTHER PLATFORMS
    # --------------------------------------------------------

    options = get_generic_options()

    with yt_dlp.YoutubeDL(
        options
    ) as ydl:

        return ydl.extract_info(
            url,
            download=False,
        )


# ============================================================
# FORMAT HELPERS
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

    if not has_video and not has_audio:

        return None

    width = fmt.get(
        "width"
    )

    height = fmt.get(
        "height"
    )

    filesize = (
        fmt.get("filesize")
        or fmt.get("filesize_approx")
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

        "width": width,

        "height": height,

        "resolution": (
            f"{width}x{height}"
            if width and height
            else None
        ),

        "fps": fmt.get(
            "fps"
        ),

        "vcodec": vcodec,

        "acodec": acodec,

        "abr": fmt.get(
            "abr"
        ),

        "vbr": fmt.get(
            "vbr"
        ),

        "tbr": fmt.get(
            "tbr"
        ),

        "filesize": filesize,

        "filesize_approx": fmt.get(
            "filesize_approx"
        ),

        "has_video": has_video,

        "has_audio": has_audio,

        "url": None,

    }


# ============================================================
# FORMAT SELECTION
# ============================================================

def get_formats(
    info,
):

    formats = []

    for fmt in (
        info.get(
            "formats",
            []
        )
        or []
    ):

        public = format_to_public(
            fmt
        )

        if public:

            formats.append(
                public
            )

    return formats


def choose_recommended_video(
    formats,
):

    video_formats = [
        fmt
        for fmt in formats
        if fmt.get("has_video")
    ]

    if not video_formats:

        return None

    # Prefer formats that already contain
    # both video and audio.
    progressive = [
        fmt
        for fmt in video_formats
        if fmt.get("has_audio")
    ]

    candidates = (
        progressive
        or video_formats
    )

    def score(fmt):

        height = (
            fmt.get("height")
            or 0
        )

        width = (
            fmt.get("width")
            or 0
        )

        fps = (
            fmt.get("fps")
            or 0
        )

        tbr = (
            fmt.get("tbr")
            or 0
        )

        return (
            height,
            width,
            fps,
            tbr,
        )

    return max(
        candidates,
        key=score,
    )


def choose_recommended_audio(
    formats,
):

    audio_formats = [
        fmt
        for fmt in formats
        if (
            fmt.get("has_audio")
            and not fmt.get("has_video")
        )
    ]

    if not audio_formats:

        # Progressive format fallback.
        audio_formats = [
            fmt
            for fmt in formats
            if fmt.get("has_audio")
        ]

    if not audio_formats:

        return None

    def score(fmt):

        abr = (
            fmt.get("abr")
            or 0
        )

        tbr = (
            fmt.get("tbr")
            or 0
        )

        return (
            abr,
            tbr,
        )

    return max(
        audio_formats,
        key=score,
    )


# ============================================================
# ANALYZE
# ============================================================

def analyze_url(
    url: str,
):

    url = (
        url
        or ""
    ).strip()

    if not url:

        raise ValueError(
            "URL is required."
        )

    platform = detect_platform(
        url
    )

    logger.info(
        "Analyzing URL platform=%s url=%s",
        platform,
        url,
    )

    info = extract_info(
        url,
        platform,
    )

    if not info:

        raise RuntimeError(
            "No media information was returned."
        )

    formats = get_formats(
        info
    )

    recommended_video = (
        choose_recommended_video(
            formats
        )
    )

    recommended_audio = (
        choose_recommended_audio(
            formats
        )
    )

    thumbnail = (
        info.get("thumbnail")
        or None
    )

    title = (
        info.get("title")
        or "Untitled"
    )

    duration = (
        info.get("duration")
    )

    media_id = (
        info.get("id")
    )

    return {

        "success": True,

        "platform": platform,

        "id": media_id,

        "title": title,

        "thumbnail": thumbnail,

        "duration": duration,

        "uploader": info.get(
            "uploader"
        ),

        "channel": info.get(
            "channel"
        ),

        "webpage_url": info.get(
            "webpage_url"
        ),

        "formats": formats,

        "recommended_video": (
            recommended_video
        ),

        "recommended_audio": (
            recommended_audio
        ),

        "youtube": (
            {
                "video_id": get_youtube_video_id(
                    url
                ),
                "pot_provider": (
                    BGUTIL_PROVIDER_URL
                ),
                "pot_provider_reachable": (
                    is_bgutil_provider_reachable()
                ),
                "cookies_configured": bool(
                    YOUTUBE_COOKIES_BASE64
                ),
            }
            if platform == "youtube"
            else None
        ),

    }


# ============================================================
# DOWNLOAD FORMAT
# ============================================================

def build_video_format(format_id: str | None):

    if format_id:

        return (
            f"{format_id}+bestaudio/"
            f"{format_id}/"
            "bestvideo+bestaudio/"
            "best"
        )

    return (
        "bestvideo+bestaudio/"
        "best"
    )


def build_audio_format():

    return (
        "bestaudio/best"
    )


# ============================================================
# DOWNLOAD MEDIA
# ============================================================

def download_media(
    url: str,
    format_id: str | None,
    media_type: str,
    audio_format: str,
):

    cleanup_old_files()

    platform = detect_platform(
        url
    )

    logger.info(
        "Downloading platform=%s media_type=%s format_id=%s",
        platform,
        media_type,
        format_id,
    )

    # --------------------------------------------------------
    # First extract information.
    # --------------------------------------------------------

    info = extract_info(
        url,
        platform,
    )

    if not info:

        raise RuntimeError(
            "Unable to obtain media information."
        )

    title = (
        info.get("title")
        or "download"
    )

    media_id = (
        info.get("id")
        or uuid.uuid4().hex[:8]
    )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    if media_type == "audio":

        extension = (
            audio_format
            or "mp3"
        ).lower()

        if extension not in {
            "mp3",
            "m4a",
            "wav",
            "opus",
            "flac",
        }:

            extension = "mp3"

        filename = make_safe_filename(
            title,
            extension,
            media_id,
        )

        output_path = (
            DOWNLOAD_DIR
            / filename
        )

        output_template = str(
            output_path
        )

        if platform == "youtube":

            options = get_youtube_options(
                output_template
            )

        else:

            options = get_generic_options(
                output_template
            )

        options.update({

            "format": build_audio_format(),

            "postprocessors": [

                {
                    "key": "FFmpegExtractAudio",

                    "preferredcodec": extension,

                    "preferredquality": "192",

                }

            ],

        })

    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    else:

        filename = make_safe_filename(
            title,
            "mp4",
            media_id,
        )

        output_path = (
            DOWNLOAD_DIR
            / filename
        )

        output_template = str(
            output_path
        )

        if platform == "youtube":

            options = get_youtube_options(
                output_template
            )

        else:

            options = get_generic_options(
                output_template
            )

        options.update({

            "format": build_video_format(
                format_id
            ),

            "merge_output_format": "mp4",

            "postprocessors": [],

        })

    # --------------------------------------------------------
    # Perform actual download.
    # --------------------------------------------------------

    with yt_dlp.YoutubeDL(
        options
    ) as ydl:

        ydl.download(
            [url]
        )

    # --------------------------------------------------------
    # yt-dlp/FFmpeg may slightly alter the final filename.
    # Search for the expected output.
    # --------------------------------------------------------

    if output_path.exists():

        final_path = output_path

    else:

        candidates = sorted(
            DOWNLOAD_DIR.glob(
                f"*{media_id}*"
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if candidates:

            final_path = candidates[0]

        else:

            # Last fallback: most recently
            # created media file.
            all_files = [
                p
                for p in DOWNLOAD_DIR.iterdir()
                if (
                    p.is_file()
                    and p != YOUTUBE_COOKIES_FILE
                )
            ]

            if not all_files:

                raise RuntimeError(
                    "Download completed but "
                    "the output file could not be found."
                )

            final_path = max(
                all_files,
                key=lambda p: p.stat().st_mtime,
            )

    # --------------------------------------------------------
    # Validate file.
    # --------------------------------------------------------

    if not final_path.exists():

        raise RuntimeError(
            "Downloaded file does not exist."
        )

    file_size = (
        final_path.stat().st_size
    )

    if file_size <= 0:

        raise RuntimeError(
            "Downloaded file is empty."
        )

    # --------------------------------------------------------
    # Rename if necessary.
    # --------------------------------------------------------

    if final_path != output_path:

        try:

            if not output_path.exists():

                final_path.rename(
                    output_path
                )

                final_path = output_path

        except Exception as exc:

            logger.warning(
                "Could not rename final file: %s",
                exc,
            )

    # --------------------------------------------------------
    # Public download URL.
    # --------------------------------------------------------

    job_id = uuid.uuid4().hex

    # Put the file into a job-specific directory.
    job_dir = (
        DOWNLOAD_DIR
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        job_dir
        / final_path.name
    )

    shutil.move(
        str(final_path),
        str(destination),
    )

    download_url = (
        f"/files/"
        f"{job_id}/"
        f"{destination.name}"
    )

    return {

        "success": True,

        "job_id": job_id,

        "filename": destination.name,

        "downloadUrl": download_url,

        "download_url": download_url,

        "media_type": media_type,

        "format_id": format_id,

        "size": (
            destination.stat().st_size
        ),

    }


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health"
)
def health():

    provider_reachable = (
        is_bgutil_provider_reachable()
    )

    ffmpeg = get_ffmpeg_path()

    ffprobe = get_ffprobe_path()

    return {

        "success": True,

        "status": (
            "healthy"
            if provider_reachable
            else "degraded"
        ),

        "version": APP_VERSION,

        "yt_dlp_version": (
            get_ytdlp_version()
        ),

        "ffmpeg": bool(
            ffmpeg
        ),

        "ffprobe": bool(
            ffprobe
        ),

        "youtube": {

            "pot_provider": (
                BGUTIL_PROVIDER_URL
            ),

            "pot_provider_reachable": (
                provider_reachable
            ),

            "cookies_configured": bool(
                YOUTUBE_COOKIES_BASE64
            ),

            "player_client": "mweb",

        },

    }


# ============================================================
# YOUTUBE DIAGNOSTICS
# ============================================================

@app.get(
    "/youtube-status"
)
def youtube_status():

    provider_reachable = (
        is_bgutil_provider_reachable()
    )

    plugin_files = (
        find_bgutil_plugin_files()
    )

    return {

        "success": True,

        "youtube": {

            "player_client": "mweb",

            "pot_provider": (
                BGUTIL_PROVIDER_URL
            ),

            "pot_provider_reachable": (
                provider_reachable
            ),

            "cookies_configured": bool(
                YOUTUBE_COOKIES_BASE64
            ),

        },

        "yt_dlp": {

            "version": (
                get_ytdlp_version()
            ),

        },

        "bgutil_plugin": {

            "possible_files_found": (
                len(plugin_files)
            ),

            "files": plugin_files,

        },

    }


# ============================================================
# VERSION
# ============================================================

@app.get(
    "/version"
)
def version():

    return {

        "success": True,

        "version": APP_VERSION,

        "yt_dlp_version": (
            get_ytdlp_version()
        ),

        "bgutil_provider": (
            BGUTIL_PROVIDER_URL
        ),

        "bgutil_reachable": (
            is_bgutil_provider_reachable()
        ),

    }


# ============================================================
# ANALYZE ENDPOINT
# ============================================================

@app.post(
    "/analyze"
)
def analyze(
    request: AnalyzeRequest,
):

    try:

        result = analyze_url(
            request.url
        )

        return result

    except Exception as exc:

        platform = detect_platform(
            request.url
        )

        logger.exception(
            "Analyze failed."
        )

        return JSONResponse(

            status_code=422,

            content={

                "success": False,

                "platform": platform,

                "error": str(
                    exc
                ),

                "diagnostics": (
                    {
                        "yt_dlp_version": (
                            get_ytdlp_version()
                        ),
                        "bgutil_provider": (
                            BGUTIL_PROVIDER_URL
                        ),
                        "bgutil_reachable": (
                            is_bgutil_provider_reachable()
                        ),
                        "youtube_cookies_configured": (
                            bool(
                                YOUTUBE_COOKIES_BASE64
                            )
                        ),
                    }
                    if platform == "youtube"
                    else None
                ),

            },

        )


# ============================================================
# DOWNLOAD ENDPOINT
# ============================================================

@app.post(
    "/download"
)
def download(
    request: DownloadRequest,
):

    try:

        media_type = (
            request.media_type
            or "video"
        ).lower()

        if media_type not in {
            "video",
            "audio",
        }:

            return JSONResponse(

                status_code=400,

                content={

                    "success": False,

                    "error": (
                        "media_type must be "
                        "'video' or 'audio'."
                    ),

                },

            )

        result = download_media(

            url=request.url,

            format_id=request.format_id,

            media_type=media_type,

            audio_format=(
                request.audio_format
                or "mp3"
            ),

        )

        return result

    except Exception as exc:

        platform = detect_platform(
            request.url
        )

        logger.exception(
            "Download failed."
        )

        return JSONResponse(

            status_code=422,

            content={

                "success": False,

                "platform": platform,

                "error": str(
                    exc
                ),

                "diagnostics": (
                    {
                        "yt_dlp_version": (
                            get_ytdlp_version()
                        ),
                        "bgutil_provider": (
                            BGUTIL_PROVIDER_URL
                        ),
                        "bgutil_reachable": (
                            is_bgutil_provider_reachable()
                        ),
                    }
                    if platform == "youtube"
                    else None
                ),

            },

        )


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
    # Prevent path traversal.
    # --------------------------------------------------------

    safe_job_id = (
        Path(job_id).name
    )

    safe_filename = (
        Path(filename).name
    )

    if (
        safe_job_id != job_id
        or safe_filename != filename
    ):

        return JSONResponse(

            status_code=400,

            content={

                "success": False,

                "error": "Invalid file path.",

            },

        )

    file_path = (
        DOWNLOAD_DIR
        / safe_job_id
        / safe_filename
    )

    try:

        resolved_file = (
            file_path.resolve()
        )

        resolved_root = (
            DOWNLOAD_DIR.resolve()
        )

        resolved_file.relative_to(
            resolved_root
        )

    except Exception:

        return JSONResponse(

            status_code=403,

            content={

                "success": False,

                "error": "Access denied.",

            },

        )

    if not resolved_file.exists():

        return JSONResponse(

            status_code=404,

            content={

                "success": False,

                "error": "File not found.",

            },

        )

    if not resolved_file.is_file():

        return JSONResponse(

            status_code=404,

            content={

                "success": False,

                "error": "File not found.",

            },

        )

    return FileResponse(
        path=str(
            resolved_file
        ),
        filename=resolved_file.name,
        media_type="application/octet-stream",
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

        "status": "running",

        "endpoints": [

            "/health",

            "/version",

            "/youtube-status",

            "/analyze",

            "/download",

        ],

    }


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
        "Starting Media Downloader API"
    )

    logger.info(
        "Version: %s",
        APP_VERSION,
    )

    logger.info(
        "yt-dlp: %s",
        get_ytdlp_version(),
    )

    logger.info(
        "FFmpeg: %s",
        get_ffmpeg_path()
        or "NOT FOUND",
    )

    logger.info(
        "FFprobe: %s",
        get_ffprobe_path()
        or "NOT FOUND",
    )

    logger.info(
        "BGUTIL provider: %s",
        BGUTIL_PROVIDER_URL,
    )

    logger.info(
        "YouTube player client: mweb"
    )

    logger.info(
        "YouTube cookies configured: %s",
        bool(
            YOUTUBE_COOKIES_BASE64
        ),
    )

    # --------------------------------------------------------
    # Wait for the provider.
    # --------------------------------------------------------

    provider_ready = (
        wait_for_bgutil_provider()
    )

    logger.info(
        "BGUTIL provider ready: %s",
        provider_ready,
    )

    # --------------------------------------------------------
    # Scan for provider plugin.
    # --------------------------------------------------------

    plugin_files = (
        find_bgutil_plugin_files()
    )

    if plugin_files:

        logger.info(
            "BGUTIL-related plugin files found: %s",
            len(plugin_files),
        )

        for plugin_file in plugin_files[:10]:

            logger.info(
                "BGUTIL plugin file: %s",
                plugin_file,
            )

    else:

        logger.warning(
            "No BGUTIL plugin files were discovered "
            "during startup."
        )

    logger.info(
        "=================================================="
    )