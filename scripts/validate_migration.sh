#!/usr/bin/env bash
# Compares row counts MySQL vs Postgres. Exits non-zero on mismatch.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
ok=0
for t in employees departments dept_emp dept_manager titles salaries; do
  m=$(docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B -e "SELECT COUNT(*) FROM employees.$t" 2>/dev/null | tr -d '\r')
  p=$(docker compose exec -T postgres psql -U postgres -d employees -At -c "SELECT COUNT(*) FROM hr.$t" | tr -d '\r')
  if [ "$m" = "$p" ]; then printf "OK   %-12s %s\n" "$t" "$p"; else printf "FAIL %-12s mysql=%s pg=%s\n" "$t" "$m" "$p"; ok=1; fi
done
exit $ok
