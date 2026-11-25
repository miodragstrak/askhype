import asyncio
import logging

from app.providers.research import GeminiResearchProvider
from app.repositories.research_repository import SupabaseResearchRepository
from app.services.research_service import ResearchService

logger = logging.getLogger("uvicorn.error").getChild("research")


async def reconcile_research_jobs():
    while True:
        try:
            repository = SupabaseResearchRepository()
            rows = await repository.active()
            if rows:
                service = ResearchService(repository, GeminiResearchProvider())
                for row in rows:
                    try:
                        await service.reconcile(row)
                    except Exception as exc:
                        logger.warning("research_reconciliation_failed %s", {
                            "research_id": row["id"], "category": type(exc).__name__,
                        })
        except Exception as exc:
            logger.warning("research_reconciliation_scan_failed %s", type(exc).__name__)
        await asyncio.sleep(15)
