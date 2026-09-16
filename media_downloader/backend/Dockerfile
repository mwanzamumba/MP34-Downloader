FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo "===== NODE =====" \
    && node --version

RUN echo "===== NPM =====" \
    && npm --version

RUN echo "===== FFMPEG =====" \
    && ffmpeg -version

RUN echo "===== FFPROBE =====" \
    && ffprobe -version

RUN echo "===== YT-DLP =====" \
    && python -m yt_dlp --version

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]