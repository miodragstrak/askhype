import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile

from app.api.dependencies import get_authenticated_identity, get_research_provider, get_research_repository
from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.exceptions import AIProviderConfigurationError, AIProviderRateLimitError, AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError
from app.providers.research import ResearchProvider
from app.repositories.research_repository import ResearchLimitReached, ResearchRepository
from app.schemas.research import ResearchJobResponse, ResearchQuotaDetail, ResearchRequest
from app.services.document_extraction import MAX_DOCUMENT_BYTES, DocumentValidationError, extract_document
from app.services.research_service import ResearchDepthNotAllowed, ResearchNotFound, ResearchService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchJobResponse, status_code=202)
async def start_research(request: Request, identity: RequestIdentity = Depends(get_authenticated_identity),
                         repository: ResearchRepository = Depends(get_research_repository),
                         provider: ResearchProvider = Depends(get_research_provider)):
    payload, document = await _parse(request)
    try:
        return await ResearchService(repository, provider).start(payload, identity, document)
    except ResearchLimitReached as exc:
        detail = ResearchQuotaDetail(
            used=exc.used, limit=exc.limit, reset_at=exc.reset_at,
            message=f"Dostigli ste dnevni limit za Deep Research ({exc.limit} zahteva). Možete nastaviti sa običnim AskHype razgovorom ili pokušati ponovo sutra.",
        )
        raise HTTPException(429, detail=detail.model_dump(mode="json")) from exc
    except ResearchDepthNotAllowed as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except AIProviderConfigurationError as exc:
        raise HTTPException(503, detail={"code": "invalid_request", "message": "Deep Research trenutno nije pravilno konfigurisan."}) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(504, detail={"code": "provider_timeout", "message": "Deep Research istraživanje je isteklo. Pokušajte ponovo kasnije."}) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(503, detail={"code": "provider_unavailable", "message": "Deep Research servis je trenutno preopterećen. Pokušajte ponovo kasnije."}) from exc
    except AIProviderRateLimitError as exc:
        raise HTTPException(503, detail={"code": "provider_rate_limited", "message": "Deep Research servis je trenutno dostigao ograničenje provajdera. Pokušajte ponovo kasnije."}) from exc
    except AIProviderResponseError as exc:
        raise HTTPException(502, detail={"code": "invalid_request", "message": "Deep Research zahtev nije moguće obraditi. Preformulišite pitanje."}) from exc


@router.get("/{research_id}", response_model=ResearchJobResponse)
async def get_research(research_id: UUID, identity: RequestIdentity = Depends(get_authenticated_identity),
                       repository: ResearchRepository = Depends(get_research_repository),
                       provider: ResearchProvider = Depends(get_research_provider)):
    try:
        return await ResearchService(repository, provider).get(research_id, identity)
    except ResearchNotFound as exc:
        raise HTTPException(404, detail="Istraživanje nije pronađeno.") from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(504, detail={"code": "provider_timeout", "message": "Deep Research istraživanje je isteklo. Pokušajte ponovo kasnije."}) from exc
    except AIProviderUnavailableError as exc:
        raise HTTPException(503, detail={"code": "provider_unavailable", "message": "Deep Research servis je trenutno preopterećen. Pokušajte ponovo kasnije."}) from exc
    except AIProviderRateLimitError as exc:
        raise HTTPException(503, detail={"code": "provider_rate_limited", "message": "Deep Research servis je trenutno dostigao ograničenje provajdera. Pokušajte ponovo kasnije."}) from exc
    except AIProviderResponseError as exc:
        raise HTTPException(502, detail={"code": "research_failed", "message": "Deep Research nije uspeo. Pokušajte ponovo kasnije."}) from exc
    except AIProviderConfigurationError as exc:
        raise HTTPException(503, detail={"code": "invalid_request", "message": "Deep Research trenutno nije pravilno konfigurisan."}) from exc


async def _parse(request: Request):
    if not request.headers.get("content-type", "").casefold().startswith("multipart/form-data"):
        try:
            return ResearchRequest.model_validate(await request.json()), None
        except Exception as exc:
            raise HTTPException(422, detail="Neispravan zahtev za istraživanje.") from exc
    try:
        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_DOCUMENT_BYTES + 1)
        payload = ResearchRequest.model_validate(json.loads(str(form.get("request", "{}"))))
    except Exception as exc:
        raise HTTPException(422, detail="Neispravan zahtev za istraživanje.") from exc
    uploads = [item for item in form.getlist("file") if isinstance(item, UploadFile)]
    if len(uploads) > 1: raise HTTPException(400, detail="Možeš poslati najviše jedan dokument.")
    if not uploads: return payload, None
    upload = uploads[0]
    body = await upload.read(MAX_DOCUMENT_BYTES + 1)
    try:
        return payload, extract_document(body, upload.filename, upload.content_type)
    except DocumentValidationError as exc:
        raise HTTPException(exc.status_code, detail=str(exc)) from exc
    finally:
        await upload.close()
