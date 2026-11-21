# Architecture notes

**AuthN:** Browser does OIDC auth-code + PKCE with Keycloak. API validates RS256 JWTs against Keycloak's JWKS (fetched over the internal Docker network), checking `iss`, `aud=securehr-portal`, `exp`.
**Issuer gotcha:** tokens are issued for `https://auth.localhost/...`, so the API config keeps the public issuer URL but fetches keys from `http://keycloak:8080`.

**AuthZ (defense in depth):**
1. UI hides what a role can't use (convenience only).
2. FastAPI `require_role` / per-field filtering.
3. Postgres RLS on `hr.salaries`; the API runs as non-owner `portal_app` and sets `app.role` / `app.emp_no` with `set_config(..., true)` inside each transaction.

**Creating employees:** `POST /hr/employees`, `hr_admin` only. The router carries the role requirement (new routes under `/hr` are protected by default) and Postgres independently refuses the INSERTs for any other role (`db/post/04_hr_write_access.sql`: INSERT policies on `employees`, `dept_emp`, `titles`, `salaries`; no UPDATE/DELETE grant anywhere). One request writes all four tables in one transaction. The employee number comes from a database sequence, never from the client. Start dates equal the hire date and end dates use the dataset's `9999-01-01` "current" marker, so the new person immediately appears in search, department lists and (for the department's current manager) salary views.

**Changing salaries:** `POST /hr/employees/{n}/salaries` (and `GET /hr/employees/{n}/salary-change` for the form), `hr_admin` only. Salaries are a history: one row per salary with `from_date` (takes effect) and `to_date` (`9999-01-01` while current). A change, in one transaction, locks the current row, inserts the new salary (effective date → `9999-01-01`) and sets the old row's `to_date` to the effective date. `db/post/05_hr_salary_adjust.sql` makes that the only possible update: the app has UPDATE on the `to_date` column alone, row-level security limits it to the open row for `hr_admin`, and a trigger requires the new end date to be today or later and to match an already-inserted replacement, refuses a second pending change and refuses one's own salary. A deferred exclusion constraint keeps at most one current salary per employee. The "not another HR admin" rule needs group membership, which only LDAP has: the API asks LDAP live (read-only bind, `app/hr_lookup.py`) before each change and refuses if LDAP cannot answer. Amounts are not written to the audit log.

**Audit:** every request inserts into `app.audit_log` in the same transaction as the read.

**Manager scoping** depends on the `emp_no` token claim (LDAP `employeeNumber` → Keycloak attribute → token). If it's missing, managers see no salaries (fails closed).

**Performance (<2s search):** trigram index on lower(full name), partial indexes on current rows (`to_date='9999-01-01'`), pagination capped at 100. Check with `EXPLAIN ANALYZE` on the full dataset; the `count(*)` can be replaced with an estimate if it dominates.

**Risks carried from the abstract:** pgloader type/date quirks (validate with `scripts/validate_migration.sh`), LDAP federation complexity (local fallback user), GitHub SAML on free plans (broker OAuth through Keycloak or use Gitea).
