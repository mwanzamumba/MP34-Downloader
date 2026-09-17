import os
import time
import uuid
import shutil
import logging
import subprocess

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

APP_VERSION = "3.7.0"

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

FILE_TTL = 1800

YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")


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
# REQUEST MODEL
# ============================================================

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

    except Exception:
        return "unknown"


# ============================================================
# YOUTUBE URL NORMALIZATION
# ============================================================

def normalize_youtube_url(url: str) -> str:

    try:

        parsed = urlparse(url)

        hostname = parsed.hostname or ""

        hostname = hostname.lower()

        # ----------------------------------------------------
        # youtu.be
        # ----------------------------------------------------

        if "youtu.be" in hostname:

            video_id = parsed.path.strip("/")

            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

        # ----------------------------------------------------
        # youtube.com
        # ----------------------------------------------------

        if "youtube.com" in hostname:

            query = parse_qs(parsed.query)

            video_id = query.get("v")

            if video_id:

                return (
                    "https://www.youtube.com/watch?"
                    f"v={video_id[0]}"
                )

        return url

    except Exception:

        return url


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

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are supported.",
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL.",
        )

    platform = detect_platform(url)

    if platform == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Unsupported media platform.",
        )

    if platform == "youtube":
        url = normalize_youtube_url(url)

    return url


# ============================================================
# COOKIE FILE
# ============================================================

def create_cookie_file():

    if not YOUTUBE_COOKIES:
        return None

    cookie_path = BASE_DIR / "youtube_cookies.txt"

    try:

        cookie_path.write_text(
            YOUTUBE_COOKIES,
            encoding="utf-8",
        )

        return str(cookie_path)

    except Exception as exc:

        logger.error(
            "Failed to create cookie file: %s",
            exc,
        )

        return None


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    download: bool = False,
    output_template: str | None = None,
):

    options = {

        # ----------------------------------------------------
        # Playlist
        # ----------------------------------------------------

        "noplaylist": True,

        # ----------------------------------------------------
        # Retry
        # ----------------------------------------------------

        "retries": 3,
        "fragment_retries": 3,

        # ----------------------------------------------------
        # Continue / overwrite
        # ----------------------------------------------------

        "continuedl": True,
        "overwrites": True,

        # ----------------------------------------------------
        # Network
        # ----------------------------------------------------

        "socket_timeout": 30,

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
            )
        },

        # ----------------------------------------------------
        # Filename
        # ----------------------------------------------------

        "restrictfilenames": True,

        # ----------------------------------------------------
        # YouTube clients
        # ----------------------------------------------------

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "default",
                    "web_embedded",
                ]
            }
        },
    }


    # ========================================================
    # OUTPUT TEMPLATE
    # ========================================================

    if output_template:

        options["outtmpl"] = output_template


    # ========================================================
    # NODE.JS
    # ========================================================

    node_path = shutil.which("node")

    if node_path:

        options["js_runtimes"] = {
            "node": {}
        }


    # ========================================================
    # YOUTUBE COOKIES
    # ========================================================

    cookie_file = create_cookie_file()

    if cookie_file:

        options["cookiefile"] = cookie_file


    # ========================================================
    # DOWNLOAD SETTINGS
    #
    # IMPORTANT:
    #
    # DO NOT set:
    #
    #     "format": "best"
    #
    # here.
    #
    # The /download endpoint decides the exact format.
    # ========================================================

    if download:

        options.update({

            # FFmpeg will merge:
            #
            # video + audio
            #
            # into MP4.
            "merge_output_format": "mp4",

        })


    return options


# ============================================================
# SAFE HELPERS
# ============================================================

def safe_string(value, default=None):

    if value is None:
        return default

    try:

        value = str(value)

        if not value:
            return default

        return value

    except Exception:

        return default


# ------------------------------------------------------------

def safe_int(value, default=0):

    try:

        if value is None:
            return default

        return int(value)

    except Exception:

        return default


# ------------------------------------------------------------

