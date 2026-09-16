import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Media Downloader API",
    description="Media analysis API using yt-dlp",
    version="1.0.0",
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

class AnalyzeRequest(BaseModel):
    url: str


# ============================================================
# URL VALIDATION
# ============================================================

SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",

    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",

    "instagram.com",
    "www.instagram.com",

    "facebook.com",
    "www.facebook.com",
    "fb.watch",

    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
}


def validate_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (parsed.hostname or "").lower()

        return hostname in SUPPORTED_HOSTS

    except Exception:
        return False


def platform_for(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()

    if "youtube.com" in hostname or "youtu.be" in hostname:
        return "YouTube"

    if "tiktok.com" in hostname:
        return "TikTok"

    if "instagram.com" in hostname:
        return "Instagram"

    if "facebook.com" in hostname or "fb.watch" in hostname:
        return "Facebook"

    if "twitter.com" in hostname or "x.com" in hostname:
        return "X"

    return "Unknown"


# ============================================================
# YOUTUBE COOKIES
# ============================================================

def create_cookie_file():
    """
    Reads YOUTUBE_COOKIES from the Render environment and
    creates a temporary Netscape cookies.txt file.

    The actual cookie contents are never returned by the API.
    """

    cookie_data = os.getenv("YOUTUBE_COOKIES", "").strip()

    if not cookie_data:
        return None

    if not cookie_data.startswith("# Netscape HTTP Cookie File"):
        raise RuntimeError(
            "YOUTUBE_COOKIES does not appear to be a valid "
            "Netscape cookies.txt file."
        )

    fd, cookie_path = tempfile.mkstemp(
        prefix="yt_cookies_",
        suffix=".txt"
    )

    try:
        os.close(fd)

        Path(cookie_path).write_text(
            cookie_data,
            encoding="utf-8"
        )

        try:
            os.chmod(cookie_path, 0o600)
        except Exception:
            pass

        return cookie_path

    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass

        try:
            os.remove(cookie_path)
        except Exception:
            pass

        raise


def delete_cookie_file(cookie_path):
    """
    Deletes the temporary cookie file.
    """

    if not cookie_path:
        return

    try:
        os.remove(cookie_path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ============================================================
# YT-DLP OPTIONS
# ============================================================

def get_ytdlp_options():
    """
    Common yt-dlp configuration.

    Node.js is used for yt-dlp JavaScript challenge solving.
    """

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,

        # yt-dlp-ejs + Node.js
        "js_runtimes": {
            "node": {}
        },
    }

    cookie_file = create_cookie_file()

    if cookie_file:
        options["cookiefile"] = cookie_file

    return options, cookie_file


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Media Downloader API",
        "yt_dlp_installed": yt_dlp is not None,
        "node_available": shutil.which("node") is not None,
        "youtube_cookies_configured": bool(
            os.getenv("YOUTUBE_COOKIES")
        ),
    }


# ============================================================
# VERSION
# ============================================================

@app.get("/version")
def version():
    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is not installed"
        )

    return {
        "yt_dlp_version": yt_dlp.version.__version__,
        "node_available": shutil.which("node") is not None,
    }


# ============================================================
# DEBUG YOUTUBE CONFIGURATION
# ============================================================

@app.get("/debug-youtube")
def debug_youtube():

    cookies = os.getenv("YOUTUBE_COOKIES", "")

    return {
        "cookies_configured": bool(cookies),
        "cookies_length": len(cookies),

        # Only show the beginning of the file.
        # NEVER return the actual cookie contents.
        "cookies_header": cookies[:40] if cookies else "",

        "node_available": shutil.which("node") is not None,

        "yt_dlp_version": (
            yt_dlp.version.__version__
            if yt_dlp
            else None
        ),
    }


# ============================================================
# DEBUG FORMATS
# ============================================================

