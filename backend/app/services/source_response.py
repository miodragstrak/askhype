from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.chat import ChatRequest, ChatResponse, SourceReference
from app.services.public_sources import PublicSourceContext


def source_failure_message(context: PublicSourceContext, language: str) -> str:
    english = language.casefold().startswith("en")
    reasons = {item.reason for item in context.failures}
    details: list[str] = []
    descriptions = {
        "blocked_target": ("The link does not point to an allowed public network target.", "Link ne vodi ka dozvoljenoj javnoj mrežnoj adresi."),
        "invalid_url": ("The URL is invalid or unsupported.", "URL nije ispravan ili nije podržan."),
        "unsupported_type": ("Only HTML, plain text and PDF are supported.", "Podržani su samo HTML, običan tekst i PDF."),
        "unsupported_encoding": ("The server returned an unsupported content encoding.", "Server je vratio nepodržano kodiranje sadržaja."),
        "too_large": ("The resource exceeds the 10 MiB size limit.", "Dokument prelazi ograničenje veličine od 10 MiB."),
        "timeout": ("Reading the resource timed out.", "Isteklo je vreme za čitanje dokumenta."),
        "redirect_limit": ("The link has too many redirects or an invalid redirect.", "Link ima previše preusmeravanja ili neispravno preusmeravanje."),
        "no_pdf_text": ("This PDF has no usable text layer (it may be scanned/image-only); OCR is not supported.", "Ovaj PDF nema upotrebljiv tekstualni sloj (moguće je da je skeniran ili sadrži samo slike); OCR nije podržan."),
        "encrypted_pdf": ("Password-protected PDFs are not supported.", "PDF dokumenti zaštićeni lozinkom nisu podržani."),
        "no_text": ("The resource contains no readable text.", "Dokument ne sadrži čitljiv tekst."),
        "unreadable_content": ("The document could not be parsed within the extraction limits.", "Dokument nije moguće obraditi u okviru ograničenja za izdvajanje teksta."),
        "url_limit": ("Only the first three distinct links are read per message.", "Po poruci se čitaju samo prva tri različita linka."),
    }
    for reason in sorted(reasons):
        if reason in descriptions:
            details.append(descriptions[reason][0 if english else 1])
    if english:
        return " ".join(["I can't currently read the content of that link.", *details, "You can send the PDF or paste the text here."])
    return " ".join(["Ne mogu trenutno da pročitam sadržaj tog linka.", *details, "Možeš da pošalješ PDF ili nalepiš tekst ovde."])


def build_source_response(
    context: PublicSourceContext,
    request: ChatRequest,
    provider: str,
    *,
    summary: str = "",
    answer_type: str = "source_analysis",
    actions: list[str] | None = None,
) -> ChatResponse:
    if not context.documents:
        summary = source_failure_message(context, request.language)
        answer_type = "source_unavailable"
    elif context.failures:
        prefix = "Some supplied links could not be read. " if request.language.startswith("en") else "Neki poslati linkovi nisu mogli da se pročitaju. "
        summary += "\n\n" + prefix + source_failure_message(context, request.language)
    return ChatResponse(
        conversation_id=request.conversation_id or f"conv_{uuid4()}",
        provider=provider,
        answer_type=answer_type,
        summary=summary,
        recommendations=[],
        follow_up_actions=actions or [],
        sources=[SourceReference(title=doc.title, url=doc.url, last_verified=doc.retrieved_at) for doc in context.documents],
        generated_at=datetime.now(UTC),
    )
