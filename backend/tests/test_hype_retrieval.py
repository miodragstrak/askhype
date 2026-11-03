import asyncio
import json
from datetime import UTC, date, datetime

import httpx
import pytest

from app.main import app
from app.providers.mock import MockAIProvider
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.hype_retrieval import (
    CONCERT_INDEX_FALLBACK_EXCERPT, MAX_PAGE_BYTES, PRODUCTION_ROOT, TV_ROOT,
    HypeContext, HypeDocument,
    HypeRetriever, _location_keys, hype_retriever, hype_topic, is_hype_url,
    parse_concert_index, parse_feed, parse_page,
)

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


@pytest.mark.parametrize(("message", "topic"), [
    ("\u0160ta ima novo na Hype TV?", "news"),
    ("Koje HYPE emisije vredi pogledati?", "shows"),
    ("Hype TV program danas", "shows"),
    ("Da li ima nekih Hype koncerata uskoro u Beogradu?", "events"),
    ("Koji Hype koncerti uskoro dolaze?", "events"),
    ("Ima li Hype koncerta večeras?", "events"),
    ("Hype Production events", "events"),
    ("Ko su izvo\u0111a\u010di Hype Production-a?", "artists"),
    ("hypetv.rs novosti", "news"),
    ("hypeproduction.rs artists", "artists"),
    ("Hype Production o nama", "production"),
    ("Gde da izadjem veceras u Beogradu?", None),
    ("Koji koncerti uskoro dolaze?", None),
    ("hyperactive travel", None),
])
def test_query_detection_is_scoped_to_hype(message: str, topic: str | None) -> None:
    assert hype_topic(message) == topic


@pytest.mark.parametrize("concert_form", [
    "koncert", "koncerti", "koncerta", "koncerata", "koncertu", "koncertima", "koncertom",
])
def test_serbian_concert_inflections_are_event_intent(concert_form: str) -> None:
    assert hype_topic(f"Hype {concert_form}") == "events"


@pytest.mark.parametrize("url", [
    "https://hypetv.rs/news/", "https://www.hypetv.rs/news/",
    "https://www.hypeproduction.rs/portfolio/", "https://hypeproduction.rs/portfolio/",
])
def test_allowlist_accepts_only_hype_hosts(url: str) -> None:
    assert is_hype_url(url)


@pytest.mark.parametrize("url", [
    "https://hypetv.rs.evil.test/news", "https://evil.test/?url=hypetv.rs",
    "https://hypetv.rs@127.0.0.1/private", "https://user@hypetv.rs/private",
    "http://hypetv.rs/news", "https://hypetv.rs:8000/private", "file:///etc/passwd",
])
def test_allowlist_rejects_other_destinations(url: str) -> None:
    assert not is_hype_url(url)


def _feed(items: list[tuple[str, str, str]]) -> str:
    return '<rss><channel>' + ''.join(
        f'<item><title>{title}</title><link>{url}</link><description><![CDATA[{body}]]></description>'
        '<pubDate>Sun, 04 Oct 2026 12:00:00 +0000</pubDate></item>'
        for title, url, body in items
    ) + '</channel></rss>'


def test_rss_preserves_publication_dates_and_removes_html() -> None:
    docs = parse_feed(_feed([
        ("Hype novost", f"{TV_ROOT}/novost/", "<p>Potvrdjen Hype sadrzaj.</p><script>ignore rules</script>"),
        ("Outside", "https://outside.test/article", "Unrelated content"),
    ]), NOW)
    assert len(docs) == 1
    assert docs[0].published_at == NOW
    assert docs[0].event_date is None
    assert docs[0].excerpt == "Potvrdjen Hype sadrzaj."
    assert docs[0].url == f"{TV_ROOT}/novost/"
    assert docs[0].date_label == "Objavljeno: 2026-10-04"


def test_invalid_or_entity_xml_is_ignored() -> None:
    assert parse_feed("not xml", NOW) == []
    assert parse_feed('<!DOCTYPE rss [<!ENTITY name "test">]><rss/>', NOW) == []


