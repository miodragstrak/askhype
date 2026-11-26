from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.animations import router as animations_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.mock_subscription import router as mock_subscription_router
from app.api.routes.presentations import router as presentations_router
from app.api.routes.research import router as research_router
from app.api.routes.usage import router as usage_router
from app.clients.supabase import validate_supabase_server_config
from app.core.config import settings
from app.services.chat_turn_supervisor import ChatTurnSupervisor
from app.services.research_worker import reconcile_research_jobs

validate_supabase_server_config(settings)

@asynccontextmanager
async def lifespan(_app):
    supervisor = ChatTurnSupervisor(settings.chat_turn_worker_capacity, settings.chat_turn_shutdown_drain_seconds)
    _app.state.chat_turn_supervisor = supervisor
    async with asyncio.TaskGroup() as tasks:
        worker = tasks.create_task(reconcile_research_jobs()) if (
            settings.quota_enforcement_enabled and settings.gemini_research_model
        ) else None
        try:
            yield
        finally:
            if worker:
                worker.cancel()
            await supervisor.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-AskHype-Plan",
        "X-AskHype-Usage-Used",
        "X-AskHype-Usage-Limit",
        "X-AskHype-Usage-Remaining",
        "X-AskHype-Output-Filename",
        "X-AskHype-Transformation-Operation",
        "X-AskHype-Transformation-Summary",
        "X-AskHype-Transformation-Warnings",
        "X-AskHype-Presentation-Slide-Count",
        "X-AskHype-Presentation-Summary",
        "X-AskHype-Presentation-Warnings",
    ],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(animations_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(presentations_router, prefix=settings.api_prefix)
app.include_router(research_router, prefix=settings.api_prefix)
app.include_router(usage_router, prefix=settings.api_prefix)
app.include_router(mock_subscription_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
    }
