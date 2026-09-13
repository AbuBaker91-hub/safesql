-- Role readonly_app: SELECT only on the public schema. Idempotent.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_app') THEN
        CREATE ROLE readonly_app LOGIN PASSWORD 'readonly';
    ELSE
        ALTER ROLE readonly_app LOGIN PASSWORD 'readonly';
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO readonly_app', current_database());
END
$$;

-- Let the connecting user assume the role via SET ROLE when no separate
-- readonly login is available (e.g. Neon's single pooled connection string).
DO $$
BEGIN
    IF current_user <> 'readonly_app' THEN
        EXECUTE format('GRANT readonly_app TO %I', current_user);
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO readonly_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_app;
