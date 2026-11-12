import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.datastructures import UploadFile

from app.api.dependencies import get_request_identity, get_usage_service
from app.auth.identity import RequestIdentity
from app.providers.exceptions import (
    AIPresentationPlanError, AIProviderConfigurationError, AIProviderResponseError,
    AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.services.chat_service import UnsupportedAIProviderError
from app.services.document_extraction import MAX_DOCUMENT_BYTES, DocumentValidationError, extract_document
from app.services.presentation_generation import PresentationGenerationError, PresentationGenerationService
from app.services.usage_service import PromptLimitReached, UsageService, UsageServiceUnavailable, quota_payload, usage_headers

router = APIRouter(prefix="/presentations", tags=["presentations"])
MAX_PROMPT_CHARS = 2_000


@router.post("/generate")
async def generate_presentation(
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    usage_service: UsageService = Depends(get_usage_service),
) -> Response:
    prompt, document = await _parse_request(request)
    try:
        reservation = await usage_service.reserve(identity)
    except PromptLimitReached as exc:
        raise HTTPException(status_code=429, detail=quota_payload(exc.snapshot)) from exc
    except UsageServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="AskHype kvote trenutno nisu dostupne. Pokušajte ponovo.") from exc

    service = PresentationGenerationService()
    try:
        result = await service.generate(prompt, document)
        await usage_service.finalize(
            reservation.usage_event_id, status="completed", provider=service.provider_name,
            conversation_id=None, failure_code=None,
        )
    except (AIPresentationPlanError, PresentationGenerationError) as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "invalid_presentation_plan")
        message = str(exc) if isinstance(exc, PresentationGenerationError) else "AI nije vratio bezbedan plan prezentacije. Preformuliši zahtev."
        raise HTTPException(status_code=400, detail=message) from exc
    except AIProviderConfigurationError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "configuration")
        raise HTTPException(status_code=503, detail="AI provider nije konfigurisan.") from exc
    except AIProviderTimeoutError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "timeout")
        raise HTTPException(status_code=504, detail="Planiranje prezentacije je isteklo. Pokušaj ponovo.") from exc
    except AIProviderResponseError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "invalid_response")
        raise HTTPException(status_code=502, detail="AI provider je vratio neispravan plan prezentacije.") from exc
    except AIProviderUnavailableError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unavailable")
        raise HTTPException(status_code=503, detail="AI provider trenutno nije dostupan.") from exc
    except UnsupportedAIProviderError as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "unsupported_provider")
        raise HTTPException(status_code=500, detail="Unsupported AI provider configuration.") from exc
    except Exception as exc:
        await _finalize_failed(usage_service, reservation.usage_event_id, "presentation_generation_failed")
        raise HTTPException(status_code=500, detail="PowerPoint prezentaciju trenutno nije moguće napraviti.") from exc

    headers = usage_headers(reservation.snapshot)
    headers.update({
        "Content-Disposition": f"attachment; filename=\"presentation.pptx\"; filename*=UTF-8''{quote(result.filename)}",
        "X-AskHype-Output-Filename": quote(result.filename),
        "X-AskHype-Presentation-Slide-Count": str(result.slide_count),
        "X-AskHype-Presentation-Summary": quote(result.summary),
        "X-AskHype-Presentation-Warnings": quote(json.dumps(result.warnings, ensure_ascii=False)),
    })
    return Response(
        content=result.content,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )


async def _parse_request(request: Request):
    if not request.headers.get("content-type", "").casefold().startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Zahtev mora biti multipart/form-data.")
    try:
        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_DOCUMENT_BYTES + 1)
    except Exception as exc:
        raise HTTPException(status_code=413, detail="Dokument je veći od dozvoljenih 15 MB.") from exc
    prompt = form.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="Opiši prezentaciju koju želiš.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(status_code=400, detail=f"Opis može imati najviše {MAX_PROMPT_CHARS} znakova.")
    uploads = [item for item in form.getlist("file") if isinstance(item, UploadFile)]
    if len(uploads) > 1:
        raise HTTPException(status_code=400, detail="Možeš poslati najviše jedan dokument.")
    if not uploads:
        return prompt, None
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
        usage_event_id, status="failed", provider=None, conversation_id=None, failure_code=failure_code,
    )
