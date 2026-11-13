-- ASK-ANIM-001: a distinct, durable UTC daily quota for successful animation generations.
create table if not exists public.animation_usage_events (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    status text not null default 'reserved',
    failure_category text,
    created_at timestamptz not null default now(),
    finalized_at timestamptz,
    constraint animation_usage_events_status_check
        check (status in ('reserved', 'completed', 'failed'))
);

create index if not exists animation_usage_events_user_created_idx
    on public.animation_usage_events (user_id, created_at desc);

alter table public.animation_usage_events enable row level security;
revoke all on table public.animation_usage_events from public, anon, authenticated;
grant all on table public.animation_usage_events to service_role;

create or replace function public.reserve_animation_usage(
    p_event_id uuid, p_user_id uuid, p_limit integer
)
returns table (allowed boolean, used integer, "limit" integer, reset_at timestamptz)
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_day_start timestamptz := date_trunc('day', v_now at time zone 'UTC') at time zone 'UTC';
    v_used integer;
begin
    if p_event_id is null or p_user_id is null or p_limit is null or p_limit <= 0 then
        raise exception 'An event, user, and positive animation limit are required';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('animation:' || p_user_id::text, 0));

    -- Interrupted reservations stop blocking quota after the provider timeout window.
    update public.animation_usage_events
       set status = 'failed', failure_category = 'interrupted', finalized_at = v_now
     where user_id = p_user_id and status = 'reserved'
       and created_at < v_now - interval '10 minutes';

    select count(*)::integer into v_used
      from public.animation_usage_events
     where user_id = p_user_id and created_at >= v_day_start
       and status in ('reserved', 'completed');

    if v_used >= p_limit then
        return query select false, v_used, p_limit, v_day_start + interval '1 day';
        return;
    end if;

    insert into public.animation_usage_events (id, user_id, status, created_at)
    values (p_event_id, p_user_id, 'reserved', v_now);
    return query select true, v_used + 1, p_limit, v_day_start + interval '1 day';
end;
$$;

create or replace function public.finalize_animation_usage(
    p_event_id uuid, p_status text, p_failure_category text default null
)
returns void language plpgsql security definer set search_path = pg_catalog, public
as $$
begin
    if p_status not in ('completed', 'failed') then
        raise exception 'Invalid animation usage status';
    end if;
    update public.animation_usage_events
       set status = p_status, failure_category = p_failure_category, finalized_at = clock_timestamp()
     where id = p_event_id and status = 'reserved';
end;
$$;

revoke all on function public.reserve_animation_usage(uuid, uuid, integer)
    from public, anon, authenticated;
grant execute on function public.reserve_animation_usage(uuid, uuid, integer) to service_role;
revoke all on function public.finalize_animation_usage(uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.finalize_animation_usage(uuid, text, text) to service_role;