@app.post("/debug-formats")
def debug_formats(request: AnalyzeRequest):

    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is not installed"
        )

    url = request.url.strip()

    if not validate_url(url):
        raise HTTPException(
            status_code=400,
            detail="Unsupported or invalid URL"
        )

    options = None
    cookie_file = None

    try:

        options, cookie_file = get_ytdlp_options()

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False
            )

        formats = info.get("formats", [])

        results = []

        for f in formats:

            results.append({
                "format_id": f.get("format_id"),

                "ext": f.get("ext"),

                "format_note": f.get("format_note"),

                "width": f.get("width"),
                "height": f.get("height"),

                "resolution": f.get("resolution"),

                "fps": f.get("fps"),

                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),

                "abr": f.get("abr"),
                "vbr": f.get("vbr"),
                "tbr": f.get("tbr"),

                "filesize": f.get("filesize"),
                "filesize_approx": f.get(
                    "filesize_approx"
                ),

                "protocol": f.get("protocol"),
            })

        return {
            "title": info.get("title"),

            "platform": platform_for(url),

            "format_count": len(results),

            "formats": results,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=422,
            detail=f"Could not inspect formats: {str(exc)}"
        )

    finally:

        delete_cookie_file(cookie_file)


# ============================================================
# ANALYZE
# ============================================================

@app.post("/analyze")
def analyze(request: AnalyzeRequest):

    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is not installed"
        )

    url = request.url.strip()

    if not validate_url(url):
        raise HTTPException(
            status_code=400,
            detail="Unsupported or invalid URL"
        )

    options = None
    cookie_file = None

    try:

        options, cookie_file = get_ytdlp_options()

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False
            )

        formats = info.get("formats", [])

        if not formats:
            raise HTTPException(
                status_code=422,
                detail="No downloadable formats were found."
            )

        # ====================================================
        # VIDEO FORMATS
        # ====================================================

        video_formats = [
            f for f in formats
            if f.get("vcodec")
            and f.get("vcodec") != "none"
        ]

        # ====================================================
        # AUDIO FORMATS
        # ====================================================

        audio_formats = [
            f for f in formats
            if f.get("acodec")
            and f.get("acodec") != "none"
        ]

        # ====================================================
        # PREFER PROGRESSIVE MP4
        #
        # Progressive = contains BOTH video and audio.
        # This is important because YouTube may return
        # format 18 instead of separate video/audio streams.
        # ====================================================

        progressive_mp4 = [
            f for f in formats
            if (
                f.get("ext") == "mp4"
                and f.get("vcodec")
                and f.get("vcodec") != "none"
                and f.get("acodec")
                and f.get("acodec") != "none"
            )
        ]

        # ====================================================
        # SELECT VIDEO
        # ====================================================

        selected_video = None

        if progressive_mp4:

            selected_video = max(
                progressive_mp4,
                key=lambda f: (
                    (f.get("height") or 0),
                    (f.get("width") or 0),
                    (f.get("tbr") or 0),
                )
            )

        elif video_formats:

            selected_video = max(
                video_formats,
                key=lambda f: (
                    (f.get("height") or 0),
                    (f.get("width") or 0),
                    (f.get("tbr") or 0),
                )
            )

        # ====================================================
        # SELECT AUDIO
        # ====================================================

        selected_audio = None

        audio_only_formats = [
            f for f in formats
            if (
                f.get("acodec")
                and f.get("acodec") != "none"
                and (
                    not f.get("vcodec")
                    or f.get("vcodec") == "none"
                )
            )
        ]

        if audio_only_formats:

            # Prefer M4A
            m4a_formats = [
                f for f in audio_only_formats
                if f.get("ext") == "m4a"
            ]

            candidates = (
                m4a_formats
                if m4a_formats
                else audio_only_formats
            )

            selected_audio = max(
                candidates,
                key=lambda f: (
                    (f.get("abr") or 0),
                    (f.get("tbr") or 0),
                )
            )

        elif selected_video:

            # Progressive format already contains audio.
            selected_audio = selected_video

        # ====================================================
        # VALIDATION
        # ====================================================

        if selected_video is None:
            raise HTTPException(
                status_code=422,
                detail="No downloadable video stream was found."
            )

        if selected_audio is None:
            raise HTTPException(
                status_code=422,
                detail="No downloadable audio stream was found."
            )

        # ====================================================
        # VIDEO RESPONSE
        # ====================================================

        video_data = {
            "url": selected_video.get("url"),

            "format_id": selected_video.get("format_id"),

            "extension": selected_video.get("ext"),

            "width": selected_video.get("width"),

            "height": selected_video.get("height"),

            "resolution": selected_video.get(
                "resolution"
            ),

            "fps": selected_video.get("fps"),

            "vcodec": selected_video.get("vcodec"),

            "acodec": selected_video.get("acodec"),

            "tbr": selected_video.get("tbr"),
        }

        # ====================================================
        # AUDIO RESPONSE
        # ====================================================

        audio_data = {
            "url": selected_audio.get("url"),

            "format_id": selected_audio.get("format_id"),

            "extension": selected_audio.get("ext"),

            "acodec": selected_audio.get("acodec"),

            "abr": selected_audio.get("abr"),

            "tbr": selected_audio.get("tbr"),

            "is_progressive": (
                selected_audio.get("vcodec")
                and selected_audio.get("vcodec") != "none"
            ),
        }

        # ====================================================
        # AVAILABLE FORMATS
        # ====================================================

        available_formats = [
            "mp4",
            "mp3",
        ]

        # ====================================================
        # RESPONSE
        # ====================================================

        return {
            "title": info.get("title"),

            "thumbnail": info.get("thumbnail"),

            "platform": platform_for(url),

            "source_url": url,

            "duration": info.get("duration"),

            "video": video_data,

            "audio": audio_data,

            "available_formats": available_formats,
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=422,
            detail=f"Could not analyse this link: {str(exc)}"
        )

    finally:

        delete_cookie_file(cookie_file)