def safe_float(value, default=0):

    try:

        if value is None:
            return default

        return float(value)

    except Exception:

        return default


# ============================================================
# FORMAT -> PUBLIC FORMAT
# ============================================================

def format_to_public(fmt):

    # --------------------------------------------------------
    # Critical protection against None
    # --------------------------------------------------------

    if not isinstance(fmt, dict):

        return None


    # --------------------------------------------------------
    # Codecs
    # --------------------------------------------------------

    vcodec = fmt.get("vcodec")

    acodec = fmt.get("acodec")


    # --------------------------------------------------------
    # Determine whether stream contains video
    # --------------------------------------------------------

    has_video = (

        vcodec is not None

        and vcodec != "none"

    )


    # --------------------------------------------------------
    # Determine whether stream contains audio
    # --------------------------------------------------------

    has_audio = (

        acodec is not None

        and acodec != "none"

    )


    # --------------------------------------------------------
    # Public format
    # --------------------------------------------------------

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
# CHOOSE RECOMMENDED VIDEO
# ============================================================

def choose_recommended_video(formats):

    candidates = []


    for fmt in formats or []:

        if not isinstance(fmt, dict):
            continue


        format_id = safe_string(
            fmt.get("format_id")
        )

        vcodec = fmt.get("vcodec")

        height = safe_int(
            fmt.get("height")
        )

        width = safe_int(
            fmt.get("width")
        )

        fps = safe_float(
            fmt.get("fps")
        )

        acodec = fmt.get("acodec")


        # ----------------------------------------------------
        # Must actually contain video
        # ----------------------------------------------------

        if not format_id:
            continue

        if not vcodec or vcodec == "none":
            continue

        if height <= 0:
            continue


        has_audio = (
            acodec is not None
            and acodec != "none"
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


    # --------------------------------------------------------
    # Prefer:
    #
    # 1. formats with audio
    # 2. highest resolution
    # 3. highest width
    # 4. highest FPS
    # --------------------------------------------------------

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


# ============================================================
# CHOOSE RECOMMENDED AUDIO
# ============================================================

def choose_recommended_audio(formats):

    candidates = []


    for fmt in formats or []:

        if not isinstance(fmt, dict):
            continue


        format_id = safe_string(
            fmt.get("format_id")
        )

        acodec = fmt.get("acodec")

        vcodec = fmt.get("vcodec")

        abr = safe_float(
            fmt.get("abr")
        )

        filesize = safe_int(
            fmt.get("filesize")
            or fmt.get("filesize_approx")
        )


        if not format_id:
            continue


        # ----------------------------------------------------
        # Must contain audio
        # ----------------------------------------------------

        if not acodec or acodec == "none":
            continue


        # ----------------------------------------------------
        # Audio-only stream
        # ----------------------------------------------------

        if vcodec and vcodec != "none":
            continue


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
    selected_video,
):

    candidates = []


    for fmt in formats or []:

        if not isinstance(fmt, dict):
            continue


        format_id = safe_string(
            fmt.get("format_id")
        )

        acodec = fmt.get("acodec")

        vcodec = fmt.get("vcodec")

        abr = safe_float(
            fmt.get("abr")
        )

        filesize = safe_int(
            fmt.get("filesize")
            or fmt.get("filesize_approx")
        )


        # ----------------------------------------------------
        # Format ID required
        # ----------------------------------------------------

        if not format_id:
            continue


        # ----------------------------------------------------
        # Must have audio
        # ----------------------------------------------------

        if not acodec:
            continue

        if acodec == "none":
            continue


        # ----------------------------------------------------
        # Must be audio-only
        # ----------------------------------------------------

        if vcodec and vcodec != "none":
            continue


        candidates.append(
            (
                abr,
                filesize,
                fmt,
            )
        )


    # --------------------------------------------------------
    # No audio found
    # --------------------------------------------------------

    if not candidates:

        return None


    # --------------------------------------------------------
    # Highest bitrate audio first
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )


    return candidates[0][2]


