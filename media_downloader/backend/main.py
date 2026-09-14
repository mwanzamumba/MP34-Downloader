from pathlib import Path
from urllib.parse import urlparse
import tempfile

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


app = FastAPI(title='Media Downloader API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def validate_url(value: str) -> str:
    parsed = urlparse(value)

    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail='Provide a valid http or https URL.'
        )

    return value


def platform_for(url: str) -> str:
    host = urlparse(url).netloc.lower()

    for domain, name in [
        ('tiktok.com', 'TikTok'),
        ('youtube.com', 'YouTube'),
        ('youtu.be', 'YouTube'),
        ('instagram.com', 'Instagram'),
        ('facebook.com', 'Facebook'),
        ('x.com', 'X / Twitter'),
    ]:
        if domain in host:
            return name

    return 'Other'


@app.post('/analyze')
async def analyze_link(data: dict):
    url = validate_url(str(data.get('url', '')))
    platform = platform_for(url)

    if yt_dlp is None:
        return {
            'title': urlparse(url).netloc,
            'thumbnail': '',
            'platform': platform,
            'source_url': url,
        }

    try:
        with yt_dlp.YoutubeDL({
            'quiet': True,
            'skip_download': True,
            'noplaylist': True,
        }) as downloader:

            info = downloader.extract_info(
                url,
                download=False,
            )

        return {
            'title': info.get('title') or urlparse(url).netloc,
            'thumbnail': info.get('thumbnail') or '',
            'platform': info.get('extractor_key') or platform,
            'source_url': url,
        }

    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f'Could not analyse this link: {error}'
        ) from error


@app.post('/download')
async def download_link(
    data: dict,
    background_tasks: BackgroundTasks,
):
    url = validate_url(str(data.get('url', '')))

    if yt_dlp is None:
        raise HTTPException(
            status_code=503,
            detail='yt-dlp is not installed.'
        )

    # Create a temporary directory for this download.
    temp_dir = Path(
        tempfile.mkdtemp(prefix='media_download_')
    )

    try:
        output_template = str(
            temp_dir / '%(title).150s.%(ext)s'
        )

        options = {
            'quiet': True,
            'noplaylist': True,
            'format': 'best',
            'outtmpl': output_template,
        }

        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(
                url,
                download=True,
            )

            file_path = Path(
                downloader.prepare_filename(info)
            )

        if not file_path.exists():
            raise HTTPException(
                status_code=500,
                detail='The media file was not created.'
            )

        # Remove the temporary directory after
        # FastAPI has finished sending the file.
        background_tasks.add_task(
            cleanup_download,
            temp_dir,
        )

        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type='application/octet-stream',
        )

    except HTTPException:
        cleanup_download(temp_dir)
        raise

    except Exception as error:
        cleanup_download(temp_dir)

        raise HTTPException(
            status_code=422,
            detail=f'Download failed: {error}'
        ) from error


def cleanup_download(directory: Path):
    """Delete a temporary download directory."""

    try:
        if directory.exists():
            for file in directory.iterdir():
                if file.is_file():
                    file.unlink()

            directory.rmdir()

    except Exception:
        pass


@app.get('/version')
async def version():
    return {
        'yt_dlp': yt_dlp.version.__version__
    }