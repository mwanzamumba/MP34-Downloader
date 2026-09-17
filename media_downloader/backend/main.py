import base64
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# APPLICATION
# ============================================================

APP_VERSION = "4.0.0"

app = FastAPI(
    title="Media Downloader API",
    version=APP_VERSION,
    description="Media analysis and download API powered by yt-dlp.",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("media-downloader")


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_DIR = BASE_DIR / "runtime"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CONFIGURATION
# ============================================================

FILE_TTL = int(
    os.getenv(
        "FILE_TTL",
        "1800",
    )
)


YOUTUBE_COOKIE_MODE = os.getenv(
    "YOUTUBE_COOKIE_MODE",
    "auto",
).lower()


POT_PROVIDER_URL = os.getenv(
    "POT_PROVIDER_URL",
    "http://127.0.0.1:4416",
)


BGUTIL_SERVER_HOME = os.getenv(
    "BGUTIL_SERVER_HOME",
    "/opt/bgutil-ytdlp-pot-provider/server",
)


# ============================================================
# COOKIE MANAGEMENT
# ============================================================

COOKIE_FILE = COOKIE_DIR / "youtube_cookies.txt"


def write_cookie_file() -> Path | None:
    """
    Creates the YouTube cookie file from Render environment variables.

    Supported variables:

        YOUTUBE_COOKIES
            Raw Netscape-format cookies.

        YOUTUBE_COOKIES_B64
            Base64 encoded Netscape-format cookies.

    The cookie contents are never returned by the API.
    """

    raw_cookies = os.getenv(
        "YOUTUBE_COOKIES",
        "",
    ).strip()

    encoded_cookies = os.getenv(
        "YOUTUBE_COOKIES_B64",
        "",
    ).strip()

    if encoded_cookies:

        try:

            raw_cookies = base64.b64decode(
                encoded_cookies
            ).decode(
                "utf-8"
            )

        except Exception as exc:

            logger.error(
                "Could not decode YOUTUBE_COOKIES_B64: %s",
                exc,
            )

            return None

    if not raw_cookies:

        return None

    try:

        COOKIE_FILE.write_text(
            raw_cookies,
            encoding="utf-8",
        )

        try:
            os.chmod(
                COOKIE_FILE,
                0o600,
            )
        except Exception:
            pass

        return COOKIE_FILE

    except Exception as exc:

        logger.error(
            "Could not write YouTube cookie file: %s",
            exc,
        )

        return None


def get_cookie_file() -> Path | None:

    if YOUTUBE_COOKIE_MODE == "never":

        return None

    return write_cookie_file()


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str) -> str:

    host = (
        urlparse(url)
        .netloc
        .lower()
        .replace(
            "www.",
            "",
        )
    )

    if (
        "youtube.com" in host
        or "youtu.be" in host
    ):
        return "youtube"

    if "tiktok.com" in host:
        return "tiktok"

    if "instagram.com" in host:
        return "instagram"

    if "facebook.com" in host:
        return "facebook"

    if "fb.watch" in host:
        return "facebook"

    if (
        "twitter.com" in host
        or "x.com" in host
    ):
        return "x"

    return "unknown"


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_youtube_url(url: str) -> str:

    parsed = urlparse(url)

    host = (
        parsed.netloc
        .lower()
        .replace(
            "www.",
            "",
        )
    )

    # --------------------------------------------------------
    # youtu.be/<id>
    # --------------------------------------------------------

    if host == "youtu.be":

        video_id = (
            parsed.path
            .strip("/")
        )

        if video_id:

            return (
                "https://www.youtube.com/watch?v="
                + video_id
            )

    # --------------------------------------------------------
    # youtube.com/shorts/<id>
    # --------------------------------------------------------

    if host in {
        "youtube.com",
        "m.youtube.com",
    }:

        match = re.search(
            r"/shorts/([^/?]+)",
            parsed.path,
        )

        if match:

            video_id = match.group(1)

            return (
                "https://www.youtube.com/watch?v="
                + video_id
            )

    return url


# ============================================================
# URL VALIDATION
# ============================================================

def validate_url(url: str) -> str:

    if not isinstance(
        url,
        str,
    ):

        raise HTTPException(
            status_code=400,
            detail="URL must be a string.",
        )

    url = url.strip()

    if not url:

        raise HTTPException(
            status_code=400,
            detail="URL is required.",
        )

    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:

        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are supported.",
        )

    platform = detect_platform(url)

    if platform == "unknown":

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported platform. "
                "Supported platforms: YouTube, TikTok, "
                "Instagram, Facebook and X."
            ),
        )

    if platform == "youtube":

        url = normalize_youtube_url(
            url
        )

    return url


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_string(
    value: Any,
) -> str | None:

    if value is None:

        return None

    try:

        return str(value)

    except Exception:

        return None