# ============================================================
# CLEANUP OLD FILES
# ============================================================

def cleanup_old_files():

    now = time.time()


    if not DOWNLOAD_DIR.exists():
        return


    for path in DOWNLOAD_DIR.iterdir():

        try:

            age = now - path.stat().st_mtime


            if age > FILE_TTL:

                if path.is_dir():

                    shutil.rmtree(
                        path,
                        ignore_errors=True,
                    )

                else:

                    path.unlink(
                        missing_ok=True
                    )


        except Exception as exc:

            logger.warning(
                "Cleanup failed for %s: %s",
                path,
                exc,
            )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {

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

        "status": "healthy",

        "version": APP_VERSION,

    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():

    return {

        "version": APP_VERSION,

        "yt_dlp": yt_dlp.version.__version__,

    }


# ============================================================
# DEBUG RUNTIME
# ============================================================

@app.get("/debug-runtime")
def debug_runtime():

    return {

        "python": os.sys.version,

        "node": shutil.which("node"),

        "ffmpeg": shutil.which("ffmpeg"),

        "ffprobe": shutil.which("ffprobe"),

        "yt_dlp": yt_dlp.version.__version__,

    }


# ============================================================
# DEBUG FFMPEG
# ============================================================

@app.get("/debug-ffmpeg")
def debug_ffmpeg():

    ffmpeg_path = shutil.which("ffmpeg")

    ffprobe_path = shutil.which("ffprobe")


    result = {

        "ffmpeg_found": ffmpeg_path is not None,

        "ffmpeg_path": ffmpeg_path,

        "ffprobe_found": ffprobe_path is not None,

        "ffprobe_path": ffprobe_path,

        "ffmpeg_version": None,

    }


    if ffmpeg_path:

        try:

            process = subprocess.run(
                [
                    ffmpeg_path,
                    "-version",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )


            first_line = (
                process.stdout
                .splitlines()[0]
                if process.stdout
                else None
            )


            result["ffmpeg_version"] = first_line


        except Exception as exc:

            result["ffmpeg_version"] = str(
                exc
            )


    return result


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(url: str):

    cleanup_old_files()


    # --------------------------------------------------------
    # Validate URL
    # --------------------------------------------------------

    url = validate_url(url)


    # --------------------------------------------------------
    # yt-dlp options
    # --------------------------------------------------------

    options = get_ytdlp_options(
        download=False
    )


    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )


    except Exception as exc:

        logger.exception(
            "Analyze failed"
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )


    # ========================================================
    # RAW FORMATS
    # ========================================================

    raw_formats = info.get(
        "formats",
        []
    )


    # ========================================================
    # PUBLIC FORMATS
    # ========================================================

    formats = []


    for fmt in raw_formats:

        public_format = format_to_public(
            fmt
        )


        if public_format:

            formats.append(
                public_format
            )


    # ========================================================
    # VIDEO FORMATS
    # ========================================================

    video_formats = [

        fmt

        for fmt in formats

        if fmt.get("has_video")

    ]


    # ========================================================
    # AUDIO FORMATS
    # ========================================================

    audio_formats = [

        fmt

        for fmt in formats

        if fmt.get("has_audio")

        and not fmt.get("has_video")

    ]


    # ========================================================
    # PROGRESSIVE FORMATS
    # ========================================================

    progressive_formats = [

        fmt

        for fmt in formats

        if fmt.get("has_video")

        and fmt.get("has_audio")

    ]


    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

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


    recommended_video = (
        format_to_public(
            recommended_video_raw
        )
        if recommended_video_raw
        else None
    )


    recommended_audio = (
        format_to_public(
            recommended_audio_raw
        )
        if recommended_audio_raw
        else None
    )


    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "title": info.get(
            "title"
        ),

        "thumbnail": info.get(
            "thumbnail"
        ),

        "duration": info.get(
            "duration"
        ),

        "platform": detect_platform(
            url
        ),

        "formats": formats,

        "video_formats": video_formats,

        "audio_formats": audio_formats,

        "progressive_formats": progressive_formats,

        "recommended_video": recommended_video,

        "recommended_audio": recommended_audio,

    }


