-- HYPE-ASK-002: durable rolling-24-hour prompt quotas.
-- Counting rule: completed events and reservations newer than 10 minutes count.
-- Failed and stale reservations do not count. Anonymous identifiers are HMAC
-- hashes produced by the backend; raw browser UUIDs must never be stored here.

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    plan text not null default 'free',
    location text,
    language text,
    can_activate_mock_premium boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint profiles_plan_check check (plan in ('free', 'premium'))
);

alter table public.profiles add column if not exists display_name text;
alter table public.profiles add column if not exists plan text not null default 'free';
alter table public.profiles add column if not exists location text;
alter table public.profiles add column if not exists language text;
alter table public.profiles add column if not exists can_activate_mock_premium boolean not null default false;
alter table public.profiles add column if not exists created_at timestamptz not null default now();
alter table public.profiles add column if not exists updated_at timestamptz not null default now();

do $$
begin
    if exists (select 1 from public.profiles where plan not in ('free', 'premium') or plan is null) then
        raise exception 'Incompatible public.profiles data: plan must be free or premium';
    end if;
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.profiles'::regclass and conname = 'profiles_plan_check'
    ) then
        alter table public.profiles
            add constraint profiles_plan_check check (plan in ('free', 'premium')) not valid;
        alter table public.profiles validate constraint profiles_plan_check;
    end if;
end
$$;

insert into public.profiles (user_id)
select id from auth.users
on conflict (user_id) do nothing;

create or replace function public.create_askhype_profile()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    insert into public.profiles (user_id, display_name)
    values (new.id, nullif(new.raw_user_meta_data ->> 'display_name', ''))
    on conflict (user_id) do nothing;
    return new;
end;
$$;

do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgname = 'askhype_create_profile_after_signup'
          and tgrelid = 'auth.users'::regclass
    ) then
        create trigger askhype_create_profile_after_signup
            after insert on auth.users
            for each row execute function public.create_askhype_profile();
    end if;
end
$$;

revoke all on function public.create_askhype_profile() from public, anon, authenticated;

create table if not exists public.usage_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) on delete cascade,
    anonymous_id_hash text,
    status text not null default 'reserved',
    provider text,
    conversation_id text,
    failure_code text,
    created_at timestamptz not null default now(),
    finalized_at timestamptz,
    constraint usage_events_one_subject_check check (
        (user_id is not null and anonymous_id_hash is null)
        or (user_id is null and anonymous_id_hash is not null)
    ),
    constraint usage_events_status_check check (status in ('reserved', 'completed', 'failed'))
);

alter table public.usage_events add column if not exists user_id uuid;
alter table public.usage_events add column if not exists anonymous_id_hash text;
alter table public.usage_events add column if not exists status text not null default 'reserved';
alter table public.usage_events add column if not exists provider text;
alter table public.usage_events add column if not exists conversation_id text;
alter table public.usage_events add column if not exists failure_code text;
alter table public.usage_events add column if not exists created_at timestamptz not null default now();
alter table public.usage_events add column if not exists finalized_at timestamptz;

-- Legacy AskHype stored the backend-generated HMAC in anonymous_id. Preserve
-- that value exactly; this is not permission to infer or migrate raw UUIDs.
do $$
declare
    v_has_legacy_anonymous_id boolean;
    v_has_conflicting_hashes boolean;
begin
    select exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'usage_events'
          and column_name = 'anonymous_id'
    ) into v_has_legacy_anonymous_id;

    if v_has_legacy_anonymous_id then
        execute $sql$
            select exists (
                select 1
                from public.usage_events
                where user_id is null
                  and anonymous_id is not null
                  and anonymous_id_hash is not null
                  and anonymous_id <> anonymous_id_hash
            )
        $sql$ into v_has_conflicting_hashes;

        if v_has_conflicting_hashes then
            raise exception 'Incompatible public.usage_events data: legacy and current anonymous hashes conflict';
        end if;

        execute $sql$
            update public.usage_events
               set anonymous_id_hash = anonymous_id
             where user_id is null
               and anonymous_id_hash is null
               and anonymous_id is not null
        $sql$;
    end if;
end
$$;

-- The legacy constraint references anonymous_id and would reject new guest
-- rows that store their backend HMAC in anonymous_id_hash.
alter table public.usage_events
    drop constraint if exists usage_events_identity_check;

do $$
begin
    if exists (
        select 1 from public.usage_events
        where (user_id is null) = (anonymous_id_hash is null)
    ) then
        raise exception 'Incompatible public.usage_events data: exactly one subject identifier is required';
    end if;
    if exists (select 1 from public.usage_events where status not in ('reserved', 'completed', 'failed')) then
        raise exception 'Incompatible public.usage_events data: unsupported status';
    end if;
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.usage_events'::regclass
          and conname = 'usage_events_one_subject_check'
    ) then
        alter table public.usage_events add constraint usage_events_one_subject_check check (
            (user_id is not null and anonymous_id_hash is null)
            or (user_id is null and anonymous_id_hash is not null)
        ) not valid;
        alter table public.usage_events validate constraint usage_events_one_subject_check;
    end if;
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.usage_events'::regclass
          and conname = 'usage_events_status_check'
    ) then
        alter table public.usage_events
            add constraint usage_events_status_check check (status in ('reserved', 'completed', 'failed')) not valid;
        alter table public.usage_events validate constraint usage_events_status_check;
    end if;
end
$$;

create index if not exists usage_events_user_window_idx
    on public.usage_events (user_id, created_at desc) where user_id is not null;
