-- Run once per environment as a superuser, before the first migration.
-- The API and worker connect as this role. It is deliberately NOT a superuser
-- and has NO BYPASSRLS, so Row-Level Security is always enforced.
--
-- Railway: open the Postgres service > Data > Query, replace the password, run.
-- Then set DATABASE_URL for api/worker to use sqa_app, and
-- DATABASE_URL_MIGRATIONS to the default postgres URL.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqa_app') THEN
    CREATE ROLE sqa_app LOGIN PASSWORD 'CHANGE_ME'
      NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;
