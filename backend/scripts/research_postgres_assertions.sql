INSERT INTO auth.users VALUES
    ('00000000-0000-4000-8000-000000000001'), ('00000000-0000-4000-8000-000000000002');
INSERT INTO conversations(id, user_id, title) VALUES
    ('00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000001', 'One'),
    ('00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000002', 'Two');

-- Exercise the original RPC as the production caller. The five fixture jobs
-- exhaust a synthetic limit of five before any polling or reconciliation.
SET ROLE service_role;
DO $$
DECLARE
    owner_id constant uuid := '00000000-0000-4000-8000-000000000001';
    reservation record;
BEGIN
    FOR n IN 21..25 LOOP
        SELECT * INTO reservation FROM reserve_research_job(
            ('00000000-0000-4000-8000-0000000000' || n)::uuid,
            owner_id, 'gemini', 'synthetic', 'standard', 'en', 'synthetic-' || n, 5
        );
        IF reservation.allowed IS DISTINCT FROM true OR reservation.used IS DISTINCT FROM n - 20 THEN
            RAISE EXCEPTION 'Legacy reservation contract failed for fixture %', n;
        END IF;
    END LOOP;
END $$;

UPDATE research_jobs SET conversation_id = '00000000-0000-4000-8000-000000000011'
WHERE id IN ('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000024');
UPDATE research_jobs SET conversation_id = '00000000-0000-4000-8000-000000000012'
WHERE id = '00000000-0000-4000-8000-000000000023';
UPDATE research_jobs SET status = 'completed', result = '{"summary":"Synthetic report","sources":[]}'
WHERE id IN ('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000022',
             '00000000-0000-4000-8000-000000000023');
UPDATE research_jobs SET status = 'completed' WHERE id = '00000000-0000-4000-8000-000000000021';
UPDATE research_jobs SET status = 'failed', failure_category = 'provider_timeout'
WHERE id = '00000000-0000-4000-8000-000000000025';
RESET ROLE;

DO $$
BEGIN
    IF (SELECT count(*) FROM conversation_messages) <> 1 OR NOT EXISTS (
        SELECT 1 FROM conversation_messages
        WHERE id = '00000000-0000-4000-8000-000000000021'
          AND conversation_id = '00000000-0000-4000-8000-000000000011'
          AND user_id = '00000000-0000-4000-8000-000000000001' AND role = 'assistant'
          AND text IS NULL AND response->>'answer_type' = 'deep_research'
          AND response->'research'->>'summary' = 'Synthetic report'
    ) THEN
        RAISE EXCEPTION 'Result persistence, ownership, or deduplication failed';
    END IF;
    IF (SELECT status FROM research_jobs WHERE id = '00000000-0000-4000-8000-000000000022')
        IS DISTINCT FROM 'completed' THEN
        RAISE EXCEPTION 'Unlinked legacy job could not complete';
    END IF;
END $$;

-- Inject a real insert failure and check that the job update rolls back.
ALTER TABLE conversation_messages ADD CHECK (response->>'summary' <> 'Reject fixture');
SET ROLE service_role;
DO $$
DECLARE
    reservation record;
BEGIN
    BEGIN
        UPDATE research_jobs SET status = 'completed', result = '{"summary":"Reject fixture"}'
        WHERE id = '00000000-0000-4000-8000-000000000024';
        RAISE EXCEPTION 'Expected persistence failure';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    IF NOT EXISTS (
        SELECT 1 FROM research_jobs WHERE id = '00000000-0000-4000-8000-000000000024'
          AND status = 'queued' AND result IS NULL
    ) THEN
        RAISE EXCEPTION 'Persistence failure did not roll back completion';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM research_jobs WHERE id = '00000000-0000-4000-8000-000000000025'
          AND status = 'failed' AND failure_category = 'provider_timeout'
    ) THEN
        RAISE EXCEPTION 'Timeout is incompatible with the legacy status constraint';
    END IF;
    IF (SELECT count(*) FROM research_jobs) <> 5 THEN
        RAISE EXCEPTION 'Reconciliation changed the quota reservation count';
    END IF;
    SELECT * INTO reservation FROM reserve_research_job(
        '00000000-0000-4000-8000-000000000026', '00000000-0000-4000-8000-000000000001',
        'gemini', 'synthetic', 'standard', 'en', 'synthetic-26', 5
    );
    IF reservation.allowed IS DISTINCT FROM false OR reservation.used IS DISTINCT FROM 5 THEN
        RAISE EXCEPTION 'Reconciliation altered the legacy quota decision';
    END IF;
END $$;
RESET ROLE;

SET ROLE authenticated;
SET request.jwt.claim.sub = '00000000-0000-4000-8000-000000000002';
DO $$
BEGIN
    IF (SELECT count(*) FROM conversations) <> 1 OR EXISTS (
        SELECT 1 FROM conversations WHERE id = '00000000-0000-4000-8000-000000000011'
    ) OR EXISTS (SELECT 1 FROM conversation_messages) THEN
        RAISE EXCEPTION 'Cross-user RLS read isolation failed';
    END IF;
    DELETE FROM conversations WHERE id = '00000000-0000-4000-8000-000000000011';
    IF FOUND THEN RAISE EXCEPTION 'Cross-user RLS delete isolation failed'; END IF;
END $$;
RESET ROLE;

DELETE FROM conversations WHERE id = '00000000-0000-4000-8000-000000000011';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM research_jobs WHERE id = '00000000-0000-4000-8000-000000000021'
          AND conversation_id IS NULL AND status = 'completed'
    ) OR EXISTS (SELECT 1 FROM conversation_messages) THEN
        RAISE EXCEPTION 'Conversation deletion did not detach the job and cascade its message';
    END IF;
END $$;
