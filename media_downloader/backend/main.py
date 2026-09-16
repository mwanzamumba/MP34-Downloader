import asyncio
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# ============================================================
# APP CONFIGURATION
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    version="2.0.0",
    description="Media analysis and downloading API powered by yt-dlp.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_DOWNLOADS = int(os.getenv("MAX_DOWNLOADS", "2"))

# Keep downloaded files for this amount of seconds.
FILE_TTL = int(os.getenv("FILE_TTL", "1800"))


# ============================================================
# REQUEST MODELS
# ============================================================

class AnalyzeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str | None = None
    media_type: str = "video"
    audio_format: str = "mp3"


# ============================================================
# URL HELPERS
# ============================================================

SUPPORTED_DOMAINS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "twitter.com": "X",
    "x.com": "X",
}


def normalize_hostname(hostname: str) -> str:
    hostname = hostname.lower().strip()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    if hostname.startswith("m."):
        hostname = hostname[2:]

    return hostname


def platform_for(url: str) -> str:
    try:
        parsed = urlparse(url)
        hostname = normalize_hostname(parsed.hostname or "")

        for domain, platform in SUPPORTED_DOMAINS.items():
            if hostname == domain or hostname.endswith("." + domain):
                return platform

    except Exception:
        pass

    return "Unknown"


def validate_url(url: str) -> str:
    url = url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="Please provide a media URL.",
        )

    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="URL must start with http:// or https://.",
        )

    platform = platform_for(url)

    if platform == "Unknown":
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported platform. "
                "Supported platforms are YouTube, Facebook, "
                "Instagram, TikTok and X."
            ),
        )

    return url


# ============================================================
# COOKIE MANAGEMENT
# ============================================================

def create_cookie_file() -> str | None:
    """
    Render stores YouTube cookies in YOUTUBE_COOKIES.

    The value must contain the Netscape cookie-file contents.

    The temporary file is deleted after yt-dlp finishes.
    """

    cookies = os.getenv("YOUTUBE_COOKIES")

    if not cookies:
        return None

    temp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )

    try:
        temp.write(cookies)
        temp.flush()
        temp.close()
        return temp.name

    except Exception:
        try:
            temp.close()
        except Exception:
            pass

        try:
            os.unlink(temp.name)
        except Exception:
            pass

        raise


def delete_cookie_file(cookie_file: str | None):
    if not cookie_file:
        return

    try:
        os.remove(cookie_file)
    except OSError:
        pass


# ============================================================
# YT-DLP CONFIGURATION
# ============================================================

def get_ytdlp_options(
    *,
    cookie_file: str | None = None,
    quiet: bool = True,
    extra: dict | None = None,
) -> dict:

    options = {
        "quiet": quiet,
        "no_warnings": False,

        # Node + yt-dlp-ejs
        "js_runtimes": {
            "node": {},
        },

        # Do not download unless explicitly requested.
        "noplaylist": True,

        # Networking
        "socket_timeout": 30,

        # Helps yt-dlp work with modern sites.
        "retries": 3,
        "fragment_retries": 3,

        # We only need metadata during analysis.
        "skip_download": True,
    }

    if cookie_file:
        options["cookiefile"] = cookie_file

    if extra:
        options.update(extra)

    return options


# ============================================================
# FORMAT CLASSIFICATION
# ============================================================

def has_video(fmt: dict) -> bool:
    return (
        fmt.get("vcodec")
        and fmt.get("vcodec") != "none"
    )


def has_audio(fmt: dict) -> bool:
    return (
        fmt.get("acodec")
        and fmt.get("acodec") != "none"
    )


def is_progressive(fmt: dict) -> bool:
    return has_video(fmt) and has_audio(fmt)


def is_storyboard(fmt: dict) -> bool:
    return (
        fmt.get("format_note") == "storyboard"
        or fmt.get("ext") == "mhtml"
        or fmt.get("protocol") == "mhtml"
    )


def is_audio_only(fmt: dict) -> bool:
    return has_audio(fmt) and not has_video(fmt)


