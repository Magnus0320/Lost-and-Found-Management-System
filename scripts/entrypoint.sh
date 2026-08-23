#!/bin/sh
# Container entrypoint.
#
# Migrations run to completion BEFORE uvicorn starts. Because the container
# HEALTHCHECK polls the API's /health endpoint, and /health cannot answer until
# uvicorn is listening, the container can only ever report healthy after the
# schema is fully migrated.
set -e

echo "[entrypoint] Applying database migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete. Current revision:"
alembic current

echo "[entrypoint] Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
