# Voice engine + build toolchain in one image.
#
# CPU by default. For GPU, swap the base for an nvidia/cuda runtime image and
# install the matching torch wheels, then run with `--gpus all`.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    NODE_MAJOR=22

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium curl ca-certificates gnupg fonts-liberation \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first so the torch layer is cached across code changes.
COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

COPY . .

ENV CHROME_PATH=/usr/bin/chromium \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    FFPROBE_PATH=/usr/bin/ffprobe \
    VOICE_HOST=0.0.0.0 \
    VOICE_PORT=5651 \
    VOICE_SAMPLES_DIR=/app/engine/voices \
    VOICE_DATA_DIR=/app/engine/data \
    OUTPUT_DIR=/app/output

EXPOSE 5651
CMD ["python", "engine/engine.py"]
