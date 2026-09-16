FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

# -----------------------------
# VERIFY NODE
# -----------------------------
RUN echo "========================================" \
    && echo "NODE VERSION" \
    && node --version \
    && echo "NODE PATH" \
    && which node \
    && echo "========================================"

# -----------------------------
# VERIFY NPM
# -----------------------------
RUN echo "========================================" \
    && echo "NPM VERSION" \
    && npm --version \
    && echo "========================================"

# -----------------------------
# VERIFY FFMPEG
# -----------------------------
RUN echo "========================================" \
    && echo "FFMPEG VERSION" \
    && ffmpeg -version \
    && echo "========================================"

# -----------------------------
# VERIFY FFPROBE
# -----------------------------
RUN echo "========================================" \
    && echo "FFPROBE VERSION" \
    && ffprobe -version \
    && echo "========================================"

# -----------------------------
# VERIFY YT-DLP
# -----------------------------
RUN echo "========================================" \
    && echo "YT-DLP VERSION" \
    && python -m yt_dlp --version \
    && echo "========================================"

# -----------------------------
# VERIFY EJS
# -----------------------------
RUN echo "========================================" \
    && echo "YT-DLP-EJS PACKAGE" \
    && python -m pip show yt-dlp-ejs \
    && echo "========================================"

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]