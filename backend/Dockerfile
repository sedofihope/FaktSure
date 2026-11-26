FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
    STORAGE_ROOT=/data/documents

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --retries 10 --timeout 300 -r requirements.txt
ENV HOME=/home/app

COPY --chown=10001:10001 backend/app ./app
COPY --chown=10001:10001 backend/alembic ./alembic
COPY --chown=10001:10001 backend/alembic.ini ./alembic.ini
COPY --chown=10001:10001 scripts/create_admin.py ./scripts/create_admin.py
COPY --chown=10001:10001 backend/docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod 0555 /app/docker-entrypoint.sh \
    && mkdir -p /data/documents /home/app \
    && chown -R 10001:10001 /data /home/app

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
