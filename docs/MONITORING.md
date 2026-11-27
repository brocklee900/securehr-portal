# Employee directory SLO and Discord paging

The journey is **an authenticated user searches the employee directory**. The target is **99.9% over a rolling 30 days**. A good request must satisfy **both** HTTP status **below 500** and total Nginx request time **at most 500 ms**. A slow 5xx consumes the budget once. The error budget is 0.1% of eligible requests, not a fixed amount of downtime.

```text
Nginx access log -> nginx-log-exporter -> Prometheus -> Alertmanager -> Discord on-call engineer
```

## Measurement scope

Only `GET /api/employees` on the portal HTTPS server is eligible, with any query string (including an unfiltered directory request). Nginx's `$request_time` measures the edge request through completion; backend-only latency would miss proxy delays. A 0.5-second histogram bucket supplies the numerator exactly, without a percentile approximation.

At the edge, “valid” means a nonempty Bearer authorization header and no authentication/input rejection. Statuses 400, 401, 403, 404, 405, 413, 414 and 422 are excluded. Health checks, OPTIONS, POST, employee detail/salary requests, other virtual hosts, HTTP-to-HTTPS redirects and the trailing-slash redirect are excluded. All remaining responses below 500, including 429 and 499, satisfy the status part of the supplied SLI; they still have to meet the latency limit.

The backend validates JWTs. Nginx cannot establish token validity when the backend is unreachable, so bearer-bearing attempts returning 5xx are conservatively included. This keeps Nginx-generated 502/504 failures visible. It also means an invalid bearer token used during a backend outage can enter the denominator. Strict identity validation at the edge would require a separate authentication integration.

The search log and portal upstream logs omit tokens, query strings, names, IP addresses and employee numbers. Metric labels are limited to fixed service/SLO labels, HTTP method and status. Nginx rotates the search log daily or above 20 MB (checked hourly), keeping seven rotated files. Docker retains three 10 MB files of Nginx stdout/stderr.

## Start monitoring locally

From the repository root, with the app dependencies already running:

```bash
docker compose up -d --build --no-deps nginx
docker compose --profile monitoring up -d nginx-log-exporter prometheus alertmanager
```