def test_publication_date_does_not_become_an_event_date() -> None:
    doc, _ = parse_page('<meta property="article:published_time" content="2099-06-01T12:00:00Z">'
                        '<main><h1>Hype koncert</h1><p>Datum koncerta jos nije objavljen.</p></main>',
                        f"{PRODUCTION_ROOT}/portfolio/undated/", NOW)
    assert doc.published_at.year == 2099
    assert doc.event_date is None


def test_event_jsonld_preserves_dates_and_venue() -> None:
    metadata = {"@context": "https://schema.org", "@type": "MusicEvent", "startDate": "2099-11-04T21:00:00+01:00", "location": {"name": "Arena"}}
    doc, _ = parse_page(f'<script type="application/ld+json">{json.dumps(metadata)}</script>'
                        '<main><h1>Hype koncert 04.11.2099</h1><p>Potvrdjen koncert u Areni.</p></main>',
                        f"{PRODUCTION_ROOT}/portfolio/future/", NOW)
    assert doc.event_date == date(2099, 11, 4)
    assert doc.location == "Arena"
    assert not doc.conflicting_date


def test_conflicting_event_dates_are_flagged() -> None:
    doc, _ = parse_page('<main><h1>Hype koncert 04.11.2099</h1><p>Datum: 5. novembra 2099. Mesto: Arena.</p></main>',
                        f"{PRODUCTION_ROOT}/portfolio/conflict/", NOW)
    assert doc.conflicting_date


def test_event_like_body_listing_with_different_date_is_conflicting() -> None:
    doc, _ = parse_page(
        '<main><h1>VESNA ZMIJANAC - SKOPJE - 28.11.2026.</h1>'
        '<p>VESNA ZMIJANAC – SARAJEVO – 19.12.2026</p></main>',
        f"{PRODUCTION_ROOT}/portfolio/vesna-zmijanac/",
        NOW,
    )

    assert doc.title == "VESNA ZMIJANAC - SKOPJE - 28.11.2026."
    assert doc.event_date == date(2026, 11, 28)
    assert doc.conflicting_date


def test_production_catalog_location_is_copied_from_title() -> None:
    doc, _ = parse_page('<main><h1>IZVODJAC - SARAJEVO - 19.12.2099</h1><p>Potvrdjen koncert na zvanicnoj stranici.</p></main>',
                        f"{PRODUCTION_ROOT}/portfolio/concert/", NOW)
    assert doc.location == "SARAJEVO"
    assert doc.event_date == date(2099, 12, 19)


def test_official_concert_index_parses_explicit_event_fields() -> None:
    url = f"{PRODUCTION_ROOT}/portfolio/miroslav-ilic-beogradska-arena-10-12-2026/"
    documents = parse_concert_index(
        f'<main><a href="{url}">MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026.</a></main>',
        f"{PRODUCTION_ROOT}/koncerti/",
        NOW,
    )

    assert len(documents) == 1
    assert documents[0].title == "MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026."
    assert documents[0].event_date == date(2026, 12, 10)
    assert documents[0].location == "BEOGRADSKA ARENA"
    assert documents[0].url == url


def test_non_official_page_cannot_provide_concert_index_fallback() -> None:
    html = '<main><a href="https://www.hypeproduction.rs/portfolio/event/">DOGAĐAJ - BEOGRAD - 10.12.2026.</a></main>'

    assert parse_concert_index(html, f"{PRODUCTION_ROOT}/random/", NOW) == []
    assert parse_concert_index(html, f"{TV_ROOT}/koncerti/", NOW) == []


@pytest.mark.parametrize(("query_location", "event_location"), [
    ("Beograd", "Beogradska Arena"),
    ("Beogradu", "Beogradska Arena"),
    ("Beograda", "Beograd"),
    ("Beogradska", "Beograd"),
    ("Beogradski", "Beograd"),
    ("Beogradskoj", "Beograd"),
])
def test_serbian_beograd_forms_share_a_location_key(
    query_location: str,
    event_location: str,
) -> None:
    assert _location_keys(query_location) & _location_keys(event_location) == {"beograd"}


