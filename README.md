# SecureHR Portal

A proof-of-concept enterprise HR portal with single sign-on, role-based access and an automated delivery pipeline.

**React/TypeScript** → **FastAPI** → **PostgreSQL** (row-level security + audit log), identity via **Keycloak** (OIDC) federated to **OpenLDAP**, TLS via **Nginx**, CI/CD via **GitHub + Jenkins** (Jenkins signs in through the same Keycloak SSO).

```
Browser ──TLS──> Nginx ─┬─ portal.localhost  → React (Vite) ──┐ OIDC (auth code + PKCE)
                        │                      /api/ → FastAPI ── Postgres (schema hr, RLS; app.audit_log)
                        ├─ auth.localhost    → Keycloak ── LDAP (users + groups)
                        └─ jenkins.localhost → Jenkins (OIDC login) ── runs lint, tests, scans in Docker
```

## Access model

| Role | Directory | Department data | Salaries | Audit log |
|---|---|---|---|---|
| `employee` | name, title, department | read | none (API 403, database returns 0 rows) | no |
| `manager` | + demographics | read | own department's **current** staff only | no |
| `hr_admin` | everything | everything | everyone | read (append-only for everyone) |

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
Avoid `@ : / # %` in passwords (they end up in connection URLs). The last line lets Jenkins trust your local certificate; the file is machine-specific and git-ignored. On Windows, if `mkcert` isn't on your PATH: `cp ~/AppData/Local/mkcert/rootCA.pem jenkins/rootCA.pem`.

### 2. Migrate the sample data (MySQL to PostgreSQL)
```bash
export MSYS_NO_PATHCONV=1
bash scripts/migrate_mysql_to_pg.sh
```
Clones `datacharmer/test_db`, loads it into MySQL, copies it into Postgres schema `hr` with pgloader, then adds search indexes and the row-level security and audit rules (`db/post/02_*.sql`, `03_*.sql`). Takes 5 to 10 minutes. Success ends with six `OK` lines (employees 300024, salaries 2844047, ...). Afterwards `docker compose stop mysql`.

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
| `alice.hr` | Full directory, salaries for everyone, **Audit log** link in the top bar |
| `bob.manager` | Salary history only for Marketing (`d001`) staff; "Salary data not available" elsewhere; no Audit log link |
| `carol.employee` | No salary section at all |
| `admin.local` | Fallback HR admin that works without LDAP (set its password in Keycloak first) |

Bob's LDAP `employeeNumber` is `110039`, a **current** manager of `d001`. Row-level security only recognises managers whose `dept_manager.to_date = '9999-01-01'`, so a former manager's number sees nothing. To list current managers:
```bash
docker compose exec postgres psql -U postgres -d employees -c "SELECT dept_no, emp_no FROM hr.dept_manager WHERE to_date='9999-01-01' ORDER BY 1;"
```

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

## Testing

| Layer | Command | What it covers |
|---|---|---|
| Unit (11) | `cd backend && pytest -q` | Role logic, token claims, denial auditing. No database needed; integration tests are skipped. |
| Integration (68) | `bash scripts/run_integration_tests.sh` | Runs in Docker: a throwaway Postgres with a small fixed dataset and your real security rules, real signed tokens through the real validation code. |

The integration suite checks that: tokens with a wrong audience, wrong issuer, bad signature, `alg: none` or expired are rejected; every data endpoint needs a login; search, paging and department filters return exactly the expected people (including an employee who moved departments); employees never get salaries; managers see only their **current** department (former managers and missing employee numbers see nothing); the audit log is HR-only, append-only, records denied requests, and audits its own reads; and, directly in Postgres without the API, row-level security holds and the app's database user cannot modify HR data or bypass the rules.

