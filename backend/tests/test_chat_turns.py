import asyncio
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import Request

from app.api.dependencies import get_authenticated_identity
from app.api.routes.chat import get_chat_turn_repository, settings
from app.auth.identity import RequestIdentity
from app.main import app, lifespan
from app.providers.exceptions import AIProviderTimeoutError, AIProviderUnavailableError
from app.schemas.chat import ChatResponse
from app.services import chat_turns


class Repository:
    """Transport double. Transaction and RLS guarantees are tested separately in PostgreSQL."""
    def __init__(self):
        self.rows = {}
        self.fail_settlement = 0
        self.lose_ack = False
        self.reservations = 0
        self.assistant_rows = set()
        self.completed_usage = set()

    async def accept(self, user, turn, conversation, request, images, create):
        fingerprint = chat_turns.request_fingerprint(request, images)
        if turn in self.rows:
            owner, prior_fingerprint, value = self.rows[turn]
            if owner != user:
                return {"error": "not_found"}
            if fingerprint != prior_fingerprint or conversation != value["conversation_id"]:
                return {"error": "conflict"}
            return {"claimed": False, "turn": value}
        if not create:
            return {"error": "not_found"}
        value = {"id": turn, "conversation_id": conversation, "assistant_message_id": uuid4(),
                 "status": "processing", "created_at": datetime.now(UTC)}
        self.rows[turn] = (user, fingerprint, value)
        self.reservations += 1
        return {"claimed": True, "turn": value}

    async def finish(self, user, turn, status, response, failure):
        if self.fail_settlement:
            self.fail_settlement -= 1
            raise RuntimeError("Synthetic settlement interruption")
        value = await self.read(user, turn)
        if value["status"] == "processing":
            value.update(status=status, response=response, failure_code=failure)
            if status == "completed":
                self.assistant_rows.add(value["assistant_message_id"])
                self.completed_usage.add(turn)
        if self.lose_ack:
            self.lose_ack = False
            raise RuntimeError("Synthetic lost DB acknowledgement")
        return value

    async def read(self, user, turn):
        row = self.rows.get(turn)
        return row[2] if row and row[0] == user else None


@asynccontextmanager
async def turn_client():
    async with lifespan(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"x-synthetic-user": "owner"},
    ) as client:
        yield client


@pytest.fixture
def setup(monkeypatch):
    repo = Repository()
    owner = uuid4()
    other = uuid4()
    identities = {"owner": owner, "other": other}

    async def authenticate(request: Request):
        user = identities[request.headers["x-synthetic-user"]]
        return RequestIdentity("authenticated", user, None, "free", None)

    monkeypatch.setattr(settings, "server_chat_turns_enabled", True)
    monkeypatch.setattr(settings, "quota_enforcement_enabled", True)
    monkeypatch.setitem(app.dependency_overrides, get_authenticated_identity, authenticate)
    async def get_repository():
        return repo

    monkeypatch.setitem(app.dependency_overrides, get_chat_turn_repository, get_repository)
    return repo, ("/api/chat/turns/" + str(uuid4())), {
        "conversation_id": str(uuid4()), "create_conversation": "true",
    }


def mock_response():
    return ChatResponse(
        conversation_id="synthetic-thread", provider="mock", answer_type="chat", summary="Saved answer",
        recommendations=[], follow_up_actions=[], sources=[{"title": "Example", "url": "https://example.test"}],
        generated_at=datetime.now(UTC),
    )


def test_concurrent_duplicate_returns_processing_then_replays_saved_answer(setup, monkeypatch):
    repo, route, params = setup

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        class Chat:
            async def generate_response(self, request):
                calls.append(request.message)
                entered.set()
                await release.wait()
                return mock_response()

        monkeypatch.setattr(chat_turns, "ChatService", Chat)
        async with turn_client() as client:
            first = asyncio.create_task(client.post(route, params=params, json={"message": "Hello"}))
            started = asyncio.create_task(entered.wait())
            done, _ = await asyncio.wait({started, first}, timeout=2, return_when=asyncio.FIRST_COMPLETED)
            if first in done:
                result = first.result()
                pytest.fail(f"Provider was not dispatched: {result.status_code} {result.text}")
            assert started in done
            assert (await client.get(route)).status_code == 202
            assert (await client.post(route, params=params, json={"message": "Hello"})).status_code == 202
            assert (await client.post(route, params=params, json={"message": "Different"})).status_code == 409
            assert (await client.get(route, headers={"x-synthetic-user": "other"})).status_code == 404
            release.set()
            result = await first
            assert result.status_code == 200
            assert result.headers["Cache-Control"] == "private, no-store"
            assert result.json()["response"]["sources"][0]["title"] == "Example"
            assert (await client.get(route)).json() == result.json()
            assert (await client.post(route, params=params, json={"message": "Hello"})).json() == result.json()
            assert calls == ["Hello"]
            assert repo.reservations == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode,expected", [("retry_save", "completed"), ("lost_ack", "completed"), ("timeout", "unknown"), ("transport", "unknown"), ("save_lost", "processing")])
