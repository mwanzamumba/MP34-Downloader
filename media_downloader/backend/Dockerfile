FROM python:3.12-slim

WORKDIR /app

# ------------------------------------------------------------
# Install FFmpeg and Node.js
# ------------------------------------------------------------

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Python dependencies
# ------------------------------------------------------------

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Application
# ------------------------------------------------------------

COPY . .

# ------------------------------------------------------------
# Verify important dependencies during build
# ------------------------------------------------------------

RUN echo "===== NODE =====" \
    && node --version

RUN echo "===== FFMPEG =====" \
    && ffmpeg -version

RUN echo "===== YT-DLP =====" \
    && python -m yt_dlp --version

# ------------------------------------------------------------
# Render
# ------------------------------------------------------------

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]