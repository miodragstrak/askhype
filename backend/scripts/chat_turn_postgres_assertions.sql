\if :upgrade
do $$ begin
    assert exists (select 1 from public.conversation_messages where text = 'Existing message');
end $$;
\endif

insert into auth.users (id) values ('10000000-0000-4000-8000-000000000001'),
    ('10000000-0000-4000-8000-000000000002') on conflict do nothing;

create function fail_test_settlement() returns trigger language plpgsql as $$
begin
    if new.status = 'completed' then raise exception 'Synthetic quota failure' using errcode = '23514'; end if;
    return new;
end;
$$;

do $$
declare
    a uuid := '10000000-0000-4000-8000-000000000001';
    b uuid := '10000000-0000-4000-8000-000000000002';
    thread uuid := '20000000-0000-4000-8000-000000000003';
    turn uuid := '30000000-0000-4000-8000-000000000003';
    other uuid := '30000000-0000-4000-8000-000000000004';
    result jsonb := '{"provider":"mock","conversation_id":"mock-thread","summary":"An answer","sources":[{"title":"Example","url":"https://example.test/"}]}';
    row jsonb;
    assistant uuid;
begin
    row := public.accept_chat_turn(a, turn, thread, repeat('a',64),'Input','Title',true,0);
    assert row->>'claimed' = 'true';
    assistant := (row->'turn'->>'assistant_message_id')::uuid;
    assert (select count(*) from public.usage_events where user_id = a) = 1;
    assert public.accept_chat_turn(a, turn, thread, repeat('a',64),'Input','Title',true,0)->>'claimed' = 'false';
    assert public.accept_chat_turn(a, turn, thread, repeat('b',64),'Other','Title',true,0)->>'error' = 'conflict';
    assert public.accept_chat_turn(b, other, thread, repeat('a',64),'Input','Title',true,0)->>'error' = 'not_found';
    assert public.accept_chat_turn(b, turn, thread, repeat('a',64),'Input','Title',true,0)->>'error' = 'not_found';
    assert public.read_chat_turn(b, turn) is null;
    assert not exists (select 1 from public.usage_events where user_id = b);

    -- Colliding assistant insert rolls back the terminal transition and usage update.
    insert into public.conversation_messages(id, conversation_id, user_id, role, text)
    values(assistant, thread, a, 'user', 'Synthetic collision');
    begin
        perform public.settle_chat_turn(a, turn, 'completed', result, null);
        raise exception 'Expected uniqueness failure';
    exception when unique_violation then null;
    end;
    assert public.read_chat_turn(a, turn)->>'status' = 'processing';
    assert (select status from public.usage_events where user_id = a) = 'reserved';
    delete from public.conversation_messages where id = assistant;

    -- Inject a quota update failure after the assistant insert.
    create trigger fail_test_settlement before update on public.usage_events
    for each row execute function fail_test_settlement();
    begin
        perform public.settle_chat_turn(a, turn, 'completed', result, null);
        raise exception 'Expected settlement failure';
    exception when check_violation then null;
    end;
    assert not exists(select 1 from public.conversation_messages where id = assistant);
    assert public.read_chat_turn(a, turn)->>'status' = 'processing';
    drop trigger fail_test_settlement on public.usage_events;

    row := public.settle_chat_turn(a, turn, 'completed', result, null);
    assert row->'response' = result;
    assert public.read_chat_turn(a, turn) = row;
    assert public.settle_chat_turn(a, turn, 'completed', result, null) = row;
    assert public.accept_chat_turn(a, turn, thread, repeat('a',64),'Input','Title',true,0)->'turn' = row;
    assert (select count(*) from public.conversation_messages where conversation_id = thread) = 2;
    assert (select count(*) from public.usage_events where user_id = a and status = 'completed') = 1;

    perform public.accept_chat_turn(a, other, thread, repeat('a',64),'Interrupted','Title',false,1);
    update public.chat_turns set created_at = clock_timestamp() - interval '4 minutes' where id = other;
    assert public.read_chat_turn(a, other)->>'status' = 'unknown';
    assert public.settle_chat_turn(a, other, 'completed', result, null)->>'status' = 'unknown';
    assert exists(select 1 from public.usage_events where status = 'failed' and failure_code = 'execution_interrupted');

    -- Quota denial for a distinct owner must not create a conversation or a turn.
    insert into public.usage_events (user_id, status) select b, 'completed' from generate_series(1,10);
    assert public.accept_chat_turn(b, '30000000-0000-4000-8000-000000000005',
        '20000000-0000-4000-8000-000000000006', repeat('a',64),'Rejected','Title',true,0)->>'error' = 'quota';
    assert not exists(select 1 from public.conversations where user_id = b);
    assert (select count(*) from public.usage_events where user_id = b) = 10;

    -- A Deep Research completion still writes the existing response shape.
    insert into public.conversations (id,user_id,title)
        values ('20000000-0000-4000-8000-000000000007',a,'Linked research fixture');
    perform public.reserve_research_job('30000000-0000-4000-8000-000000000007',a,
        'gemini','synthetic','standard','en','synthetic-job',3);
    update public.research_jobs set conversation_id='20000000-0000-4000-8000-000000000007',
        status='completed', result='{"summary":"Synthetic research","sources":[]}'
        where id='30000000-0000-4000-8000-000000000007';
    assert exists(select 1 from public.conversation_messages where id='30000000-0000-4000-8000-000000000007'
        and response->>'answer_type' = 'deep_research');

    -- Stable compound cursor for tied timestamps and old persisted rows.
    insert into public.conversations (id,user_id,title,updated_at)
    values ('20000000-0000-4000-8000-000000000005',a,'Page 1','2000-01-01Z'),
           ('20000000-0000-4000-8000-000000000004',a,'Page 2','2000-01-01Z');
    assert (select title from public.conversations where user_id=a and
        (updated_at,id) < ('2000-01-01Z'::timestamptz,'20000000-0000-4000-8000-000000000005'::uuid)
        order by updated_at desc,id desc limit 1) = 'Page 2';
end $$;

set role authenticated;
set request.jwt.claim.sub = '10000000-0000-4000-8000-000000000002';
do $$ begin
    assert not exists(select 1 from public.conversation_messages);
    assert not has_function_privilege('public.read_chat_turn(uuid,uuid)', 'execute');
end $$;
set request.jwt.claim.sub = '10000000-0000-4000-8000-000000000001';
do $$ begin
    assert exists(select 1 from public.conversation_messages where metadata->>'ordinary_turn'='true');
    update public.conversation_messages set text='Changed' where metadata->>'ordinary_turn'='true';
    assert not found;
    delete from public.conversations where id='20000000-0000-4000-8000-000000000003';
    assert found;
end $$;
reset role;
do $$ begin
    assert not exists(select 1 from public.chat_turns where conversation_id='20000000-0000-4000-8000-000000000003');
    assert public.accept_chat_turn('10000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000003',
        '20000000-0000-4000-8000-000000000003',repeat('a',64),'Input','Title',true,0)->>'error' = 'not_found';
end $$;
