# Security review: SecureHR Portal

Review date: October 30, 2026. Scope: the code and configuration in this repository, as run by `docker compose` on a developer machine. Not in scope: production hosting, network design outside Docker, the sample dataset itself.

## Method
1. Read the authentication, authorisation, database and pipeline code and configuration.
2. Wrote automated tests for each security claim (79 tests; see README, "Testing").
3. **Mutation-checked the tests:** deliberately broke the security rules one at a time (RLS off, `BYPASSRLS` granted to the app role, audit log readable by all, UPDATE granted on salaries, employees allowed on the salaries endpoint, audience / issuer / signature / expiry checks disabled, `/audit` opened to managers, demographics leaked to employees, former managers treated as current) and confirmed the test suite fails each time, and only on the relevant tests.
4. Scanned dependencies and the backend image in CI (`pip-audit`, Trivy).

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Backend dependencies had known vulnerabilities, including a critical authentication bypass in PyJWT 2.10.1 | Critical | **Fixed**: upgraded (PyJWT 2.15.1, FastAPI 0.162.0 / Starlette 1.10.0); scans now run on every build |
| 2 | Refused requests (403) were not written to the audit log | Medium | **Fixed**: logged as `denied` with user, role, resource and the roles required |
| 3 | The audit viewer endpoint failed: the application's database user had no read access to the log | Medium | **Fixed**: append-only for the app; readable only when the request carries `hr_admin`, enforced in Postgres |
| 4 | Manager salary scoping must use current management and current department only | Medium | **Verified by tests**: former managers, people who moved departments and missing employee numbers get nothing |
| 5 | Database security rules rely on the API to state the caller's role | Medium | **Accepted**, see below |
| 6 | Jenkins has the Docker socket mounted and opened to all users in the container | High (local demo) | **Accepted for the demo**, see below |
| 7 | Any signed-in manager or employee can trigger Jenkins builds | Medium | **Open**: recommended change below |
| 8 | TLS stops at Nginx; traffic between containers is plain HTTP | Medium | **Accepted** with note |
| 9 | Keycloak runs in `start-dev` mode and the frontend runs the Vite dev server | Medium | **Accepted for the demo** |
| 10 | Multi-factor authentication not implemented | Low to Medium | **Descoped** |
| 11 | No secrets manager; secrets live in `.env` | Low to Medium | **Partial** |
| 12 | Frontend dependencies: 4 npm advisories (3 moderate, 1 high), not triaged; Trivy scans only the backend image | Medium | **Open** |
| 13 | 44 HIGH vulnerabilities in the Debian base image have no fix available and are ignored by the scan gate | Low to Medium | **Accepted**, re-scan periodically |
| 14 | Failed logins (401) are not in the audit log | Low | **By design** |
| 15 | No rate limiting on the API | Low | **Open** |

## Details

### Fixed

**1. Vulnerable dependencies.** The first CI scan reported 24 advisories in two packages. The one that mattered most was PyJWT, the library that validates Keycloak tokens: version 2.10.1 had a critical authentication-bypass issue fixed in 2.14. Upgraded to current releases, verified with `pip-audit` (no known vulnerabilities) and a clean Trivy report, and re-verified against the running portal. CI now fails the build on any fixable HIGH or CRITICAL finding.

**2. Denied requests are audited.** Previously only successful reads reached `app.audit_log`. A 403 for a logged-in user is now recorded with action `denied`, the resource, the caller's role, and the roles that would have been allowed. If the audit write itself fails, the request still gets its 403, so a logging fault can never turn a refusal into an error or a grant. Covered by unit and integration tests.

**3. Audit log access.** The first version of the audit viewer failed because the application's database user could only insert into the log. The application's database user may append entries and may read them only when the request's role is `hr_admin` (row-level security on `app.audit_log`). It cannot UPDATE, DELETE or TRUNCATE them, even as `hr_admin`. Reading the log is itself logged.

**4. Manager scoping.** Salary access for managers is limited to people currently in a department the manager currently manages. The first demo manager number belonged to a *former* manager (term ended 1991), which showed how easy it is to get the dates wrong. The tests now pin it down: former managers, people who moved departments, and tokens with no employee number all get no salary data (fail closed).

### What is in place (positives)
- Authorisation at three layers: UI, API role checks, and Postgres row-level security.
- Token validation checks signature (RS256 only), issuer, audience and expiry; `alg: none` and wrong-key tokens are rejected (tested).
- The API's database user is not a superuser, does not bypass RLS and has read-only access to HR data (tested).
- The backend container runs as a non-root user; all user input reaches SQL as bound parameters (an injection attempt is in the test suite); CORS is limited to the portal origin and GET.
- Nginx sets HSTS and `X-Content-Type-Options` for the portal site; HTTP redirects to HTTPS; Keycloak has brute-force protection enabled in the realm.
- `.env`, private keys and certificates are git-ignored; CI uses `.env.example` only.

