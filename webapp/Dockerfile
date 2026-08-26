# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev


FROM python:3.14-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    SECRET_KEY=collectstatic-build-only \
    DB_NAME=collectstatic \
    DB_USER=collectstatic \
    DB_PASSWORD=collectstatic \
    GOOGLE_OAUTH_CLIENT_ID=collectstatic \
    GOOGLE_OAUTH_CLIENT_SECRET=collectstatic \
    ALLOWED_HOSTS=localhost

RUN python manage.py collectstatic --noinput

USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
