FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Install dependencies first so layer caching survives source edits.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
# Alembic is the source of truth for the schema; the image needs both.
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
# Browser UI served by StaticFiles at /app.
COPY frontend ./frontend

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# Migrations run in the entrypoint, before uvicorn binds the port, so the
# HEALTHCHECK above can only pass once the schema is up to date.
ENTRYPOINT ["/srv/scripts/entrypoint.sh"]
