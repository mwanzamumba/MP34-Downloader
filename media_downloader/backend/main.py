import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yt_dlp

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl


app = FastAPI(
    title="Media Downloader API",
    version="2.4.0",
    description="Media analysis and downloading API powered by yt-dlp.",
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
# DIRECTORIES / SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

FILE_TTL = int(os.getenv("FILE_TTL", "1800"))

# Cookie remains configured in Render, but this version
# deliberately does NOT use it for YouTube extraction.
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "").strip()


# ============================================================
# REQUEST MODELS
# ============================================================

class AnalyzeRequest(BaseModel):
    url: HttpUrl


class DownloadRequest(BaseModel):
    url: HttpUrl
    format_id: Optional[str] = None
    media_type: str = "video"
    audio_format: str = "mp3"


# ============================================================
# SUPPORTED PLATFORMS
# ============================================================

SUPPORTED_PLATFORMS = {
    "youtube": [
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtu.be",
    ],
    "facebook": [
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "fb.watch",
    ],
    "instagram": [
        "instagram.com",
        "www.instagram.com",
    ],
    "tiktok": [
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
    ],
    "x": [
        "twitter.com",
        "www.twitter.com",
        "x.com",
        "www.x.com",
    ],
}


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str) -> str:
    parsed = urlparse(url)

    host = parsed.netloc.lower().split(":")[0]

    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return platform

    return "unknown"


def platform_display_name(platform: str) -> str:
    names = {
        "youtube": "YouTube",
        "facebook": "Facebook",
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "x": "X",
        "unknown": "Unknown",
    }

    return names.get(platform, platform.title())


def validate_url(url: str):
    platform = detect_platform(url)

    if platform == "unknown":
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported media platform. "
                "Supported platforms are YouTube, "
                "Facebook, Instagram, TikTok and X."
            ),
        )

    return platform


# ============================================================
# COOKIE FUNCTIONS
# ============================================================

def create_cookie_file() -> Optional[str]:
    """
    Creates a temporary cookie file.

    NOTE:
    This function is kept for future use, but the current
    diagnostic version deliberately does NOT use cookies
    for YouTube extraction.
    """

    if not YOUTUBE_COOKIES:
        return None

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )

    try:
        temp_file.write(YOUTUBE_COOKIES)
        temp_file.flush()
        temp_file.close()

        return temp_file.name

    except Exception:

        try:
            temp_file.close()
        except Exception:
            pass

        try:
            os.unlink(temp_file.name)
        except Exception:
            pass

        raise


def remove_cookie_file(cookie_file: Optional[str]):
    if not cookie_file:
        return

    try:
        os.unlink(cookie_file)
    except Exception:
        pass


# ============================================================
# SYSTEM CHECKS
# ============================================================

def executable_available(name: str) -> bool:
    return shutil.which(name) is not None


def ffmpeg_available() -> bool:
    return executable_available("ffmpeg")


def ffprobe_available() -> bool:
    return executable_available("ffprobe")


def node_available() -> bool:
    return executable_available("node")


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    skip_download: bool = True,
    cookie_file: Optional[str] = None,
):
    options = {
        "quiet": True,
        "no_warnings": False,

        # VERY IMPORTANT
        # Prevent yt-dlp from loading external config files
        # that may force a format.
        "ignoreconfig": True,

        "noplaylist": True,

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        # Use Node for YouTube JS challenge solving.
        "js_runtimes": {
            "node": {}
        },

        "skip_download": skip_download,
    }

    if cookie_file:
        options["cookiefile"] = cookie_file

    return options


# ============================================================
# FORMAT HELPERS
# ============================================================

def has_video(fmt: dict) -> bool:
    codec = fmt.get("vcodec")

    return (
        codec is not None
        and codec != "none"
    )


def has_audio(fmt: dict) -> bool:
    codec = fmt.get("acodec")

    return (
        codec is not None
        and codec != "none"
    )