create index if not exists usage_events_anonymous_window_idx
    on public.usage_events (anonymous_id_hash, created_at desc) where anonymous_id_hash is not null;
create index if not exists usage_events_stale_reservations_idx
    on public.usage_events (created_at) where status = 'reserved';

alter table public.profiles enable row level security;
alter table public.usage_events enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
    for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists profiles_update_own_preferences on public.profiles;
create policy profiles_update_own_preferences on public.profiles
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

revoke all on table public.profiles from anon, authenticated;
grant select on table public.profiles to authenticated;
grant update (display_name, location, language, updated_at) on table public.profiles to authenticated;
grant all on table public.profiles to service_role;

revoke all on table public.usage_events from anon, authenticated;
grant all on table public.usage_events to service_role;

-- Remove only the known legacy AskHype overload. PostgreSQL function identity
-- is name plus argument types, so CREATE OR REPLACE below cannot replace this
-- six-argument version. Leaving it would retain monthly/period semantics and
-- the caller-supplied p_plan argument as an ambiguous, stale RPC surface.
do $$
begin
    if to_regprocedure(
        'public.reserve_prompt_usage(uuid,text,text,integer,timestamptz,uuid)'
    ) is not null then
        execute $sql$
            revoke all on function public.reserve_prompt_usage(
                uuid, text, text, integer, timestamptz, uuid
            ) from public, anon, authenticated
        $sql$;
    end if;
end
$$;

drop function if exists public.reserve_prompt_usage(
    uuid, text, text, integer, timestamptz, uuid
);

create or replace function public.reserve_prompt_usage(
    p_user_id uuid,
    p_anonymous_id_hash text,
    p_limit integer,
    p_request_id uuid
)
returns table (
    allowed boolean,
    usage_event_id uuid,
    used integer,
    "limit" integer,
    remaining integer,
    reset_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_window_start timestamptz;
    v_stale_before timestamptz;
    v_subject text;
    v_limit integer;
    v_used integer;
    v_reset_at timestamptz;
    v_event_id uuid;
begin
    if (p_user_id is null) = (p_anonymous_id_hash is null) then
        raise exception 'Exactly one quota subject is required';
    end if;

    v_window_start := v_now - interval '24 hours';
    v_stale_before := v_now - interval '10 minutes';
    v_subject := case when p_user_id is not null then 'user:' || p_user_id::text
                      else 'guest:' || p_anonymous_id_hash end;
    perform pg_advisory_xact_lock(hashtextextended(v_subject, 0));

    if p_user_id is not null then
        select case when p.plan = 'premium' then 200 else 10 end
          into v_limit
          from public.profiles p
         where p.user_id = p_user_id;
        v_limit := coalesce(v_limit, 10);
    else
        if p_limit is null or p_limit <= 0 then
            raise exception 'Anonymous quota limit must be positive';
        end if;
        v_limit := p_limit;
    end if;

    update public.usage_events e
       set status = 'failed', finalized_at = v_now, failure_code = 'stale_reservation'
     where e.status = 'reserved'
       and e.created_at < v_stale_before
       and ((p_user_id is not null and e.user_id = p_user_id)
         or (p_user_id is null and e.anonymous_id_hash = p_anonymous_id_hash));

    select e.id into v_event_id
      from public.usage_events e
     where e.id = p_request_id
       and ((p_user_id is not null and e.user_id = p_user_id)
         or (p_user_id is null and e.anonymous_id_hash = p_anonymous_id_hash));

    select count(*)::integer, min(e.created_at) + interval '24 hours'
      into v_used, v_reset_at
      from public.usage_events e
     where e.created_at >= v_window_start
       and (e.status = 'completed' or (e.status = 'reserved' and e.created_at >= v_stale_before))
       and ((p_user_id is not null and e.user_id = p_user_id)
         or (p_user_id is null and e.anonymous_id_hash = p_anonymous_id_hash));

    if v_event_id is not null then
        return query select true, v_event_id, v_used, v_limit,
            greatest(v_limit - v_used, 0), v_reset_at;
        return;
    end if;

    if v_used >= v_limit then
        return query select false, null::uuid, v_used, v_limit, 0, v_reset_at;
        return;
    end if;

    insert into public.usage_events (id, user_id, anonymous_id_hash, status, created_at)
    values (p_request_id, p_user_id, p_anonymous_id_hash, 'reserved', v_now)
    returning id into v_event_id;

    v_used := v_used + 1;
    v_reset_at := coalesce(v_reset_at, v_now + interval '24 hours');
    return query select true, v_event_id, v_used, v_limit,
        greatest(v_limit - v_used, 0), v_reset_at;
end;
$$;

create or replace function public.finalize_prompt_usage(
    p_usage_event_id uuid,
    p_status text,
    p_provider text,
    p_conversation_id text,
    p_failure_code text
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    if p_status not in ('completed', 'failed') then
        raise exception 'Final status must be completed or failed';
    end if;

    update public.usage_events
       set status = p_status,
           provider = p_provider,
           conversation_id = p_conversation_id,
           failure_code = p_failure_code,
           finalized_at = clock_timestamp()
     where id = p_usage_event_id and status = 'reserved';
end;
$$;

revoke all on function public.reserve_prompt_usage(uuid, text, integer, uuid) from public, anon, authenticated;
revoke all on function public.finalize_prompt_usage(uuid, text, text, text, text) from public, anon, authenticated;
grant execute on function public.reserve_prompt_usage(uuid, text, integer, uuid) to service_role;
grant execute on function public.finalize_prompt_usage(uuid, text, text, text, text) to service_role;
