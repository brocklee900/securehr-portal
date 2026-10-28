-- Run after pgloader: indexes for <2s search, grants, and row-level security.
SET search_path TO hr, public;

CREATE INDEX IF NOT EXISTS idx_emp_name_trgm ON hr.employees
  USING gin ((lower(first_name || ' ' || last_name)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_dept_emp_current ON hr.dept_emp (dept_no) WHERE to_date = '9999-01-01';
CREATE INDEX IF NOT EXISTS idx_titles_current  ON hr.titles (emp_no) WHERE to_date = '9999-01-01';
CREATE INDEX IF NOT EXISTS idx_salaries_emp    ON hr.salaries (emp_no, from_date DESC);
ANALYZE;

GRANT USAGE ON SCHEMA hr TO portal_app;
GRANT SELECT ON ALL TABLES IN SCHEMA hr TO portal_app;

-- Row-level security (second layer behind API role checks).
-- The API sets app.role / app.emp_no per transaction (backend/app/db.py).
CREATE OR REPLACE FUNCTION app.current_emp_no() RETURNS int LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.emp_no', true), '')::int $$;
CREATE OR REPLACE FUNCTION app.current_role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT COALESCE(current_setting('app.role', true), '') $$;
GRANT EXECUTE ON FUNCTION app.current_emp_no(), app.current_role() TO portal_app;

ALTER TABLE hr.salaries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS salaries_hr ON hr.salaries;
DROP POLICY IF EXISTS salaries_mgr ON hr.salaries;
CREATE POLICY salaries_hr ON hr.salaries FOR SELECT TO portal_app
  USING (app.current_role() = 'hr_admin');
CREATE POLICY salaries_mgr ON hr.salaries FOR SELECT TO portal_app
  USING (
    app.current_role() = 'manager' AND emp_no IN (
      SELECT de.emp_no FROM hr.dept_emp de
      WHERE de.to_date = '9999-01-01' AND de.dept_no IN (
        SELECT dm.dept_no FROM hr.dept_manager dm
        WHERE dm.emp_no = app.current_emp_no() AND dm.to_date = '9999-01-01'))
  );
-- Employees get no policy => zero salary rows even if the API check were bypassed.