def test_cancelled_event_is_not_a_document() -> None:
    metadata = {"@type": "Event", "startDate": "2099-11-04", "eventStatus": "https://schema.org/EventCancelled"}
    doc, _ = parse_page(f'<script type="application/ld+json">{json.dumps(metadata)}</script>'
                        '<main><h1>Hype koncert 04.11.2099</h1><p>Koncert je otkazan.</p></main>',
                        f"{PRODUCTION_ROOT}/portfolio/cancelled/", NOW)
    assert doc is None


def _event_transport(calls: list[str]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url == f"{PRODUCTION_ROOT}/koncerti/":
            return httpx.Response(200, headers={"content-type": "text/html"}, text='<main><h1>Koncerti</h1>'
                '<a href="/portfolio/past-01-01-2001/">Stari koncert 01.01.2001</a>'
                '<a href="/portfolio/future-01-11-2099/">Naredni koncert 01.11.2099</a>'
                '<a href="/portfolio/second-01-12-2099/">Drugi koncert 01.12.2099</a>'
                '<a href="/portfolio/conflict-04-11-2099/">Koncert 04.11.2099</a></main>')
        if request.url.host == "hypetv.rs" and request.url.path == "/":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=_feed([
                ("Hype TV koncert 01.10.2099", f"{TV_ROOT}/future-tv/", "Hype koncert sa potvrdjenim datumom."),
            ]))
        title = {
            "/portfolio/past-01-01-2001/": "Stari koncert 01.01.2001",
            "/portfolio/future-01-11-2099/": "Naredni koncert 01.11.2099",
            "/portfolio/second-01-12-2099/": "Drugi koncert 01.12.2099",
            "/portfolio/conflict-04-11-2099/": "Koncert 04.11.2099",
            "/future-tv/": "Hype TV koncert 01.10.2099",
        }.get(request.url.path)
        if title:
            body = "Datum: 5. novembra 2099." if "conflict" in request.url.path else "Opis potvrdjenog Hype koncerta iz izvora."
            return httpx.Response(200, headers={"content-type": "text/html"}, text=f'<main><h1>{title}</h1><p>{body}</p></main>')
        return httpx.Response(404)
    return httpx.MockTransport(handle)


def test_upcoming_retrieval_prefers_production_and_excludes_past() -> None:
    calls = []
    retriever = HypeRetriever(transport=_event_transport(calls))
    context = asyncio.run(retriever.retrieve("Koji Hype koncerti uskoro dolaze?"))
    assert [doc.owner for doc in context.documents] == ["Hype Production"] * 3
    assert context.documents[0].event_date == date(2099, 11, 1)
    assert all(doc.event_date >= context.today for doc in context.documents)
    assert all("past" not in doc.url for doc in context.documents)
    fallback = next(doc for doc in context.documents if "conflict" in doc.url)
    assert fallback.excerpt == CONCERT_INDEX_FALLBACK_EXCERPT
    assert "5. novembra" not in fallback.excerpt
    assert len(calls) <= 8
    first_calls = list(calls)
    asyncio.run(retriever.retrieve("Koji Hype koncerti uskoro dolaze?"))
    assert calls == first_calls


def _location_event_transport(calls: list[str], *, crowded: bool = False) -> httpx.MockTransport:
    matching_path = "/portfolio/miroslav-ilic-beogradska-arena-10-12-2026/"
    unrelated = [
        (f"/portfolio/izvodjac-{index}-nis-{index:02d}-12-2026/", f"IZVODJAC {index} - NIS - {index:02d}.12.2026")
        for index in range(1, 7 if crowded else 2)
    ]
    events = [
        *unrelated,
        (matching_path, "MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026."),
        ("/portfolio/stari-beograd-01-01-2020/", "STARI KONCERT - BEOGRAD - 01.01.2020"),
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == f"{PRODUCTION_ROOT}/koncerti/":
            links = "".join(f'<a href="{path}">{title}</a>' for path, title in events)
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=f"<main><h1>Koncerti</h1>{links}</main>",
            )
        if request.url.host == "hypetv.rs":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text="<rss><channel/></rss>")
        title = dict(events).get(request.url.path)
        if title:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=f"<main><h1>{title}</h1><p>Potvrđen koncert iz zvaničnog Hype Production izvora.</p></main>",
            )
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def test_matching_beograd_event_ranks_above_unrelated_city_and_past_event() -> None:
    calls: list[str] = []
    context = asyncio.run(
        HypeRetriever(_location_event_transport(calls))._retrieve(
            "Hype koncerti iz Beograda",
            "events",
            date(2026, 11, 3),
        )
    )

    assert context[0].title == "MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026."
    assert context[0].location == "BEOGRADSKA ARENA"
    assert all(doc.event_date and doc.event_date >= date(2026, 11, 3) for doc in context)
    assert all("stari-beograd" not in doc.url for doc in context)


