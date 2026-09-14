from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

app = FastAPI(title='Media Downloader API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
DOWNLOADS_DIR = Path(__file__).parent / 'downloads'

def validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise HTTPException(status_code=422, detail='Provide a valid http or https URL.')
    return value

def platform_for(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for domain, name in [('tiktok.com', 'TikTok'), ('youtube.com', 'YouTube'), ('youtu.be', 'YouTube'), ('instagram.com', 'Instagram'), ('facebook.com', 'Facebook'), ('x.com', 'X / Twitter')]:
        if domain in host:
            return name
    return 'Other'

@app.post('/analyze')
async def analyze_link(data: dict):
    url = validate_url(str(data.get('url', '')))
    platform = platform_for(url)
    if yt_dlp is None:
        return {'title': urlparse(url).netloc, 'thumbnail': '', 'platform': platform, 'source_url': url}
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'noplaylist': True}) as downloader:
            info = downloader.extract_info(url, download=False)
        return {'title': info.get('title') or urlparse(url).netloc, 'thumbnail': info.get('thumbnail') or '', 'platform': info.get('extractor_key') or platform, 'source_url': url}
    except Exception as error:
        raise HTTPException(status_code=422, detail=f'Could not analyse this link: {error}') from error

@app.post('/download')
async def download_link(data: dict):
    url = validate_url(str(data.get('url', '')))
    if yt_dlp is None:
        raise HTTPException(status_code=503, detail='Install backend requirements first: pip install -r requirements.txt')
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    try:
        options = {'outtmpl': str(DOWNLOADS_DIR / '%(title).150s.%(ext)s'), 'noplaylist': True, 'format': 'best'}
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            file_name = Path(downloader.prepare_filename(info)).name
        return {'file_name': file_name}
    except Exception as error:
        raise HTTPException(status_code=422, detail=f'Download failed: {error}') from error
