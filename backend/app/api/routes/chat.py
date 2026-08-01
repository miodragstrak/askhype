from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_request_identity, get_usage_service
from app.auth.identity import RequestIdentity
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService, UnsupportedAIProviderError
from app.services.usage_service import (
    PromptLimitReached,
    UsageService,
    UsageServiceUnavailable,
    quota_payload,
    usage_headers,
)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    response: Response,
    identity: RequestIdentity = Depends(get_request_identity),
    usage_service: UsageService = Depends(get_usage_service),
) -> ChatResponse:
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
        chat_response = await ChatService().generate_response(request)
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