def test_miroslav_beogradska_arena_survives_crowded_candidate_selection() -> None:
    calls: list[str] = []
    context = asyncio.run(
        HypeRetriever(_location_event_transport(calls, crowded=True))._retrieve(
            "Da li ima nekih Hype koncerata uskoro u Beogradu?",
            "events",
            date(2026, 11, 3),
        )
    )
    expected_url = f"{PRODUCTION_ROOT}/portfolio/miroslav-ilic-beogradska-arena-10-12-2026/"

    assert expected_url in calls
    assert any(doc.url == expected_url for doc in context)


@pytest.mark.parametrize("detail_mode", ["unavailable", "too_short"])
def test_official_index_event_survives_without_usable_detail(detail_mode: str) -> None:
    miroslav_url = f"{PRODUCTION_ROOT}/portfolio/miroslav-ilic-beogradska-arena-10-12-2026/"
    skopje_url = f"{PRODUCTION_ROOT}/portfolio/vesna-zmijanac-skopje-28-11-2026/"

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{PRODUCTION_ROOT}/koncerti/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<main><h1>Koncerti</h1>'
                    f'<a href="{miroslav_url}">MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026.</a>'
                    f'<a href="{skopje_url}">VESNA ZMIJANAC - SKOPJE - 28.11.2026.</a>'
                    '<a href="/portfolio/past/">STARI DOGAĐAJ - BEOGRAD - 01.01.2020.</a></main>'
                ),
            )
        if request.url.host == "hypetv.rs":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text="<rss><channel/></rss>")
        if detail_mode == "too_short":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<main><h1>x</h1></main>")
        return httpx.Response(404)

    documents = asyncio.run(
        HypeRetriever(httpx.MockTransport(handle))._retrieve(
            "Da li ima nekih Hype koncerata uskoro u Beogradu?",
            "events",
            date(2026, 11, 3),
        )
    )

    assert [doc.url for doc in documents] == [miroslav_url, skopje_url]
    assert documents[0].title == "MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026."
    assert documents[0].event_date == date(2026, 12, 10)
    assert documents[0].location == "BEOGRADSKA ARENA"
    assert documents[0].excerpt == "Zvanična Hype Production lista koncerata navodi ovaj događaj."
    assert all("past" not in doc.url for doc in documents)


def test_cancelled_detail_removes_official_index_evidence() -> None:
    event_url = f"{PRODUCTION_ROOT}/portfolio/cancelled-index-event/"

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{PRODUCTION_ROOT}/koncerti/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=f'<main><a href="{event_url}">OTKAZANI DOGAĐAJ - BEOGRAD - 10.12.2099.</a></main>',
            )
        if request.url.host == "hypetv.rs":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text="<rss><channel/></rss>")
        if str(request.url) == event_url:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<script type="application/ld+json">'
                    '{"@type":"MusicEvent","startDate":"2099-12-10",'
                    '"eventStatus":"https://schema.org/EventCancelled"}'
                    '</script><main><h1>Otkazani događaj</h1></main>'
                ),
            )
        return httpx.Response(404)

    documents = asyncio.run(
        HypeRetriever(httpx.MockTransport(handle))._retrieve(
            "Hype koncert u Beogradu",
            "events",
            date(2026, 11, 3),
        )
    )

    assert documents == []


