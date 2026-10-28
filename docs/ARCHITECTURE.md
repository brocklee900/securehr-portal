# Architecture notes

**AuthN:** Browser does OIDC auth-code + PKCE with Keycloak. API validates RS256 JWTs against Keycloak's JWKS (fetched over the internal Docker network), checking `iss`, `aud=securehr-portal`, `exp`.
**Issuer gotcha:** tokens are issued for `https://auth.localhost/...`, so the API config keeps the public issuer URL but fetches keys from `http://keycloak:8080`.

**AuthZ (defense in depth):**
1. UI hides what a role can't use (convenience only).
2. FastAPI `require_role` / per-field filtering.
3. Postgres RLS on `hr.salaries`; the API runs as non-owner `portal_app` and sets `app.role` / `app.emp_no` with `set_config(..., true)` inside each transaction.

**Audit:** every request inserts into `app.audit_log` in the same transaction as the read.

**Manager scoping** depends on the `emp_no` token claim (LDAP `employeeNumber` → Keycloak attribute → token). If it's missing, managers see no salaries (fails closed).

**Performance (<2s search):** trigram index on lower(full name), partial indexes on current rows (`to_date='9999-01-01'`), pagination capped at 100. Check with `EXPLAIN ANALYZE` on the full dataset; the `count(*)` can be replaced with an estimate if it dominates.

**Risks carried from the abstract:** pgloader type/date quirks (validate with `scripts/validate_migration.sh`), LDAP federation complexity (local fallback user), GitHub SAML on free plans (broker OAuth through Keycloak or use Gitea).
