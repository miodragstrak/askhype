#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
container=''
cleanup() {
    if [[ -n "$container" ]]; then
        docker rm -fv "$container" >/dev/null
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

container=$(docker run --detach --network none --label askhype.test=research-postgres \
    -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-bookworm)
pg() {
    docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"
}

for ((attempt=1; attempt<=60; attempt++)); do
    # The image's temporary initialization server listens on sockets only.
    if pg -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1; then break; fi
    if ((attempt == 60)); then
        docker logs "$container" >&2
        exit 1
    fi
    sleep 1
done

pg <<'SQL'
CREATE ROLE anon;
CREATE ROLE authenticated;
CREATE ROLE service_role BYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
SQL

for migration in \
    202611130001_ask_dr_001_research_jobs.sql \
    202611220001_ask_p0_history_conversations.sql \
    202611250001_research_conversation_lifecycle.sql; do
    printf 'Applying %s\n' "$migration"
    pg --single-transaction -f - < "$root/supabase/migrations/$migration"
done

pg -f - < "$root/backend/scripts/research_postgres_assertions.sql"
printf 'PostgreSQL integration assertions passed.\n'
