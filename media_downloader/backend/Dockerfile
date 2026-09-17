FROM node:20-bookworm-slim

# ============================================================
# ENVIRONMENT
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV BGUTIL_SERVER_HOME=/opt/bgutil-ytdlp-pot-provider/server
ENV POT_PROVIDER_URL=http://127.0.0.1:4416

ENV YTDLP_NO_UPDATE=1


# ============================================================
# SYSTEM DEPENDENCIES
# ============================================================

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ffmpeg \
        git \
        curl \
        ca-certificates \
        build-essential \
        pkg-config \
        libcairo2-dev \
        libpango1.0-dev \
        libjpeg-dev \
        libgif-dev \
        librsvg2-dev \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# PYTHON
# ============================================================

WORKDIR /app

COPY requirements.txt .

RUN python3 -m pip install \
        --break-system-packages \
        --no-cache-dir \
        --upgrade pip \
    && python3 -m pip install \
        --break-system-packages \
        --no-cache-dir \
        -r requirements.txt


# ============================================================
# BGUTIL PO TOKEN PROVIDER
# ============================================================

WORKDIR /opt

RUN git clone \
        --single-branch \
        --branch 2.0.0 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        bgutil-ytdlp-pot-provider


WORKDIR /opt/bgutil-ytdlp-pot-provider/server

RUN npm ci \
    && npx tsc


# ============================================================
# APPLICATION
# ============================================================

WORKDIR /app

COPY . .


# ============================================================
# DOWNLOAD DIRECTORY
# ============================================================

RUN mkdir -p /app/downloads \
    && mkdir -p /app/runtime


# ============================================================
# STARTUP
# ============================================================

CMD sh -c '\
    echo "Starting BgUtils PO Token provider..." && \
    node /opt/bgutil-ytdlp-pot-provider/server/build/main.js \
        --host 127.0.0.1 \
        --port 4416 \
        > /tmp/bgutil-provider.log 2>&1 & \
    echo "Waiting for PO Token provider..." && \
    for i in $(seq 1 30); do \
        if curl -fsS http://127.0.0.1:4416/ >/dev/null 2>&1; then \
            echo "PO Token provider is ready." && \
            break; \
        fi; \
        sleep 1; \
    done && \
    echo "Starting FastAPI..." && \
    exec python3 -m uvicorn main:app \
        --host 0.0.0.0 \
        --port ${PORT:-10000} \
'