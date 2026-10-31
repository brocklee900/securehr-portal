# Milestone status (as of October 30, 2026)

| # | Milestone | Due | Status |
|---|---|---|---|
| 1 | Kickoff, repo, abstract | Oct 9 | Done |
| 2 | Docker Compose, MySQL to PostgreSQL migration validated | Oct 16 | Done: 6 tables match row for row |
| 3 | Keycloak + LDAP, TLS on all services | Oct 23 | Done (TLS at the edge; internal hops HTTP) |
| 4 | FastAPI backend, OIDC token validation | Oct 30 | Done |
| 5 | React/TypeScript frontend with role-based UI | Nov 6 | Done |
| 6 | GitHub + Jenkins on SSO, webhooks, CI running | Nov 13 | **Partial:** Jenkins SSO and CI pipeline done. GitHub SSO and webhooks outstanding (recommended: Gitea + Keycloak) |
| 7 | MFA, audit logging, row-level security, security scans | Nov 20 | **Partial:** RLS, audit log (with denied requests), audit viewer, dependency and container scans done. MFA descoped. Document repository not started |
| 8 | Integration testing, security review, bug fixes, documentation | Nov 27 | **In progress:** 79 automated tests, security review written. Remaining: findings 7, 12, 15; timing measurement; final read-through |
| 9 | Final demo, presentation, project report | Dec 1 | Not started |

## Remaining work, in suggested order
1. **Git server SSO + webhooks** (required by the abstract): Gitea in compose, OIDC login via Keycloak, webhook to Jenkins.
2. **Quick security follow-ups:** restrict Jenkins builds to HR admins, `npm audit` in CI, Nginx rate limit.
3. **Evidence for the report:** screenshots of each role's view, audit log, green pipeline; search timing on the full dataset; test and scan output.
4. **Demo script and slides.**
5. Stretch (only if time allows): document repository with MinIO; MFA.

## Suggested ownership
Vincent: database, backend, tests. Jin Ting: Keycloak, LDAP, Nginx. Jin: frontend, Jenkins and CI. Pair on Keycloak and Jenkins integration per the risk table.
