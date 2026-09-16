from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from cookies_unlock import install_cookie_unlock

install_cookie_unlock()

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


app = FastAPI(title="MP34 Downloader API")


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

    url = validate_url(str(raw_url))

    if yt_dlp is None:
        raise HTTPException(
            status_code=503,
            detail="yt-dlp is not installed.",
        )

    try:

        # ----------------------------------------------------
        # YT-DLP OPTIONS
        # ----------------------------------------------------

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        # ----------------------------------------------------
        # EXTRACT INFORMATION
        # ----------------------------------------------------

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False,
            )

        if not info:
            raise HTTPException(
                status_code=422,
                detail="Could not find media information.",
            )

        formats = info.get("formats", [])

        # ----------------------------------------------------
        # FIND VIDEO AND AUDIO STREAMS
        # ----------------------------------------------------

        video_formats = []
        audio_formats = []

        for fmt in formats:

            stream_url = fmt.get("url")

            if not stream_url:
                continue

            video_ext = fmt.get("video_ext")
            audio_ext = fmt.get("audio_ext")

            # Video stream
            if (
                video_ext
                and video_ext != "none"
            ):
                video_formats.append(fmt)

            # Audio stream
            if (
                audio_ext
                and audio_ext != "none"
            ):
                audio_formats.append(fmt)

        # ----------------------------------------------------
        # CHECK VIDEO
        # ----------------------------------------------------

        if not video_formats:
            raise HTTPException(
                status_code=422,
                detail="No downloadable video stream was found.",
            )

        # ----------------------------------------------------
        # CHECK AUDIO
        # ----------------------------------------------------

        if not audio_formats:
            raise HTTPException(
                status_code=422,
                detail="No downloadable audio stream was found.",
            )

        # ====================================================
        # VIDEO SELECTION
        # ====================================================

        # Prefer Facebook-style progressive MP4 formats
        # such as "hd" and "sd".

        progressive_video = [
            fmt
            for fmt in video_formats
            if (
                fmt.get("ext") == "mp4"
                and str(fmt.get("format_id", "")).lower()
                in {"hd", "sd"}
            )
        ]

        if progressive_video:
            video_formats = progressive_video

        def video_score(fmt):

            format_id = str(
                fmt.get("format_id", "")
            ).lower()

            # Explicit quality preference.
            if format_id == "hd":
                quality_bonus = 2_000_000

            elif format_id == "sd":
                quality_bonus = 1_000_000

            else:
                quality_bonus = 0

            width = fmt.get("width") or 0
            height = fmt.get("height") or 0
            bitrate = fmt.get("tbr") or 0

            return (
                quality_bonus
                + (width * height)
                + bitrate
            )

        best_video = max(
            video_formats,
            key=video_score,
        )

        # ====================================================
        # AUDIO SELECTION
        # ====================================================

        # Prefer M4A/AAC because it can later be converted
        # to MP3 on the phone.

        m4a_audio = [
            fmt
            for fmt in audio_formats
            if fmt.get("ext") == "m4a"
        ]

        if m4a_audio:
            audio_formats = m4a_audio

        def audio_score(fmt):

            return (
                fmt.get("abr") or 0,
                fmt.get("tbr") or 0,
            )

        best_audio = max(
            audio_formats,
            key=audio_score,
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

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

                "url": best_video.get("url"),

                "format_id": (
                    best_video.get("format_id")
                ),

                "extension": (
                    best_video.get("ext")
                    or "mp4"
                ),

                "width": (
                    best_video.get("width")
                ),

                "height": (
                    best_video.get("height")
                ),

                "resolution": (
                    best_video.get("resolution")
                ),
            },

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            "audio": {

                "url": best_audio.get("url"),

                "format_id": (
                    best_audio.get("format_id")
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

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not analyse this link: {error}"
            ),
        ) from error


# ============================================================
# VALIDATE STREAMS
# ============================================================

@app.post("/validate-streams")
async def validate_streams(data: dict):

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be JSON.",
        )

    video_url = data.get("video_url")
    audio_url = data.get("audio_url")

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

    headers = {
        "User-Agent": "facebookexternalhit/1.1",
        "Accept": "*/*",
    }

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
        ) as client:

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

            video_response = await client.head(
                video_url,
                headers=headers,
            )

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            audio_response = await client.head(
                audio_url,
                headers=headers,
            )

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
        ) from error