### Accepted risks and limitations

**5. RLS trusts the API for the caller's identity.** The API tells Postgres who is asking (`app.role`, `app.emp_no`) for each request. Row-level security therefore protects against mistakes in the API's own checks, but a fully compromised API, or an SQL-injection flaw that allows stacked statements, could claim `hr_admin`. Closing that gap would require separate database logins per role or per-user database credentials, which is a larger redesign. Mitigations in place: parameterised queries everywhere, a minimal database user, and tests that exercise the rules directly.

**6. Docker socket in Jenkins.** Jenkins can run `docker` commands (needed to build images and run the integration database), which is effectively root on the host for anything running in that container. The demo also opens the socket to every user in the container (`chmod 666`). Acceptable for a local class demo; for anything shared, use a separate build agent or rootless Docker.

**8. Internal traffic is not encrypted.** Browsers reach every service over TLS through Nginx. Inside the Docker network, Nginx to backend, backend to Keycloak (key fetch) and so on use plain HTTP, and Keycloak's HTTP port is enabled. The requirement "TLS on all services" is therefore met at the network edge, not hop by hop.

**9. Development modes.** Keycloak is started with `start-dev` and the frontend serves the Vite dev server. Production would use `start` with real certificates and a built static frontend.

**10. No MFA.** Listed in the abstract as an additional feature and not implemented. Because every login (portal and Jenkins) goes through Keycloak, enabling an OTP required action in the realm would cover both; it was left out to keep demos simple.

**11. Secrets.** Secrets are kept out of Git via `.env`, but there is no secrets manager. Demo credentials (`Passw0rd!` for the LDAP users, the realm's `admin.local` fallback user) are deliberately weak and must be removed before any shared use.

**13. Base image CVEs.** Trivy runs with `--ignore-unfixed`, so only vulnerabilities with an available fix fail the build. The 44 HIGH findings in Debian packages (util-linux, ncurses, systemd) are not exploitable through this application's surface as far as reviewed, but remain until Debian ships patches; rebuild periodically to pick them up.

**14. 401s not audited.** Requests without a valid identity are not logged, because anyone on the network could otherwise fill the audit table with junk rows. Keycloak records login failures itself.

### Open: recommended next steps
- **7. Restrict who can build in Jenkins.** `jenkins/casc.yaml` gives managers and employees `Job/Build`. Builds run repository code with Docker access, so building should be limited to `hr_admin` or a dedicated developer role. Branch builds from the GitHub repository carry the same risk: only trusted people should be able to push branches.
- **12. Frontend scanning.** Triage the 4 npm advisories (`npm audit`), then add `npm audit --audit-level=high` to the pipeline and scan the frontend image with Trivy.
- **15. Rate limiting.** Add a limit at Nginx (`limit_req`) for `/api/`.
- Search currently treats `%` and `_` typed by the user as wildcards (harmless, but unescaped).

## Requirements check (from the project abstract)

| Requirement | Result |
|---|---|
| SSO login through OIDC with LDAP-backed credentials | Met |
| Three roles with enforced permissions | Met (API and database; tested) |
| Browse, search and filter employees, departments, titles, salaries | Met; the portal runs on the full migrated dataset, and the automated tests use a small fixed dataset |
| GitHub and Jenkins sign-in through the same SSO | **Jenkins met; GitHub not met.** GitHub's native SAML SSO needs a paid Enterprise plan; see below. |
| Automated build, test and deploy pipeline triggered by commits | Pipeline met; commit-triggered webhooks need a public address (builds are started manually); deploy stage only validates the compose file |
| TLS on all services | Met at the edge; internal hops are plain HTTP (finding 8) |
| Search under 2 seconds on the full dataset | **Not yet measured.** Indexes are in place (trigram, partial); time a few searches on the full data and record the result for the report |
| Audit logging of data access | Met, including denied requests |
| Fully containerised, reproducible, documented | Met; Keycloak LDAP and Jenkins mapper settings are manual steps documented in the README |

**GitHub sign-in.** The abstract's risk table offers a self-hosted alternative. Running Gitea in the compose stack with Keycloak as its OIDC provider would satisfy "GitHub/Git and Jenkins through the same SSO", and as a bonus lets Gitea send webhooks to Jenkins over the Docker network without a public tunnel.
