alter table public.research_jobs
    add column conversation_id uuid references public.conversations(id) on delete set null,
    add column query text;

create index research_jobs_active_updated_idx on public.research_jobs (updated_at)
    where status in ('queued', 'running');
create index research_jobs_conversation_created_idx
    on public.research_jobs (user_id, conversation_id, created_at desc);

create function public.persist_research_conversation_result()
returns trigger language plpgsql security definer set search_path = pg_catalog
as $$
declare
    chat_id text;
begin
    select coalesce(server_conversation_id, 'research_' || new.id::text)
        into chat_id from public.conversations
        where id = new.conversation_id and user_id = new.user_id for update;
    if not found then return new; end if;
    insert into public.conversation_messages (id, conversation_id, user_id, role, response)
    values (new.id, new.conversation_id, new.user_id, 'assistant', jsonb_build_object(
        'conversation_id', chat_id, 'provider', new.provider,
        'answer_type', 'deep_research', 'summary', new.result->'summary',
        'generated_at', new.result->'generated_at', 'research', new.result,
        'recommendations', '[]'::jsonb, 'follow_up_actions', '[]'::jsonb,
        'sources', coalesce(new.result->'sources', '[]'::jsonb)
    )) on conflict (id) do nothing;
    update public.conversations set updated_at = greatest(updated_at, now())
        where id = new.conversation_id and user_id = new.user_id;
    return new;
end;
$$;
revoke all on function public.persist_research_conversation_result() from public, anon, authenticated;

create trigger research_conversation_result
after update of status on public.research_jobs
for each row when (old.status <> 'completed' and new.status = 'completed' and new.result is not null)
execute function public.persist_research_conversation_result();