def is_video_only(fmt: dict) -> bool:
    return has_video(fmt) and not has_audio(fmt)


def numeric(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_size(fmt: dict):
    size = fmt.get("filesize")

    if size:
        return size

    return fmt.get("filesize_approx")


def quality_score(fmt: dict) -> float:
    """
    General quality score.

    Resolution is weighted heavily.
    Bitrate is used as a secondary signal.
    """

    height = numeric(fmt.get("height"))
    width = numeric(fmt.get("width"))
    tbr = numeric(fmt.get("tbr"))

    return (
        height * 1000
        + width
        + tbr
    )


# ============================================================
# FORMAT PRESENTATION
# ============================================================

def format_to_public(fmt: dict, media_type: str | None = None):
    video = has_video(fmt)
    audio = has_audio(fmt)

    if video and audio:
        detected_type = "video"
    elif video:
        detected_type = "video_only"
    elif audio:
        detected_type = "audio"
    else:
        detected_type = "other"

    return {
        "format_id": str(fmt.get("format_id", "")),
        "type": media_type or detected_type,
        "ext": fmt.get("ext"),
        "format_note": fmt.get("format_note"),
        "width": fmt.get("width"),
        "height": fmt.get("height"),
        "resolution": fmt.get("resolution"),
        "fps": fmt.get("fps"),
        "vcodec": fmt.get("vcodec"),
        "acodec": fmt.get("acodec"),
        "abr": fmt.get("abr"),
        "vbr": fmt.get("vbr"),
        "tbr": fmt.get("tbr"),
        "filesize": format_size(fmt),
        "protocol": fmt.get("protocol"),
        "has_video": video,
        "has_audio": audio,
        "progressive": video and audio,
    }


# ============================================================
# ANALYSIS
# ============================================================

def extract_info(url: str):
    cookie_file = create_cookie_file()

    try:
        options = get_ytdlp_options(
            cookie_file=cookie_file,
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(
                url,
                download=False,
            )

    except yt_dlp.utils.DownloadError as exc:
        message = str(exc)

        raise HTTPException(
            status_code=422,
            detail=clean_yt_error(message),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Media analysis failed: {str(exc)}",
        )

    finally:
        delete_cookie_file(cookie_file)


def clean_yt_error(message: str) -> str:
    message = message.strip()

    if "Sign in to confirm" in message:
        return (
            "YouTube requires authentication for this media. "
            "Please try another video."
        )

    if "Private video" in message:
        return "This is a private video."

    if "Video unavailable" in message:
        return "This video is unavailable."

    if "age-restricted" in message.lower():
        return "This video is age-restricted."

    if len(message) > 500:
        return message[:500] + "..."

    return message


def build_analysis(info: dict, platform: str):
    raw_formats = info.get("formats") or []

    usable_formats = [
        fmt
        for fmt in raw_formats
        if not is_storyboard(fmt)
        and (has_video(fmt) or has_audio(fmt))
    ]

    progressive = [
        fmt
        for fmt in usable_formats
        if is_progressive(fmt)
    ]

    video_only = [
        fmt
        for fmt in usable_formats
        if is_video_only(fmt)
    ]

    audio_only = [
        fmt
        for fmt in usable_formats
        if is_audio_only(fmt)
    ]

    # --------------------------------------------------------
    # VIDEO FORMATS
    # --------------------------------------------------------

    video_formats = progressive + video_only

    video_formats.sort(
        key=quality_score,
        reverse=True,
    )

    # Remove duplicate display combinations.
    seen_video = set()
    public_video_formats = []

    for fmt in video_formats:
        key = (
            fmt.get("height"),
            fmt.get("width"),
            fmt.get("ext"),
            fmt.get("format_id"),
        )

        if key in seen_video:
            continue

        seen_video.add(key)

        public_video_formats.append(
            format_to_public(
                fmt,
                "video",
            )
        )

    # --------------------------------------------------------
    # AUDIO FORMATS
    # --------------------------------------------------------

    audio_only.sort(
        key=lambda x: (
            numeric(x.get("abr")),
            numeric(x.get("tbr")),
        ),
        reverse=True,
    )

    public_audio_formats = [
        format_to_public(
            fmt,
            "audio",
        )
        for fmt in audio_only
    ]

    # --------------------------------------------------------
    # PROGRESSIVE FORMATS
    # --------------------------------------------------------

    public_progressive = [
        format_to_public(
            fmt,
            "video",
        )
        for fmt in sorted(
            progressive,
            key=quality_score,
            reverse=True,
        )
    ]

    return {
        "title": info.get("title") or "Unknown title",
        "platform": platform,

        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),

        "uploader": info.get("uploader"),
        "channel": info.get("channel"),

        "format_count": len(usable_formats),

        "video_formats": public_video_formats,
        "audio_formats": public_audio_formats,
        "progressive_formats": public_progressive,

        "has_video": bool(video_formats),
        "has_audio": bool(audio_only or progressive),

        "recommended_video": (
            public_video_formats[0]
            if public_video_formats
            else None
        ),

        "recommended_audio": (
            public_audio_formats[0]
            if public_audio_formats
            else None
        ),
    }


# ============================================================
# ROOT / HEALTH
# ============================================================

@app.get("/")
def root():
    return {
        "name": "Media Downloader API",
        "version": "2.0.0",
        "status": "online",
        "supported_platforms": [
            "YouTube",
            "Facebook",
            "Instagram",
            "TikTok",
            "X",
        ],
    }


@app.get("/version")
def version():
    return {
        "api_version": "2.0.0",
        "yt_dlp": yt_dlp.version.__version__,
        "node_required": True,
        "cookies_configured": bool(
            os.getenv("YOUTUBE_COOKIES")
        ),
    }


# ============================================================
# DEBUG YOUTUBE
# ============================================================

@app.get("/debug-youtube")
def debug_youtube():
    cookies = os.getenv("YOUTUBE_COOKIES")

    node_path = shutil.which("node")

    return {
        "cookies_configured": bool(cookies),
        "cookies_length": len(cookies) if cookies else 0,
        "cookies_header": (
            cookies[:50]
            if cookies
            else None
        ),
        "node_available": bool(node_path),
        "node_path": node_path,
    }


# ============================================================
# DEBUG FORMATS
# ============================================================

@app.post("/debug-formats")
def debug_formats(request: AnalyzeRequest):
    url = validate_url(request.url)

    platform = platform_for(url)

    info = extract_info(url)

    formats = []

    for fmt in info.get("formats") or []:

        # Never expose signed media URLs.
        formats.append({
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "format_note": fmt.get("format_note"),
            "width": fmt.get("width"),
            "height": fmt.get("height"),
            "resolution": fmt.get("resolution"),
            "fps": fmt.get("fps"),
            "vcodec": fmt.get("vcodec"),
            "acodec": fmt.get("acodec"),
            "abr": fmt.get("abr"),
            "vbr": fmt.get("vbr"),
            "tbr": fmt.get("tbr"),
            "filesize": fmt.get("filesize"),
            "filesize_approx": fmt.get(
                "filesize_approx"
            ),
            "protocol": fmt.get("protocol"),
        })

    return {
        "title": info.get("title"),
        "platform": platform,
        "format_count": len(formats),
        "formats": formats,
    }


# ============================================================
# MAIN ANALYZE ENDPOINT
# ============================================================

@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    url = validate_url(request.url)

    platform = platform_for(url)

    info = extract_info(url)

    return build_analysis(
        info,
        platform,
    )


# ============================================================
# FORMAT SELECTION
# ============================================================

def choose_video_format(
    formats: list,
    requested_format_id: str | None,
):
    usable = [
        fmt
        for fmt in formats
        if not is_storyboard(fmt)
        and has_video(fmt)
    ]

    if not usable:
        return None

    # User explicitly selected a format.
    if requested_format_id:
        for fmt in usable:
            if str(fmt.get("format_id")) == str(
                requested_format_id
            ):
                return fmt

    # Prefer progressive MP4 because it already contains
    # video + audio and does not require merging.
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

    # Otherwise use the highest video format.
    return max(
        usable,
        key=quality_score,
    )


def choose_audio_format(
    formats: list,
    requested_format_id: str | None,
):
    usable = [
        fmt
        for fmt in formats
        if not is_storyboard(fmt)
        and is_audio_only(fmt)
    ]

    if requested_format_id:
        for fmt in usable:
            if str(fmt.get("format_id")) == str(
                requested_format_id
            ):
                return fmt

    if not usable:
        return None

    m4a = [
        fmt
        for fmt in usable
        if fmt.get("ext") == "m4a"
    ]

    if m4a:
        return max(
            m4a,
            key=lambda x: (
                numeric(x.get("abr")),
                numeric(x.get("tbr")),
            ),
        )

    return max(
        usable,
        key=lambda x: (
            numeric(x.get("abr")),
            numeric(x.get("tbr")),
        ),
    )


# ============================================================
# FFMPEG
# ============================================================

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


# ============================================================
# DOWNLOAD HELPERS
# ============================================================

def cleanup_old_files():
    """
    Remove files older than FILE_TTL.
    """

    now = asyncio.get_event_loop().time()

    # asyncio loop time is not filesystem time.
    # Use os.path.getmtime instead.
    import time

    for item in DOWNLOAD_DIR.iterdir():

        try:
            age = time.time() - item.stat().st_mtime

            if age > FILE_TTL:
                if item.is_file():
                    item.unlink()

                elif item.is_dir():
                    shutil.rmtree(item)

        except OSError:
            pass


def safe_filename(name: str) -> str:
    name = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        name,
    )

    name = name.strip(" .")

    if not name:
        name = "download"

    return name[:150]


