-- Lets HR admins change a salary. Run after 04_hr_write_access.sql. Safe to re-run.
--
-- Salaries are a history: each row is one salary with the date it took effect (from_date) and the date it ended
-- (to_date, '9999-01-01' while it is still the current one). A change therefore
--   1. inserts the new salary, running from the effective date to '9999-01-01', and
--   2. closes the row that was current, setting its to_date to that same effective date.
-- Step 2 is the app's only UPDATE on HR data, and this file narrows it as far as possible:
--   * column privilege: only to_date can be updated, so an amount or a start date can never be edited;
--   * row-level security: only when the request carries hr_admin, and only on the row that is still open;
--   * a trigger: the new end date must be the start of the replacement salary, which must already exist, be
--     today or later, and come after the old row's start. Past salaries therefore cannot be rewritten.
-- The trigger also refuses a second pending change (the open salary starts in the future) and refuses a
-- change to one's own salary. HR may not change another HR admin's salary either; that rule needs LDAP group
-- membership, which the database does not have, so the API enforces it (backend/app/hr_lookup.py).
SET search_path TO hr, public;

-- At most one current ('9999-01-01') salary per employee. Checked at COMMIT (deferred), because a change
-- briefly has two open rows: the new one is inserted before the old one is closed.
DO $$
DECLARE offenders text;
BEGIN
  SELECT string_agg(emp_no::text, ', ') INTO offenders FROM (
    SELECT emp_no FROM hr.salaries WHERE to_date = '9999-01-01' GROUP BY emp_no HAVING count(*) > 1 LIMIT 20) s;
  IF offenders IS NOT NULL THEN
    RAISE EXCEPTION 'These employees already have more than one current salary, fix them first: %', offenders;
  END IF;
END $$;
ALTER TABLE hr.salaries DROP CONSTRAINT IF EXISTS salaries_one_current;
ALTER TABLE hr.salaries ADD CONSTRAINT salaries_one_current
  EXCLUDE USING btree (emp_no WITH =) WHERE (to_date = '9999-01-01') DEFERRABLE INITIALLY DEFERRED;

-- The only column the app may update.
REVOKE UPDATE ON hr.salaries FROM portal_app;
GRANT UPDATE (to_date) ON hr.salaries TO portal_app;

DROP POLICY IF EXISTS salaries_close_hr ON hr.salaries;
CREATE POLICY salaries_close_hr ON hr.salaries FOR UPDATE TO portal_app
  USING (app.current_role() = 'hr_admin' AND to_date = '9999-01-01')
  WITH CHECK (app.current_role() = 'hr_admin');

-- Rules for the app's own writes. Other database users (the migration, an administrator) are not affected.
-- Requests without hr_admin are left alone here: row-level security refuses them with "permission denied".
CREATE OR REPLACE FUNCTION app.salaries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_user <> 'portal_app' OR app.current_role() <> 'hr_admin' THEN
    RETURN NEW;
  END IF;

  IF NEW.emp_no = app.current_emp_no() THEN
    RAISE EXCEPTION 'You cannot change your own salary' USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF TG_OP = 'INSERT' THEN
    -- A new hire's first salary may start on any hire date. For anyone who already has a salary, a new row
    -- may only be a future-or-today change that becomes the current salary.
    IF EXISTS (SELECT 1 FROM hr.salaries WHERE emp_no = NEW.emp_no)
       AND (NEW.from_date < current_date OR NEW.to_date <> '9999-01-01') THEN
      RAISE EXCEPTION 'A salary change must take effect today or later and become the current salary'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;

  -- UPDATE: closing the current salary (row-level security already limits this to the open row).
  IF NEW.emp_no IS DISTINCT FROM OLD.emp_no OR NEW.salary IS DISTINCT FROM OLD.salary
     OR NEW.from_date IS DISTINCT FROM OLD.from_date THEN
    RAISE EXCEPTION 'Only the end date of a salary can change' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.to_date <> '9999-01-01' THEN
    RAISE EXCEPTION 'Only the current salary can be closed' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.from_date > current_date THEN
    RAISE EXCEPTION 'This employee already has a pending salary change (from %)', OLD.from_date
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.to_date < current_date OR NEW.to_date <= OLD.from_date THEN
    RAISE EXCEPTION 'A salary change must take effect today or later, after the current salary started'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM hr.salaries
                 WHERE emp_no = NEW.emp_no AND from_date = NEW.to_date AND to_date = '9999-01-01') THEN
    RAISE EXCEPTION 'Add the new salary (starting %) before closing the current one', NEW.to_date
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS salaries_guard ON hr.salaries;
CREATE TRIGGER salaries_guard BEFORE INSERT OR UPDATE ON hr.salaries
  FOR EACH ROW EXECUTE FUNCTION app.salaries_guard();