def is_progressive(fmt: dict) -> bool:
    return (
        has_video(fmt)
        and has_audio(fmt)
    )


def is_storyboard(fmt: dict) -> bool:
    return str(
        fmt.get("format_id", "")
    ).startswith("sb")


def is_audio_only(fmt: dict) -> bool:
    return (
        has_audio(fmt)
        and not has_video(fmt)
    )


def is_video_only(fmt: dict) -> bool:
    return (
        has_video(fmt)
        and not has_audio(fmt)
    )


def numeric(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def get_filesize(fmt: dict):

    size = fmt.get("filesize")

    if size:
        return int(size)

    approx = fmt.get("filesize_approx")

    if approx:
        return int(approx)

    return None


def quality_score(fmt: dict):

    height = numeric(
        fmt.get("height")
    )

    width = numeric(
        fmt.get("width")
    )

    fps = numeric(
        fmt.get("fps")
    )

    bitrate = numeric(
        fmt.get("tbr")
    )

    return (
        height * 1_000_000
        + width * 1_000
        + fps * 10
        + bitrate
    )


# ============================================================
# PUBLIC FORMAT REPRESENTATION
# ============================================================

def format_to_public(
    fmt: dict,
    format_type: str,
):

    video = has_video(fmt)
    audio = has_audio(fmt)

    return {
        "format_id": str(
            fmt.get("format_id", "")
        ),

        "type": format_type,

        "ext": fmt.get("ext"),

        "format_note": fmt.get(
            "format_note"
        ),

        "width": fmt.get("width"),

        "height": fmt.get("height"),

        "resolution": fmt.get(
            "resolution"
        ),

        "fps": fmt.get("fps"),

        "vcodec": fmt.get("vcodec"),

        "acodec": fmt.get("acodec"),

        "abr": fmt.get("abr"),

        "vbr": fmt.get("vbr"),

        "tbr": fmt.get("tbr"),

        "filesize": get_filesize(fmt),

        "has_video": video,

        "has_audio": audio,

        "progressive": (
            video and audio
        ),
    }


# ============================================================
# ERROR CLEANING
# ============================================================

def clean_yt_error(
    error: Exception,
) -> str:

    message = str(error)

    if not message:
        return (
            "yt-dlp failed without "
            "returning an error message."
        )

    return message[-3000:]


# ============================================================
# EXTRACT INFORMATION
# ============================================================

def extract_info(url: str):

    """
    Extract media information.

    IMPORTANT:
    The diagnostic version deliberately does NOT use
    YOUTUBE_COOKIES.

    This allows us to determine whether the cookies are
    causing YouTube to return unusable formats.
    """

    cookie_file = None

    try:

        platform = detect_platform(url)

        # ----------------------------------------------------
        # DIAGNOSTIC CHANGE
        #
        # Do NOT create/use the YouTube cookie file.
        # ----------------------------------------------------

        options = get_ytdlp_options(
            skip_download=True,
            cookie_file=None,
        )

        print(
            f"[EXTRACT] Platform: {platform}"
        )

        print(
            "[EXTRACT] YouTube cookies: DISABLED "
            "for diagnostic test"
        )

        print(
            f"[EXTRACT] URL: {url}"
        )

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        return info

    finally:

        remove_cookie_file(
            cookie_file
        )


# ============================================================
# CHOOSE VIDEO FORMAT
# ============================================================

def choose_video_format(
    info: dict,
    requested_id: Optional[str] = None,
):

    formats = info.get("formats") or []

    usable = [
        fmt
        for fmt in formats
        if (
            not is_storyboard(fmt)
            and has_video(fmt)
        )
    ]

    # --------------------------------------------------------
    # Requested format
    # --------------------------------------------------------

    if requested_id:

        for fmt in usable:

            if str(
                fmt.get("format_id")
            ) == str(requested_id):

                return fmt

    # --------------------------------------------------------
    # Prefer MP4 progressive
    # --------------------------------------------------------

    progressive_mp4 = [
        fmt
        for fmt in usable
        if (
            is_progressive(fmt)
            and fmt.get("ext") == "mp4"
        )
    ]

    if progressive_mp4:

        return max(
            progressive_mp4,
            key=quality_score,
        )

    # --------------------------------------------------------
    # Any progressive format
    # --------------------------------------------------------

    progressive = [
        fmt
        for fmt in usable
        if is_progressive(fmt)
    ]

    if progressive:

        return max(
            progressive,
            key=quality_score,
        )

    # --------------------------------------------------------
    # Video-only
    # --------------------------------------------------------

    video_only = [
        fmt
        for fmt in usable
        if is_video_only(fmt)
    ]

    if video_only:

        return max(
            video_only,
            key=quality_score,
        )

    return None


# ============================================================
# CHOOSE AUDIO FORMAT
# ============================================================

def choose_audio_format(
    info: dict,
    requested_id: Optional[str] = None,
):

    formats = info.get("formats") or []

    audio_formats = [
        fmt
        for fmt in formats
        if (
            not is_storyboard(fmt)
            and is_audio_only(fmt)
        )
    ]

    # --------------------------------------------------------
    # Requested format
    # --------------------------------------------------------

    if requested_id:

        for fmt in formats:

            if str(
                fmt.get("format_id")
            ) == str(requested_id):

                if has_audio(fmt):

                    return fmt

    # --------------------------------------------------------
    # Prefer M4A
    # --------------------------------------------------------

    m4a_formats = [
        fmt
        for fmt in audio_formats
        if fmt.get("ext") == "m4a"
    ]

    if m4a_formats:

        return max(
            m4a_formats,
            key=lambda x: numeric(
                x.get("abr")
            ),
        )

    # --------------------------------------------------------
    # Any audio-only
    # --------------------------------------------------------

    if audio_formats:

        return max(
            audio_formats,
            key=lambda x: numeric(
                x.get("abr")
            ),
        )

    # --------------------------------------------------------
    # Fall back to progressive
    # --------------------------------------------------------

    progressive = [
        fmt
        for fmt in formats
        if (
            not is_storyboard(fmt)
            and is_progressive(fmt)
        )
    ]

    if progressive:

        return max(
            progressive,
            key=quality_score,
        )

    return None


# ============================================================
# BUILD ANALYSIS RESPONSE
# ============================================================

def build_analysis(info: dict):

    formats = info.get("formats") or []

    video_formats = []

    audio_formats = []

    progressive_formats = []

    for fmt in formats:

        if is_storyboard(fmt):
            continue

        video = has_video(fmt)

        audio = has_audio(fmt)

        # Video
        if video:

            video_formats.append(
                format_to_public(
                    fmt,
                    "video",
                )
            )

        # Audio only
        if audio and not video:

            audio_formats.append(
                format_to_public(
                    fmt,
                    "audio",
                )
            )

        # Video + Audio
        if video and audio:

            progressive_formats.append(
                format_to_public(
                    fmt,
                    "progressive",
                )
            )

    # --------------------------------------------------------
    # Sort formats
    # --------------------------------------------------------

    video_formats.sort(
        key=lambda x: (
            x.get("height") or 0,
            x.get("width") or 0,
        ),
        reverse=True,
    )

    audio_formats.sort(
        key=lambda x: (
            x.get("abr") or 0
        ),
        reverse=True,
    )

    progressive_formats.sort(
        key=lambda x: (
            x.get("height") or 0,
            x.get("width") or 0,
        ),
        reverse=True,
    )

    recommended_video = choose_video_format(
        info
    )

    recommended_audio = choose_audio_format(
        info
    )

    return {
        "success": True,

        "title": info.get(
            "title"
        ) or "Unknown title",

        "platform": platform_display_name(
            detect_platform(
                info.get(
                    "webpage_url",
                    "",
                )
            )
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

        "channel": info.get(
            "channel"
        ),

        "has_video": (
            len(video_formats) > 0
        ),

        "has_audio": (
            len(audio_formats) > 0
            or len(progressive_formats) > 0
        ),

        "recommended_video": (
            format_to_public(
                recommended_video,
                "video",
            )
            if recommended_video
            else None
        ),

        "recommended_audio": (
            format_to_public(
                recommended_audio,
                "audio",
            )
            if recommended_audio
            else None
        ),

        "video_formats": (
            video_formats
        ),

        "audio_formats": (
            audio_formats
        ),

        "progressive_formats": (
            progressive_formats
        ),
    }


# ============================================================
# SAFE FILE NAME
# ============================================================

def safe_filename(name: str) -> str:

    name = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        name,
    )

    name = name.strip()

    if not name:

        name = "download"

    return name[:180]


# ============================================================
# CLEAN OLD DOWNLOADS
# ============================================================

def cleanup_old_downloads():

    if not DOWNLOAD_DIR.exists():
        return

    current_time = os.path.getmtime(
        DOWNLOAD_DIR
    )

    for item in DOWNLOAD_DIR.iterdir():

        try:

            if item.is_dir():

                age = (
                    current_time
                    - item.stat().st_mtime
                )

                if age > FILE_TTL:

                    shutil.rmtree(
                        item,
                        ignore_errors=True,
                    )

        except Exception:

            pass


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "name": "Media Downloader API",

        "version": "2.4.0",

        "status": "online",

        "youtube_cookie_test": (
            "disabled"
        ),

        "supported_platforms": [
            "YouTube",
            "Facebook",
            "Instagram",
            "TikTok",
            "X",
        ],
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    try:

        yt_dlp_version = (
            yt_dlp.version.__version__
        )

    except Exception:

        yt_dlp_version = "unknown"

    return {

        "api_version": "2.4.0",

        "yt_dlp": yt_dlp_version,

        "node_available": (
            node_available()
        ),

        "ffmpeg_available": (
            ffmpeg_available()
        ),

        "ffprobe_available": (
            ffprobe_available()
        ),

        "cookies_configured": (
            bool(YOUTUBE_COOKIES)
        ),

        "cookies_length": (
            len(YOUTUBE_COOKIES)
        ),

        "youtube_cookies_used": False,
    }


# ============================================================
# DEBUG YOUTUBE
# ============================================================

@app.get("/debug-youtube")
def debug_youtube():

    test_url = (
        "https://www.youtube.com/watch?v=L5aSgl7HKBA"
    )

    try:

        info = extract_info(
            test_url
        )

        formats = (
            info.get("formats")
            or []
        )

        usable_formats = []

        for fmt in formats:

            if is_storyboard(fmt):
                continue

            if has_video(fmt) or has_audio(fmt):

                usable_formats.append(
                    format_to_public(
                        fmt,
                        (
                            "progressive"
                            if is_progressive(fmt)
                            else
                            "video"
                            if has_video(fmt)
                            else
                            "audio"
                        ),
                    )
                )

        return {

            "success": True,

            "title": info.get(
                "title"
            ),

            "platform": detect_platform(
                test_url
            ),

            "cookies_configured": (
                bool(YOUTUBE_COOKIES)
            ),

            "youtube_cookies_used": False,

            "node_available": (
                node_available()
            ),

            "ffmpeg_available": (
                ffmpeg_available()
            ),

            "ffprobe_available": (
                ffprobe_available()
            ),

            "format_count": len(
                formats
            ),

            "usable_format_count": len(
                usable_formats
            ),

            "formats": usable_formats,
        }

    except Exception as error:

        return {

            "success": False,

            "error": clean_yt_error(
                error
            ),

            "cookies_configured": (
                bool(YOUTUBE_COOKIES)
            ),

            "youtube_cookies_used": False,

            "node_available": (
                node_available()
            ),

            "ffmpeg_available": (
                ffmpeg_available()
            ),

            "ffprobe_available": (
                ffprobe_available()
            ),
        }


# ============================================================
# DEBUG FORMATS
# ============================================================

@app.post("/debug-formats")
def debug_formats(
    request: AnalyzeRequest
):

    url = str(request.url)

    validate_url(url)

    try:

        info = extract_info(
            url
        )

        formats = []

        for fmt in (
            info.get("formats")
            or []
        ):

            if is_storyboard(fmt):
                continue

            if is_progressive(fmt):

                format_type = (
                    "progressive"
                )

            elif has_video(fmt):

                format_type = "video"

            elif has_audio(fmt):

                format_type = "audio"

            else:

                continue

            formats.append(
                format_to_public(
                    fmt,
                    format_type,
                )
            )

        return {

            "success": True,

            "title": info.get(
                "title"
            ),

            "platform": platform_display_name(
                detect_platform(url)
            ),

            "format_count": len(
                formats
            ),

            "formats": formats,
        }

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=clean_yt_error(
                error
            ),
        )


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(
    request: AnalyzeRequest
):

    url = str(request.url)

    validate_url(url)

    try:

        info = extract_info(
            url
        )

        return build_analysis(
            info
        )

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=clean_yt_error(
                error
            ),
        )


