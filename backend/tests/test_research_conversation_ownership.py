import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.repositories.research_repository import InMemoryResearchRepository, SupabaseResearchRepository
from app.schemas.research import ResearchRequest
from app.services.research_service import ResearchNotFound, ResearchService


def test_supabase_link_requires_conversation_owner():
    client = MagicMock()
    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    owner, conversation = uuid4(), uuid4()

    assert not asyncio.run(SupabaseResearchRepository(client).link(uuid4(), owner, conversation, "Synthetic"))
    query.eq.assert_any_call("id", str(conversation))
    query.eq.assert_any_call("user_id", str(owner))
    query.update.assert_not_called()


def test_rejected_link_never_submits_provider_job():
    class ForeignConversationRepository(InMemoryResearchRepository):
        async def link(self, *args):
            return False

    repository = ForeignConversationRepository()
    provider = MagicMock()
    with pytest.raises(ResearchNotFound):
        asyncio.run(ResearchService(repository, provider).start(
            ResearchRequest(query="Synthetic", conversation_id=uuid4()),
            SimpleNamespace(user_id=uuid4()),
        ))
    provider.start_research.assert_not_called()
    row, = repository.jobs.values()
    assert row["status"] == "failed"
    assert row["failure_category"] == "invalid_request"
