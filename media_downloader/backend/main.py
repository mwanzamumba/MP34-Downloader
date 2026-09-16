import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


# ============================================================
# YT-DLP
# ============================================================

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="MP34 Downloader API"
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
# URL VALIDATION
# ============================================================

def validate_url(value: str) -> str:

    value = value.strip()

    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=422,
            detail="Please provide a valid http or https URL.",
        )

    if not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Invalid media URL.",
        )

    return value


# ============================================================
# PLATFORM DETECTION
# ============================================================

def platform_for(url: str) -> str:

    host = urlparse(url).netloc.lower()

    platforms = [
        ("tiktok.com", "TikTok"),
        ("youtube.com", "YouTube"),
        ("youtu.be", "YouTube"),
        ("instagram.com", "Instagram"),
        ("facebook.com", "Facebook"),
        ("fb.watch", "Facebook"),
        ("x.com", "X / Twitter"),
        ("twitter.com", "X / Twitter"),
    ]

    for domain, name in platforms:

        if domain in host:
            return name

    return "Other"


# ============================================================
# YOUTUBE COOKIES
# ============================================================

def create_cookie_file():
    """
    Creates a unique temporary Netscape-format cookie file
    from the YOUTUBE_COOKIES environment variable.

    The cookie contents are never returned through the API.
    """

    cookies = os.getenv("YOUTUBE_COOKIES")

    if not cookies:
        return None

    cookies = cookies.strip()

    if not cookies:
        return None

    # --------------------------------------------------------
    # Validate Netscape cookie format
    # --------------------------------------------------------

    if not cookies.startswith(
        "# Netscape HTTP Cookie File"
    ):

        raise RuntimeError(
            "YOUTUBE_COOKIES is not in Netscape cookie-file format."
        )

    cookie_path = None

    try:

        # ----------------------------------------------------
        # Create unique temporary file
        # ----------------------------------------------------

        file_descriptor, cookie_path = tempfile.mkstemp(
            prefix="yt_cookies_",
            suffix=".txt",
        )

        # Close the low-level descriptor.
        os.close(file_descriptor)

        # ----------------------------------------------------
        # Write cookie contents
        # ----------------------------------------------------

        Path(cookie_path).write_text(
            cookies,
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # Restrict permissions where supported
        # ----------------------------------------------------

        try:

            os.chmod(
                cookie_path,
                0o600,
            )

        except OSError:
            # Windows may not support Unix-style permissions.
            pass

        return cookie_path

    except Exception:

        # ----------------------------------------------------
        # Remove file if creation failed
        # ----------------------------------------------------

        if cookie_path:

            try:

                os.unlink(
                    cookie_path
                )

            except OSError:
                pass

        raise


def delete_cookie_file(cookie_path):
    """
    Deletes a temporary cookie file after yt-dlp finishes.
    """

    if not cookie_path:
        return

    try:

        os.unlink(
            cookie_path
        )

    except FileNotFoundError:

        pass

    except OSError:

        # Cleanup failure should not break the API response.
        pass


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    return {
        "status": "online",
        "service": "MP34 Downloader API",
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
async def version():

    return {
        "yt_dlp": (
            yt_dlp.version.__version__
            if yt_dlp
            else "not installed"
        )
    }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
async def analyze_link(data: dict):

    # --------------------------------------------------------
    # Validate request body
    # --------------------------------------------------------

    if not isinstance(data, dict):

        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON.",
        )

    raw_url = data.get("url")

    if not raw_url:

        raise HTTPException(
            status_code=422,
            detail="Please provide a media URL.",
        )

    url = validate_url(
        str(raw_url)
    )

    # --------------------------------------------------------
    # Check yt-dlp
    # --------------------------------------------------------

    if yt_dlp is None:

        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed.",
        )

    cookie_file = None

    try:

        # ====================================================
        # YT-DLP OPTIONS
        # ====================================================

        options = {

            "quiet": True,

            "no_warnings": True,

            "skip_download": True,

            "noplaylist": True,

            # ------------------------------------------------
            # JavaScript challenge solving
            # ------------------------------------------------
            #
            # Requires Node.js and yt-dlp-ejs.
            #
            "js_runtimes": {
                "node": {}
            },
        }

        # ====================================================
        # YOUTUBE COOKIES
        # ====================================================

        cookie_file = create_cookie_file()

        if cookie_file:

            options["cookiefile"] = cookie_file

        # ====================================================
        # EXTRACT INFORMATION
        # ====================================================

        with yt_dlp.YoutubeDL(
            options
        ) as downloader:

            info = downloader.extract_info(
                url,
                download=False,
            )

        # ----------------------------------------------------
        # Check result
        # ----------------------------------------------------

        if not info:

            raise HTTPException(
                status_code=422,
                detail="Could not find media information.",
            )

        # ====================================================
        # FORMATS
        # ====================================================

        formats = info.get(
            "formats",
            []
        )

        # ====================================================
        # FIND VIDEO AND AUDIO STREAMS
        # ====================================================

        video_formats = []

        audio_formats = []

        for fmt in formats:

            stream_url = fmt.get(
                "url"
            )

            if not stream_url:
                continue

            video_ext = fmt.get(
                "video_ext"
            )

            audio_ext = fmt.get(
                "audio_ext"
            )

            # ------------------------------------------------
            # Video stream
            # ------------------------------------------------

            if (
                video_ext
                and video_ext != "none"
            ):

                video_formats.append(
                    fmt
                )

            # ------------------------------------------------
            # Audio stream
            # ------------------------------------------------

            if (
                audio_ext
                and audio_ext != "none"
            ):

                audio_formats.append(
                    fmt
                )

        # ====================================================
        # CHECK VIDEO
        # ====================================================

        if not video_formats:

            raise HTTPException(
                status_code=422,
                detail="No downloadable video stream was found.",
            )

        # ====================================================
        # CHECK AUDIO
        # ====================================================

        if not audio_formats:

            raise HTTPException(
                status_code=422,
                detail="No downloadable audio stream was found.",
            )

        # ====================================================
        # VIDEO SELECTION
        # ====================================================

        progressive_video = [

            fmt

            for fmt in video_formats

            if (
                fmt.get("ext") == "mp4"
                and str(
                    fmt.get(
                        "format_id",
                        ""
                    )
                ).lower()
                in {
                    "hd",
                    "sd",
                }
            )
        ]

        if progressive_video:

            video_formats = (
                progressive_video
            )

        # ----------------------------------------------------
        # Video score
        # ----------------------------------------------------

        def video_score(fmt):

            format_id = str(
                fmt.get(
                    "format_id",
                    ""
                )
            ).lower()

            if format_id == "hd":

                quality_bonus = 2_000_000

            elif format_id == "sd":

                quality_bonus = 1_000_000

            else:

                quality_bonus = 0

            width = (
                fmt.get("width")
                or 0
            )

            height = (
                fmt.get("height")
                or 0
            )

            bitrate = (
                fmt.get("tbr")
                or 0
            )

            return (
                quality_bonus
                + (width * height)
                + bitrate
            )

        # ----------------------------------------------------
        # Best video
        # ----------------------------------------------------

        best_video = max(
            video_formats,
            key=video_score,
        )

        # ====================================================
        # AUDIO SELECTION
        # ====================================================

        m4a_audio = [

            fmt

            for fmt in audio_formats

            if fmt.get("ext") == "m4a"
        ]

        if m4a_audio:

            audio_formats = m4a_audio

        # ----------------------------------------------------
        # Audio score
        # ----------------------------------------------------

        def audio_score(fmt):

            return (

                fmt.get("abr")
                or 0,

                fmt.get("tbr")
                or 0,
            )

        # ----------------------------------------------------
        # Best audio
        # ----------------------------------------------------

        best_audio = max(
            audio_formats,
            key=audio_score,
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            # ------------------------------------------------
            # Basic information
            # ------------------------------------------------

            "title": (
                info.get("title")
                or "Untitled media"
            ),

            "thumbnail": (
                info.get("thumbnail")
                or ""
            ),

            "platform": (
                info.get("extractor_key")
                or platform_for(url)
            ),

            "source_url": url,

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

            "video": {

                "url": (
                    best_video.get("url")
                ),

                "format_id": (
                    best_video.get(
                        "format_id"
                    )
                ),

                "extension": (
                    best_video.get("ext")
                    or "mp4"
                ),

                "width": (
                    best_video.get(
                        "width"
                    )
                ),

                "height": (
                    best_video.get(
                        "height"
                    )
                ),

                "resolution": (
                    best_video.get(
                        "resolution"
                    )
                ),
            },

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            "audio": {

                "url": (
                    best_audio.get("url")
                ),

                "format_id": (
                    best_audio.get(
                        "format_id"
                    )
                ),

                "extension": (
                    best_audio.get("ext")
                    or "m4a"
                ),

                "abr": (
                    best_audio.get("abr")
                ),
            },

            # ------------------------------------------------
            # AVAILABLE OUTPUTS
            # ------------------------------------------------

            "available_formats": [
                "mp3",
                "mp4",
            ],
        }

    # ========================================================
    # HTTP EXCEPTIONS
    # ========================================================

    except HTTPException:

        raise

    # ========================================================
    # GENERAL ERRORS
    # ========================================================

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not analyse this link: {error}"
            ),
        ) from error

    finally:

        # ====================================================
        # DELETE TEMPORARY COOKIE FILE
        # ====================================================

        delete_cookie_file(
            cookie_file
        )