# ============================================================
# DOWNLOAD ENDPOINT
# ============================================================

@app.post("/download")
def download(request: DownloadRequest):

    url = validate_url(request.url)

    platform = platform_for(url)

    cleanup_old_files()

    if request.media_type not in {
        "video",
        "audio",
    }:
        raise HTTPException(
            status_code=400,
            detail="media_type must be video or audio.",
        )

    if request.media_type == "audio" and not ffmpeg_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Audio extraction requires FFmpeg "
                "on the server."
            ),
        )

    cookie_file = create_cookie_file()

    job_id = uuid.uuid4().hex

    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        # ----------------------------------------------------
        # First inspect the media.
        # ----------------------------------------------------

        options = get_ytdlp_options(
            cookie_file=cookie_file,
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False,
            )

        formats = info.get("formats") or []

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        if request.media_type == "video":

            selected = choose_video_format(
                formats,
                request.format_id,
            )

            if not selected:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No downloadable video "
                        "format was found."
                    ),
                )

            selected_id = selected.get(
                "format_id"
            )

            # Progressive formats already contain audio.
            if is_progressive(selected):

                format_selector = str(
                    selected_id
                )

            else:

                # Separate video stream.
                # Try best audio automatically.
                audio = choose_audio_format(
                    formats,
                    None,
                )

                if audio:
                    format_selector = (
                        f"{selected_id}+"
                        f"{audio.get('format_id')}"
                    )
                else:
                    format_selector = str(
                        selected_id
                    )

            output_template = str(
                job_dir / "%(title).150s.%(ext)s"
            )

            download_options = get_ytdlp_options(
                cookie_file=cookie_file,
                quiet=False,
                extra={
                    "format": format_selector,

                    "outtmpl": output_template,

                    "noplaylist": True,

                    "merge_output_format": "mp4",

                    "postprocessors": [],

                    "skip_download": False,
                },
            )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        else:

            selected = choose_audio_format(
                formats,
                request.format_id,
            )

            if selected:

                selected_id = selected.get(
                    "format_id"
                )

                format_selector = str(
                    selected_id
                )

            else:

                # No audio-only stream exists.
                #
                # This is exactly what happened with your
                # current YouTube response:
                #
                # format 18 = video + audio.
                #
                # Download it and extract the audio.

                progressive = [
                    fmt
                    for fmt in formats
                    if is_progressive(fmt)
                ]

                if not progressive:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "No downloadable audio "
                            "or progressive video+audio "
                            "format was found."
                        ),
                    )

                selected = max(
                    progressive,
                    key=quality_score,
                )

                format_selector = str(
                    selected.get("format_id")
                )

            output_template = str(
                job_dir / "%(title).150s.%(ext)s"
            )

            audio_format = (
                request.audio_format.lower()
            )

            allowed_audio_formats = {
                "mp3",
                "m4a",
                "wav",
                "opus",
            }

            if audio_format not in allowed_audio_formats:
                audio_format = "mp3"

            download_options = get_ytdlp_options(
                cookie_file=cookie_file,
                quiet=False,
                extra={
                    "format": format_selector,

                    "outtmpl": output_template,

                    "noplaylist": True,

                    "skip_download": False,

                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": audio_format,
                            "preferredquality": (
                                "192"
                                if audio_format == "mp3"
                                else None
                            ),
                        }
                    ],
                },
            )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download([url])

        # ----------------------------------------------------
        # FIND RESULT
        # ----------------------------------------------------

        files = [
            item
            for item in job_dir.iterdir()
            if item.is_file()
        ]

        if not files:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Download completed but "
                    "no output file was produced."
                ),
            )

        # Pick newest/largest output.
        output_file = max(
            files,
            key=lambda x: x.stat().st_mtime,
        )

        original_title = (
            info.get("title")
            or "download"
        )

        return {
            "success": True,
            "platform": platform,
            "title": original_title,
            "media_type": request.media_type,
            "format_id": str(
                selected.get("format_id")
                if selected
                else ""
            ),
            "filename": output_file.name,
            "size": output_file.stat().st_size,
            "download_url": (
                f"/files/{job_id}/"
                f"{output_file.name}"
            ),
        }

    except HTTPException:
        raise

    except yt_dlp.utils.DownloadError as exc:

        raise HTTPException(
            status_code=422,
            detail=clean_yt_error(
                str(exc)
            ),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(exc)}",
        )

    finally:
        delete_cookie_file(cookie_file)


