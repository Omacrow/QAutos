-- Local development only (docker-compose runs this on first start).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE sqa_app LOGIN PASSWORD 'sqa_app_dev' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
