import os
import re
import uuid
import shutil
import tempfile
import subprocess
import time

from pathlib import Path
from typing import Optional

import yt_dlp

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_VERSION = "3.2.0"

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
    "",
).strip()


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    description=(
        "Media downloader API using "
        "FastAPI and yt-dlp"
    ),
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
    format_id: Optional[str] = None
    media_type: str = "video"
    audio_format: Optional[str] = "mp3"


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str) -> str:

    value = url.lower()

    if (
        "youtube.com" in value
        or "youtu.be" in value
        or "youtube-nocookie.com" in value
    ):
        return "YouTube"

    if (
        "facebook.com" in value
        or "fb.watch" in value
    ):
        return "Facebook"

    if "instagram.com" in value:
        return "Instagram"

    if "tiktok.com" in value:
        return "TikTok"

    if (
        "twitter.com" in value
        or "x.com" in value
    ):
        return "X"

    return "Unknown"


# ============================================================
# SYSTEM CHECKS
# ============================================================

def executable_available(
    name: str,
) -> bool:

    return shutil.which(name) is not None


def node_available() -> bool:

    return executable_available(
        "node"
    )


def ffmpeg_available() -> bool:

    return executable_available(
        "ffmpeg"
    )


def ffprobe_available() -> bool:

    return executable_available(
        "ffprobe"
    )


# ============================================================
# COOKIE MANAGEMENT
# ============================================================

def create_cookie_file() -> Optional[str]:

    if not YOUTUBE_COOKIES:
        return None

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )

    try:

        temp_file.write(
            YOUTUBE_COOKIES
        )

        temp_file.flush()

        return temp_file.name

    finally:

        temp_file.close()


def remove_cookie_file(
    cookie_file: Optional[str],
):

    if not cookie_file:
        return

    try:

        if os.path.exists(
            cookie_file
        ):

            os.remove(
                cookie_file
            )

    except Exception:

        pass


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options(
    skip_download: bool = True,
    cookie_file: Optional[str] = None,
):

    options = {

        "ignoreconfig": True,

        "noplaylist": True,

        "socket_timeout": 60,

        "retries": 5,

        "fragment_retries": 5,

        "file_access_retries": 3,

        "js_runtimes": {
            "node": {}
        },

        "skip_download":
            skip_download,

        "continuedl": True,

        "overwrites": True,
    }

    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------

    if cookie_file:

        options["cookiefile"] = (
            cookie_file
        )

        options["extractor_args"] = {

            "youtube": {

                "player_client": [
                    "default",
                    "web_embedded",
                ]
            }
        }

    return options


# ============================================================
# FORMAT HELPERS
# ============================================================

def has_video(
    fmt: dict,
) -> bool:

    codec = fmt.get(
        "vcodec"
    )

    return (
        codec is not None
        and codec != "none"
    )


def has_audio(
    fmt: dict,
) -> bool:

    codec = fmt.get(
        "acodec"
    )

    return (
        codec is not None
        and codec != "none"
    )


def is_progressive(
    fmt: dict,
) -> bool:

    return (
        has_video(fmt)
        and has_audio(fmt)
    )


def safe_int(
    value,
):

    try:

        if value is None:
            return None

        return int(value)

    except Exception:

        return None


def safe_float(
    value,
):

    try:

        if value is None:
            return None

        return float(value)

    except Exception:

        return None


# ============================================================
# PUBLIC FORMAT OBJECT
# ============================================================

def format_to_public(
    fmt: dict,
    format_type: str,
) -> dict:

    width = safe_int(
        fmt.get("width")
    )

    height = safe_int(
        fmt.get("height")
    )

    if width and height:

        resolution = (
            f"{width}x{height}"
        )

    else:

        resolution = (
            fmt.get("resolution")
        )

    return {

        "format_id":
            str(
                fmt.get(
                    "format_id",
                    "",
                )
            ),

        "ext":
            fmt.get("ext"),

        "resolution":
            resolution,

        "width":
            width,

        "height":
            height,

        "fps":
            safe_float(
                fmt.get("fps")
            ),

        "filesize":
            safe_int(
                fmt.get("filesize")
                or
                fmt.get(
                    "filesize_approx"
                )
            ),

        "vcodec":
            fmt.get("vcodec"),

        "acodec":
            fmt.get("acodec"),

        "abr":
            safe_float(
                fmt.get("abr")
            ),

        "vbr":
            safe_float(
                fmt.get("vbr")
            ),

        "format_note":
            fmt.get(
                "format_note"
            ),

        "protocol":
            fmt.get(
                "protocol"
            ),

        "format_type":
            format_type,
    }


