# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

ARG APP_UID=1000
# GID 101 coincide con el grupo "nginx" de la imagen web y permite lectura de los PDF.
ARG MEDIA_GID=101
ARG DJANGO_ENV=production

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tar gzip \
    && rm --recursive --force /var/lib/apt/lists/* \
    && groupadd --gid "${MEDIA_GID}" media \
    && useradd --uid "${APP_UID}" --gid "${MEDIA_GID}" --create-home --shell /usr/sbin/nologin app

COPY requirements/ ./requirements/

RUN pip install --no-cache-dir --requirement "requirements/${DJANGO_ENV}.txt"

COPY manage.py ./
COPY pytest.ini ./
COPY config/ ./config/
COPY apps/ ./apps/
COPY tests/ ./tests/

RUN install --directory --mode 0750 /app/staticfiles /data/media \
    && chown --recursive app:media /app /data/media

USER app

EXPOSE 8000

CMD ["sh", "-c", "umask 0027; exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120 --access-logfile -"]