# ============================================================
# FILE DELIVERY
# ============================================================

@app.get("/files/{job_id}/{filename}")
def get_file(
    job_id: str,
    filename: str,
):

    # Prevent path traversal.
    safe_job_id = Path(job_id).name
    safe_name = Path(filename).name

    file_path = (
        DOWNLOAD_DIR
        / safe_job_id
        / safe_name
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
        path=str(file_path),
        filename=safe_name,
        media_type="application/octet-stream",
    )


# ============================================================
# VALIDATE STREAMS
# ============================================================

@app.post("/validate-streams")
def validate_streams(
    request: AnalyzeRequest,
):

    url = validate_url(request.url)

    platform = platform_for(url)

    info = extract_info(url)

    formats = info.get("formats") or []

    usable = [
        fmt
        for fmt in formats
        if not is_storyboard(fmt)
        and (
            has_video(fmt)
            or has_audio(fmt)
        )
    ]

    progressive = [
        fmt
        for fmt in usable
        if is_progressive(fmt)
    ]

    video_only = [
        fmt
        for fmt in usable
        if is_video_only(fmt)
    ]

    audio_only = [
        fmt
        for fmt in usable
        if is_audio_only(fmt)
    ]

    return {
        "success": True,
        "platform": platform,
        "title": info.get("title"),

        "video_available": bool(
            progressive or video_only
        ),

        "audio_available": bool(
            progressive or audio_only
        ),

        "progressive_count": len(
            progressive
        ),

        "video_only_count": len(
            video_only
        ),

        "audio_only_count": len(
            audio_only
        ),

        "ffmpeg_available": (
            ffmpeg_available()
        ),
    }