# ============================================================
# FORMAT COLLECTION
# ============================================================

def collect_formats(
    info: dict,
):

    formats = (
        info.get(
            "formats"
        )
        or []
    )

    video_formats = []

    audio_formats = []

    progressive_formats = []

    for fmt in formats:

        format_id = str(
            fmt.get(
                "format_id",
                "",
            )
        )

        # Skip storyboard formats.
        if format_id.startswith(
            "sb"
        ):
            continue

        if (
            not has_video(fmt)
            and not has_audio(fmt)
        ):
            continue

        if is_progressive(fmt):

            progressive_formats.append(
                format_to_public(
                    fmt,
                    "progressive",
                )
            )

        elif has_video(fmt):

            video_formats.append(
                format_to_public(
                    fmt,
                    "video",
                )
            )

        elif has_audio(fmt):

            audio_formats.append(
                format_to_public(
                    fmt,
                    "audio",
                )
            )

    return (
        video_formats,
        audio_formats,
        progressive_formats,
    )


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

    return url


# ============================================================
# ERROR CLEANING
# ============================================================

def clean_error(
    error: Exception,
) -> str:

    message = str(
        error
    ).strip()

    if not message:

        return (
            "Unknown yt-dlp error."
        )

    return message


# ============================================================
# EXTRACT MEDIA INFORMATION
# ============================================================

