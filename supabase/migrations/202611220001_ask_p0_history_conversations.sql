-- ASK-P0-HISTORY-01: private, durable conversation history for authenticated users.
create table if not exists public.conversations (
    id uuid primary key,
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null,
    server_conversation_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint conversations_title_length_check check (char_length(title) between 1 and 200),
    constraint conversations_id_user_unique unique (id, user_id)
);

create table if not exists public.conversation_messages (
    id uuid primary key,
    conversation_id uuid not null,
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    role text not null,
    text text,
    response jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint conversation_messages_conversation_owner_fk
        foreign key (conversation_id, user_id)
        references public.conversations(id, user_id) on delete cascade,
    constraint conversation_messages_role_check check (role in ('user', 'assistant')),
    constraint conversation_messages_payload_check check (
        (role = 'user' and text is not null and response is null)
        or (role = 'assistant' and text is null and response is not null)
    )
);

create index if not exists conversations_user_updated_idx
    on public.conversations (user_id, updated_at desc);
create index if not exists conversation_messages_conversation_created_idx
    on public.conversation_messages (conversation_id, created_at asc);

alter table public.conversations enable row level security;
alter table public.conversation_messages enable row level security;

revoke all on table public.conversations from public, anon;
revoke all on table public.conversation_messages from public, anon;
grant select, insert, update, delete on table public.conversations to authenticated;
grant select, insert, update, delete on table public.conversation_messages to authenticated;

create policy conversations_owner_select on public.conversations
    for select to authenticated using (user_id = auth.uid());
create policy conversations_owner_insert on public.conversations
    for insert to authenticated with check (user_id = auth.uid());
create policy conversations_owner_update on public.conversations
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy conversations_owner_delete on public.conversations
    for delete to authenticated using (user_id = auth.uid());

create policy conversation_messages_owner_select on public.conversation_messages
    for select to authenticated using (user_id = auth.uid());
create policy conversation_messages_owner_insert on public.conversation_messages
    for insert to authenticated with check (
        user_id = auth.uid()
        and exists (
            select 1 from public.conversations c
            where c.id = conversation_id and c.user_id = auth.uid()
        )
    );
create policy conversation_messages_owner_update on public.conversation_messages
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy conversation_messages_owner_delete on public.conversation_messages
    for delete to authenticated using (user_id = auth.uid());