def test_conflicting_miroslav_detail_uses_only_official_index_fallback() -> None:
    expected_url = f"{PRODUCTION_ROOT}/portfolio/miroslav-ilic-beogradska-arena-10-12-2026/"

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{PRODUCTION_ROOT}/koncerti/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<main><h1>Koncerti</h1>'
                    f'<a href="{expected_url}">MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026.</a>'
                    '<a href="/portfolio/past/">STARI DOGAĐAJ - BEOGRAD - 01.01.2020.</a></main>'
                ),
            )
        if request.url.host == "hypetv.rs":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text="<rss><channel/></rss>")
        if str(request.url) == expected_url:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<main><h1>MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026.</h1>'
                    '<p>Aca Lukas. Datum: 04.11.2026. Informacije sa neusaglašene stranice.</p></main>'
                ),
            )
        if request.url.path == "/portfolio/past/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<main><h1>STARI DOGAĐAJ - BEOGRAD - 01.01.2020.</h1><p>Arhivski događaj.</p></main>',
            )
        return httpx.Response(404)

    documents = asyncio.run(
        HypeRetriever(httpx.MockTransport(handle))._retrieve(
            "Da li ima nekih Hype koncerata uskoro u Beogradu?",
            "events",
            date(2026, 11, 3),
        )
    )

    assert len(documents) == 1
    fallback = documents[0]
    assert fallback.title == "MIROSLAV ILIĆ – BEOGRADSKA ARENA – 10.12.2026."
    assert fallback.event_date == date(2026, 12, 10)
    assert fallback.location == "BEOGRADSKA ARENA"
    assert fallback.url == expected_url
    assert fallback.excerpt == CONCERT_INDEX_FALLBACK_EXCERPT
    assert "Aca Lukas" not in fallback.excerpt
    assert "04.11.2026" not in fallback.excerpt
    assert fallback.conflicting_date is False


def test_generic_question_does_not_access_network() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Generic questions must not trigger Hype retrieval")
    assert asyncio.run(HypeRetriever(httpx.MockTransport(handle)).retrieve("Restoran za veceru")) is None


def test_network_failure_returns_insufficient_context() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Unavailable", request=request)
    context = asyncio.run(HypeRetriever(httpx.MockTransport(handle)).retrieve("Hype TV novosti"))
    assert context.documents == []
    assert json.loads(context.to_prompt())["insufficient_sources"]


def test_cached_page_keeps_original_verification_time() -> None:
    async def retrieve_twice():
        retriever = HypeRetriever(httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/html"}, text='<main><h1>Hype vest</h1><p>Potvrdjeni sadrzaj za proveru kesa.</p></main>')))
        async with httpx.AsyncClient(transport=retriever.transport) as client:
            first = await retriever._fetch(client, f"{TV_ROOT}/article/")
            second = await retriever._fetch(client, f"{TV_ROOT}/article/")
        assert first[2] == second[2]
    asyncio.run(retrieve_twice())


def test_cancelled_feed_item_is_removed_after_detail_verification() -> None:
    url = f"{TV_ROOT}/cancelled/"
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cancelled/":
            return httpx.Response(200, headers={"content-type": "text/html"}, text='<script type="application/ld+json">'
                '{"@type":"MusicEvent","startDate":"2099-11-04","eventStatus":"https://schema.org/EventCancelled"}'
                '</script><main><h1>Hype koncert 04.11.2099</h1><p>Koncert je otkazan.</p></main>')
        if request.url.host == "hypetv.rs":
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=_feed([("Hype koncert 04.11.2099", url, "Najava buduceg koncerta.")]))
        return httpx.Response(404)
    context = asyncio.run(HypeRetriever(httpx.MockTransport(handle)).retrieve("Hype koncerti uskoro"))
    assert context.documents == []


