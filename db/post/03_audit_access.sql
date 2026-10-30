-- Audit log access control. Run after 02_post_migration.sql (needs app.current_role()).
-- The API role may append rows, but can only READ them when the request carries role hr_admin.
-- No UPDATE/DELETE grant => append-only for the application.
GRANT SELECT, INSERT ON app.audit_log TO portal_app;
ALTER TABLE app.audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_insert ON app.audit_log;
DROP POLICY IF EXISTS audit_read_hr ON app.audit_log;
CREATE POLICY audit_insert  ON app.audit_log FOR INSERT TO portal_app WITH CHECK (true);
CREATE POLICY audit_read_hr ON app.audit_log FOR SELECT TO portal_app USING (app.current_role() = 'hr_admin');
