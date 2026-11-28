# SecureHR Portal

A proof-of-concept enterprise HR portal with single sign-on, role-based access and an automated delivery pipeline.

**React/TypeScript** → **FastAPI** → **PostgreSQL** (row-level security + audit log), identity via **Keycloak** (OIDC) federated to **OpenLDAP**, TLS via **Nginx**, source control via **Gitea** and CI/CD via **Jenkins** (Gitea and Jenkins both sign in through the same Keycloak SSO; Gitea webhooks trigger Jenkins builds).

```
Browser ──TLS──> Nginx ─┬─ portal.localhost  → React (Vite) ──┐ OIDC (auth code + PKCE)
                        │                      /api/ → FastAPI ── Postgres (schema hr, RLS; app.audit_log)
                        ├─ auth.localhost    → Keycloak ── LDAP (users + groups)
                        ├─ gitea.localhost   → Gitea (OIDC login) ──webhook──> Jenkins
                        └─ jenkins.localhost → Jenkins (OIDC login) ── runs lint, tests, scans in Docker
```

## Access model

| Role | Directory | Department data | Salaries | Audit log |
|---|---|---|---|---|
| `employee` | name, title, department | read | none (API 403, database returns 0 rows) | no |
| `manager` | + demographics | read | own department's **current** staff only | no |
| `hr_admin` | everything | everything | everyone, and can **change** salaries | read (append-only for everyone) |

Only `hr_admin` can **create employees** (the *New employee* page in the top bar) and **change salaries** (the *Change salary* box under an employee's salary history). Those are the only writes the portal performs on HR data. Hiring is insert-only. A salary change adds the new salary and ends the current one, and that end date is the only value the app can ever update: nobody, including HR admins, can edit or delete employee, department, title or salary rows through the app.

Salary change rules (each enforced by the API, and all but the LDAP one by Postgres too):
- Never your own salary, and never another HR admin's (anyone in the LDAP `hr-admins` group, checked live; if LDAP can't be reached, changes are refused).
- Takes effect today or later, at most a year ahead. Past salaries are never rewritten.
- At most one pending (future-dated) change per employee; a second one is refused until it takes effect.

Access is enforced three times: the UI hides what a role can't use, the API checks the role on every request, and PostgreSQL row-level security enforces salary and audit-log access even if the API had a bug. Every successful read **and every refused request** is written to `app.audit_log`.

---

## Setup guide

