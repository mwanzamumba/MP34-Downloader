FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ============================================================
# SYSTEM PACKAGES
# ============================================================

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# NODE.JS 20+
# ============================================================

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version \
    && npm --version \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# APP
# ============================================================

WORKDIR /app

# ============================================================
# PYTHON DEPENDENCIES
# ============================================================

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ============================================================
# BGUTIL PO TOKEN PROVIDER
# ============================================================

RUN git clone \
        --single-branch \
        --branch 2.0.0 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        /opt/bgutil-ytdlp-pot-provider

RUN cd /opt/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc

# ============================================================
# APPLICATION
# ============================================================

COPY . .

RUN mkdir -p /app/downloads

# ============================================================
# START BOTH SERVICES
# ============================================================

CMD ["sh", "-c", "node /opt/bgutil-ytdlp-pot-provider/server/build/main.js --host 127.0.0.1 --port 4416 & uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]