def test_settlement_retry_does_not_repeat_provider(setup, monkeypatch, mode, expected):
    repo, route, params = setup
    calls = []
    repo.fail_settlement = {"retry_save": 1, "lost_ack": 0, "timeout": 0, "transport": 0, "save_lost": 2}[mode]
    repo.lose_ack = mode == "lost_ack"

    class Chat:
        async def generate_response(self, request):
            calls.append(request.message)
            if mode == "timeout":
                raise AIProviderTimeoutError("Internal")
            if mode == "transport":
                raise AIProviderUnavailableError("Ambiguous transport")
            return mock_response()

    monkeypatch.setattr(chat_turns, "ChatService", Chat)

    async def run():
        async with turn_client() as client:
            first = await client.post(route, params=params, json={"message": "Hello"})
            assert first.status_code == (503 if mode == "save_lost" else 200)
            retry = await client.post(route, params=params, json={"message": "Hello"})
            assert retry.json()["status"] == expected
            assert repo.reservations == 1
            assert calls == ["Hello"]

    asyncio.run(run())


def test_cancelled_execution_leaves_durable_claim_for_status_recovery(setup, monkeypatch):
    repo, route, params = setup
    calls = []

    class Chat:
        async def generate_response(self, request):
            calls.append(request.message)
            raise asyncio.CancelledError

    monkeypatch.setattr(chat_turns, "ChatService", Chat)

    async def run():
        async with turn_client() as client:
            with pytest.raises(asyncio.CancelledError):
                await client.post(route, params=params, json={"message": "Hello"})
            assert (await client.get(route)).json()["status"] == "processing"
            assert (await client.post(route, params=params, json={"message": "Hello"})).status_code == 202
            assert repo.reservations == 1 and calls == ["Hello"]

    asyncio.run(run())


def test_real_tcp_disconnect_and_cancelled_waiter_preserve_generation(setup, monkeypatch, caplog):
    repo, route, params = setup

    async def run():
        entered, release, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        class Chat:
            async def generate_response(self, request):
                calls.append(request.message)
                entered.set()
                await release.wait()
                return mock_response()

        monkeypatch.setattr(chat_turns, "ChatService", Chat)

        async def cancel_disconnected_post(scope, receive, send):
            if scope["type"] != "http" or scope["method"] != "POST":
                await app(scope, receive, send)
                return
            waiter = asyncio.create_task(app(scope, receive, send))
            await entered.wait()  # The body has been consumed and the provider is gated.
            try:
                assert (await receive())["type"] == "http.disconnect"
            finally:
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter
                disconnected.set()

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(cancel_disconnected_post, http="h11", log_level="error"))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(8):
                    while not server.started:
                        await asyncio.sleep(.01)
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    body = b'{"message":"Hello"}'
                    writer.write(
                        f"POST {route}?conversation_id={params['conversation_id']}&create_conversation=true HTTP/1.1\r\n"
                        f"Host: localhost\r\nX-Synthetic-User: owner\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n\r\n".encode() + body
                    )
                    await writer.drain()
                    await entered.wait()
                    writer.transport.abort()
                    await disconnected.wait()
                    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                                                 headers={"x-synthetic-user": "owner"}, trust_env=False) as client:
                        assert (await client.get(route)).status_code == 202
                        release.set()
                        while (result := await client.get(route)).status_code == 202:
                            await asyncio.sleep(.01)
                        assert result.json()["response"]["summary"] == "Saved answer"
                        assert calls == ["Hello"]
                        assert repo.reservations == len(repo.assistant_rows) == len(repo.completed_usage) == 1
            finally:
                release.set()
                server.should_exit = True
                await serving

    caplog.set_level("INFO", logger="app.services.chat_turn_supervisor")
    asyncio.run(run())
    assert "http_waiter_cancelled" in caplog.text


def test_waiter_cancellation_after_admission_commit_before_ack(setup, monkeypatch):
    repo, route, params = setup

    async def run():
        accepted, release = asyncio.Event(), asyncio.Event()
        accept = repo.accept
        calls = []

        async def delayed_ack(*args):
            result = await accept(*args)
            if result["claimed"]:
                accepted.set()
                await release.wait()
            return result

        class Chat:
            async def generate_response(self, request):
                calls.append(request.message)
                return mock_response()

        monkeypatch.setattr(repo, "accept", delayed_ack)
        monkeypatch.setattr(chat_turns, "ChatService", Chat)
        async with turn_client() as client, asyncio.timeout(5):
            waiter = asyncio.create_task(client.post(route, params=params, json={"message": "Hello"}))
            await accepted.wait()
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert (await client.post(route, params=params, json={"message": "Hello"})).status_code == 202
            release.set()
            while (read := await client.get(route)).status_code == 202:
                await asyncio.sleep(.01)
            assert read.json()["status"] == "completed"
            assert calls == ["Hello"]
            assert repo.reservations == len(repo.assistant_rows) == len(repo.completed_usage) == 1

    asyncio.run(run())


def test_overload_rejects_before_admission_and_leaves_status_readable(setup, monkeypatch):
    repo, route, params = setup
    monkeypatch.setattr(settings, "chat_turn_worker_capacity", 1)

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        class Chat:
            async def generate_response(self, request):
                entered.set()
                await release.wait()
                return mock_response()

        monkeypatch.setattr(chat_turns, "ChatService", Chat)
        async with turn_client() as client, asyncio.timeout(5):
            first = asyncio.create_task(client.post(route, params=params, json={"message": "First"}))
            try:
                await entered.wait()
                other = "/api/chat/turns/" + str(uuid4())
                assert (await client.post(other, params=params, json={"message": "Other"})).status_code == 503
                assert (await client.get(other)).status_code == 404
                assert (await client.get(route)).status_code == 202
                assert repo.reservations == 1
            finally:
                release.set()
            assert (await first).status_code == 200

    asyncio.run(run())
