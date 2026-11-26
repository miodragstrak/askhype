import asyncio
import json
import logging
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.api.dependencies import get_authenticated_identity, get_request_identity, get_usage_service
from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.services.chat_turn_supervisor import SupervisorUnavailable
from app.services.chat_turns import (
    ChatTurn, ChatTurnAdmissionUnavailable, ChatTurnRepository, run_chat_turn,
)
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.attachments import MAX_IMAGE_BYTES, MAX_IMAGES, ImageAttachment, ImageAttachmentError, validate_image
from app.services.chat_service import ChatService, UnsupportedAIProviderError
from app.services.usage_service import (
    PromptLimitReached,
    UsageService,
    UsageServiceUnavailable,
    quota_payload,
    UsageSnapshot,
    usage_headers,
)

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    http_request: Request,
    response: Response,
    identity: RequestIdentity = Depends(get_request_identity),
    usage_service: UsageService = Depends(get_usage_service),
) -> ChatResponse:
    request, images = await _parse_chat_request(http_request)
    try:
        reservation = await usage_service.reserve(identity)
    except PromptLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_payload(exc.snapshot),
        ) from exc
    except UsageServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AskHype kvote trenutno nisu dostupne. Pokušajte ponovo.",
        ) from exc

    try:
        service = ChatService()
        chat_response = (
            await service.generate_response(request, images)
            if images else await service.generate_response(request)
        )
        await usage_service.finalize(
            reservation.usage_event_id,
            status="completed",
            provider=chat_response.provider,
            conversation_id=chat_response.conversation_id,
            failure_code=None,
        )
        for key, value in usage_headers(reservation.snapshot).items():
            response.headers[key] = value
        return chat_response
    except AIProviderConfigurationError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider nije konfigurisan. Proverite podešavanja i pokušajte ponovo.",
        ) from exc
    except AIProviderTimeoutError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI provider trenutno ne odgovara dovoljno brzo. Pokušajte ponovo.",
        ) from exc
    except AIProviderResponseError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "invalid_response")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider je vratio neispravan odgovor. Pokušajte ponovo.",
        ) from exc
    except AIProviderUnavailableError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider trenutno nije dostupan. Pokušajte ponovo.",
        ) from exc
    except UnsupportedAIProviderError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unsupported_provider")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsupported AI provider configuration.",
        ) from exc


async def get_chat_turn_repository() -> ChatTurnRepository:
    return ChatTurnRepository()


async def _require_server_turns() -> None:
    if not settings.server_chat_turns_enabled or not settings.quota_enforcement_enabled:
        raise HTTPException(404, "Server conversation turns are disabled.")


def _public_turn(row, response: Response):
    if row is None:
        raise HTTPException(404, "Razgovor ili poruka nisu pronađeni.")
    response.status_code = 202 if row["status"] == "processing" else 200
    response.headers["Cache-Control"] = "private, no-store"
    return ChatTurn.model_validate(row)


@router.post("/chat/turns/{turn_id}", response_model=ChatTurn, dependencies=[Depends(_require_server_turns)])
async def submit_chat_turn(
    turn_id: UUID, conversation_id: UUID, http_request: Request, response: Response,
    create_conversation: bool = False,
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: ChatTurnRepository = Depends(get_chat_turn_repository),
):
    request, images = await _parse_chat_request(http_request)
    supervisor = http_request.app.state.chat_turn_supervisor
    user_id = identity.user_id

    try:
        task, trace = supervisor.start(turn_id, lambda trace: run_chat_turn(
            repository, user_id, turn_id, conversation_id, request, images, create_conversation, trace,
        ))
    except SupervisorUnavailable:
        raise HTTPException(503, "Obrada razgovora je trenutno zauzeta.") from None
    try:
        admission = await asyncio.shield(task)
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():
            trace.event("http_waiter_cancelled")
        raise
    except ChatTurnAdmissionUnavailable:
        raise HTTPException(503, "Čuvanje razgovora trenutno nije dostupno.") from None
    except Exception:
        # The supervisor records the sanitized exception category.
        raise HTTPException(503, "Status poruke trenutno nije dostupan.") from None
    match admission.get("error"):
        case "not_found":
            raise HTTPException(404, "Razgovor ili poruka nisu pronađeni.")
        case "conflict":
            raise HTTPException(409, "Identifikator poruke je već upotrebljen.")
        case "quota":
            snapshot = UsageSnapshot(
                identity=identity.kind, plan=identity.plan, used=admission["used"], limit=admission["limit"],
                remaining=admission["remaining"], reset_at=datetime.fromisoformat(admission["reset_at"]) if admission["reset_at"] else None,
            )
            raise HTTPException(429, quota_payload(snapshot))
    return _public_turn(admission["turn"], response)


@router.get("/chat/turns/{turn_id}", response_model=ChatTurn, dependencies=[Depends(_require_server_turns)])
async def read_chat_turn(
    turn_id: UUID, response: Response,
    identity: RequestIdentity = Depends(get_authenticated_identity),
    repository: ChatTurnRepository = Depends(get_chat_turn_repository),
):
    try:
        row = await repository.read(identity.user_id, turn_id)
    except Exception as exc:
        logger.warning("chat_turn_read_error turn=%s category=%s", turn_id, type(exc).__name__)
        raise HTTPException(503, "Status poruke trenutno nije dostupan.") from None
    return _public_turn(row, response)


async def _finalize_failed(
    usage_service: UsageService,
    usage_event_id,
    failure_code: str,
) -> None:
    await usage_service.finalize(
        usage_event_id,
        status="failed",
        provider=None,
        conversation_id=None,
        failure_code=failure_code,
    )


async def _parse_chat_request(http_request: Request) -> tuple[ChatRequest, list[ImageAttachment]]:
    content_type = http_request.headers.get("content-type", "").casefold()
    try:
        if content_type.startswith("application/json"):
            return ChatRequest.model_validate(await http_request.json()), []
        if not content_type.startswith("multipart/form-data"):
            raise HTTPException(status_code=415, detail="Podržani su JSON i multipart/form-data zahtevi.")
        form = await http_request.form(max_files=MAX_IMAGES + 1, max_fields=10, max_part_size=MAX_IMAGE_BYTES + 1)
        uploads = [item for item in form.getlist("images") if isinstance(item, UploadFile)]
        if len(uploads) > MAX_IMAGES:
            raise HTTPException(status_code=400, detail="Možeš poslati najviše 3 slike u jednoj poruci.")
        raw_request = form.get("request")
        if not isinstance(raw_request, str):
            raise HTTPException(status_code=400, detail="Nedostaje polje request.")
        payload = json.loads(raw_request)
        if uploads and not str(payload.get("message", "")).strip():
            payload["message"] = "Analiziraj priloženu sliku/slike i opiši relevantne informacije."
        parsed_request = ChatRequest.model_validate(payload)
        images = [
            validate_image(await upload.read(MAX_IMAGE_BYTES + 1), upload.content_type, upload.filename)
            for upload in uploads
        ]
        return parsed_request, images
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Neispravno request JSON polje.") from exc
    except ImageAttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
