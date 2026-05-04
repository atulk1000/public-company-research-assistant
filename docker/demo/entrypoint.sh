#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/venv/bin:$PATH"
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/company_assistant}"
export POSTGRES_DB="${POSTGRES_DB:-company_assistant}"
export POSTGRES_USER="${POSTGRES_USER:-postgres}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

BOOTSTRAP_MARKER="/var/lib/postgresql/data/.demo_bootstrapped_v1"

echo "Starting embedded Postgres..."
/usr/local/bin/docker-entrypoint.sh postgres &
POSTGRES_PID=$!

API_PID=""
UI_PID=""

cleanup() {
  set +e
  if [[ -n "${API_PID}" ]]; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  if [[ -n "${UI_PID}" ]]; then
    kill "${UI_PID}" 2>/dev/null || true
  fi
  kill "${POSTGRES_PID}" 2>/dev/null || true
}

trap cleanup EXIT SIGINT SIGTERM

echo "Waiting for Postgres to accept connections..."
until pg_isready -h localhost -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
  sleep 1
done

if [[ ! -f "${BOOTSTRAP_MARKER}" ]]; then
  echo "Initializing demo database..."
  psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}" -f /app/db/schema.sql
  psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}" -f /app/db/seed.sql
  psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}" -f /app/db/views.sql
  python /app/ingestion/bootstrap_from_raw.py
  touch "${BOOTSTRAP_MARKER}"
else
  echo "Demo database already bootstrapped; reusing existing local state."
fi

echo "Starting API on port 8000..."
uvicorn app.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "Starting Streamlit UI on port 8501..."
streamlit run app/ui_streamlit.py --server.port=8501 --server.address=0.0.0.0 &
UI_PID=$!

wait -n "${POSTGRES_PID}" "${API_PID}" "${UI_PID}"
