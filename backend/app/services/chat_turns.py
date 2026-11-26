"""Durable admission and settlement for authenticated ordinary chat."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.clients.supabase import get_supabase_admin_client
from app.providers.exceptions import (
    AIProviderConfigurationError, AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.schemas.attachments import ImageAttachment
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService, UnsupportedAIProviderError

logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    id: UUID
    conversation_id: UUID
    assistant_message_id: UUID
    status: Literal["processing", "completed", "failed", "unknown"]
    created_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None
    response: ChatResponse | None = None


def request_fingerprint(request: ChatRequest, images: list[ImageAttachment]) -> str:
    value = {
        "chat": request.model_dump(mode="json"),
        "images": [(image.content_type, hashlib.sha256(image.data).hexdigest()) for image in images],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ChatTurnRepository:
    async def _rpc(self, name, values):
        params = {key: str(value) if isinstance(value, UUID) else value for key, value in values.items()}
        def execute():
            return get_supabase_admin_client().rpc(name, params).execute().data

        return await asyncio.to_thread(execute)

    async def accept(self, user, turn, conversation, request, images, create):
        return await self._rpc("accept_chat_turn", {
            "p_user": user, "p_turn": turn, "p_conversation": conversation,
            "p_fingerprint": request_fingerprint(request, images), "p_message": request.message,
            "p_title": request.message.strip()[:80] or "Razgovor", "p_create": create,
            "p_attachment_count": len(images),
        })

    async def finish(self, user, turn, status, response=None, failure=None):
        return await self._rpc("settle_chat_turn", {
            "p_user": user, "p_turn": turn, "p_status": status,
            "p_response": response.model_dump(mode="json") if response else None, "p_failure": failure,
        })

    async def read(self, user, turn):
        return await self._rpc("read_chat_turn", {"p_user": user, "p_turn": turn})


_FAILURES = {
    AIProviderConfigurationError: "configuration",
    AIProviderResponseError: "invalid_response",
    UnsupportedAIProviderError: "unsupported_provider",
}


async def execute_claimed_turn(repository, user, turn, request, images):
    """Run only for the transaction winner. Settlement retry never re-enters generation."""
    response = None
    failure = None
    status = "completed"
    try:
        async with asyncio.timeout(120):
            service = ChatService()
            response = (await service.generate_response(request, images) if images
                        else await service.generate_response(request))
    except asyncio.CancelledError:
        # Admission is already durable. A later status read expires an abandoned claim.
        raise
    except (TimeoutError, AIProviderTimeoutError):
        status, failure = "unknown", "provider_timeout"
    except AIProviderUnavailableError:
        # The existing adapter also uses this for transport errors after dispatch.
        status, failure = "unknown", "provider_unavailable"
    except tuple(_FAILURES) as exc:
        status, failure = "failed", next(code for error, code in _FAILURES.items() if isinstance(exc, error))
    except Exception as exc:
        logger.warning("chat_turn_execution_error turn=%s category=%s", turn, type(exc).__name__)
        status, failure = "unknown", "execution_error"

    for _ in range(2):
        try:
            return await repository.finish(user, turn, status, response, failure)
        except Exception as exc:
            logger.warning("chat_turn_settlement_error turn=%s category=%s", turn, type(exc).__name__)
    raise ChatTurnSettlementUnavailable()


class ChatTurnSettlementUnavailable(RuntimeError):
    pass
