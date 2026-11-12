from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.datastructures import UploadFile

from app.api.dependencies import get_request_identity, get_usage_service
from app.auth.identity import RequestIdentity
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.schemas.documents import DocumentAnalysisResponse
from app.services.chat_service import UnsupportedAIProviderError
from app.services.document_analysis import DocumentAnalysisService
from app.services.document_extraction import MAX_DOCUMENT_BYTES, DocumentValidationError, extract_document
from app.services.usage_service import (
    PromptLimitReached,
    UsageService,
    UsageServiceUnavailable,
    quota_payload,
    usage_headers,
)

router = APIRouter(prefix="/documents", tags=["documents"])
MAX_PROMPT_CHARS = 2_000


@router.post("/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document(
    http_request: Request,
    response: Response,
    identity: RequestIdentity = Depends(get_request_identity),
    usage_service: UsageService = Depends(get_usage_service),
) -> DocumentAnalysisResponse:
    prompt, document = await _parse_document_request(http_request)
    try:
        reservation = await usage_service.reserve(identity)
    except PromptLimitReached as exc:
        raise HTTPException(status_code=429, detail=quota_payload(exc.snapshot)) from exc
    except UsageServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="AskHype kvote trenutno nisu dostupne. Pokušajte ponovo.") from exc

    try:
        service = DocumentAnalysisService()
        result = await service.analyze(prompt, document)
        await usage_service.finalize(
            reservation.usage_event_id,
            status="completed",
            provider=service.provider_name,
            conversation_id=None,
            failure_code=None,
        )
        for key, value in usage_headers(reservation.snapshot).items():
            response.headers[key] = value
        return result
    except AIProviderConfigurationError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "configuration")
        raise HTTPException(status_code=503, detail="AI provider nije konfigurisan.") from exc
    except AIProviderTimeoutError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "timeout")
        raise HTTPException(status_code=504, detail="Analiza dokumenta je istekla. Pokušajte ponovo.") from exc
    except AIProviderResponseError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "invalid_response")
        raise HTTPException(status_code=502, detail="AI provider je vratio neispravnu analizu.") from exc
    except AIProviderUnavailableError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unavailable")
        raise HTTPException(status_code=503, detail="AI provider trenutno nije dostupan.") from exc
    except UnsupportedAIProviderError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unsupported_provider")
        raise HTTPException(status_code=500, detail="Unsupported AI provider configuration.") from exc


async def _parse_document_request(http_request: Request):
    content_type = http_request.headers.get("content-type", "").casefold()
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Zahtev mora biti multipart/form-data.")
    try:
        form = await http_request.form(max_files=2, max_fields=5, max_part_size=MAX_DOCUMENT_BYTES + 1)
    except Exception as exc:
        raise HTTPException(status_code=413, detail="Dokument je veći od dozvoljenih 15 MB.") from exc
    uploads = [item for item in form.getlist("file") if isinstance(item, UploadFile)]
    if len(uploads) != 1:
        raise HTTPException(status_code=400, detail="Pošalji tačno jedan dokument.")
    prompt = form.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="Postavi pitanje o dokumentu.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(status_code=400, detail=f"Pitanje može imati najviše {MAX_PROMPT_CHARS} znakova.")
    upload = uploads[0]
    body = await upload.read(MAX_DOCUMENT_BYTES + 1)
    try:
        document = extract_document(body, upload.filename, upload.content_type)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        await upload.close()
    return prompt, document


async def _finalize_failed(usage_service: UsageService, usage_event_id, failure_code: str) -> None:
    await usage_service.finalize(
        usage_event_id,
        status="failed",
        provider=None,
        conversation_id=None,
        failure_code=failure_code,
    )

