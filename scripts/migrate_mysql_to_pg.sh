#!/usr/bin/env bash
# Milestone 2: MySQL "employees" -> PostgreSQL schema `hr`, then validate.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

[ -d db/test_db ] || git clone https://github.com/datacharmer/test_db db/test_db

docker compose --profile migration up -d mysql
echo "Waiting for MySQL..."; until docker compose exec -T mysql mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent; do sleep 2; done
docker compose exec -T -w /test_db mysql sh -c "mysql -uroot -p'$MYSQL_ROOT_PASSWORD' < employees.sql"

docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U postgres -d employees >/dev/null; do sleep 2; done

docker run --rm --network securehr_default -v "$PWD/db/post:/post:ro" \
  -e MYSQL_URI="mysql://root:${MYSQL_ROOT_PASSWORD}@mysql:3306/employees" \
  -e PG_URI="postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/employees" \
  dimitri/pgloader:latest pgloader /post/pgloader.load

docker compose exec -T postgres psql -U postgres -d employees -v ON_ERROR_STOP=1 < db/post/02_post_migration.sql
bash scripts/validate_migration.sh
