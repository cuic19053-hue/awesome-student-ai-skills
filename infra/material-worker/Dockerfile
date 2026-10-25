FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MATERIAL_PIPELINE_ENABLED=true MATERIAL_CHROMIUM_PATH=/usr/bin/chromium \
    MATERIAL_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
    MATERIAL_API_URL=https://agent.stardust.website \
    HOME=/home/worker
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium libreoffice-writer fonts-noto-cjk ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONPATH=/app:/app/server
COPY infra/material-worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/worker-requirements.txt \
    && useradd --create-home --uid 10001 worker
ARG APP_VERSION=unknown
ENV APP_VERSION=$APP_VERSION
COPY server /app/server
COPY utils /app/utils
COPY subskills /app/subskills
COPY index.json /app/index.json
USER worker
CMD ["python", "server/material_worker.py"]