# ============================================================
# VALIDATE STREAMS
# ============================================================

@app.post("/validate-streams")
def validate_streams(
    request: AnalyzeRequest
):

    url = str(request.url)

    validate_url(url)

    try:

        info = extract_info(
            url
        )

        video = choose_video_format(
            info
        )

        audio = choose_audio_format(
            info
        )

        return {

            "success": True,

            "title": info.get(
                "title"
            ),

            "video": (
                format_to_public(
                    video,
                    "video",
                )
                if video
                else None
            ),

            "audio": (
                format_to_public(
                    audio,
                    "audio",
                )
                if audio
                else None
            ),

            "ffmpeg_available": (
                ffmpeg_available()
            ),

            "node_available": (
                node_available()
            ),

            "youtube_cookies_used": False,
        }

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=clean_yt_error(
                error
            ),
        )


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
def download(
    request: DownloadRequest
):

    url = str(request.url)

    platform = validate_url(
        url
    )

    media_type = (
        request.media_type.lower()
    )

    if media_type not in [
        "video",
        "audio",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "media_type must be either "
                "'video' or 'audio'."
            ),
        )

    # --------------------------------------------------------
    # Audio requires FFmpeg
    # --------------------------------------------------------

    if (
        media_type == "audio"
        and not ffmpeg_available()
    ):

        raise HTTPException(
            status_code=500,
            detail=(
                "FFmpeg is required for "
                "audio extraction but is "
                "not available on the server."
            ),
        )

    cleanup_old_downloads()

    job_id = uuid.uuid4().hex

    job_dir = (
        DOWNLOAD_DIR
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # No YouTube cookies for this diagnostic
    # --------------------------------------------------------

    cookie_file = None

    try:

        info_options = get_ytdlp_options(
            skip_download=True,
            cookie_file=None,
        )

        with yt_dlp.YoutubeDL(
            info_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

        title = safe_filename(
            info.get("title")
            or "download"
        )

        # ====================================================
        # VIDEO
        # ====================================================

        if media_type == "video":

            selected = choose_video_format(
                info,
                request.format_id,
            )

            if not selected:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No downloadable "
                        "video format was found."
                    ),
                )

            selected_id = selected.get(
                "format_id"
            )

            # ------------------------------------------------
            # Progressive format
            # ------------------------------------------------

            if is_progressive(
                selected
            ):

                format_selector = str(
                    selected_id
                )

            # ------------------------------------------------
            # Video-only format
            # ------------------------------------------------

            else:

                format_selector = (
                    f"{selected_id}+bestaudio/best"
                )

            output_template = str(
                job_dir
                / f"{title}.%(ext)s"
            )

            download_options = {

                "quiet": False,

                "no_warnings": False,

                "ignoreconfig": True,

                "noplaylist": True,

                "socket_timeout": 60,

                "retries": 5,

                "fragment_retries": 5,

                "js_runtimes": {
                    "node": {}
                },

                "format": format_selector,

                "outtmpl": output_template,

                "merge_output_format": "mp4",

                "skip_download": False,
            }

        # ====================================================
        # AUDIO
        # ====================================================

        else:

            selected = choose_audio_format(
                info,
                request.format_id,
            )

            if not selected:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No downloadable "
                        "audio format was found."
                    ),
                )

            selected_id = selected.get(
                "format_id"
            )

            audio_format = (
                request.audio_format.lower()
            )

            allowed_audio_formats = [
                "mp3",
                "m4a",
                "wav",
                "opus",
            ]

            if (
                audio_format
                not in allowed_audio_formats
            ):

                audio_format = "mp3"

            output_template = str(
                job_dir
                / f"{title}.%(ext)s"
            )

            download_options = {

                "quiet": False,

                "no_warnings": False,

                "ignoreconfig": True,

                "noplaylist": True,

                "socket_timeout": 60,

                "retries": 5,

                "fragment_retries": 5,

                "js_runtimes": {
                    "node": {}
                },

                "format": str(
                    selected_id
                ),

                "outtmpl": output_template,

                "skip_download": False,

                "postprocessors": [

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
                ],
            }

        # ----------------------------------------------------
        # DOWNLOAD LOGGING
        # ----------------------------------------------------

        print(
            f"[DOWNLOAD] Platform: {platform}"
        )

        print(
            f"[DOWNLOAD] URL: {url}"
        )

        print(
            f"[DOWNLOAD] Media type: "
            f"{media_type}"
        )

        print(
            f"[DOWNLOAD] Format: "
            f"{selected_id}"
        )

        print(
            "[DOWNLOAD] YouTube cookies: "
            "DISABLED"
        )

        # ----------------------------------------------------
        # Execute download
        # ----------------------------------------------------

        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download(
                [url]
            )

        # ----------------------------------------------------
        # Find generated file
        # ----------------------------------------------------

        files = [

            file

            for file in job_dir.iterdir()

            if file.is_file()

        ]

        if not files:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Download completed "
                    "without producing "
                    "an output file."
                ),
            )

        output_file = max(
            files,
            key=lambda file: (
                file.stat().st_mtime
            ),
        )

        file_size = (
            output_file.stat().st_size
        )

        return {

            "success": True,

            "platform": platform_display_name(
                platform
            ),

            "title": (
                info.get("title")
                or title
            ),

            "media_type": media_type,

            "format_id": str(
                selected_id
            ),

            "filename": (
                output_file.name
            ),

            "size": file_size,

            "download_url": (
                f"/files/"
                f"{job_id}/"
                f"{output_file.name}"
            ),

            "youtube_cookies_used": False,
        }

    except HTTPException:

        raise

    except Exception as error:

        print(
            f"[DOWNLOAD ERROR] {error}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Download failed: "
                f"{type(error).__name__}: "
                f"{clean_yt_error(error)}"
            ),
        )

    finally:

        remove_cookie_file(
            cookie_file
        )


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

    safe_job_id = Path(
        job_id
    ).name

    safe_name = Path(
        filename
    ).name

    file_path = (
        DOWNLOAD_DIR
        / safe_job_id
        / safe_name
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "File not found or "
                "has expired."
            ),
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail=(
                "Requested file "
                "does not exist."
            ),
        )

    return FileResponse(
        path=file_path,
        filename=safe_name,
    )