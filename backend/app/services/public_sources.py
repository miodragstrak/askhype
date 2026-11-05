"""Explicit-user-URL retrieval. Independent of the allowlisted Hype reader."""

import asyncio
import ipaddress
import json
import re
import socket
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import httpx

MAX_URLS = 3
MAX_URL_LENGTH = 2048
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 12
PARSE_TIMEOUT_SECONDS = 8
MAX_SOURCE_CHARS = 10_000
MAX_CONTEXT_CHARS = 40_000
SUPPORTED_TYPES = frozenset({"text/html", "application/pdf", "text/plain"})
_URL_PATTERN = re.compile(r"(?<![\w/+.-])https?://[^\s<>\"'`]+", re.IGNORECASE)
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")
_METADATA_HOSTS = frozenset({"metadata", "metadata.google.internal", "instance-data.ec2.internal"})
_BLOCKED_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    # Keep these explicit: is_global classifications differ across Python 3.12+.
    "192.0.0.0/24", "192.88.99.0/24", "168.63.129.16/32",
    "64:ff9b::/96", "64:ff9b:1::/48", "2001::/23", "2002::/16",
))


class SourceRetrievalError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PublicDocument:
    title: str
    url: str
    content_type: str
    text: str
    retrieved_at: datetime
    truncated: bool = False


@dataclass(frozen=True)
class SourceFailure:
    url: str
    reason: str


@dataclass
class PublicSourceContext:
    documents: list[PublicDocument] = field(default_factory=list)
    failures: list[SourceFailure] = field(default_factory=list)

    def to_prompt(self, message: str) -> str:
        budget = MAX_SOURCE_CHARS
        while True:
            value = {
                "documents": [
                    {
                        "title": doc.title,
                        "url": doc.url,
                        "content_type": doc.content_type,
                        "text": select_excerpts(doc.text, message, budget),
                        "partial_content": doc.truncated or len(doc.text) > budget,
                    }
                    for doc in self.documents
                ],
                "failures": [{"url": item.url, "reason": item.reason} for item in self.failures],
            }
            prompt = json.dumps(value, ensure_ascii=False)
            if len(prompt) <= MAX_CONTEXT_CHARS:
                return prompt
            budget //= 2