The same script runs as the **Integration tests** stage in Jenkins (results published as JUnit). Together: 79 tests.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Cwd must be an absolute path` during migration | Git Bash path rewriting: `export MSYS_NO_PATHCONV=1` first. |
| `$'\r': command not found` | CRLF line endings: `sed -i 's/\r$//' .env scripts/*.sh` |
| Vite says `Blocked request. This host ("frontend") is not allowed` | `location /` in `nginx/nginx.conf` must re-declare its `proxy_set_header` lines (already done). `docker compose restart nginx`. |
| Cannot sign in as `admin.local` | In the **securehr** realm: Users → `admin.local` → Credentials → Reset password (Temporary off); confirm group `hr-admins`. The Keycloak admin account lives in `master` and cannot sign in to the portal. |
| `hr_admin` role missing, or role mapping empty | Wrong realm (`master`), "Hide inherited roles" is ticked, or LDAP groups were not synced (step 4c). |
| Signed in but "No portal role assigned" | The user has no group carrying a realm role. |
| Manager sees no salaries anywhere | `emp_no` claim missing (step 4a or mapper in 4c), or the number is not a *current* manager. |
| Jenkins 502 | Jenkins is restarting or failed on startup: `docker compose logs --no-log-prefix jenkins \| head -60`. Then `docker compose restart nginx`. |
| Jenkins: "Access Denied ... missing Overall/Read" after login | Jenkins sees no groups: add the `roles` mapper (step 4e) and check `groupsFieldName: roles` in `jenkins/casc.yaml`. |
| Jenkins "Oops!" page after being logged in a while | Token refresh failure caused by `rootURLFromRequest`; it must not be set in `casc.yaml` (already removed). |
| Build: `docker: not found` or `permission denied ... docker.sock` | Rebuild Jenkins (`docker compose up -d --build jenkins`), then run the `chmod 666` command from step 5. |
| Build: `Invalid option type` or `expecting '}'` in the Jenkinsfile | A plugin is missing from `jenkins/Dockerfile`, or the file was damaged by pasting. Check braces: `grep -o '{' Jenkinsfile \| wc -l` equals `grep -o '}' Jenkinsfile \| wc -l`. |
| Integration script: `Postgres did not start` | Docker Desktop not running or out of resources; the script prints the container log. |
| pgloader cannot log in to MySQL | pgloader cannot use MySQL 8's default auth; compose pins `mysql:8.0` with `mysql_native_password`. |

---

## Repository layout

| Path | Purpose |
|---|---|
| `docker-compose.yml`, `.env.example` | Full stack |
| `db/init/` | First-start Postgres setup: app role, `app.audit_log` |
| `db/post/` | After migration: indexes and RLS (`02_`), audit-log access rules (`03_`), pgloader config |
| `scripts/` | Certificates, migration, validation, integration tests |
| `ldap/bootstrap.ldif`, `keycloak/` | Demo directory, realm import file, federation guide |
| `nginx/` | TLS reverse proxy |
| `backend/` | FastAPI app (`app/`), unit tests, integration tests (`tests/integration/`), `Dockerfile`, `Dockerfile.test` |
| `frontend/` | React/TS: login, search, detail, departments, audit log |
| `jenkins/`, `Jenkinsfile` | Jenkins image and config-as-code (OIDC login, roles); pipeline definition |
| `docs/` | Architecture notes, milestone status, security review |

See `docs/SECURITY_REVIEW.md` for findings, fixes and accepted risks.

## Status

- [x] Data migrated and validated (300,024 employees, 2.84M salary rows)
- [x] TLS, Keycloak, LDAP federation, three roles
- [x] API with token validation and role checks; React UI with role-based views
- [x] Row-level security, audit logging (including denied requests), audit viewer
- [x] Jenkins signs in through Keycloak; CI pipeline with lint, unit and integration tests, dependency and container scans
- [x] 79 automated tests
- [ ] GitHub (or Git server) sign-in through the same SSO
- [ ] Webhook-triggered builds (needs a public address or a self-hosted Git server)
- [ ] Multi-factor authentication (not implemented; see security review)
- [ ] Document repository stretch goal (not started)

All demo passwords are for local development only. Rotate every value in `.env` and remove the demo LDAP users and `admin.local` before sharing the stack.
