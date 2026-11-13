-- ASK-DR-001: private asynchronous Deep Research jobs and distinct daily quota.
create table if not exists public.research_jobs (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    provider text not null,
    model text not null,
    provider_job_id text not null,
    status text not null default 'queued',
    depth text not null,
    language text not null,
    result jsonb,
    failure_category text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint research_jobs_status_check check (status in ('queued', 'running', 'completed', 'failed')),
    constraint research_jobs_depth_check check (depth in ('quick', 'standard', 'deep'))
);

create index if not exists research_jobs_user_created_idx
    on public.research_jobs (user_id, created_at desc);

alter table public.research_jobs enable row level security;
revoke all on table public.research_jobs from public, anon, authenticated;
grant all on table public.research_jobs to service_role;

create or replace function public.reserve_research_job(
    p_research_id uuid, p_user_id uuid, p_provider text, p_model text,
    p_depth text, p_language text, p_provider_job_id text, p_limit integer
)
returns table (allowed boolean, used integer, "limit" integer, reset_at timestamptz)
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_day_start timestamptz := date_trunc('day', v_now at time zone 'UTC') at time zone 'UTC';
    v_used integer;
begin
    if p_user_id is null or p_limit is null or p_limit <= 0 then
        raise exception 'A user and positive research limit are required';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('research:' || p_user_id::text, 0));
    select count(*)::integer into v_used from public.research_jobs
     where user_id = p_user_id and created_at >= v_day_start;
    if v_used >= p_limit then
        return query select false, v_used, p_limit, v_day_start + interval '1 day';
        return;
    end if;
    insert into public.research_jobs
        (id, user_id, provider, model, provider_job_id, depth, language, status, created_at, updated_at)
    values
        (p_research_id, p_user_id, p_provider, p_model, p_provider_job_id, p_depth, p_language,
         'queued', v_now, v_now);
    return query select true, v_used + 1, p_limit, v_day_start + interval '1 day';
end;
$$;

revoke all on function public.reserve_research_job(uuid, uuid, text, text, text, text, text, integer)
    from public, anon, authenticated;
grant execute on function public.reserve_research_job(uuid, uuid, text, text, text, text, text, integer)
    to service_role;