### Prerequisites
- **Docker Desktop** (running), **Git**, **mkcert** (https://github.com/FiloSottile/mkcert), Python 3.12 (only to run backend tests outside Docker)

**Windows:** run every `bash scripts/...` command in **Git Bash** (or WSL). Three quirks:
1. Run `export MSYS_NO_PATHCONV=1` in each new Git Bash window before Docker commands, or paths get rewritten.
2. If a script fails with `$'\r': command not found`, fix line endings: `sed -i 's/\r$//' .env scripts/*.sh`
3. Type commands by hand or paste one line at a time. Long pasted blocks sometimes arrive garbled.

### 1. Configure and create certificates
```bash
cp .env.example .env              # then change every change-me-... value
bash scripts/gen-certs.sh         # creates nginx/certs/securehr.pem and securehr-key.pem
cp "$(mkcert -CAROOT)/rootCA.pem" jenkins/rootCA.pem
```
Running on the shared cloud server instead of a laptop? Skip `mkcert` and see step 8.

Already have certificates from an earlier setup? Re-run `bash scripts/gen-certs.sh` (it now also covers `gitea.localhost`; your CA stays the same) and `docker compose restart nginx`.

Avoid `@ : / # %` in passwords (they end up in connection URLs). The last line lets Jenkins trust your local certificate; the file is machine-specific and git-ignored. On Windows, if `mkcert` isn't on your PATH: `cp ~/AppData/Local/mkcert/rootCA.pem jenkins/rootCA.pem`.

### 2. Migrate the sample data (MySQL to PostgreSQL)
```bash
export MSYS_NO_PATHCONV=1
bash scripts/migrate_mysql_to_pg.sh
```
Clones `datacharmer/test_db`, loads it into MySQL, copies it into Postgres schema `hr` with pgloader, then adds search indexes and the row-level security and audit rules (`db/post/02_*.sql`, `03_*.sql`), the HR-admin-only insert rules for new employees (`04_*.sql`) and the salary-change rules (`05_*.sql`). Takes 5 to 10 minutes. Success ends with six `OK` lines (employees 300024, salaries 2844047, ...). Afterwards `docker compose stop mysql`.

**Already migrated before the *New employee* page existed?** Don't re-migrate. Apply the one new file (safe to repeat), then rebuild the backend and frontend:
```bash
docker compose exec -T postgres psql -U postgres -d employees -v ON_ERROR_STOP=1 < db/post/04_hr_write_access.sql
docker compose up -d --build backend
```

**Already set up before salary changes existed?** Don't re-migrate. Salary changes need the database rules and a read-only LDAP account for the backend (it checks who is in `hr-admins`):
1. Add `LDAP_READONLY_PASSWORD=...` to `.env` (see `.env.example`).
2. Apply the rules (safe to repeat): `docker compose exec -T postgres psql -U postgres -d employees -v ON_ERROR_STOP=1 < db/post/05_hr_salary_adjust.sql`
3. The read-only account is only created when LDAP's volumes are first initialised. LDAP holds only the demo users from `ldap/bootstrap.ldif`, so recreate it: `docker compose rm -sf ldap`, then `docker volume rm securehr_ldapdata securehr_ldapconf`, then `docker compose up -d ldap`.
4. In Keycloak (securehr realm) → User federation → `ldap` → Action → **Remove imported users**, then **Sync all users** (the recreated entries have new IDs).
5. `docker compose up -d --build backend frontend`

### 3. Start the stack
```bash
docker compose up -d --build
docker compose ps                 # all Up; give Keycloak about a minute
```
Open https://auth.localhost (no certificate warning expected), then https://portal.localhost.

### 4. Configure Keycloak
Sign in at https://auth.localhost/admin with `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` from `.env`.

> **Switch the realm first.** The top-left dropdown defaults to `master`. Everything below is done in the **securehr** realm.

**4a. Unmanaged attributes.** Realm settings → General → **Unmanaged Attributes = Enabled** → Save (otherwise the employee number never reaches the token).

**4b. LDAP provider.** User federation → Add LDAP provider:

| Field | Value |
|---|---|
| UI display name | `ldap` |
| Vendor | Other |
| Connection URL | `ldap://ldap:389` |
| Bind type / Bind DN | simple / `cn=admin,dc=securehr,dc=local` |
| Bind credentials | `LDAP_ADMIN_PASSWORD` from `.env` |
| Edit mode | READ_ONLY |
| Users DN | `ou=people,dc=securehr,dc=local` |
| Username and RDN LDAP attribute | `uid` |
| UUID LDAP attribute | `entryUUID` |
| User object classes | `inetOrgPerson` |

Use **Test connection** and **Test authentication**, then Save.

**4c. Two mappers** (provider → Mappers → Add mapper):
- `groups`: type `group-ldap-mapper`, LDAP Groups DN `ou=groups,dc=securehr,dc=local`, Group Name LDAP Attribute `cn`, Group Object Classes `groupOfNames`, Membership LDAP Attribute `member`, Membership Attribute Type `DN`, Mode `READ_ONLY`, Retrieve Strategy `LOAD_GROUPS_BY_MEMBER_ATTRIBUTE`. Save, then **Action → Sync LDAP groups to Keycloak**.
- `emp_no`: type `user-attribute-ldap-mapper`, User Model Attribute `emp_no`, LDAP Attribute `employeeNumber`, Read only On, Always read value from LDAP On.

**4d. Sync users.** On the provider page: **Action → Sync all users** (expect 3 added). Check `alice.hr`: Groups shows `hr-admins`, Role mapping (uncheck "Hide inherited roles") shows `hr_admin`.

**4e. Jenkins client.** Clients → `jenkins`:
- **Credentials** tab: the client secret must equal `JENKINS_OIDC_SECRET` in `.env`.
- **Client scopes** → `jenkins-dedicated` → Add mapper → By configuration → **User Realm Role**: Name `roles`, Token Claim Name `roles`, Multivalued On, Add to ID token / access token / userinfo all On. Jenkins reads its groups from this claim.

(LDAP federation and the Jenkins `roles` mapper live in Keycloak's database, not in the realm import file, so every fresh setup repeats 4b to 4e.)

### 5. Jenkins
1. Allow Jenkins to use Docker. This resets whenever the Jenkins container is recreated:
   ```bash
   docker compose exec -u root jenkins chmod 666 /var/run/docker.sock
   ```
2. Open https://jenkins.localhost. It redirects to Keycloak; sign in as `alice.hr` (an admin). Other roles get read and build access only.
3. New Item → name `securehr-portal` → **Multibranch Pipeline** → Branch Sources → GitHub → paste your repo URL (add a token credential if the repo is private) → Save. Jenkins scans the repo, finds the `Jenkinsfile`, and builds `main`.
4. Webhooks need a public address, so builds are started with **Scan Repository Now** / **Build Now** locally.

**Pipeline stages:** Lint (ruff, eslint, tsc) → Unit tests → Integration tests → Build images → Security scans (pip-audit, Trivy) → Deploy to staging (validates the compose file only).

### 6. Try it

Use a private window per login. Demo password for all LDAP users: `Passw0rd!`

| Sign in as | Expect |
|---|---|
| `alice.hr` | Full directory, salaries for everyone, **New employee** and **Audit log** links in the top bar, a **Change salary** box on every employee page |
| `bob.manager` | Salary history only for Marketing (`d001`) staff; "Salary data not available" elsewhere; no Audit log link |
| `carol.employee` | No salary section at all |
| `admin.local` | Fallback HR admin that works without LDAP (set its password in Keycloak first) |

To see the HR-admin rule, give an HR admin an employee number in LDAP (alice has none in the demo directory): add `employeeNumber: <n>` to her entry in `ldap/bootstrap.ldif` before LDAP is first initialised. Employee `<n>`'s page then says HR admins cannot change it, and alice cannot change her own salary.

Bob's LDAP `employeeNumber` is `110039`, a **current** manager of `d001`. Row-level security only recognises managers whose `dept_manager.to_date = '9999-01-01'`, so a former manager's number sees nothing. To list current managers:
```bash
docker compose exec postgres psql -U postgres -d employees -c "SELECT dept_no, emp_no FROM hr.dept_manager WHERE to_date='9999-01-01' ORDER BY 1;"
```

### 7. Git server (Gitea) with SSO and webhooks

Gitea replaces GitHub as the Git server so that source control signs in through the same Keycloak as everything else, and so it can call Jenkins over the Docker network (no public address needed for webhooks).

**7a. One command** (safe to re-run; does not touch the database):
```bash
export MSYS_NO_PATHCONV=1
bash scripts/gen-certs.sh && docker compose restart nginx     # only if your certificate predates gitea.localhost
bash scripts/setup-gitea.sh
docker compose exec -u root jenkins chmod 666 /var/run/docker.sock   # Jenkins was rebuilt, see step 5
```
The script adds `GITEA_SECRET_KEY` and `GITEA_OIDC_SECRET` to `.env`, starts the stack, creates the `gitea` client in the **securehr** realm (with a `roles` claim) and registers Keycloak as Gitea's login source. Users with the `hr_admin` role become Gitea site admins; everyone else gets a restricted account with no access until an admin grants it.

**7b. Sign in.** Open https://gitea.localhost → **Sign in with keycloak** as `alice.hr`. You should see **Site Administration** in the user menu. (Private window per login, as in step 6.)

**7c. Create the repository and push.** In Gitea create an empty private repository `securehr-portal` under `alice.hr`. Accounts are SSO-only, so Git over HTTPS uses a token as the password: Settings → Applications → generate a token with repository read/write, organization read and user read. Then:
```bash
git remote add gitea https://gitea.localhost/alice.hr/securehr-portal.git
git push gitea main            # username alice.hr, password = the token
```
If Git reports an unknown certificate authority: `git config http.sslCAInfo "$(mkcert -CAROOT)/rootCA.pem"` (on Windows `cp ~/AppData/Local/mkcert/rootCA.pem` as in step 1 if `mkcert` is not on your PATH).

**7d. Connect Jenkins** (https://jenkins.localhost, as `alice.hr`):
1. Manage Jenkins → Credentials → System → Global → Add credentials → Kind **Gitea Personal Access Token**, ID `gitea-token`, paste the token from 7c.
2. Manage Jenkins → System → **Gitea Servers** → Add: Name `gitea`, Server URL `https://gitea.localhost`, Credentials `gitea-token`, **Manage hooks** ticked → Save.
3. Open the `securehr-portal` job → Configure → Branch Sources: replace the GitHub source with **Gitea** (server `gitea`, credentials `gitea-token`, owner `alice.hr`, repository `securehr-portal`) → Save. (Or create a new Multibranch Pipeline with that source.)
4. Jenkins scans, builds `main`, and registers a webhook in the repository for you.

**7e. Check it works.** Push a small commit (`git push gitea main`). A build should start within seconds without clicking *Build Now*. In Gitea, repository → Settings → Webhooks shows the Jenkins hook with a green delivery; the commit shows a build status. A signed-in `bob.manager` or `carol.employee` gets an account with no repositories.

**Manual Keycloak client** (only if the script could not reach Keycloak's admin API): in the **securehr** realm, Clients → Create: ID `gitea`, Client authentication **On**, Standard flow only, Valid redirect URI `https://gitea.localhost/user/oauth2/keycloak/callback`; Credentials tab secret = `GITEA_OIDC_SECRET` from `.env`; Client scopes → `gitea-dedicated` → Add mapper → By configuration → **User Realm Role**: Name `roles`, Token Claim Name `roles`, Multivalued On, Add to ID token / access token / userinfo On. Then re-run the script (it skips what exists).

### 8. Shared cloud server (AWS EC2 + free DuckDNS name)

The abstract calls for a shared cloud server for Keycloak, Jenkins and Postgres. The whole stack runs on one EC2 instance (they depend on each other, and the compose file already wires them together), and the team uses it in the browser at real HTTPS addresses. Laptops keep running the local stack exactly as before: nothing below changes them.

Everything hostname-related comes from `SECUREHR_DOMAIN` in `.env` (`localhost` by default): the sites are `portal.`, `auth.`, `gitea.` and `jenkins.` + that name.

**8a. Free name.** Sign in at https://www.duckdns.org and add a subdomain, e.g. `myteam`, giving `myteam.duckdns.org`. DuckDNS also answers for every name under it (`portal.myteam.duckdns.org` and so on), so one entry covers all four sites. You fill in its IP in 8b.

**8b. Server (AWS console → EC2).**
1. Launch an instance: Ubuntu 24.04, `t3.large` (8 GB; the stack runs about ten containers including Keycloak and Jenkins), 30 GB disk, with a key pair you keep.
2. Security group: **443** and **80** from anywhere (80 is needed for Let's Encrypt and redirects), **22** from your team's IP addresses only. Nothing else: Postgres and LDAP stay private.
3. Elastic IPs → allocate one → associate it with the instance, so the address survives stop/start. Put that address in DuckDNS (8a) and save.

Cost: about $0.08/hour, roughly $60/month if left running. **Stop the instance when nobody is using it**, and set a billing alert. Check whether the course offers AWS Academy or education credits.

**8c. Install and configure** (on the server: `ssh -i yourkey.pem ubuntu@myteam.duckdns.org`):
```bash
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker ubuntu && exit   # log in again afterwards
git clone <your repo URL> securehr-portal && cd securehr-portal
cp .env.example .env && nano .env
```
In `.env`: set `SECUREHR_DOMAIN=myteam.duckdns.org`, `KEYCLOAK_COMMAND=start`, `FRONTEND_TARGET=prod`, `LETSENCRYPT_EMAIL=` your address, and replace **every** `change-me-...` value with a long random one (`openssl rand -hex 24`). This server is on the internet. No mkcert and no `rootCA.pem` are needed: Let's Encrypt certificates are trusted everywhere.

**8d. Certificates, data, start.**
```bash
bash scripts/get-public-certs.sh          # trusted HTTPS for all four names; also starts the stack
bash scripts/migrate_mysql_to_pg.sh       # step 2, same as on a laptop (5 to 10 minutes)
docker compose stop mysql
docker compose up -d --build
```
Renew the certificates by re-running `get-public-certs.sh` (they last 90 days; it renews in the last 30). The script prints a monthly `cron` line for this.

**8e. Keycloak, Jenkins, Gitea.** Same as steps 4 to 7 with your domain instead of `localhost` (e.g. https://auth.myteam.duckdns.org/admin, https://jenkins.myteam.duckdns.org). Then, before telling anyone the address:
- Give the LDAP demo users real passwords, or replace them with your team's accounts in `ldap/bootstrap.ldif` before first start. `Passw0rd!` must not be on the internet.
- Disable or re-password `admin.local` in Keycloak.
- Jenkins' Docker access (step 5) is effectively root on the server: limit **Job/Build** to HR admins (security review, finding 7).

**8f. Using it as a team.**
- Everyone: https://portal.myteam.duckdns.org and the other three sites.
- Code: push to Gitea on the server (step 7). Jenkins builds on each push.
- Database: Postgres is not exposed. To use a local tool (psql, DBeaver), open an SSH tunnel and connect to `localhost:5433`:
  ```bash
  ssh -i yourkey.pem -N -L 5433:127.0.0.1:5432 ubuntu@myteam.duckdns.org
  ```
- Deploy new code on the server: `git pull && docker compose up -d --build`.
- Stop/start the EC2 instance from the console when not in use; the stack restarts on boot (`restart: unless-stopped`), but re-run the Jenkins `chmod` from step 5 if builds need Docker.

### Stopping and resuming
Data lives in Docker volumes and survives restarts.
```bash
docker compose stop               # or quit Docker Desktop
# later:
export MSYS_NO_PATHCONV=1
docker compose up -d
docker compose exec -u root jenkins chmod 666 /var/run/docker.sock   # if Jenkins builds need Docker again
```
**Never run `docker compose down -v`**: `-v` deletes the volumes (database, Keycloak settings, LDAP, Jenkins).

---

## Employee search monitoring

The directory SLO is **99.9% of valid search requests returning status below 500 within 500 ms, over 30 days**, measured at Nginx. The optional `monitoring` Compose profile adds Prometheus and Alertmanager; the page condition requires **both 1-hour and 5-minute burn rates >= 14.4**. Discord pages mention the on-call engineer and include the first runbook step: inspect Nginx upstream logs and PostgreSQL query latency.

See **[monitoring setup and incident runbook](docs/MONITORING.md)** for starting the services, enabling Discord, viewing the SLI/error budget, and enabling query statistics on an existing database. Delivery defaults to local-only until you run `python scripts/configure_monitoring.py` and start with the Discord override. Webhook credentials stay in git-ignored local files.

## Testing

| Layer | Command | What it covers |
|---|---|---|
| Unit (85) | `cd backend && pytest -q` | Role logic, token claims, denial auditing, new-employee validation rules, salary-change rules and the LDAP lookup (against an in-memory directory). No database needed; integration tests are skipped. |
| Integration (189) | `bash scripts/run_integration_tests.sh` | Runs in Docker: a throwaway Postgres with a small fixed dataset and your real security rules, real signed tokens through the real validation code. |
| Monitoring | `python scripts/test_monitoring.py` | SLO rule scenarios, real Nginx log collection and rotation, and Discord payloads sent to a local mock webhook. |

The integration suite checks that: tokens with a wrong audience, wrong issuer, bad signature, `alg: none` or expired are rejected; every data endpoint needs a login; search, paging and department filters return exactly the expected people (including an employee who moved departments); employees never get salaries; managers see only their **current** department (former managers and missing employee numbers see nothing); the audit log is HR-only, append-only, records denied requests, and audits its own reads; and, directly in Postgres without the API, row-level security holds and the app's database user cannot update or delete HR data or bypass the rules. For creating employees it checks that all four tables are filled together or not at all, that only `hr_admin` can do it (API and database each, separately), that clients cannot choose the employee number, and that the audit entry holds no personal data. For salary changes it checks that the old salary is closed and the new one added together, that only `hr_admin` can do it (API and database separately), that own and other HR admins' salaries are refused (and refused if LDAP is down), that past dates, a second pending change, and editing amounts or start dates are refused in the database itself, and that the audit entry holds no amounts. The integration tests replace LDAP with a fake directory (employee 10004 plays an HR admin).

The same script runs as the **Integration tests** stage in Jenkins (results published as JUnit). Together: 274 tests.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Cwd must be an absolute path` during migration | Git Bash path rewriting: `export MSYS_NO_PATHCONV=1` first. |
| `$'\r': command not found` | CRLF line endings: `sed -i 's/\r$//' .env scripts/*.sh` |
| Vite says `Blocked request. This host ("frontend") is not allowed` | `location /` in `nginx/templates/nginx.conf.template` must re-declare its `proxy_set_header` lines (already done). `docker compose restart nginx`. |
| Cannot sign in as `admin.local` | In the **securehr** realm: Users → `admin.local` → Credentials → Reset password (Temporary off); confirm group `hr-admins`. The Keycloak admin account lives in `master` and cannot sign in to the portal. |
| `hr_admin` role missing, or role mapping empty | Wrong realm (`master`), "Hide inherited roles" is ticked, or LDAP groups were not synced (step 4c). |
| Signed in but "No portal role assigned" | The user has no group carrying a realm role. |
| Manager sees no salaries anywhere | `emp_no` claim missing (step 4a or mapper in 4c), or the number is not a *current* manager. |
| Jenkins 502 | Jenkins is restarting or failed on startup: `docker compose logs --no-log-prefix jenkins \| head -60`. Then `docker compose restart nginx`. |
| Jenkins: "Access Denied ... missing Overall/Read" after login | Jenkins sees no groups: add the `roles` mapper (step 4e) and check `groupsFieldName: roles` in `jenkins/casc.yaml`. |
| Jenkins "Oops!" page after being logged in a while | Token refresh failure caused by `rootURLFromRequest`; it must not be set in `casc.yaml` (already removed). |
| Build: `docker: not found` or `permission denied ... docker.sock` | Rebuild Jenkins (`docker compose up -d --build jenkins`), then run the `chmod 666` command from step 5. |
| Build: `Invalid option type` or `expecting '}'` in the Jenkinsfile | A plugin is missing from `jenkins/Dockerfile`, or the file was damaged by pasting. Check braces: `grep -o '{' Jenkinsfile \| wc -l` equals `grep -o '}' Jenkinsfile \| wc -l`. |
| Creating an employee fails with a server error, or the log says `employees_emp_no_seq does not exist` / `permission denied` | `db/post/04_hr_write_access.sql` has not been applied to this database (command under step 2), or the migration was re-run afterwards without it (re-migrating drops the rules). |
| Creating an employee says "Employee number already in use" (409) | The numbering sequence is behind the data (for example after restoring a backup). Re-run `04_hr_write_access.sql`; it moves the sequence past the highest employee number. |
| Change salary box says "Cannot check whether this employee is an HR admin" (503) | The backend cannot bind to LDAP as `cn=readonly`: `LDAP_READONLY_PASSWORD` missing from `.env`, or LDAP was initialised before the read-only account existed (see "Already set up before salary changes existed?" under step 2). `docker compose logs backend`. |
| Changing a salary fails with `permission denied` or a server error | `db/post/05_hr_salary_adjust.sql` has not been applied (command under step 2). |
| Applying `05_hr_salary_adjust.sql` says employees "already have more than one current salary" | The data has two open (`9999-01-01`) salaries for those people. Fix them as `postgres` (close all but the latest), then re-run. |
| `get-public-certs.sh`: name "does not resolve" or "points at" another address | The DuckDNS IP is not this server's Elastic IP (step 8a/8b). Fix it on duckdns.org, wait a minute, re-run. |
| `get-public-certs.sh`: Let's Encrypt says `Timeout during connect` or `unauthorized` | Port 80 is not open to the internet in the EC2 security group, or Nginx is not running (`docker compose ps nginx`). |
| Server: browser says the certificate is for `temporary` | The Let's Encrypt step did not finish: re-run `bash scripts/get-public-certs.sh` and read its output. |
| Server: login redirects to `auth.localhost` | `SECUREHR_DOMAIN` is missing from `.env` on the server, or Keycloak's realm was imported before it was set. Set it, then `docker compose up -d`; for the realm, update the client redirect URIs in Keycloak (Clients → `securehr-portal`, `jenkins`) or recreate Keycloak's data. |
| Integration script: `Postgres did not start` | Docker Desktop not running or out of resources; the script prints the container log. |
| pgloader cannot log in to MySQL | pgloader cannot use MySQL 8's default auth; compose pins `mysql:8.0` with `mysql_native_password`. |
| Gitea sign-in: `x509: certificate signed by unknown authority` | `gitea/rootCA.pem` was missing or stale when the image was built: `cp jenkins/rootCA.pem gitea/rootCA.pem && docker compose up -d --build gitea`. |
| Gitea sign-in loops back or says the OAuth2 request failed | The redirect URI or secret differs from the Keycloak `gitea` client. Re-run `bash scripts/setup-gitea.sh` (it re-syncs both). |
| Signed in to Gitea but alice is not an admin | The `roles` claim is missing: Keycloak → Clients → `gitea` → Client scopes → `gitea-dedicated` must contain the `roles` mapper, and alice must have the `hr_admin` role (step 4d). Emergency admin: `docker compose exec -u git gitea gitea admin user create --admin --username localadmin --random-password --email localadmin@securehr.local`. |
| Gitea webhook shows `denied by egress policy` | Gitea 28 only allows webhooks to private addresses listed in `[security] ALLOWED_HOST_LIST` (compose sets `private`). Check `docker compose exec gitea env \| grep ALLOWED_HOST` and that `jenkins.localhost` resolves from the Gitea container. |
| Jenkins: `SSL peer unverified` / git clone fails on `gitea.localhost` | Jenkins image predates this change. `docker compose up -d --build jenkins`, then the `chmod 666` command from step 5. |

---

## Repository layout

| Path | Purpose |
|---|---|
| `docker-compose.yml`, `.env.example` | Full stack |
| `db/init/` | First-start Postgres setup: app role, `app.audit_log` |
| `db/post/` | After migration: indexes and RLS (`02_`), audit-log access rules (`03_`), HR-admin inserts and the employee-number sequence (`04_`), salary changes (`05_`), pgloader config |
| `scripts/` | Certificates (`gen-certs.sh` for laptops, `get-public-certs.sh` for the shared server), migration, validation, integration tests, Gitea/Keycloak setup (`setup-gitea.sh`) |
| `ldap/bootstrap.ldif`, `keycloak/` | Demo directory, realm import file, federation guide |
| `nginx/` | TLS reverse proxy; `templates/nginx.conf.template` gets the domain filled in at startup |
| `backend/` | FastAPI app (`app/`), unit tests, integration tests (`tests/integration/`), `Dockerfile`, `Dockerfile.test` |
| `frontend/` | React/TS: login, search, detail, departments, audit log, new employee (HR admins) |
| `gitea/` | Gitea image (official image plus the local CA when present); configured by environment variables in `docker-compose.yml` |
| `jenkins/`, `Jenkinsfile` | Jenkins image and config-as-code (OIDC login, roles); pipeline definition |
| `docs/` | Architecture notes, milestone status, security review |

See `docs/SECURITY_REVIEW.md` for findings, fixes and accepted risks.

## Status

- [x] Data migrated and validated (300,024 employees, 2.84M salary rows)
- [x] TLS, Keycloak, LDAP federation, three roles
- [x] API with token validation and role checks; React UI with role-based views
- [x] Row-level security, audit logging (including denied requests), audit viewer
- [x] Jenkins signs in through Keycloak; CI pipeline with lint, unit and integration tests, dependency and container scans
- [x] HR admins can create employees (form, API, insert-only database rules, audit entry)
- [x] 196 automated tests
- [ ] Git server sign-in through the same SSO: Gitea added and scripted (step 7); tick once verified end to end
- [ ] Webhook-triggered builds: Gitea to Jenkins over the Docker network (step 7); tick once a push starts a build
- [ ] Multi-factor authentication (not implemented; see security review)
- [ ] Document repository stretch goal (not started)

All demo passwords are for local development only. Rotate every value in `.env` and remove the demo LDAP users and `admin.local` before sharing the stack.
