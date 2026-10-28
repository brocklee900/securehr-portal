# Milestone checklist
- [ ] **M1 (Oct 9)** repo, roles, abstract
- [ ] **M2 (Oct 16)** `docker compose up postgres`; `scripts/migrate_mysql_to_pg.sh` ends with all OK rows
- [ ] **M3 (Oct 23)** mkcert certs; Keycloak up; LDAP federation + group/role + `emp_no` mappers; `https://auth.localhost` trusted
- [ ] **M4 (Oct 30)** API endpoints return data with a real token; `pytest` green; add integration tests against a seeded DB
- [ ] **M5 (Nov 6)** login → search → detail → departments; salary section hidden for employees
- [ ] **M6 (Nov 13)** GitHub OAuth via Keycloak; Jenkins OIDC login (JCasC); webhook → pipeline runs
- [ ] **M7 (Nov 20)** OTP MFA required; audit viewer role; RLS tests; pip-audit + Trivy in pipeline (MinIO optional)
- [ ] **M8 (Nov 27)** integration + security review; code freeze; docs
- [ ] **M9 (Dec 1)** demo + report

Suggested ownership: Vincent – DB/backend; Jin Ting – Keycloak/LDAP/Nginx; Jin – frontend/Jenkins/CI (pair on Keycloak + Jenkins per risk table).
