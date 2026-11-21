-- Lets HR admins create employees. Run after 02_post_migration.sql and 03_audit_access.sql (needs app.current_role()).
-- Safe to re-run. Same defence in depth as the rest of the project: the API checks the role, AND Postgres refuses
-- the write unless the request carries role hr_admin. The app's database user still gets NO UPDATE or DELETE on
-- HR data, so a bug (or a stolen token) can add rows but can never rewrite or erase history.
SET search_path TO hr, public;

-- Employee numbers. The migrated table has no generator, so add a sequence that continues after the highest
-- existing number. USAGE lets the app call nextval(); it cannot call setval() (that needs UPDATE).
CREATE SEQUENCE IF NOT EXISTS hr.employees_emp_no_seq AS integer;
SELECT setval('hr.employees_emp_no_seq', COALESCE(max(emp_no), 1), max(emp_no) IS NOT NULL) FROM hr.employees;
GRANT USAGE ON SEQUENCE hr.employees_emp_no_seq TO portal_app;

-- A new employee is one row in each of these four tables (written together, in one transaction, by the API).
GRANT INSERT ON hr.employees, hr.dept_emp, hr.titles, hr.salaries TO portal_app;

-- employees, dept_emp and titles had no row-level security. Turning it on denies everything without a policy, so
-- each gets (1) a SELECT policy that keeps the directory readable by every role, exactly as before, and
-- (2) an INSERT policy that only lets hr_admin add rows.
ALTER TABLE hr.employees ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS employees_read ON hr.employees;
DROP POLICY IF EXISTS employees_insert_hr ON hr.employees;
CREATE POLICY employees_read ON hr.employees FOR SELECT TO portal_app USING (true);
CREATE POLICY employees_insert_hr ON hr.employees FOR INSERT TO portal_app
  WITH CHECK (app.current_role() = 'hr_admin');

ALTER TABLE hr.dept_emp ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dept_emp_read ON hr.dept_emp;
DROP POLICY IF EXISTS dept_emp_insert_hr ON hr.dept_emp;
CREATE POLICY dept_emp_read ON hr.dept_emp FOR SELECT TO portal_app USING (true);
CREATE POLICY dept_emp_insert_hr ON hr.dept_emp FOR INSERT TO portal_app
  WITH CHECK (app.current_role() = 'hr_admin');

ALTER TABLE hr.titles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS titles_read ON hr.titles;
DROP POLICY IF EXISTS titles_insert_hr ON hr.titles;
CREATE POLICY titles_read ON hr.titles FOR SELECT TO portal_app USING (true);
CREATE POLICY titles_insert_hr ON hr.titles FOR INSERT TO portal_app
  WITH CHECK (app.current_role() = 'hr_admin');

-- salaries already has RLS (02_post_migration.sql): its SELECT policies stay as they are; add the INSERT policy.
DROP POLICY IF EXISTS salaries_insert_hr ON hr.salaries;
CREATE POLICY salaries_insert_hr ON hr.salaries FOR INSERT TO portal_app
  WITH CHECK (app.current_role() = 'hr_admin');