def safe_int(
    value: Any,
) -> int | None:

    if value is None:

        return None

    try:

        return int(value)

    except Exception:

        return None


def safe_float(
    value: Any,
) -> float | None:

    if value is None:

        return None

    try:

        return float(value)

    except Exception:

        return None


# ============================================================
# PO TOKEN CONFIGURATION
# ============================================================

def get_youtube_extractor_args() -> dict:

    """
    Current yt-dlp supports automatic PO-token fetching
    through provider plugins.

    We use the BgUtils provider over localhost.

    `fetch_pot=auto` means yt-dlp asks the provider when
    a PO token is actually required rather than generating
    one unnecessarily for every request.
    """

    return {
        "youtube": {
            "player_client": [
                "default",
                "web_embedded",
                "mweb",
            ],
            "fetch_pot": [
                "auto",
            ],
            "pot_trace": [
                "false",
            ],
            "po_token": [],
        },
        "youtubepot-bgutilhttp": {
            "base_url": [
                POT_PROVIDER_URL,
            ],
        },
    }


# ============================================================
# BASE YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    download: bool = False,
    output_template: str | None = None,
    use_cookies: bool = False,
) -> dict:

    options: dict = {

        # ----------------------------------------------------
        # General
        # ----------------------------------------------------

        "noplaylist": True,

        "quiet": True,

        "no_warnings": True,

        "ignoreerrors": False,

        "retries": 3,

        "fragment_retries": 3,

        "continuedl": True,

        "overwrites": True,

        "socket_timeout": 30,

        # ----------------------------------------------------
        # Network
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

        # ----------------------------------------------------
        # Filename safety
        # ----------------------------------------------------

        "restrictfilenames": True,

        # ----------------------------------------------------
        # YouTube PO-token architecture
        # ----------------------------------------------------

        "extractor_args": (
            get_youtube_extractor_args()
        ),
    }


    # ========================================================
    # OPTIONAL COOKIES
    # ========================================================

    if use_cookies:

        cookie_file = get_cookie_file()

        if cookie_file:

            options["cookiefile"] = str(
                cookie_file
            )

            logger.info(
                "YouTube cookie fallback enabled."
            )


    # ========================================================
    # OUTPUT
    # ========================================================

    if output_template:

        options["outtmpl"] = output_template


    # ========================================================
    # DOWNLOAD SETTINGS
    # ========================================================

    if download:

        options.update(
            {
                "merge_output_format": "mp4",

                "postprocessors": [],

            }
        )


    return options


# ============================================================
# COOKIE FALLBACK EXTRACTION
# ============================================================

def extract_info_with_fallback(
    url: str,
    download: bool = False,
    output_template: str | None = None,
) -> tuple[dict, bool]:

    """
    Extraction strategy:

        1. Try normal extraction without cookies.
        2. If YouTube extraction fails and cookies exist,
           retry with cookies.

    This prevents a stale cookie file from breaking every
    public YouTube request.
    """

    platform = detect_platform(url)

    attempts: list[bool] = [
        False,
    ]

    if (
        platform == "youtube"
        and YOUTUBE_COOKIE_MODE != "never"
    ):

        if (
            os.getenv("YOUTUBE_COOKIES", "").strip()
            or os.getenv("YOUTUBE_COOKIES_B64", "").strip()
        ):

            attempts.append(
                True
            )


    last_error: Exception | None = None


    for use_cookies in attempts:

        try:

            options = get_ytdlp_options(
                download=download,
                output_template=output_template,
                use_cookies=use_cookies,
            )

            logger.info(
                "yt-dlp extraction: platform=%s cookies=%s",
                platform,
                use_cookies,
            )

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False,
                )

                if not info:

                    raise RuntimeError(
                        "yt-dlp returned no information."
                    )

                return info, use_cookies

        except Exception as exc:

            last_error = exc

            logger.warning(
                "yt-dlp extraction failed. "
                "cookies=%s error=%s",
                use_cookies,
                exc,
            )

            continue


    raise RuntimeError(
        str(last_error)
        if last_error
        else "Unable to extract media information."
    )


# ============================================================
# PUBLIC FORMAT CONVERSION
# ============================================================