def extract_media_info(
    url: str,
):

    platform = detect_platform(
        url
    )

    cookie_file = None

    try:

        # ----------------------------------------------------
        # YouTube cookies
        # ----------------------------------------------------

        if platform == "YouTube":

            if YOUTUBE_COOKIES:

                cookie_file = (
                    create_cookie_file()
                )

        options = (
            get_ytdlp_options(
                skip_download=True,
                cookie_file=cookie_file,
            )
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
# RECOMMENDED VIDEO
# ============================================================

def choose_recommended_video(
    video_formats: list,
    progressive_formats: list,
):

    candidates = []

    # Progressive formats are preferred because
    # they already contain video + audio.
    candidates.extend(
        progressive_formats
    )

    candidates.extend(
        video_formats
    )

    if not candidates:

        return None

    usable = [

        item

        for item
        in candidates

        if item.get("height")
    ]

    if not usable:

        return candidates[0]

    under_720 = [

        item

        for item
        in usable

        if (
            item.get("height")
            and
            item["height"] <= 720
        )
    ]

    if under_720:

        usable = under_720

    usable.sort(

        key=lambda item: (

            item.get("height")
            or 0,

            item.get("fps")
            or 0,
        )
    )

    return usable[-1]


# ============================================================
# RECOMMENDED AUDIO
# ============================================================

def choose_recommended_audio(
    audio_formats: list,
):

    if not audio_formats:

        return None

    usable = [

        item

        for item
        in audio_formats

        if item.get("abr") is not None
    ]

    if not usable:

        return audio_formats[0]

    usable.sort(

        key=lambda item: (

            item.get("abr")
            or 0
        )
    )

    return usable[-1]


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():

    return {

        "name":
            "Media Downloader API",

        "version":
            APP_VERSION,

        "status":
            "online",

        "platforms": [

            "YouTube",
            "Facebook",
            "Instagram",
            "TikTok",
            "X",
        ],
    }


# ============================================================
# HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():

    return {

        "status":
            "ok",

        "version":
            APP_VERSION,
    }


# ============================================================
# VERSION ENDPOINT
# ============================================================

@app.get("/version")
def version():

    try:

        yt_version = (
            yt_dlp.version.__version__
        )

    except Exception:

        yt_version = "unknown"

    return {

        "api_version":
            APP_VERSION,

        "yt_dlp":
            yt_version,

        "node_available":
            node_available(),

        "ffmpeg_available":
            ffmpeg_available(),

        "ffprobe_available":
            ffprobe_available(),

        "cookies_configured":
            bool(
                YOUTUBE_COOKIES
            ),
    }


# ============================================================
# YOUTUBE DEBUG ENDPOINT
# ============================================================

@app.get("/debug-youtube")
def debug_youtube():

    test_url = (
        "https://www.youtube.com/watch?v=L5aSgl7HKBA"
    )

    cookie_file = None

    try:

        if YOUTUBE_COOKIES:

            cookie_file = (
                create_cookie_file()
            )

        command = [

            "python",
            "-m",
            "yt_dlp",

            "--js-runtimes",
            "node",

            "--simulate",

            "--no-playlist",

            "--extractor-args",
            (
                "youtube:"
                "player_client="
                "default,web_embedded"
            ),

            test_url,
        ]

        if cookie_file:

            command.insert(
                len(command) - 1,
                "--cookies",
            )

            command.insert(
                len(command) - 1,
                cookie_file,
            )

        result = subprocess.run(

            command,

            capture_output=True,

            text=True,

            timeout=180,
        )

        return {

            "success":
                result.returncode == 0,

            "return_code":
                result.returncode,

            "stdout":
                result.stdout,

            "stderr":
                result.stderr,

            "cookies_configured":
                bool(
                    YOUTUBE_COOKIES
                ),

            "youtube_cookies_used":
                bool(
                    cookie_file
                ),

            "node_available":
                node_available(),

            "ffmpeg_available":
                ffmpeg_available(),

            "ffprobe_available":
                ffprobe_available(),
        }

    except subprocess.TimeoutExpired:

        return {

            "success":
                False,

            "error":
                "yt-dlp test timed out after 180 seconds.",

            "cookies_configured":
                bool(
                    YOUTUBE_COOKIES
                ),

            "youtube_cookies_used":
                bool(
                    cookie_file
                ),

            "node_available":
                node_available(),

            "ffmpeg_available":
                ffmpeg_available(),

            "ffprobe_available":
                ffprobe_available(),
        }

    except Exception as error:

        return {

            "success":
                False,

            "error":
                str(error),

            "cookies_configured":
                bool(
                    YOUTUBE_COOKIES
                ),

            "youtube_cookies_used":
                bool(
                    cookie_file
                ),

            "node_available":
                node_available(),

            "ffmpeg_available":
                ffmpeg_available(),

            "ffprobe_available":
                ffprobe_available(),
        }

    finally:

        remove_cookie_file(
            cookie_file
        )


# ============================================================
# ANALYZE ENDPOINT
# ============================================================

@app.post("/analyze")
def analyze(
    request: AnalyzeRequest,
):

    url = validate_url(
        request.url
    )

    platform = detect_platform(
        url
    )

    if platform == "Unknown":

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported platform. "
                "Supported platforms: "
                "YouTube, Facebook, "
                "Instagram, TikTok and X."
            ),
        )

    try:

        info = extract_media_info(
            url
        )

        (
            video_formats,
            audio_formats,
            progressive_formats,
        ) = collect_formats(
            info
        )

        recommended_video = (
            choose_recommended_video(
                video_formats,
                progressive_formats,
            )
        )

        recommended_audio = (
            choose_recommended_audio(
                audio_formats
            )
        )

        return {

            "success":
                True,

            "title":
                info.get(
                    "title"
                ),

            "platform":
                platform,

            "thumbnail":
                info.get(
                    "thumbnail"
                ),

            "duration":
                safe_int(
                    info.get(
                        "duration"
                    )
                ),

            "uploader":
                info.get(
                    "uploader"
                ),

            "channel":
                info.get(
                    "channel"
                ),

            "webpage_url":
                info.get(
                    "webpage_url"
                ),

            "has_video":
                bool(
                    video_formats
                    or
                    progressive_formats
                ),

            "has_audio":
                bool(
                    audio_formats
                    or
                    progressive_formats
                ),

            "video_formats":
                video_formats,

            "audio_formats":
                audio_formats,

            "progressive_formats":
                progressive_formats,

            "recommended_video":
                recommended_video,

            "recommended_audio":
                recommended_audio,
        }

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=clean_error(
                error
            ),
        )


# ============================================================
# DOWNLOAD ENDPOINT
# ============================================================