# ============================================================
# VALIDATE STREAMS
# ============================================================

@app.post("/validate-streams")
async def validate_streams(data: dict):

    # --------------------------------------------------------
    # Validate request
    # --------------------------------------------------------

    if not isinstance(data, dict):

        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON.",
        )

    video_url = data.get(
        "video_url"
    )

    audio_url = data.get(
        "audio_url"
    )

    if not video_url:

        raise HTTPException(
            status_code=422,
            detail="video_url is required.",
        )

    if not audio_url:

        raise HTTPException(
            status_code=422,
            detail="audio_url is required.",
        )

    # ========================================================
    # REQUEST HEADERS
    # ========================================================

    headers = {

        "User-Agent": (
            "facebookexternalhit/1.1"
        ),

        "Accept": "*/*",
    }

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
        ) as client:

            # ================================================
            # VIDEO
            # ================================================

            video_response = (
                await client.head(
                    video_url,
                    headers=headers,
                )
            )

            # ================================================
            # AUDIO
            # ================================================

            audio_response = (
                await client.head(
                    audio_url,
                    headers=headers,
                )
            )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "video": {

                "status_code": (
                    video_response.status_code
                ),

                "content_type": (
                    video_response.headers.get(
                        "content-type"
                    )
                ),

                "content_length": (
                    video_response.headers.get(
                        "content-length"
                    )
                ),

                "accessible": (
                    video_response.status_code < 400
                ),
            },

            "audio": {

                "status_code": (
                    audio_response.status_code
                ),

                "content_type": (
                    audio_response.headers.get(
                        "content-type"
                    )
                ),

                "content_length": (
                    audio_response.headers.get(
                        "content-length"
                    )
                ),

                "accessible": (
                    audio_response.status_code < 400
                ),
            },
        }

    except Exception as error:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not validate media streams: {error}"
            ),
        )

