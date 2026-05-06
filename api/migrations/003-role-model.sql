-- 003-role-model.sql
-- Align authentication roles across PostgreSQL, backend policy, and frontend UI.
-- Final persisted roles:
-- admin    = full system administrator
-- operator = can operate simulator runs
-- runner   = can start/view runs, but cannot cancel/delete
-- viewer   = read-only user
-- auditor  = read-only evidence/audit user
--
-- Legacy role:
-- user is migrated to operator and should no longer be stored.

BEGIN;

-- Normalize known legacy role.
UPDATE users
SET role = 'operator'
WHERE role = 'user';

-- Convert any unexpected role to viewer instead of failing the migration.
UPDATE users
SET role = 'viewer'
WHERE role IS NULL
   OR role NOT IN ('admin', 'operator', 'runner', 'viewer', 'auditor');

-- Replace old role constraint.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users
ADD CONSTRAINT users_role_check
CHECK (role IN ('admin', 'operator', 'runner', 'viewer', 'auditor'));

ALTER TABLE users
ALTER COLUMN role SET DEFAULT 'operator';

-- Helpful indexes for admin/user filtering.
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active);

-- Optional audit comments.
COMMENT ON COLUMN users.role IS
'Authentication role. Allowed values: admin, operator, runner, viewer, auditor. Legacy user is migrated to operator.';

COMMIT;