# SecureHR Portal

SSO-enabled HR data portal: **React/TS** → **FastAPI** → **PostgreSQL** (row-level security), identity via **Keycloak** (OIDC) federated to **OpenLDAP**, TLS via **Nginx**, CI/CD via **GitHub + Jenkins**.

```
Browser ──TLS──> Nginx ─┬─ portal.localhost  → React (Vite)  ─┐ OIDC (PKCE)
                        │                       /api/ → FastAPI ── Postgres (schema hr, RLS; app.audit_log)
                        ├─ auth.localhost    → Keycloak ── LDAP (users/groups) 
                        └─ jenkins.localhost → Jenkins (OIDC login, GitHub webhook)
```

## Quick start
```bash
cp .env.example .env              # edit secrets
bash scripts/gen-certs.sh         # M3: needs mkcert
bash scripts/migrate_mysql_to_pg.sh   # M2: loads test_db, pgloader -> Postgres schema `hr`, validates counts
docker compose up -d --build
```
Then open **https://portal.localhost** (`*.localhost` resolves to 127.0.0.1 in modern browsers).
Demo users (LDAP, after federation is configured per `keycloak/README.md`; password `Passw0rd!`):
`alice.hr` (HR Admin), `bob.manager` (Manager, set `employeeNumber` to a real manager `emp_no` from `hr.dept_manager`), `carol.employee`.
Fallback without LDAP: `admin.local` (hr_admin).

> First-run order matters: Postgres init creates the `portal_app` role and `app.audit_log`; the migration script then loads `hr.*` and applies indexes + RLS (`db/post/02_post_migration.sql`).

## Layout
| Path | Purpose | Milestone |
|---|---|---|
| `docker-compose.yml`, `.env.example` | Whole stack | 2 |
| `db/`, `scripts/migrate_mysql_to_pg.sh`, `scripts/validate_migration.sh` | MySQL→Postgres, indexes, RLS, audit table | 2, 7 |
| `ldap/bootstrap.ldif`, `keycloak/` | Directory + realm + federation guide | 3 |
| `nginx/`, `scripts/gen-certs.sh` | TLS reverse proxy | 3 |
| `backend/` | FastAPI: OIDC validation, role checks, endpoints, audit, tests | 4 |
| `frontend/` | React/TS: login, search, detail, departments, role-based UI | 5 |
| `jenkins/`, `Jenkinsfile` | Jenkins w/ OIDC (JCasC), pipeline: lint → test → build → scan → deploy | 6, 7 |
| `docs/` | Architecture, milestone checklist | 8 |

## Local backend dev
```bash
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pytest && ruff check .
```

## Access model
| Role | Directory | Dept data | Salaries |
|---|---|---|---|
| employee | name/title/dept only | read | ✗ (API 403, RLS 0 rows) |
| manager | + demographics | read | own department only (RLS) |
| hr_admin | all | all | all, plus `/audit` |

## Known TODOs / decisions for the team
- Replace the Vite dev server with a production build served by Nginx for staging.
- Jenkins mounts the Docker socket for convenience; use a dedicated build agent for anything beyond a class demo.
- Grant a separate read-only DB role for `/audit` (currently `portal_app` is insert-only, so that endpoint will error until you do).
- Rotate every value in `.env`; the LDAP demo passwords are for local use only.