def format_to_public(
    fmt: Any,
) -> dict | None:

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


    format_id = fmt.get(
        "format_id"
    )

    if format_id is None:

        return None


    return {
        "format_id": safe_string(
            format_id
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

def choose_recommended_video(
    formats: list[dict],
) -> dict | None:

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
            safe_int(
                fmt.get("height")
            )
            or 0
        )

        width = (
            safe_int(
                fmt.get("width")
            )
            or 0
        )

        fps = (
            safe_float(
                fmt.get("fps")
            )
            or 0
        )

        has_audio = (
            fmt.get("acodec")
            not in (
                None,
                "none",
            )
        )

        candidates.append(
            (
                has_audio,
                height,
                width,
                fps,
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
            item[3],
        ),
        reverse=True,
    )


    return candidates[0][4]


def choose_recommended_audio(
    formats: list[dict],
) -> dict | None:

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

        vcodec = fmt.get(
            "vcodec"
        )

        if (
            not acodec
            or acodec == "none"
        ):

            continue


        if (
            vcodec
            and vcodec != "none"
        ):

            continue


        abr = (
            safe_float(
                fmt.get("abr")
            )
            or 0
        )


        candidates.append(
            (
                abr,
                fmt,
            )
        )


    if not candidates:

        return None


    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )


    return candidates[0][1]