# ============================================================
# DOWNLOAD
# ============================================================

@app.post("/download")
def download(request: DownloadRequest):

    cleanup_old_files()


    # --------------------------------------------------------
    # Validate URL
    # --------------------------------------------------------

    url = validate_url(
        request.url
    )


    # --------------------------------------------------------
    # Validate request format
    # --------------------------------------------------------

    if not request.format_id:

        raise HTTPException(
            status_code=400,
            detail="Format ID is required.",
        )


    # --------------------------------------------------------
    # Media type
    # --------------------------------------------------------

    media_type = (
        request.media_type
        or "video"
    ).lower()


    # ========================================================
    # EXTRACT INFORMATION
    # ========================================================

    extract_options = get_ytdlp_options(
        download=False
    )


    try:

        with yt_dlp.YoutubeDL(
            extract_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )


    except Exception as exc:

        logger.exception(
            "Download extraction failed"
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )


    # ========================================================
    # RAW FORMATS
    # ========================================================

    raw_formats = info.get(
        "formats",
        []
    )


    # ========================================================
    # FIND SELECTED FORMAT
    # ========================================================

    selected_format = None


    for fmt in raw_formats:

        if not isinstance(fmt, dict):
            continue


        if str(
            fmt.get("format_id")
        ) == str(
            request.format_id
        ):

            selected_format = fmt

            break


    # --------------------------------------------------------
    # Format not found
    # --------------------------------------------------------

    if selected_format is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "The selected format is no longer "
                "available. Please analyze the link again."
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
    # OUTPUT TEMPLATE
    # ========================================================

    output_template = str(
        job_dir /
        "%(title).150s.%(ext)s"
    )


    # ========================================================
    # DOWNLOAD OPTIONS
    # ========================================================

    download_options = get_ytdlp_options(
        download=True,
        output_template=output_template,
    )


    # ========================================================
    # AUDIO DOWNLOAD
    # ========================================================

    if media_type == "audio":

        audio_format = (
            request.audio_format
            or "mp3"
        ).lower()


        # ----------------------------------------------------
        # Only allow supported output formats
        # ----------------------------------------------------

        allowed_audio_formats = {
            "mp3",
            "m4a",
            "wav",
            "opus",
            "flac",
        }


        if audio_format not in allowed_audio_formats:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported audio format. "
                    "Use mp3, m4a, wav, opus or flac."
                ),
            )


        # ----------------------------------------------------
        # Use selected source format
        # ----------------------------------------------------

        download_options["format"] = (
            request.format_id
        )


        # ----------------------------------------------------
        # Convert audio
        # ----------------------------------------------------

        download_options["postprocessors"] = [

            {

                "key": "FFmpegExtractAudio",

                "preferredcodec": audio_format,

                "preferredquality": "192",

            }

        ]


    # ========================================================
    # VIDEO DOWNLOAD
    # ========================================================

    elif media_type == "video":

        selected_vcodec = (
            selected_format.get(
                "vcodec"
            )
        )

        selected_acodec = (
            selected_format.get(
                "acodec"
            )
        )


        # ----------------------------------------------------
        # Determine stream types
        # ----------------------------------------------------

        has_video = (

            selected_vcodec is not None

            and selected_vcodec != "none"

        )


        has_audio = (

            selected_acodec is not None

            and selected_acodec != "none"

        )


        # ----------------------------------------------------
        # Selected format must contain video
        # ----------------------------------------------------

        if not has_video:

            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected format does not "
                    "contain a video stream."
                ),
            )


        # ====================================================
        # CASE 1
        #
        # VIDEO + AUDIO ALREADY PRESENT
        # ====================================================

        if has_audio:

            logger.info(
                "Selected format %s already contains "
                "video and audio.",
                request.format_id,
            )


            download_options["format"] = (
                request.format_id
            )


        # ====================================================
        # CASE 2
        #
        # VIDEO ONLY
        #
        # Facebook DASH commonly comes here.
        # ====================================================

        else:

            logger.info(
                "Selected format %s is video-only. "
                "Searching for audio stream.",
                request.format_id,
            )


            # ------------------------------------------------
            # Find best audio stream
            # ------------------------------------------------

            audio_stream = choose_audio_for_video(
                raw_formats,
                selected_format,
            )


            # ------------------------------------------------
            # No audio available
            # ------------------------------------------------

            if audio_stream is None:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "This video has no compatible "
                        "audio stream available."
                    ),
                )


            audio_format_id = safe_string(
                audio_stream.get(
                    "format_id"
                )
            )


            if not audio_format_id:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "A valid audio stream "
                        "could not be selected."
                    ),
                )


            logger.info(
                "Merging video format %s "
                "with audio format %s",
                request.format_id,
                audio_format_id,
            )


            # ------------------------------------------------
            # THIS IS THE IMPORTANT FIX
            #
            # Example:
            #
            # 1654577275915349v
            # +
            # 1559689128550234a
            #
            # ------------------------------------------------

            download_options["format"] = (

                f"{request.format_id}"
                f"+"
                f"{audio_format_id}"

            )


        # ----------------------------------------------------
        # Force final container
        # ----------------------------------------------------

        download_options[
            "merge_output_format"
        ] = "mp4"


    # ========================================================
    # INVALID MEDIA TYPE
    # ========================================================

    else:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid media_type. "
                "Use 'video' or 'audio'."
            ),
        )


    # ========================================================
    # DOWNLOAD
    # ========================================================

    try:

        logger.info(
            "Starting download: %s",
            download_options.get(
                "format"
            ),
        )


        with yt_dlp.YoutubeDL(
            download_options
        ) as ydl:

            ydl.download(
                [url]
            )


    except Exception as exc:

        logger.exception(
            "Download failed"
        )


        # ----------------------------------------------------
        # Remove failed job directory
        # ----------------------------------------------------

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )


        raise HTTPException(
            status_code=500,
            detail=(
                "Download failed: "
                f"{str(exc)}"
            ),
        )


    # ========================================================
    # FIND DOWNLOADED FILE
    # ========================================================

    files = []


    if job_dir.exists():

        for path in job_dir.rglob("*"):

            if not path.is_file():
                continue


            if path.suffix.lower() in (
                ".part",
                ".ytdl",
            ):
                continue


            files.append(path)


    # ========================================================
    # NO FILE FOUND
    # ========================================================

    if not files:

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


    # ========================================================
    # SELECT LARGEST OUTPUT FILE
    # ========================================================

    output_file = max(
        files,
        key=lambda path: path.stat().st_size,
    )


    # ========================================================
    # PUBLIC DOWNLOAD URL
    # ========================================================

    download_url = (
        f"/files/"
        f"{job_id}/"
        f"{output_file.name}"
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

        "size": output_file.stat().st_size,

    }


# ============================================================
# SERVE FILE
# ============================================================

@app.get(
    "/files/{job_id}/{filename}"
)
def get_file(
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


    # --------------------------------------------------------
    # File must exist
    # --------------------------------------------------------

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )


    # --------------------------------------------------------
    # File must actually be a file
    # --------------------------------------------------------

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )


    # ========================================================
    # CONTENT TYPE
    # ========================================================

    extension = (
        file_path.suffix.lower()
    )


    content_types = {

        ".mp4": "video/mp4",

        ".webm": "video/webm",

        ".mkv": "video/x-matroska",

        ".mp3": "audio/mpeg",

        ".m4a": "audio/mp4",

        ".wav": "audio/wav",

        ".opus": "audio/opus",

        ".flac": "audio/flac",

    }


    media_type = content_types.get(
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

@app.on_event("startup")
def startup_event():

    logger.info(
        "========================================"
    )

    logger.info(
        "Media Downloader API starting"
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
        "Node.js: %s",
        shutil.which("node"),
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