@app.post("/download")
def download(
    request: DownloadRequest,
):

    url = validate_url(
        request.url
    )

    platform = detect_platform(
        url
    )

    if platform == "Unknown":

        raise HTTPException(
            status_code=400,
            detail="Unsupported platform.",
        )

    job_id = uuid.uuid4().hex

    output_dir = (
        DOWNLOAD_DIR / job_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cookie_file = None

    try:

        # ====================================================
        # CREATE YOUTUBE COOKIE FILE
        # ====================================================

        if platform == "YouTube":

            if YOUTUBE_COOKIES:

                cookie_file = (
                    create_cookie_file()
                )


        # ====================================================
        # LOG DOWNLOAD REQUEST
        # ====================================================

        print("")
        print(
            "========================================"
        )
        print(
            "          DOWNLOAD REQUEST"
        )
        print(
            "========================================"
        )

        print(
            f"Platform: {platform}"
        )

        print(
            f"Media type: "
            f"{request.media_type}"
        )

        print(
            f"Requested format: "
            f"{request.format_id}"
        )

        print(
            "Cookies used: "
            f"{bool(cookie_file)}"
        )

        print(
            "========================================"
        )


        # ====================================================
        # STEP 1
        # EXTRACT MEDIA INFORMATION
        # ====================================================

        extract_options = (
            get_ytdlp_options(
                skip_download=True,
                cookie_file=cookie_file,
            )
        )

        print(
            "[DOWNLOAD] Extracting media information..."
        )

        with yt_dlp.YoutubeDL(
            extract_options
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )


        formats = (
            info.get(
                "formats"
            )
            or []
        )


        print(
            "[DOWNLOAD] Formats found: "
            f"{len(formats)}"
        )


        # ====================================================
        # STEP 2
        # FIND REQUESTED FORMAT
        # ====================================================

        requested_format = None

        if request.format_id:

            requested_format = next(

                (
                    fmt

                    for fmt
                    in formats

                    if str(
                        fmt.get(
                            "format_id",
                            "",
                        )
                    )
                    == str(
                        request.format_id
                    )
                ),

                None,
            )


        if requested_format:

            print(
                "[DOWNLOAD] Requested format found."
            )

            print(
                "[DOWNLOAD] Format ID: "
                f"{requested_format.get('format_id')}"
            )

            print(
                "[DOWNLOAD] Extension: "
                f"{requested_format.get('ext')}"
            )

            print(
                "[DOWNLOAD] Video codec: "
                f"{requested_format.get('vcodec')}"
            )

            print(
                "[DOWNLOAD] Audio codec: "
                f"{requested_format.get('acodec')}"
            )

            print(
                "[DOWNLOAD] Protocol: "
                f"{requested_format.get('protocol')}"
            )

        else:

            print(
                "[DOWNLOAD] Requested format "
                "was not found."
            )


        # ====================================================
        # STEP 3
        # SELECT DOWNLOAD FORMAT
        # ====================================================

        if (
            request.media_type.lower()
            == "audio"
        ):

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            if requested_format:

                selected_format = str(
                    requested_format.get(
                        "format_id"
                    )
                )

            else:

                selected_format = (
                    "bestaudio/best"
                )

        else:

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

            if requested_format:

                selected_format = str(
                    requested_format.get(
                        "format_id"
                    )
                )

            else:

                selected_format = (
                    "best[ext=mp4]"
                    "[vcodec!=none]"
                    "[acodec!=none]"
                    "/best[ext=mp4]"
                    "/best"
                )


        print(
            "[DOWNLOAD] Selected format: "
            f"{selected_format}"
        )


        # ====================================================
        # STEP 4
        # OUTPUT TEMPLATE
        # ====================================================

        output_template = str(

            output_dir
            / "%(title)s.%(ext)s"
        )


        # ====================================================
        # STEP 5
        # DOWNLOAD OPTIONS
        # ====================================================

        options = (
            get_ytdlp_options(
                skip_download=False,
                cookie_file=cookie_file,
            )
        )

        options["format"] = (
            selected_format
        )

        options["outtmpl"] = (
            output_template
        )

        options["noplaylist"] = True

        options["continuedl"] = True

        options["overwrites"] = True

        options["retries"] = 5

        options["fragment_retries"] = 5

        options["file_access_retries"] = 3


        # ====================================================
        # AUDIO
        # ====================================================

        if (
            request.media_type.lower()
            == "audio"
        ):

            audio_format = (
                request.audio_format
                or "mp3"
            ).lower()

            allowed_audio = [

                "mp3",
                "m4a",
                "wav",
                "opus",
                "flac",
            ]

            if (
                audio_format
                not in allowed_audio
            ):

                audio_format = "mp3"


            options[
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


        # ====================================================
        # VIDEO
        # ====================================================

        else:

            options[
                "merge_output_format"
            ] = "mp4"


        # ====================================================
        # STEP 6
        # ACTUAL DOWNLOAD
        # ====================================================

        print("")
        print(
            "========================================"
        )

        print(
            "[DOWNLOAD] STARTING ACTUAL DOWNLOAD"
        )

        print(
            f"[DOWNLOAD] URL: {url}"
        )

        print(
            f"[DOWNLOAD] Format: "
            f"{selected_format}"
        )

        print(
            "========================================"
        )


        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            downloaded_info = (
                ydl.extract_info(
                    url,
                    download=True,
                )
            )


        # ====================================================
        # STEP 7
        # FIND DOWNLOADED FILE
        # ====================================================

        files = [

            file

            for file
            in output_dir.iterdir()

            if file.is_file()
        ]


        if not files:

            raise Exception(
                "yt-dlp completed but "
                "no output file was found."
            )


        files.sort(

            key=lambda file:
                file.stat().st_mtime,

            reverse=True,
        )


        output_file = files[0]


        # ====================================================
        # SUCCESS LOG
        # ====================================================

        print("")
        print(
            "========================================"
        )

        print(
            "[DOWNLOAD] DOWNLOAD SUCCESSFUL"
        )

        print(
            f"[DOWNLOAD] Filename: "
            f"{output_file.name}"
        )

        print(
            f"[DOWNLOAD] Size: "
            f"{output_file.stat().st_size} bytes"
        )

        print(
            "========================================"
        )


        # ====================================================
        # RETURN RESULT
        # ====================================================

        return {

            "success":
                True,

            "title":
                downloaded_info.get(
                    "title"
                ),

            "platform":
                platform,

            "format_id":
                selected_format,

            "filename":
                output_file.name,

            "file_size":
                output_file.stat().st_size,

            "download_url":
                (
                    f"/files/"
                    f"{job_id}/"
                    f"{output_file.name}"
                ),
        }


    except Exception as error:

        # ====================================================
        # DOWNLOAD ERROR LOG
        # ====================================================

        print("")
        print(
            "========================================"
        )

        print(
            "[DOWNLOAD] DOWNLOAD FAILED"
        )

        print(
            f"[DOWNLOAD] ERROR: "
            f"{error}"
        )

        print(
            "========================================"
        )


        # ====================================================
        # REMOVE FAILED DOWNLOAD
        # ====================================================

        try:

            if output_dir.exists():

                shutil.rmtree(
                    output_dir
                )

        except Exception:

            pass


        raise HTTPException(
            status_code=422,
            detail=clean_error(
                error
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
def serve_file(
    job_id: str,
    filename: str,
):

    # Prevent path traversal.
    safe_filename = Path(
        filename
    ).name

    job_dir = (
        DOWNLOAD_DIR / job_id
    )

    file_path = (
        job_dir / safe_filename
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


    return FileResponse(
        path=file_path,
        filename=file_path.name,
    )


# ============================================================
# CLEAN OLD DOWNLOADS
# ============================================================

def cleanup_old_files():

    if not DOWNLOAD_DIR.exists():

        return


    current_time = time.time()


    for job_dir in (
        DOWNLOAD_DIR.iterdir()
    ):

        if not job_dir.is_dir():

            continue


        try:

            modified_time = (
                job_dir.stat().st_mtime
            )

            age = (
                current_time
                - modified_time
            )


            if age > FILE_TTL:

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True,
                )


        except Exception:

            pass


# ============================================================
# STARTUP
# ============================================================

@app.on_event(
    "startup"
)
def startup_event():

    print("")
    print(
        "========================================"
    )

    print(
        "       MEDIA DOWNLOADER API"
    )

    print(
        "========================================"
    )

    print(
        f"API Version: {APP_VERSION}"
    )

    print(
        "yt-dlp Version: "
        f"{yt_dlp.version.__version__}"
    )

    print(
        "Node available: "
        f"{node_available()}"
    )

    print(
        "FFmpeg available: "
        f"{ffmpeg_available()}"
    )

    print(
        "FFprobe available: "
        f"{ffprobe_available()}"
    )

    print(
        "YouTube cookies configured: "
        f"{bool(YOUTUBE_COOKIES)}"
    )

    print(
        "File TTL: "
        f"{FILE_TTL} seconds"
    )

    print(
        "========================================"
    )

    cleanup_old_files()