def choose_audio_for_video(
    formats: list[dict],
    selected_video: dict,
) -> dict | None:

    """
    Finds an audio-only stream to pair with a video-only
    stream.

    We prefer higher bitrate audio.
    """

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

        acodec = fmt.get(
            "acodec"
        )


        if (
            not acodec
            or acodec == "none"
        ):

            continue


        if (
            vcodec
            and vcodec != "none"
        ):

            continue


        abr = (
            safe_float(
                fmt.get("abr")
            )
            or 0
        )


        filesize = (
            safe_int(
                fmt.get("filesize")
            )
            or safe_int(
                fmt.get("filesize_approx")
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
# CLEANUP
# ============================================================

def cleanup_old_downloads():

    now = time.time()


    if not DOWNLOAD_DIR.exists():

        return


    for job_dir in DOWNLOAD_DIR.iterdir():

        try:

            if not job_dir.is_dir():

                continue


            age = (
                now
                - job_dir.stat().st_mtime
            )


            if age > FILE_TTL:

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True,
                )

                logger.info(
                    "Removed expired job: %s",
                    job_dir.name,
                )

        except Exception as exc:

            logger.warning(
                "Cleanup error: %s",
                exc,
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
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "success": True,
        "name": "Media Downloader API",
        "version": APP_VERSION,
        "yt_dlp_version": yt_dlp.version.__version__,
        "po_token_provider": True,
        "cookie_fallback": (
            YOUTUBE_COOKIE_MODE != "never"
        ),
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    cleanup_old_downloads()

    return {
        "status": "ok",
        "version": APP_VERSION,
        "yt_dlp_version": yt_dlp.version.__version__,
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {
        "app_version": APP_VERSION,
        "yt_dlp_version": yt_dlp.version.__version__,
        "python_version": os.sys.version,
        "po_token_provider": True,
        "po_token_provider_url": POT_PROVIDER_URL,
        "cookie_mode": YOUTUBE_COOKIE_MODE,
        "cookie_configured": bool(
            os.getenv("YOUTUBE_COOKIES", "").strip()
            or os.getenv("YOUTUBE_COOKIES_B64", "").strip()
        ),
    }


# ============================================================
# DEBUG RUNTIME
# ============================================================

@app.get("/debug-runtime")
def debug_runtime():

    node_path = shutil.which(
        "node"
    )

    python_path = shutil.which(
        "python"
    )

    return {
        "python_path": python_path,
        "node_path": node_path,
        "yt_dlp_version": yt_dlp.version.__version__,
        "po_token_provider_url": POT_PROVIDER_URL,
        "bgutil_server_home": BGUTIL_SERVER_HOME,
    }


# ============================================================
# DEBUG FFMPEG
# ============================================================

@app.get("/debug-ffmpeg")
def debug_ffmpeg():

    ffmpeg_path = shutil.which(
        "ffmpeg"
    )

    ffprobe_path = shutil.which(
        "ffprobe"
    )


    ffmpeg_version = None


    if ffmpeg_path:

        try:

            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-version",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            ffmpeg_version = (
                result.stdout
                .splitlines()[0]
                if result.stdout
                else None
            )

        except Exception:
            pass


    return {
        "ffmpeg_found": bool(
            ffmpeg_path
        ),

        "ffmpeg_path": ffmpeg_path,

        "ffprobe_found": bool(
            ffprobe_path
        ),

        "ffprobe_path": ffprobe_path,

        "ffmpeg_version": ffmpeg_version,
    }


# ============================================================
# DEBUG PO TOKEN PROVIDER
# ============================================================

@app.get("/debug-pot")
def debug_pot():

    provider_path = (
        Path(BGUTIL_SERVER_HOME)
        / "build"
        / "main.js"
    )


    provider_running = False


    try:

        import urllib.request

        with urllib.request.urlopen(
            POT_PROVIDER_URL,
            timeout=3,
        ) as response:

            provider_running = (
                response.status
                < 500
            )

    except Exception:

        provider_running = False


    return {
        "provider_url": POT_PROVIDER_URL,
        "provider_running": provider_running,
        "server_home": BGUTIL_SERVER_HOME,
        "provider_script_exists": provider_path.exists(),
    }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(
    request: AnalyzeRequest,
):

    cleanup_old_downloads()


    url = validate_url(
        request.url
    )


    platform = detect_platform(
        url
    )


    try:

        info, used_cookies = (
            extract_info_with_fallback(
                url,
                download=False,
            )
        )

    except Exception as exc:

        logger.exception(
            "Analyze failed."
        )

        raise HTTPException(
            status_code=422,
            detail=(
                "Unable to analyze this media URL. "
                + str(exc)
            ),
        )


    raw_formats = info.get(
        "formats",
        [],
    )


    public_formats = []


    for fmt in raw_formats:

        converted = (
            format_to_public(
                fmt
            )
        )

        if converted:

            public_formats.append(
                converted
            )


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


    title = (
        info.get("title")
        or "Untitled"
    )


    thumbnail = info.get(
        "thumbnail"
    )


    duration = safe_float(
        info.get("duration")
    )


    return {
        "success": True,

        "platform": platform,

        "title": title,

        "thumbnail": thumbnail,

        "duration": duration,

        "webpage_url": (
            info.get("webpage_url")
            or url
        ),

        "used_cookies": used_cookies,

        "formats": public_formats,

        "video": (
            format_to_public(
                recommended_video
            )
            if recommended_video
            else None
        ),

        "audio": (
            format_to_public(
                recommended_audio
            )
            if recommended_audio
            else None
        ),
    }


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
def download(
    request: DownloadRequest,
):

    cleanup_old_downloads()


    url = validate_url(
        request.url
    )


    platform = detect_platform(
        url
    )


    format_id = (
        request.format_id
        .strip()
    )


    if not format_id:

        raise HTTPException(
            status_code=400,
            detail="format_id is required.",
        )


    media_type = (
        request.media_type
        .lower()
        .strip()
    )


    if media_type not in {
        "video",
        "audio",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "media_type must be "
                "'video' or 'audio'."
            ),
        )


    job_id = uuid.uuid4().hex


    job_dir = (
        DOWNLOAD_DIR
        / job_id
    )


    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    output_template = str(
        job_dir
        / "%(title).150s.%(ext)s"
    )


    # ========================================================
    # RE-EXTRACT
    # ========================================================

    try:

        info, used_cookies = (
            extract_info_with_fallback(
                url,
                download=False,
            )
        )

    except Exception as exc:

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=422,
            detail=(
                "Unable to prepare media download. "
                + str(exc)
            ),
        )


    raw_formats = info.get(
        "formats",
        [],
    )


    selected_format = None


    for fmt in raw_formats:

        if not isinstance(
            fmt,
            dict,
        ):

            continue


        if str(
            fmt.get("format_id")
        ) == format_id:

            selected_format = fmt

            break


    if selected_format is None:

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "The requested format is no longer "
                "available. Please analyze the URL again."
            ),
        )


    # ========================================================
    # AUDIO DOWNLOAD
    # ========================================================

    if media_type == "audio":

        acodec = selected_format.get(
            "acodec"
        )


        if (
            not acodec
            or acodec == "none"
        ):

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected format does not "
                    "contain audio."
                ),
            )


        output_format = (
            request.audio_format
            or "mp3"
        ).lower()


        allowed_audio_formats = {
            "mp3",
            "m4a",
            "wav",
            "opus",
            "flac",
        }


        if output_format not in (
            allowed_audio_formats
        ):

            output_format = "mp3"


        options = get_ytdlp_options(
            download=True,
            output_template=output_template,
            use_cookies=used_cookies,
        )


        options["format"] = format_id


        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": output_format,
                "preferredquality": (
                    "192"
                    if output_format == "mp3"
                    else None
                ),
            }
        ]


        try:

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                ydl.download(
                    [url]
                )

        except Exception as exc:

            logger.exception(
                "Audio download failed."
            )

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=422,
                detail=(
                    "Audio download failed. "
                    + str(exc)
                ),
            )


    # ========================================================
    # VIDEO DOWNLOAD
    # ========================================================

    else:

        vcodec = selected_format.get(
            "vcodec"
        )

        if (
            not vcodec
            or vcodec == "none"
        ):

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected format is not "
                    "a video stream."
                ),
            )


        acodec = selected_format.get(
            "acodec"
        )


        has_audio = (
            acodec is not None
            and acodec != "none"
        )


        options = get_ytdlp_options(
            download=True,
            output_template=output_template,
            use_cookies=used_cookies,
        )


        # ----------------------------------------------------
        # Progressive video + audio
        # ----------------------------------------------------

        if has_audio:

            options["format"] = (
                format_id
            )

            logger.info(
                "Downloading progressive video: %s",
                format_id,
            )


        # ----------------------------------------------------
        # Video-only DASH
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

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "The selected video stream "
                        "does not contain audio and "
                        "no compatible audio stream "
                        "was found."
                    ),
                )


            audio_id = str(
                audio_format.get(
                    "format_id"
                )
            )


            options["format"] = (
                f"{format_id}+{audio_id}"
            )


            options[
                "merge_output_format"
            ] = "mp4"


            logger.info(
                "Merging video=%s with audio=%s",
                format_id,
                audio_id,
            )


        try:

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                ydl.download(
                    [url]
                )

        except Exception as exc:

            logger.exception(
                "Video download failed."
            )

            shutil.rmtree(
                job_dir,
                ignore_errors=True,
            )

            raise HTTPException(
                status_code=422,
                detail=(
                    "Video download failed. "
                    + str(exc)
                ),
            )


    # ========================================================
    # FIND OUTPUT
    # ========================================================

    output_files = []


    for path in job_dir.iterdir():

        if not path.is_file():

            continue


        if path.name.endswith(
            ".part"
        ):

            continue


        if path.name.endswith(
            ".ytdl"
        ):

            continue


        output_files.append(
            path
        )


    if not output_files:

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "yt-dlp completed but no output "
                "file was created."
            ),
        )


    output_files.sort(
        key=lambda p: p.stat().st_size,
        reverse=True,
    )


    output_file = output_files[0]


    file_size = (
        output_file.stat().st_size
    )


    filename = output_file.name


    return {
        "success": True,

        "job_id": job_id,

        "filename": filename,

        "downloadUrl": (
            f"/files/"
            f"{job_id}/"
            f"{filename}"
        ),

        "media_type": media_type,

        "format_id": format_id,

        "size": file_size,

        "platform": platform,

        "used_cookies": used_cookies,
    }


