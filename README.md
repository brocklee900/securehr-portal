# SecureHR Portal

A proof-of-concept enterprise HR portal with single sign-on and role-based access.

**React/TypeScript** → **FastAPI** → **PostgreSQL** (row-level security + audit log), identity via **Keycloak** (OIDC) federated to **OpenLDAP**, TLS via **Nginx**, CI/CD via **GitHub + Jenkins**.

```
Browser ──TLS──> Nginx ─┬─ portal.localhost  → React (Vite) ──┐ OIDC (auth code + PKCE)
                        │                      /api/ → FastAPI ── Postgres (schema hr, RLS; app.audit_log)
                        ├─ auth.localhost    → Keycloak ── LDAP (users + groups)
                        └─ jenkins.localhost → Jenkins (OIDC login, GitHub webhook)
```

## Access model

| Role | Directory | Department data | Salaries |
|---|---|---|---|
| `employee` | name, title, department | read | none (API 403, database returns 0 rows) |
| `manager` | + demographics | read | own department only (database RLS) |
| `hr_admin` | everything | everything | everyone, plus the audit log |

Access is enforced three times: the UI hides what a role can't use, the API checks the role on every request, and PostgreSQL row-level security enforces salary access even if the API were bypassed.

---

## Setup guide

### Prerequisites
- **Docker Desktop** (running)
- **Git**
- **mkcert**: https://github.com/FiloSottile/mkcert
- **Python 3.12** (only for running backend tests locally)

**Windows users:** run every `bash scripts/...` command in **Git Bash** (or WSL), not cmd or PowerShell. Two Git Bash quirks:
1. Run `export MSYS_NO_PATHCONV=1` in each new Git Bash window before running Docker commands, or Git Bash rewrites `/paths` and the migration script fails with `Cwd must be an absolute path`.
2. If a script fails with `$'\r': command not found`, it has Windows line endings. Fix with `sed -i 's/\r$//' .env scripts/*.sh`.

### 1. Check the backend (optional, no Docker needed)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows cmd: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q && ruff check .          # expect: 8 passed, all checks passed
cd ..
```

### 2. Configure and create TLS certificates
```bash
cp .env.example .env
```
Edit `.env` and replace every `change-me-...` value. **Avoid `@ : / # %` in passwords**, because they end up in connection URLs.

```bash
bash scripts/gen-certs.sh
ls nginx/certs                     # expect securehr.pem and securehr-key.pem
```
If `mkcert` isn't on your PATH, put `mkcert.exe` in `scripts/` and run:
`PATH="$PWD/scripts:$PATH" bash scripts/gen-certs.sh`

### 3. Migrate the sample data (MySQL to PostgreSQL)
```bash
export MSYS_NO_PATHCONV=1
bash scripts/migrate_mysql_to_pg.sh
```
This clones `datacharmer/test_db` into `db/test_db`, loads it into MySQL, copies it into Postgres schema `hr` with pgloader, then adds indexes and row-level security. It takes roughly 5 to 10 minutes. Success ends with six `OK` lines:

```
OK   employees    300024
OK   departments  9
OK   dept_emp     331603
OK   dept_manager 24
OK   titles       443308
OK   salaries     2844047
```
You can re-run `bash scripts/validate_migration.sh` at any time. Once migrated, `docker compose stop mysql` frees memory.

### 4. Start the stack
```bash
docker compose up -d --build
docker compose ps                  # all services Up; give Keycloak ~1 minute
```
Open https://auth.localhost (no certificate warning expected) and https://portal.localhost (redirects to a Keycloak login).

### 5. Configure Keycloak
Sign in at https://auth.localhost/admin using `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` from `.env`.

> **Switch the realm first.** The top-left dropdown defaults to `master`. Everything below happens in the **securehr** realm. The `hr_admin` role and the portal users do not exist in `master`.

**5a. Allow custom attributes.** Realm settings → General → **Unmanaged Attributes = Enabled** → Save. Without this the employee number never reaches the token.

**5b. Add the LDAP provider.** User federation → Add LDAP provider:

| Field | Value |
|---|---|
| UI display name | `ldap` |
| Vendor | Other |
| Connection URL | `ldap://ldap:389` |
| Bind type | simple |
| Bind DN | `cn=admin,dc=securehr,dc=local` |
| Bind credentials | `LDAP_ADMIN_PASSWORD` from `.env` |
| Edit mode | READ_ONLY |
| Users DN | `ou=people,dc=securehr,dc=local` |
| Username / RDN LDAP attribute | `uid` |
| UUID LDAP attribute | `entryUUID` |
| User object classes | `inetOrgPerson` |

Use **Test connection** and **Test authentication** (both must succeed), then Save.

**5c. Add two mappers** (provider → Mappers → Add mapper):

*Groups to roles*
- Name `groups`, type `group-ldap-mapper`
- LDAP Groups DN `ou=groups,dc=securehr,dc=local`
- Group Name LDAP Attribute `cn`, Group Object Classes `groupOfNames`
- Membership LDAP Attribute `member`, Membership Attribute Type `DN`
- Mode `READ_ONLY`, User Groups Retrieve Strategy `LOAD_GROUPS_BY_MEMBER_ATTRIBUTE`
- Save, then **Action → Sync LDAP groups to Keycloak**

*Employee number*
- Name `emp_no`, type `user-attribute-ldap-mapper`
- User Model Attribute `emp_no`, LDAP Attribute `employeeNumber`
- Read only On, Always read value from LDAP On

**5d. Sync users.** On the provider page: **Action → Sync all users** (expect 3 added).

**5e. Verify.** For `alice.hr`: Groups tab shows `hr-admins`, and Role mapping (with "Hide inherited roles" unchecked) shows `hr_admin`. For `bob.manager`: Attributes shows `emp_no`.

### 6. Test the portal

Use a private window per login. Demo password for all LDAP users: `Passw0rd!`

| Sign in as | Expect |
|---|---|
| `alice.hr` | Full directory; salary history for every employee |
| `bob.manager` | Salary history only for employees in his own department (`d001`, Marketing); "Salary data not available" elsewhere |
| `carol.employee` | No salary section at all |
| `admin.local` | Fallback HR admin that works without LDAP (you must set its password in Keycloak first, see Troubleshooting) |

**Manager scoping uses the `emp_no` claim.** Bob's LDAP `employeeNumber` is `110039`, a *current* manager of `d001`. Row-level security only recognises managers whose `dept_manager.to_date = '9999-01-01'`, so a former manager's number would see no salaries. To give a manager another identity:
```bash
docker compose exec postgres psql -U postgres -d employees -c "SELECT dm.dept_no, dm.emp_no FROM hr.dept_manager dm WHERE dm.to_date='9999-01-01' ORDER BY 1;"
```
Then update `employeeNumber` in LDAP (`ldapmodify`) and run **Sync all users** in Keycloak. The user must sign out and back in to get a fresh token.

