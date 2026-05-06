-- 003-role-model.sql
-- Align authentication roles across PostgreSQL, backend policy, and frontend UI.
--
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

-- Drop old role constraint before writing new role values.
-- The old constraint only allows ('admin', 'user'), so UPDATE role='operator'
-- must not run before this.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

-- Extra-safe cleanup for databases where Postgres generated a different
-- check-constraint name.
DO $$
DECLARE
    constraint_record RECORD;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%role%'
    LOOP
        EXECUTE format('ALTER TABLE users DROP CONSTRAINT IF EXISTS %I', constraint_record.conname);
    END LOOP;
END $$;

-- Normalize known legacy role.
UPDATE users
SET role = 'operator'
WHERE role = 'user';

-- Convert NULL or unexpected roles to viewer instead of failing the migration.
UPDATE users
SET role = 'viewer'
WHERE role IS NULL
   OR role NOT IN ('admin', 'operator', 'runner', 'viewer', 'auditor');

-- Set final default.
ALTER TABLE users
ALTER COLUMN role SET DEFAULT 'operator';

-- Add final role constraint.
ALTER TABLE users
ADD CONSTRAINT users_role_check
CHECK (role IN ('admin', 'operator', 'runner', 'viewer', 'auditor'));

-- Helpful indexes for admin/user filtering.
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active);

COMMENT ON COLUMN users.role IS
'Authentication role. Allowed values: admin, operator, runner, viewer, auditor. Legacy user is migrated to operator.';

COMMIT;