# ============================================================
# VALIDATE STREAMS
# ============================================================

@app.post("/validate-streams")
async def validate_streams(request: AnalyzeRequest):

    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail="yt-dlp is not installed"
        )

    url = request.url.strip()

    if not validate_url(url):
        raise HTTPException(
            status_code=400,
            detail="Unsupported or invalid URL"
        )

    options = None
    cookie_file = None

    try:

        options, cookie_file = get_ytdlp_options()

        with yt_dlp.YoutubeDL(options) as downloader:

            info = downloader.extract_info(
                url,
                download=False
            )

        formats = info.get("formats", [])

        video_formats = [
            f for f in formats
            if f.get("vcodec")
            and f.get("vcodec") != "none"
        ]

        audio_formats = [
            f for f in formats
            if f.get("acodec")
            and f.get("acodec") != "none"
        ]

        selected_video = None
        selected_audio = None

        if video_formats:

            selected_video = max(
                video_formats,
                key=lambda f: (
                    (f.get("height") or 0),
                    (f.get("width") or 0),
                    (f.get("tbr") or 0),
                )
            )

        audio_only = [
            f for f in audio_formats
            if not f.get("vcodec")
            or f.get("vcodec") == "none"
        ]

        if audio_only:

            selected_audio = max(
                audio_only,
                key=lambda f: (
                    (f.get("abr") or 0),
                    (f.get("tbr") or 0),
                )
            )

        elif selected_video:

            if (
                selected_video.get("acodec")
                and selected_video.get("acodec") != "none"
            ):
                selected_audio = selected_video

        result = {
            "video": None,
            "audio": None,
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0
        ) as client:

            if selected_video and selected_video.get("url"):

                try:

                    response = await client.head(
                        selected_video["url"]
                    )

                    result["video"] = {
                        "status_code": response.status_code,
                        "available": response.status_code < 400,
                    }

                except Exception as exc:

                    result["video"] = {
                        "available": False,
                        "error": str(exc),
                    }

            if selected_audio and selected_audio.get("url"):

                try:

                    response = await client.head(
                        selected_audio["url"]
                    )

                    result["audio"] = {
                        "status_code": response.status_code,
                        "available": response.status_code < 400,
                    }

                except Exception as exc:

                    result["audio"] = {
                        "available": False,
                        "error": str(exc),
                    }

        return result

    except Exception as exc:

        raise HTTPException(
            status_code=422,
            detail=f"Could not validate streams: {str(exc)}"
        )

    finally:

        delete_cookie_file(cookie_file)