Open [Prometheus](http://localhost:9090) and [Alertmanager](http://localhost:9093). Both bind to loopback only; the exporter has no published host port. The default Alertmanager configuration is **local-only: alerts are visible, but no pages are sent**.

Gitea is optional for portal/monitoring startup. Nginx resolves its address only when someone opens `gitea.localhost`; it is not a Compose startup dependency. Missing `GITEA_SECRET_KEY` / `GITEA_OIDC_SECRET` warnings do not prevent these services from starting. Configure Gitea separately using the README's Git-server setup when needed.

If PostgreSQL cannot publish host port 5432 because another local installation is using it, set `POSTGRES_HOST_PORT=15432` (or another free port) in `.env` and retry. This changes only connections from your host to `localhost`; application and migration connections inside Docker continue to use `postgres:5432`.

Check [scrape targets](http://localhost:9090/targets) and [alert rules](http://localhost:9090/alerts). Sign in to the portal and perform several searches, then allow two scrape intervals (30 seconds). Use these expressions in the Prometheus query view:

| View | PromQL |
|---|---|
| 30-day SLI, percent (target 99.9) | `100 * securehr:employee_search:good_ratio_30d` |
| 30-day eligible requests | `securehr:employee_search:requests_30d` |
| Remaining error budget, percent (negative means exhausted) | `100 * securehr:employee_search:error_budget_remaining_ratio_30d` |
| 1-hour burn rate (page threshold 14.4) | `securehr:employee_search:burn_rate_1h` |
| 5-minute burn rate (page threshold 14.4) | `securehr:employee_search:burn_rate_5m` |
| Request volume, per second | `sum(rate(securehr_search_http_response_count_total[5m]))` |
| Response volume by status | `sum by (status) (rate(securehr_search_http_response_count_total[5m]))` |

Prometheus retains 35 days in its named volume. Short-window rules evaluate every 15 seconds; the 30-day report evaluates every five minutes. No traffic produces missing/NaN data, **not 100% success**. Before 30 days of continuous collection have elapsed, the report covers only the available history. The first hour after startup likewise has a partial burn-rate history.

## Enable Discord on-call pages

1. In the destination Discord server/channel, create an incoming webhook and give the on-call engineer access to the channel. Enable channel/mobile notifications. In Discord Developer Mode, right-click the engineer's profile and copy their **user ID**. The receiver uses a direct user mention, which Discord webhook defaults permit; role mentions require an `allowed_mentions` payload that the native Alertmanager integration does not expose.
2. Run this from a local terminal; the URL is hidden while typing:

   ```bash
   python scripts/configure_monitoring.py
   ```

   It writes `monitoring/secrets/discord_webhook_url` and `monitoring/alertmanager/discord.local.yml`, both git-ignored. Only Alertmanager mounts the secret directory. The URL is never passed as a CLI argument. Protect the local secret directory with your host's filesystem permissions.
3. Start or update the monitoring services with the Discord override:

   ```bash
   docker compose build nginx
   docker compose -f docker-compose.yml -f monitoring/discord.compose.yml --profile monitoring up -d nginx-log-exporter prometheus alertmanager
   ```

   Keep using this override for subsequent `up` commands; starting Alertmanager with only the base Compose file restores local-only delivery. After changing the webhook/config, restart Alertmanager with the same override.

`EmployeeSearchSLOBurnRate` pages when **both** 1-hour and 5-minute burn rates are **>= 14.4**. Burn rate is bad-request ratio divided by 0.001, so the page condition is at least 1.44% bad requests in both windows. There is no extra `for` delay or minimum-request threshold. Alertmanager groups for 10 seconds, repeats ongoing pages hourly, and sends a recovery notification when either window recovers. Only firing alerts with `severity="page"` mention the on-call engineer.

The configured user ID determines who is on call; update it with the setup script and restart Alertmanager when the engineer changes. This project does not schedule rotations, acknowledgements or escalations. Discord notification settings still control whether the message makes a sound or reaches a phone. Verify the real channel with a test before relying on it.

To send a clearly labeled test page through the configured receiver (this mentions the on-call engineer):

```bash
python scripts/send_test_alert.py
```

The test alert expires after one minute; the recovery notification may take up to the five-minute group interval. Check the channel for both messages. No webhook URL appears in the command or test payload.

## PostgreSQL query statistics

Compose preloads `pg_stat_statements`; new databases create the extension at initialization. For an existing database, recreate the Postgres container with its existing volume, then apply the idempotent extension script. This briefly interrupts database connections; do it during a suitable maintenance interval. It does not re-migrate or delete data.

```bash
docker compose up -d --no-deps postgres
docker compose cp db/post/06_query_statistics.sql postgres:/tmp/06_query_statistics.sql
docker compose exec -T postgres psql -U postgres -d employees -v ON_ERROR_STOP=1 -f /tmp/06_query_statistics.sql
```

No extra database privileges are granted to the app. Query statistics remain an operator diagnostic.

## Incident runbook

1. **Inspect Nginx upstream logs and PostgreSQL query latency first.**

   ```bash
   docker compose logs --since 15m nginx
   docker compose exec postgres psql -U postgres -d employees
   ```

   In the Nginx JSON records, inspect `route="employee_search"`, `status`, `request_time`, `upstream_status`, `upstream_connect_time` and `upstream_response_time`. Compare total latency to upstream latency to distinguish proxy/client delays from backend work. Connection errors and upstream timeouts also appear in the Nginx error log on stderr.

   In psql, inspect completed search/count statements (milliseconds):

   ```sql
   SELECT queryid, calls,
          round(mean_exec_time::numeric, 2) AS mean_ms,
          round(max_exec_time::numeric, 2) AS max_ms,
          round(total_exec_time::numeric, 2) AS total_ms,
          rows, left(query, 240) AS normalized_query
   FROM pg_stat_statements
   WHERE dbid = (SELECT oid FROM pg_database WHERE datname = 'employees')
     AND query ILIKE '%employees%'
     AND query NOT ILIKE '%pg_stat_statements%'
   ORDER BY total_exec_time DESC
   LIMIT 15;

   SELECT pid, now() - query_start AS elapsed, wait_event_type, wait_event,
          pg_blocking_pids(pid) AS blockers
   FROM pg_stat_activity
   WHERE datname = 'employees' AND state = 'active' AND pid <> pg_backend_pid()
   ORDER BY query_start;
   ```

   `pg_stat_statements` values are cumulative since statistics were reset. Compare two snapshots for incident-period changes; a lifetime mean can hide a new regression. Avoid resetting shared statistics during an incident. If the extension is missing, use `pg_stat_activity` immediately and follow the setup above in a suitable interval.
2. Check both burn rates and request volume in Prometheus. Check `up{job="nginx-search"}` and `securehr_search_parse_errors_total` before trusting the result. A quiet directory can page on very few bad requests; that follows the supplied SLO.
3. For 502/504, check `docker compose ps` and `docker compose logs --since 15m backend postgres`, then inspect backend reachability, DB connection pool saturation and active-query blocking. For slow 200s, inspect search/count query plans, indexes, large offsets and recently changed filters. Do not run an expensive `EXPLAIN ANALYZE` on production without assessing its execution cost.
4. Restore the failing component or roll back the implicated change, perform authenticated searches, and verify both latency and errors recover. The page resolves when either window drops below 14.4; the 30-day error-budget report retains the incident's impact.
5. If Discord is silent, inspect `docker compose logs --since 15m alertmanager`, the on-call user's channel permissions, silences and `alertmanager_notifications_failed_total{integration="discord"}`. A broken Discord route cannot reliably report its own failure through Discord; check the local alert UI.

## Verification and limits

Run `python scripts/test_monitoring.py` with Docker running. It validates Prometheus/Alertmanager configuration, tests the burn-rate math and 30-day recording rules, and sends requests through the production Nginx configuration with disposable backend fixtures. It tests the 500 ms boundary, rejected requests, health checks, fast/slow 5xx, Nginx-generated 502s, zero traffic, counter resets, aggregation, exact 14.4 thresholds, recovery, log rotation, and Discord firing/resolved payloads against a **local mock endpoint**. The same suite runs in Jenkins. It uses randomly named containers/volumes and cleans up only those resources.

The log exporter is a live tailer with in-memory counters, not a durable event ledger. Counter resets are handled by Prometheus `increase`, but collection gaps and first samples of a new status series cannot be reconstructed exactly. Exporter outages and parsing errors have separate alerts. No-data periods must be investigated, not treated as compliance; a live exporter alone does not prove Nginx is receiving traffic. This single-host demo cannot page if Docker/the host or Prometheus itself is down. Independent external checks are needed for those failure modes.

References: [Nginx request logging](https://nginx.org/en/docs/http/ngx_http_log_module.html), [log exporter](https://github.com/martin-helmich/prometheus-nginxlog-exporter), [Alertmanager Discord configuration](https://prometheus.io/docs/alerting/latest/configuration/#discord_config), [Discord allowed mentions](https://github.com/discord/discord-api-docs/blob/main/developers/resources/message.mdx#allowed-mentions-object), [Prometheus rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).
