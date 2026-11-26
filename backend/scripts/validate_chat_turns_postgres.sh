#!/usr/bin/env bash
# Requires PostgreSQL binaries and a non-root user. Uses only a disposable Unix socket.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
pgbin=${PG_BIN:-$(pg_config --bindir)}
work=$(mktemp -d)
cleanup() {
    "$pgbin/pg_ctl" -D "$work/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf -- "$work"
}
trap cleanup EXIT
"$pgbin/initdb" -D "$work/data" --no-locale --auth=trust -U postgres >/dev/null
"$pgbin/pg_ctl" -D "$work/data" -l "$work/server.log" -o "-c listen_addresses='' -k $work" -w start >/dev/null || { cat "$work/server.log" >&2; exit 1; }
pg() {
    "$pgbin/psql" -X -q -v ON_ERROR_STOP=1 -h "$work" -U postgres "$@"
}
pg -d postgres <<'SQL'
create role anon;
create role authenticated;
create role service_role bypassrls;
create database turn_fresh;
create database turn_upgrade;
SQL
for database in turn_fresh turn_upgrade; do
    pg -d "$database" <<'SQL'
create schema auth;
create table auth.users (id uuid primary key, raw_user_meta_data jsonb);
create function auth.uid() returns uuid language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated, service_role;
SQL
    for migration in "$root"/supabase/migrations/*.sql; do
        if [[ "$database" == turn_upgrade && "$migration" == *008b* ]]; then
            pg -d "$database" <<'SQL'
insert into auth.users (id) values ('10000000-0000-4000-8000-000000000001');
insert into public.conversations(id, user_id, title)
values ('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001','Existing history');
insert into public.conversation_messages(id, conversation_id, user_id, role, text)
values ('30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
        '10000000-0000-4000-8000-000000000001','user','Existing message');
SQL
        fi
        pg -d "$database" --single-transaction -f "$migration"
    done
    pg -d "$database" -v upgrade="$([[ "$database" == turn_upgrade ]] && echo true || echo false)"         -f "$root/backend/scripts/chat_turn_postgres_assertions.sql"
    call="select (public.accept_chat_turn('10000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000009','20000000-0000-4000-8000-000000000009', repeat('a',64),'Race','Race',true,0))->>'claimed'"
    pg -d "$database" -At -c "begin; $call; select pg_sleep(.3); commit;" > "$work/one" &
    first=$!
    pg -d "$database" -At -c "$call" > "$work/two" &
    second=$!
    wait "$first"
    wait "$second"
    [[ "$(cat "$work/one" "$work/two" | awk '/^(true|false)$/ {print}' | sort)" == $'false\ntrue' ]]
    echo "PASS $database: schema, settlement, ownership, pagination, concurrent claim"
done

if [[ "${RUN_CHAT_TURN_PROCESS_TESTS:-0}" == 1 ]]; then
    (
        cd "$root/backend"
        ASKHYPE_CHAT_TEST_POSTGRES_SOCKET="$work" ASKHYPE_CHAT_TEST_PSQL="$pgbin/psql" \
            "${CHAT_TURN_TEST_PYTHON:-python3}" -m pytest -q tests/test_chat_turn_processes.py
    )
fi
