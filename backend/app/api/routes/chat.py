from fastapi import APIRouter, HTTPException, status

from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService, UnsupportedAIProviderError

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        return await ChatService().generate_response(request)
    except AIProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider nije konfigurisan. Proverite podešavanja i pokušajte ponovo.",
        ) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI provider trenutno ne odgovara dovoljno brzo. Pokušajte ponovo.",
        ) from exc
    except AIProviderResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider je vratio neispravan odgovor. Pokušajte ponovo.",
        ) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider trenutno nije dostupan. Pokušajte ponovo.",
        ) from exc
    except UnsupportedAIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsupported AI provider configuration.",
        ) from exc
