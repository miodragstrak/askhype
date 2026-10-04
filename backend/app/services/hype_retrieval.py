import asyncio
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.parse import urlencode
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

TV_ROOT = "https://hypetv.rs"
PRODUCTION_ROOT = "https://www.hypeproduction.rs"
HYPE_HOSTS = frozenset({"hypetv.rs", "www.hypetv.rs", "hypeproduction.rs", "www.hypeproduction.rs"})
MAX_PAGE_BYTES = 1_000_000
MAX_DOCUMENTS = 3
MAX_DETAIL_PAGES = 6
CACHE_SECONDS = 300
_QUERY_STOPWORDS = frozenset("sta ima novo novosti na hype hypetv hypeproduction tv production a koje koji ko su vredi pogledati uskoro dolaze emisija emisije program danas izvodac izvodaci artist artists koncert koncerti koncertima events shows news sadrzaj o i u za da mi molim".split())
_MONTHS = {form: index for index, forms in enumerate(
    [("januar", "januara"), ("februar", "februara"), ("mart", "marta"),
     ("april", "aprila"), ("maj", "maja"), ("jun", "juna"), ("jul", "jula"),
     ("avgust", "avgusta"), ("septembar", "septembra"), ("oktobar", "oktobra"),
     ("novembar", "novembra"), ("decembar", "decembra")], 1
) for form in forms}


def normalize(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold().replace("đ", "d")) if not unicodedata.combining(char))


def hype_topic(message: str) -> str | None:
    text = normalize(message)
    if not re.search(r"\b(?:hype(?:tv|production)?|hajp|хајп)\b", text):
        return None
    if any(word in text for word in ["koncert", "dogadaj", "event", "festival"]):
        return "events"
    if any(word in text for word in ["izvod", "artist", "pevac", "muzicar"]):
        return "artists"
    if any(word in text for word in ["emisij", "program", "show", "zvezde"]):
        return "shows"
    if "production" in text:
        return "production"
    return "news"


def is_hype_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in HYPE_HOSTS
                and parsed.username is None and parsed.password is None and parsed.port in (None, 443))
    except ValueError:
        return False


def _text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, nav, header, footer, aside, form, svg, .menu, #header-outer, #footer-outer"):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _event_date(text: str) -> date | None:
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", text)
    if match:
        day, month, year = map(int, match.groups())
    else:
        match = re.search(r"\b(\d{1,2})\.?\s+(" + "|".join(_MONTHS) + r")[a-z]*\s+(20\d{2})\b", normalize(text))
        if not match:
            return None
        day, month, year = int(match[1]), _MONTHS[match[2]], int(match[3])
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class HypeDocument:
    title: str
    url: str
    excerpt: str
    retrieved_at: datetime
    published_at: datetime | None = None
    event_date: date | None = None
    conflicting_date: bool = False
    location: str | None = None

    @property
    def owner(self) -> str:
        return "Hype TV" if urlsplit(self.url).hostname.removeprefix("www.") == "hypetv.rs" else "Hype Production"

    @property
    def date_label(self) -> str | None:
        if self.event_date:
            return self.event_date.isoformat()
        if self.published_at:
            return f"Objavljeno: {self.published_at.date().isoformat()}"
        return None


@dataclass(frozen=True)
class HypeContext:
    topic: str
    today: date
    documents: list[HypeDocument] = field(default_factory=list)

    def to_prompt(self) -> str:
        return json.dumps({
            "topic": self.topic,
            "today_in_Belgrade": self.today.isoformat(),
            "insufficient_sources": len(self.documents) < MAX_DOCUMENTS,
            "documents": [{
                "title": doc.title, "url": doc.url, "owner": doc.owner,
                "excerpt": doc.excerpt, "published_at": doc.published_at.isoformat() if doc.published_at else None,
                "event_date": doc.event_date.isoformat() if doc.event_date else None,
                "location": doc.location,
            } for doc in self.documents],
        }, ensure_ascii=False)