def test_redirect_outside_allowlist_is_never_followed() -> None:
    calls = []
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://outside.test/private"})
    async def fetch():
        retriever = HypeRetriever(httpx.MockTransport(handle))
        async with httpx.AsyncClient(transport=retriever.transport) as client:
            return await retriever._fetch(client, f"{TV_ROOT}/redirect/")
    assert asyncio.run(fetch()) is None
    assert calls == [f"{TV_ROOT}/redirect/"]


def test_oversized_page_is_not_used() -> None:
    async def fetch():
        retriever = HypeRetriever(httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * (MAX_PAGE_BYTES + 1))))
        async with httpx.AsyncClient(transport=retriever.transport) as client:
            return await retriever._fetch(client, f"{TV_ROOT}/large/")
    assert asyncio.run(fetch()) is None


def test_user_supplied_url_cannot_change_retrieval_destinations() -> None:
    calls = []
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)
    asyncio.run(HypeRetriever(httpx.MockTransport(handle)).retrieve("Hype koncert https://localhost/private"))
    assert len(calls) == 2
    assert all(is_hype_url(url) for url in calls)


def test_mock_uses_only_retrieved_content_and_does_not_pad_recommendations() -> None:
    context = HypeContext("events", NOW.date(), [HypeDocument("Koncert 04.11.2099", f"{PRODUCTION_ROOT}/portfolio/event/", "Potvrdjen koncert.", NOW, event_date=date(2099, 11, 4))])
    response = asyncio.run(MockAIProvider().generate_chat_response(ChatRequest(message="Hype koncert", conversation_id="existing"), hype_context=context))
    assert response.conversation_id == "existing"
    assert response.answer_type == "hype_content"
    assert len(response.recommendations) == 1
    assert response.recommendations[0].estimated_price is None
    assert response.recommendations[0].date_or_duration == "2099-11-04"
    assert str(response.sources[0].url) == context.documents[0].url
    assert response.sources[0].last_verified == NOW
    assert all("Hype" in action for action in response.follow_up_actions)


def test_mock_failure_does_not_fabricate_hype_events() -> None:
    response = asyncio.run(MockAIProvider().generate_chat_response(ChatRequest(message="Hype koncert"), hype_context=HypeContext("events", NOW.date())))
    assert response.recommendations == []
    assert response.sources == []
    assert "nemam dovoljno" in response.summary


def test_historical_events_are_not_described_as_upcoming() -> None:
    context = HypeContext("events", NOW.date(), [HypeDocument("Koncert 01.01.2001", f"{PRODUCTION_ROOT}/portfolio/past/", "Arhivski koncert.", NOW, event_date=date(2001, 1, 1))])
    response = asyncio.run(MockAIProvider().generate_chat_response(ChatRequest(message="Prosli Hype koncerti"), hype_context=context))
    assert "datumima od" not in response.summary
    assert response.recommendations[0].date_or_duration == "2001-01-01"


def test_generic_service_does_not_call_retriever() -> None:
    class NoRetrieval:
        async def retrieve(self, message):
            pytest.fail("Generic request reached retriever")
    response = asyncio.run(ChatService(provider=MockAIProvider(), retriever=NoRetrieval()).generate_response(ChatRequest(message="Restoran u Beogradu")))
    assert response.answer_type == "recommendations"
    assert len(response.recommendations) == 3


def test_hype_request_reaches_retrieval_through_existing_chat_route(monkeypatch) -> None:
    async def retrieve(message):
        return HypeContext("news", NOW.date(), [HypeDocument("Hype novost", f"{TV_ROOT}/novost/", "Vest objavljena na Hype TV.", NOW, published_at=NOW)])
    monkeypatch.setattr(hype_retriever, "retrieve", retrieve)
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.post("/api/chat", headers={"X-Anonymous-ID": "11111111-1111-4111-8111-111111111111"}, json={"message": "Sta ima novo na Hype TV?"})
    response = asyncio.run(request())
    assert response.status_code == 200
    data = response.json()
    assert data["answer_type"] == "hype_content"
    assert data["sources"][0]["url"] == f"{TV_ROOT}/novost/"
    assert data["recommendations"][0]["date_or_duration"] == "Objavljeno: 2026-10-04"
