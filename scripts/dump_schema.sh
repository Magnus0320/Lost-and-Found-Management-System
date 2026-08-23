#!/bin/sh
# Regenerate schema.sql from the running compose database.
#
#   ./scripts/dump_schema.sh
#
# Requires `docker compose up` to be running. The pg_dump \restrict /
# \unrestrict nonce lines are stripped: they are per-session tokens that change
# on every dump and would otherwise produce a spurious diff each time.
set -e

OUT="${1:-schema.sql}"
DB_USER="${POSTGRES_USER:-lostfound}"
DB_NAME="${POSTGRES_DB:-lostfound}"

REVISION=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT version_num FROM alembic_version" 2>/dev/null || echo "unknown")

{
  echo "-- ============================================================"
  echo "-- GENERATED FILE - DO NOT EDIT BY HAND."
  echo "--"
  echo "-- This is a point-in-time snapshot of the schema, dumped with"
  echo "-- pg_dump --schema-only for readability and review."
  echo "--"
  echo "-- It is NOT the source of truth. The Alembic migrations under"
  echo "-- migrations/versions/ are. Editing this file changes nothing;"
  echo "-- to change the schema, edit app/db/models.py, generate a"
  echo "-- migration, apply it, then regenerate this file with:"
  echo "--"
  echo "--     ./scripts/dump_schema.sh"
  echo "--"
  echo "-- Alembic revision at time of dump: $REVISION"
  echo "-- ============================================================"
  echo
  docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" \
      --schema-only --no-owner --no-privileges \
    | grep -vE '^\\(un)?restrict '
} > "$OUT"

echo "Wrote $OUT ($(wc -l < "$OUT" | tr -d ' ') lines, revision $REVISION)"