def _json_objects(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_objects(child)


def parse_page(html: str, url: str, retrieved_at: datetime) -> tuple[HypeDocument | None, list[tuple[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    metadata = {}
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            for obj in _json_objects(json.loads(tag.get_text())):
                types = obj.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if any(str(kind).endswith("Event") for kind in types):
                    metadata.update(obj)
        except (ValueError, TypeError, RecursionError):
            continue
    if str(metadata.get("eventStatus", "")).endswith("EventCancelled"):
        return None, []
    published = soup.select_one('meta[property="article:published_time"], meta[name="date"], time[datetime]')
    published_at = _datetime((published.get("content") or published.get("datetime")) if published else None)
    for tag in soup.select("script, style, noscript, nav, header, footer, aside, form, svg, .menu, #header-outer, #footer-outer"):
        tag.decompose()
    root = soup.select_one("main, .entry-content, .post-content, .page-content, #content") or soup.body or soup
    heading = root.select_one("h1") or soup.select_one('meta[property="og:title"]') or soup.title
    title = (heading.get("content") or heading.get_text(" ", strip=True)) if heading else ""
    title = " ".join(title.split())
    excerpt = " ".join(root.get_text(" ", strip=True).split())
    start = _datetime(str(metadata.get("startDate", "")))
    title_date = _event_date(title)
    body_date = _event_date(excerpt[excerpt.find("Datum:"):][:100]) if "Datum:" in excerpt else None
    event_date = start.date() if start else title_date or body_date
    conflicting = len({value for value in [start.date() if start else None, title_date, body_date] if value}) > 1
    location = metadata.get("location")
    location = location.get("name") if isinstance(location, dict) else None
    # Production catalog headings often supply a venue/city between artist and date.
    title_parts = re.split(r"\s+[-–—]\s+", title)
    if not location and title_date and len(title_parts) >= 3 and _event_date(title_parts[-1]):
        location = title_parts[-2]
    links = []
    for anchor in root.select("a[href]"):
        target = urljoin(url, anchor.get("href", ""))
        label = anchor.get_text(" ", strip=True) or anchor.get("title", "")
        if not label and (image := anchor.find("img")):
            label = image.get("alt", "")
        if is_hype_url(target) and urlsplit(target).path not in ("", "/"):
            links.append((target.split("#", 1)[0], label))
    document = HypeDocument(title, url, excerpt[:1800], retrieved_at, published_at, event_date, conflicting, location)
    return (document if title and len(excerpt) > 30 else None), links


def parse_feed(xml: str, retrieved_at: datetime) -> list[HypeDocument]:
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        return []
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []
    documents = []
    for item in root.findall(".//item")[:20]:
        url = (item.findtext("link") or "").strip()
        title = _text(item.findtext("title") or "")
        content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or item.findtext("description") or ""
        excerpt = _text(content)
        if is_hype_url(url) and title and excerpt:
            documents.append(HypeDocument(title, url, excerpt[:1800], retrieved_at,
                                          _datetime(item.findtext("pubDate")), _event_date(title)))
    return documents


class HypeRetriever:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self._cache: dict[str, tuple[float, str, str, datetime]] = {}

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[str, str, datetime] | None:
        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1], cached[2], cached[3]
        original_url = url
        try:
            for _ in range(3):
                if not is_hype_url(url):
                    return None
                async with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if not any(kind in content_type for kind in ["html", "xml", "rss"]):
                        return None
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_PAGE_BYTES:
                            return None
                    text = body.decode(response.encoding or "utf-8", errors="replace")
                    if len(self._cache) >= 16:
                        del self._cache[min(self._cache, key=lambda key: self._cache[key][0])]
                    retrieved_at = datetime.now(UTC)
                    self._cache[original_url] = (time.monotonic(), text, url, retrieved_at)
                    return text, url, retrieved_at
        except (httpx.HTTPError, ValueError, LookupError):
            return None
        return None

    async def retrieve(self, message: str) -> HypeContext | None:
        topic = hype_topic(message)
        if topic is None:
            return None
        today = datetime.now(ZoneInfo("Europe/Belgrade")).date()
        try:
            async with asyncio.timeout(12):
                documents = await self._retrieve(message, topic, today)
        except TimeoutError:
            documents = []
        return HypeContext(topic, today, documents)

    async def _retrieve(self, message: str, topic: str, today: date) -> list[HypeDocument]:
        tokens = [word[:80] for word in re.findall(r"\w+", normalize(message)) if len(word) > 2 and word not in _QUERY_STOPWORDS][:8]
        search = urlencode({"s": " ".join(tokens), "feed": "rss2"})
        seeds = {
            "news": [f"{TV_ROOT}/?{search}" if tokens else f"{TV_ROOT}/feed/", f"{PRODUCTION_ROOT}/feed/"],
            "shows": [f"{TV_ROOT}/?{search}" if tokens else f"{TV_ROOT}/news/category/tv/program/feed/", f"{PRODUCTION_ROOT}/tv-emisije/"],
            "artists": [f"{PRODUCTION_ROOT}/izvodjaci/", f"{TV_ROOT}/?s=Hype+Production&feed=rss2"],
            "events": [f"{PRODUCTION_ROOT}/koncerti/", f"{TV_ROOT}/?s=Hype+koncert&feed=rss2"],
            "production": [f"{PRODUCTION_ROOT}/", f"{TV_ROOT}/?s=Hype+Production&feed=rss2"],
        }[topic]
        documents: dict[str, HypeDocument] = {}
        detail_urls: set[str] = set()
        candidates: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=4, transport=self.transport,
                                     headers={"User-Agent": "AskHype-Demo/0.1 (Hype content retrieval)"}) as client:
            pages = await asyncio.gather(*(self._fetch(client, url) for url in seeds))
            for page in pages:
                if page is None:
                    continue
                html, url, retrieved_at = page
                if "<rss" in html[:1000]:
                    for doc in parse_feed(html, retrieved_at):
                        documents[doc.url] = doc
                        candidates[doc.url] = doc.title
                else:
                    doc, links = parse_page(html, url, retrieved_at)
                    if doc and topic != "events":
                        documents[doc.url] = doc
                    for target, label in links:
                        if topic in ("events", "artists") and "/portfolio/" not in urlsplit(target).path:
                            continue
                        candidates[target] = label

            def candidate_rank(item: tuple[str, str]) -> tuple:
                url, title = item
                event_date = _event_date(title) or _event_date(urlsplit(url).path)
                production = "hypeproduction.rs" in urlsplit(url).hostname
                matches = sum(word in normalize(title) for word in tokens)
                return (0 if (production == (topic in ("events", "artists"))) else 1,
                        0 if event_date and event_date >= today else 1, -matches,
                        event_date or date.max) if topic == "events" else (0 if (production == (topic in ("artists", "production"))) else 1, -matches)

            selected = sorted(candidates.items(), key=candidate_rank)[:MAX_DETAIL_PAGES]
            pages = await asyncio.gather(*(self._fetch(client, url) for url, _ in selected))
            for (target, _), page in zip(selected, pages):
                if page:
                    documents.pop(target, None)
                    doc, _ = parse_page(page[0], page[1], page[2])
                    if doc:
                        documents[doc.url] = doc
                        detail_urls.add(doc.url)

        historical = any(word in normalize(message) for word in ["prosli", "odrzani", "arhiv", "istorij", "past"])
        docs = [doc for doc in documents.values() if not doc.conflicting_date]
        if topic == "events" and not historical:
            docs = [doc for doc in docs if doc.url in detail_urls and doc.event_date and doc.event_date >= today]

        def rank(doc: HypeDocument) -> tuple:
            primary = doc.owner == ("Hype Production" if topic in ("artists", "events", "production") else "Hype TV")
            if topic == "events":
                return (not primary, not (doc.event_date and doc.event_date >= today), doc.event_date or date.max)
            matches = sum(word in normalize(doc.title + " " + doc.excerpt) for word in tokens)
            return (not primary, -matches, -(doc.published_at.timestamp() if doc.published_at else 0))

        return sorted(docs, key=rank)[:MAX_DOCUMENTS]


hype_retriever = HypeRetriever()
