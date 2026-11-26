-- Additive. Ordinary authenticated chat only. Legacy messages remain readable.
create table public.chat_turns (
    id uuid primary key,
    conversation_id uuid not null,
    user_id uuid not null,
    request_fingerprint text not null check (length(request_fingerprint) = 64),
    assistant_message_id uuid not null unique default gen_random_uuid(),
    usage_event_id uuid not null unique,
    status text not null check (status in ('processing', 'completed', 'failed', 'unknown')),
    created_at timestamptz not null default clock_timestamp(),
    completed_at timestamptz,
    failure_code text,
    constraint chat_turn_owner_fk foreign key (conversation_id, user_id)
        references public.conversations(id, user_id) on delete cascade
);

alter table public.chat_turns enable row level security;
revoke all on public.chat_turns from public, anon, authenticated;
create index chat_turns_conversation_owner_idx on public.chat_turns (conversation_id, user_id);
create index conversations_owner_cursor_idx on public.conversations (user_id, updated_at desc, id desc);
create index conversation_messages_cursor_idx on public.conversation_messages (conversation_id, created_at desc, id desc);

-- Persist a tombstone while the owner exists so a previously accepted ID cannot
-- be claimed again after deleting its conversation (including by a legacy client).
create table public.deleted_chat_turns (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade
);
alter table public.deleted_chat_turns enable row level security;
revoke all on public.deleted_chat_turns from public, anon, authenticated;

-- Keep legacy rows writable by their owners. Ordinary turn rows are server-owned.
create policy ordinary_turn_message_server_insert on public.conversation_messages as restrictive
    for insert to authenticated with check (not (metadata ?| array['ordinary_turn', 'ordinary_turn_id']));
create policy ordinary_turn_message_server_update on public.conversation_messages as restrictive
    for update to authenticated using (not (metadata ?| array['ordinary_turn', 'ordinary_turn_id']))
    with check (not (metadata ?| array['ordinary_turn', 'ordinary_turn_id']));
create policy ordinary_turn_message_server_delete on public.conversation_messages as restrictive
    for delete to authenticated using (not (metadata ?| array['ordinary_turn', 'ordinary_turn_id']));

-- Only service-role RPCs expose the state. The response lives in the existing message row.
create function public.chat_turn_view(p_turn public.chat_turns)
returns jsonb language sql stable security definer set search_path = pg_catalog
as $$
    select jsonb_build_object('id', p_turn.id, 'conversation_id', p_turn.conversation_id,
        'assistant_message_id', p_turn.assistant_message_id, 'status', p_turn.status,
        'created_at', p_turn.created_at, 'completed_at', p_turn.completed_at,
        'failure_code', p_turn.failure_code, 'response',
        (select m.response from public.conversation_messages m
            where m.id = p_turn.assistant_message_id and m.user_id = p_turn.user_id
               and m.conversation_id = p_turn.conversation_id));
$$;

create function public.accept_chat_turn(
    p_user uuid, p_turn uuid, p_conversation uuid, p_fingerprint text,
    p_message text, p_title text, p_create boolean, p_attachment_count integer
)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $$
declare
    v_turn public.chat_turns;
    v_quota record;
    v_usage uuid := gen_random_uuid();
begin
    -- Serialize claims for this logical ID, including attempts by another account.
    perform pg_advisory_xact_lock(hashtextextended('chat_turn:' || p_turn::text, 0));
    select * into v_turn from public.chat_turns where id = p_turn;
    if found then
        if v_turn.user_id <> p_user then return jsonb_build_object('error', 'not_found'); end if;
        if v_turn.conversation_id <> p_conversation or v_turn.request_fingerprint <> p_fingerprint then
            return jsonb_build_object('error', 'conflict');
        end if;
        return jsonb_build_object('claimed', false, 'turn', public.chat_turn_view(v_turn));
    end if;

    if exists (select 1 from public.deleted_chat_turns where id = p_turn) then
        return jsonb_build_object('error', 'not_found');
    end if;

    -- Lock an existing thread. A quota denial leaves a new thread and its messages absent.
    perform 1 from public.conversations where id = p_conversation and user_id = p_user for update;
    if not found and (not p_create or exists (select 1 from public.conversations where id = p_conversation)) then
        return jsonb_build_object('error', 'not_found');
    end if;
    -- Existing clients and research share this message ID namespace.
    if exists (select 1 from public.conversation_messages where id = p_turn) then
        return jsonb_build_object('error', 'conflict');
    end if;
    select * into strict v_quota from public.reserve_prompt_usage(p_user, null, null, v_usage);
    if not v_quota.allowed then
        return jsonb_build_object('error', 'quota', 'used', v_quota.used, 'limit', v_quota."limit",
            'remaining', v_quota.remaining, 'reset_at', v_quota.reset_at);
    end if;

    if p_create then
        insert into public.conversations (id, user_id, title)
        values (p_conversation, p_user, p_title)
        on conflict (id) do nothing;
    end if;
    -- Recheck ownership in the transaction after a possible concurrent create.
    perform 1 from public.conversations where id = p_conversation and user_id = p_user for update;
    if not found then
        raise exception 'Conversation owner changed during acceptance' using errcode = '23503';
    end if;
    insert into public.chat_turns (id, conversation_id, user_id, request_fingerprint, usage_event_id, status)
    values (p_turn, p_conversation, p_user, p_fingerprint, v_usage, 'processing')
    returning * into v_turn;
    insert into public.conversation_messages (id, conversation_id, user_id, role, text, metadata, created_at)
    values (p_turn, p_conversation, p_user, 'user', p_message,
        jsonb_build_object('ordinary_turn', true, 'attachment_count', p_attachment_count), v_turn.created_at);
    update public.conversations set updated_at = greatest(updated_at, v_turn.created_at)
        where id = p_conversation;
    return jsonb_build_object('claimed', true, 'turn', public.chat_turn_view(v_turn));