def explicit_urls(message: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_PATTERN.finditer(message):
        url = match.group().rstrip(".,;:!?")
        # Keep balanced parentheses inside URL paths, strip prose/Markdown closers.
        for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
            while url.endswith(closing) and url.count(closing) > url.count(opening):
                url = url[:-1]
        if url not in urls:
            urls.append(url)
        if len(urls) > MAX_URLS:
            break
    return urls


def select_excerpts(text: str, message: str, budget: int) -> str:
    """Keep the beginning, query-ranked chunks and ending in source order."""
    if len(text) <= budget:
        return text
    chunk_size = 1200
    chunks = [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]
    terms = set(re.findall(r"[^\W_]{4,}", _URL_PATTERN.sub("", message).casefold()))
    scores = [sum(chunk.casefold().count(term) for term in terms) for chunk in chunks]
    count = max(1, budget // (chunk_size + 80))
    selected = {0}
    if count > 1:
        selected.add(len(chunks) - 1)
    for index in sorted(range(1, len(chunks) - 1), key=lambda index: (-scores[index], index)):
        if len(selected) >= count:
            break
        selected.add(index)
    return "\n\n".join(
        f"[Source characters {index * chunk_size}-{min((index + 1) * chunk_size, len(text))}]\n{chunks[index]}"
        for index in sorted(selected)
    )[:budget]


async def resolve_host(host: str, port: int) -> list[str]:
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(record[4][0] for record in records))


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if any(address.version == network.version and address in network for network in _BLOCKED_NETWORKS):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.is_site_local:
            return False
        # Reject transition/translation forms that can conceal a non-public IPv4.
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
    return True


class PublicSourceReader:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable[[str, int], Awaitable[list[str]]] = resolve_host,
    ) -> None:
        self.transport = transport
        self.resolver = resolver

    async def retrieve(self, message: str) -> PublicSourceContext | None:
        urls = explicit_urls(message)
        if not urls:
            return None
        context = PublicSourceContext()
        for url in urls[:MAX_URLS]:
            try:
                async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                    body, content_type, encoding, final_url = await self._fetch(url)
                extracted = await self._extract(body, content_type, encoding)
                context.documents.append(PublicDocument(
                    title=extracted["title"] or unquote(httpx.URL(final_url).path.rsplit("/", 1)[-1])[:300] or httpx.URL(final_url).host,
                    url=final_url,
                    content_type=content_type,
                    text=extracted["text"],
                    retrieved_at=datetime.now(UTC),
                    truncated=extracted["truncated"],
                ))
            except SourceRetrievalError as exc:
                context.failures.append(SourceFailure(url[:MAX_URL_LENGTH], exc.reason))
            except httpx.InvalidURL:
                # HTTPX also parses Location headers while preparing next_request,
                # even with automatic redirect following disabled.
                context.failures.append(SourceFailure(url[:MAX_URL_LENGTH], "invalid_url"))
            except (TimeoutError, httpx.TimeoutException):
                context.failures.append(SourceFailure(url[:MAX_URL_LENGTH], "timeout"))
            except (httpx.HTTPError, OSError, ValueError):
                context.failures.append(SourceFailure(url[:MAX_URL_LENGTH], "fetch_failed"))
        if len(urls) > MAX_URLS:
            context.failures.append(SourceFailure("", "url_limit"))
        return context

    async def _validated_target(self, value: str) -> tuple[httpx.URL, str]:
        if len(value) > MAX_URL_LENGTH or any(ord(char) < 33 or char == "\\" for char in value):
            raise SourceRetrievalError("invalid_url")
        try:
            url = httpx.URL(value)
            host = url.host.lower().rstrip(".")
            port = url.port or (443 if url.scheme == "https" else 80)
        except (ValueError, httpx.InvalidURL) as exc:
            raise SourceRetrievalError("invalid_url") from exc
        if url.scheme not in {"http", "https"} or not host or url.userinfo or "%" in host:
            raise SourceRetrievalError("invalid_url")
        if len(str(url)) > MAX_URL_LENGTH:
            raise SourceRetrievalError("invalid_url")
        if host == "localhost" or host in _METADATA_HOSTS or host.endswith(_LOCAL_SUFFIXES):
            raise SourceRetrievalError("blocked_target")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host:
                raise SourceRetrievalError("blocked_target")
            addresses = await self.resolver(host, port)
        else:
            addresses = [str(literal)]
        # Fail closed on mixed public/private DNS answers, before any connection.
        if not addresses or not all(is_public_ip(address) for address in addresses):
            raise SourceRetrievalError("blocked_target")
        return url.copy_with(fragment=None), addresses[0]

    async def _fetch(self, value: str) -> tuple[bytes, str, str, str]:
        async with httpx.AsyncClient(
            transport=self.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(5),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        ) as client:
            for hop in range(MAX_REDIRECTS + 1):
                url, address = await self._validated_target(value)
                # Connect to the checked IP, with original Host and TLS SNI/cert
                # hostname. No second hostname lookup, proxy or DNS rebinding gap.
                async with client.stream(
                    "GET", url.copy_with(host=address),
                    headers={
                        "Host": url.netloc.decode("ascii"),
                        "Accept": ", ".join(sorted(SUPPORTED_TYPES)),
                        "Accept-Encoding": "identity",
                        "User-Agent": "AskHype-PublicSourceReader/1.0",
                    },
                    extensions={"sni_hostname": url.host},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or hop == MAX_REDIRECTS:
                            raise SourceRetrievalError("redirect_limit")
                        value = str(url.join(location))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type not in SUPPORTED_TYPES:
                        raise SourceRetrievalError("unsupported_type")
                    # Prevent decompression bombs; identity is explicitly requested.
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise SourceRetrievalError("unsupported_encoding")
                    length = response.headers.get("content-length")
                    if length and (not length.isdecimal() or int(length) > MAX_RESPONSE_BYTES):
                        raise SourceRetrievalError("too_large")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise SourceRetrievalError("too_large")
                        body.extend(chunk)
                    return bytes(body), content_type, response.charset_encoding or "utf-8", str(url)
        raise SourceRetrievalError("redirect_limit")

    async def _extract(self, body: bytes, content_type: str, encoding: str) -> dict:
        worker = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name("source_extraction.py")), content_type, encoding,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(PARSE_TIMEOUT_SECONDS):
                output, _ = await worker.communicate(body)
            if worker.returncode != 0:
                raise SourceRetrievalError("unreadable_content")
            result = json.loads(output)
            if "error" in result:
                raise SourceRetrievalError(result["error"])
            return result
        finally:
            if worker.returncode is None:
                worker.kill()
                await worker.communicate()


public_source_reader = PublicSourceReader()
