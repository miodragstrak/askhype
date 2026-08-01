from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.mock_subscription import router as mock_subscription_router
from app.api.routes.usage import router as usage_router
from app.clients.supabase import validate_supabase_server_config
from app.core.config import settings

validate_supabase_server_config(settings)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-AskHype-Plan",
        "X-AskHype-Usage-Used",
        "X-AskHype-Usage-Limit",
        "X-AskHype-Usage-Remaining",
    ],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(usage_router, prefix=settings.api_prefix)
app.include_router(mock_subscription_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
    }