end;
$$;

create function public.settle_chat_turn(
    p_user uuid, p_turn uuid, p_status text, p_response jsonb, p_failure text
)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $$
declare
    v_turn public.chat_turns;
    v_conversation uuid;
    v_now timestamptz := clock_timestamp();
begin
    if p_status not in ('completed', 'failed', 'unknown')
       or (p_status = 'completed' and (p_response is null or jsonb_typeof(p_response) <> 'object')) then
        raise exception 'Invalid chat turn settlement';
    end if;
    select conversation_id into v_conversation from public.chat_turns where id = p_turn and user_id = p_user;
    if not found then return null; end if;
    -- Same lock order as deletion, whose cascading FK removes turns.
    perform 1 from public.conversations where id = v_conversation and user_id = p_user for update;
    if not found then return null; end if;
    select * into v_turn from public.chat_turns where id = p_turn and user_id = p_user for update;
    if not found then return null; end if;
    if v_turn.status <> 'processing' then return public.chat_turn_view(v_turn); end if;

    if p_status = 'completed' then
        perform 1 from public.usage_events where id = v_turn.usage_event_id and user_id = p_user
            and status = 'reserved' for update;
        if not found then raise exception 'Missing active chat quota reservation'; end if;
        insert into public.conversation_messages (id, conversation_id, user_id, role, response, metadata, created_at)
        values (v_turn.assistant_message_id, v_turn.conversation_id, p_user, 'assistant', p_response, jsonb_build_object('ordinary_turn_id', p_turn), v_now);
        update public.conversations set updated_at = greatest(updated_at, v_now),
            server_conversation_id = p_response->>'conversation_id' where id = v_conversation;
    end if;
    perform public.finalize_prompt_usage(v_turn.usage_event_id,
        case when p_status = 'completed' then 'completed' else 'failed' end,
        p_response->>'provider', v_conversation::text, p_failure);
    if p_status = 'completed' and not exists (
        select 1 from public.usage_events where id = v_turn.usage_event_id and status = 'completed'
    ) then raise exception 'Chat quota settlement failed'; end if;
    update public.chat_turns set status = p_status, completed_at = v_now, failure_code = p_failure
        where id = p_turn returning * into v_turn;
    return public.chat_turn_view(v_turn);
end;
$$;

create function public.read_chat_turn(p_user uuid, p_turn uuid)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $$
declare v_turn public.chat_turns;
begin
    select * into v_turn from public.chat_turns where id = p_turn and user_id = p_user;
    if not found then return null; end if;
    if v_turn.status = 'processing' and v_turn.created_at < clock_timestamp() - interval '3 minutes' then
        return public.settle_chat_turn(p_user, p_turn, 'unknown', null, 'execution_interrupted');
    end if;
    return public.chat_turn_view(v_turn);
end;
$$;

create function public.retire_chat_turn()
returns trigger language plpgsql security definer set search_path = pg_catalog
as $$
begin
    insert into public.deleted_chat_turns (id, user_id)
        select old.id, old.user_id where exists (select 1 from auth.users where id = old.user_id)
        on conflict (id) do nothing;
    perform public.finalize_prompt_usage(old.usage_event_id, 'failed', null,
        old.conversation_id::text, 'conversation_deleted');
    return old;
end;
$$;
create trigger retire_chat_turn before delete on public.chat_turns
for each row execute function public.retire_chat_turn();

revoke all on function public.chat_turn_view(public.chat_turns) from public, anon, authenticated;
revoke all on function public.retire_chat_turn() from public, anon, authenticated;
revoke all on function public.accept_chat_turn(uuid, uuid, uuid, text, text, text, boolean, integer) from public, anon, authenticated;
revoke all on function public.settle_chat_turn(uuid, uuid, text, jsonb, text) from public, anon, authenticated;
revoke all on function public.read_chat_turn(uuid, uuid) from public, anon, authenticated;
grant execute on function public.accept_chat_turn(uuid, uuid, uuid, text, text, text, boolean, integer) to service_role;
grant execute on function public.settle_chat_turn(uuid, uuid, text, jsonb, text) to service_role;
grant execute on function public.read_chat_turn(uuid, uuid) to service_role;
