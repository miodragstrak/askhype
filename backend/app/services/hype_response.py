from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from app.schemas.chat import ChatResponse, Recommendation, SourceReference
from app.services.hype_retrieval import HypeContext


def build_hype_response(
    context: HypeContext,
    *,
    conversation_id: str,
    provider: str,
    summary: str | None = None,
    actions: list[str] | None = None,
    selected_urls: list[str | None] | None = None,
) -> ChatResponse:
    documents = {doc.url: doc for doc in context.documents}
    selected = set(selected_urls) if selected_urls is not None else set(documents)
    cards = [doc for url, doc in documents.items() if url in selected]
    if summary is None:
        if documents:
            summary = "Izdvojio sam sadržaj iz zvaničnih Hype izvora. Datumi su preuzeti iz izvora, a dostupnost proveri na samoj stranici."
            if context.topic == "events" and all(doc.event_date and doc.event_date >= context.today for doc in documents.values()):
                summary = f"Ovo su Hype koncerti sa objavljenim datumima od {context.today.isoformat()}. Proveri detalje i dostupnost u zvaničnom izvoru."
            if len(documents) < 3:
                summary += " Nema dovoljno potvrđenih izvora za tri preporuke; neću dopunjavati listu neproverenim informacijama."
        else:
            summary = "Trenutno nemam dovoljno dostupnog Hype sadržaja da potvrdim odgovor. Ne mogu da potvrdim aktuelne termine, izvođače ili program; pokušaj ponovo ili postavi opšte pitanje."
    categories = {
        "news": "Hype sadržaj", "shows": "Hype TV program", "artists": "Hype izvođači",
        "events": "Hype koncert", "production": "Hype Production",
    }
    return ChatResponse(
        conversation_id=conversation_id,
        provider=provider,
        answer_type="hype_content",
        summary=summary,
        recommendations=[
            Recommendation(
                id=f"hype-{uuid5(NAMESPACE_URL, doc.url)}",
                title=doc.title,
                category=categories[context.topic],
                short_description=doc.excerpt[:550],
                location=doc.location or "Lokacija nije potvrđena",
                date_or_duration=doc.date_label,
                reason=f"Sadržaj preuzet sa zvaničnog izvora {doc.owner}.",
                source_url=doc.url,
            )
            for doc in cards
        ],
        follow_up_actions=actions if actions is not None else [
            "Šta ima novo na Hype TV?",
            "Koje Hype emisije vredi pogledati?",
            "Koji Hype koncerti uskoro dolaze?",
        ],
        sources=[
            SourceReference(title=doc.title, url=doc.url, last_verified=doc.retrieved_at)
            for doc in documents.values()
        ],
        generated_at=datetime.now(UTC),
    )