**Prove the database enforces it** (run in Git Bash; adjust `110039` if you changed Bob's number):
```bash
docker compose exec -T postgres psql -U postgres -d employees <<'SQL'
BEGIN;
SET LOCAL ROLE portal_app;
SELECT set_config('app.role','manager',true), set_config('app.emp_no','110039',true);
SELECT 'own dept' AS case, count(*) FROM hr.salaries
 WHERE emp_no = (SELECT emp_no FROM hr.dept_emp WHERE to_date='9999-01-01'
   AND dept_no = (SELECT dept_no FROM hr.dept_manager WHERE emp_no=110039 AND to_date='9999-01-01') LIMIT 1)
UNION ALL
SELECT 'other dept', count(*) FROM hr.salaries
 WHERE emp_no = (SELECT emp_no FROM hr.dept_emp WHERE to_date='9999-01-01'
   AND dept_no <> (SELECT dept_no FROM hr.dept_manager WHERE emp_no=110039 AND to_date='9999-01-01') LIMIT 1);
SELECT set_config('app.role','employee',true);
SELECT 'as employee' AS case, count(*) FROM hr.salaries;
ROLLBACK;
SQL
```
Expect: own dept > 0, other dept = 0, as employee = 0.

**Check the audit log:**
```bash
docker compose exec postgres psql -U postgres -d employees -c "SELECT at,username,role,action,resource FROM app.audit_log ORDER BY at DESC LIMIT 15;"
```

### Stopping and resuming
Your data lives in Docker volumes and survives a restart.
```bash
docker compose stop                # or just quit Docker Desktop
# later:
export MSYS_NO_PATHCONV=1
docker compose up -d
```
**Never run `docker compose down -v`**, because `-v` deletes the volumes (database, Keycloak config, LDAP). After a restart, confirm the LDAP provider is still under User federation and `bob.manager` can still sign in.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Cwd must be an absolute path` during migration | Git Bash path rewriting. Run `export MSYS_NO_PATHCONV=1` in the same window first. |
| `$'\r': command not found` | CRLF line endings. `sed -i 's/\r$//' .env scripts/*.sh` |
| Vite says `Blocked request. This host ("frontend") is not allowed` | The Nginx `Host` header was dropped. The `location /` block in `nginx/nginx.conf` must re-declare its `proxy_set_header` lines (already fixed in this repo). Then `docker compose restart nginx`. |
| Can't sign in as `admin.local` | Switch to the **securehr** realm → Users → `admin.local` → Credentials → Reset password (`Passw0rd!`, Temporary off). Confirm it is in group `hr-admins`. The Keycloak admin account lives in `master` and cannot log in to the portal. |
| Role mapping doesn't show `hr_admin` | Wrong realm (you're in `master`), or "Hide inherited roles" is checked, or the groups mapper wasn't synced. See Step 5. |
| Signed in but "No portal role assigned" | The user has no group with a realm role. Check Groups and Role mapping in the `securehr` realm. |
| Manager sees no salaries anywhere | The `emp_no` claim is missing (Unmanaged Attributes not enabled, or `emp_no` mapper missing), or the number isn't a *current* manager. |
| pgloader can't log in to MySQL | pgloader can't use MySQL 8's default auth. The compose file pins `mysql:8.0` with `mysql_native_password` for this reason. |
| `/api/audit` returns an error | `portal_app` is insert-only on the audit table. Create a read-only role for it (TODO). |

## Repository layout

| Path | Purpose | Milestone |
|---|---|---|
| `docker-compose.yml`, `.env.example` | Full stack | 2 |
| `db/`, `scripts/migrate_mysql_to_pg.sh`, `scripts/validate_migration.sh` | MySQL to Postgres, indexes, RLS, audit table | 2, 7 |
| `ldap/bootstrap.ldif`, `keycloak/` | Directory, realm export, federation guide | 3 |
| `nginx/`, `scripts/gen-certs.sh` | TLS reverse proxy and local certs | 3 |
| `backend/` | FastAPI: OIDC validation, role checks, endpoints, audit, tests | 4 |
| `frontend/` | React/TS: login, search, detail, departments, role-based UI | 5 |
| `jenkins/`, `Jenkinsfile` | Jenkins with OIDC (Configuration as Code); pipeline: lint, test, build, scan, deploy | 6, 7 |
| `docs/` | Architecture notes, milestone checklist | 8 |

## Status and next steps
- [x] M2 Data migrated and validated
- [x] M3 TLS, Keycloak, LDAP federation
- [x] M4 API with token validation and role checks
- [x] M5 UI with role-based views
- [x] M7 (partial) Row-level security and audit logging verified
- [ ] M6 Jenkins SSO (`https://jenkins.localhost`), GitHub webhook, pipeline run. Replace `YOUR-ORG` in `jenkins/casc.yaml`.
- [ ] M7 MFA (Keycloak OTP), audit viewer role, dependency and container scans
- [ ] M8 Integration tests and security review
- [ ] Replace the Vite dev server with a production build served by Nginx for staging
- [ ] Jenkins mounts the Docker socket for convenience; use a dedicated build agent beyond a class demo

All demo passwords are for local development only. Rotate every value in `.env` before sharing the stack.
