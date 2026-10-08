#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$CONTROL_APP_PASSWORD" <<'SQL'
CREATE ROLE controls_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE controls TO controls_app;
GRANT USAGE ON SCHEMA public TO controls_app;
SQL