# ============================================================
# FILE DOWNLOAD
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

    safe_job_id = Path(
        job_id
    ).name

    safe_filename = Path(
        filename
    ).name


    file_path = (
        DOWNLOAD_DIR
        / safe_job_id
        / safe_filename
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


    extension = (
        file_path
        .suffix
        .lower()
    )


    media_types = {

        ".mp4": "video/mp4",

        ".webm": "video/webm",

        ".mkv": "video/x-matroska",

        ".mov": "video/quicktime",

        ".mp3": "audio/mpeg",

        ".m4a": "audio/mp4",

        ".wav": "audio/wav",

        ".opus": "audio/ogg",

        ".flac": "audio/flac",
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
        "============================================"
    )

    logger.info(
        "Media Downloader API starting..."
    )

    logger.info(
        "App version: %s",
        APP_VERSION,
    )

    logger.info(
        "yt-dlp version: %s",
        yt_dlp.version.__version__,
    )

    logger.info(
        "PO provider: %s",
        POT_PROVIDER_URL,
    )

    logger.info(
        "Cookie mode: %s",
        YOUTUBE_COOKIE_MODE,
    )

    logger.info(
        "FFmpeg: %s",
        shutil.which(
            "ffmpeg"
        ),
    )

    logger.info(
        "FFprobe: %s",
        shutil.which(
            "ffprobe"
        ),
    )

    logger.info(
        "Node.js: %s",
        shutil.which(
            "node"
        ),
    )

    logger.info(
        "============================================"
    )