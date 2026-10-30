#!/usr/bin/env bash
# Integration tests: throwaway Postgres + fixture data + pytest, all inside Docker.
# Runs the same way on a laptop (Git Bash / WSL / Linux) and inside Jenkins (no host bind mounts needed).
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
rm -f backend/integration-report.xml   # never publish a stale report from an earlier run

ID="$$"
NET="it-net-$ID"; DB="it-pg-$ID"; TC="it-tests-$ID"; IMG="securehr/backend-tests:it"
PW="it-portal-app-pw"

cleanup() {
  docker rm -f "$TC" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo ">> starting throwaway Postgres"
docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" -e POSTGRES_DB=employees -e POSTGRES_PASSWORD=postgres postgres:16 >/dev/null

# Connect over TCP: the image's temporary init server only listens on a unix socket, so this waits for the real one.
ready=0
for _ in $(seq 1 60); do
  if docker exec -e PGPASSWORD=postgres "$DB" psql -h 127.0.0.1 -U postgres -d employees -Atc 'select 1' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [ "$ready" != 1 ]; then echo "Postgres did not start"; docker logs "$DB" | tail -20; exit 1; fi

psqlx() {
  docker exec -i -e PGPASSWORD=postgres -e PORTAL_APP_PASSWORD="$PW" "$DB" \
    psql -h 127.0.0.1 -U postgres -d employees -v ON_ERROR_STOP=1 -q "$@"
}

echo ">> applying roles, fixture data, indexes, row-level security"
psqlx < db/init/01_roles_audit.sql
psqlx < backend/tests/integration/seed.sql
psqlx < db/post/02_post_migration.sql
psqlx < db/post/03_audit_access.sql

echo ">> building test image"
docker build -q -t "$IMG" -f backend/Dockerfile.test backend

echo ">> running pytest"
set +e
docker run --name "$TC" --network "$NET" \
  -e DATABASE_URL="postgresql://portal_app:${PW}@${DB}:5432/employees" "$IMG"
rc=$?
set -e
docker cp "$TC:/tmp/integration.xml" backend/integration-report.xml >/dev/null 2>&1 || true
exit $rc
