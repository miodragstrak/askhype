"""Opt-in two-process check against the disposable PostgreSQL harness."""

import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
OWNER = UUID("10000000-0000-4000-8000-000000000001")
SOCKET = "ASKHYPE_CHAT_TEST_POSTGRES_SOCKET"


def psql(statement):
    return subprocess.run(
        [os.environ["ASKHYPE_CHAT_TEST_PSQL"], "-XqAt", "-v", "ON_ERROR_STOP=1",
         "-h", os.environ[SOCKET], "-U", "postgres", "-d", "turn_fresh", "-c", statement],
        check=True, capture_output=True, text=True, timeout=4,
    ).stdout.strip()


def sql(value):
    if value is None:
        return "null"
    # The worker only uses synthetic inputs. Base64 keeps literals out of SQL syntax.
    encoded = base64.b64encode(str(value).encode()).decode()
    return f"convert_from(decode('{encoded}','base64'),'UTF8')"


async def rpc(function, *arguments):
    values = ", ".join(arguments)
    result = await asyncio.to_thread(psql, f"set role service_role; select public.{function}({values});")
    return json.loads(result) if result else None


def serve(fd, path):
    import uvicorn
    from datetime import UTC, datetime
    from app.api.dependencies import get_authenticated_identity
    from app.api.routes.chat import get_chat_turn_repository
    from app.auth.identity import RequestIdentity
    from app.core.config import settings
    from app.main import app
    from app.schemas.chat import ChatResponse
    from app.services import chat_turns

    class Repository(chat_turns.ChatTurnRepository):
        async def _rpc(self, name, values):
            casts = {
                "p_user": "uuid", "p_turn": "uuid", "p_conversation": "uuid", "p_create": "boolean",
                "p_attachment_count": "integer", "p_response": "jsonb",
            }
            return await rpc(name, *(f"{sql(json.dumps(value) if isinstance(value, dict) else value)}"
                                     f"::{casts.get(key, 'text')}" for key, value in values.items()))

    tcp_started = asyncio.Event()

    class Provider:
        async def generate_response(self, request):
            (path / f"{request.message}-{os.getpid()}").touch()
            if request.message == "socket":
                tcp_started.set()
            while not (path / f"{request.message}-release").exists():
                await asyncio.sleep(.02)
            return ChatResponse(
                conversation_id="synthetic", provider="mock", answer_type="chat", summary="Persisted",
                recommendations=[], follow_up_actions=[], sources=[], generated_at=datetime.now(UTC),
            )

    async def identity():
        return RequestIdentity("authenticated", OWNER, None, "free", None)

    async def repository():
        return Repository()

    settings.server_chat_turns_enabled = True
    settings.quota_enforcement_enabled = True
    settings.gemini_research_model = None
    app.dependency_overrides[get_authenticated_identity] = identity
    app.dependency_overrides[get_chat_turn_repository] = repository
    chat_turns.ChatService = Provider
    async def observe_socket(scope, receive, send):
        if scope["type"] != "http" or (b"x-test-disconnect", b"1") not in scope["headers"]:
            await app(scope, receive, send)
            return
        waiter = asyncio.create_task(app(scope, receive, send))
        await tcp_started.wait()
        observed = False
        try:
            observed = (await receive())["type"] == "http.disconnect"
            assert observed
        finally:
            waiter.cancel()
            try:
                await waiter
            except asyncio.CancelledError:
                if observed:
                    (path / "socket-waiter-cancelled").touch()

    uvicorn.Server(uvicorn.Config(observe_socket, http="h11", log_level="critical")).run(
        sockets=[socket.socket(fileno=fd)],
    )


def wait_for(predicate):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(.02)
    pytest.fail("Timed out waiting for worker or fixture event")


@pytest.mark.skipif(SOCKET not in os.environ, reason="Run through the disposable PostgreSQL harness")
def test_two_workers_claim_once_and_process_loss_does_not_redispatch(tmp_path):
    workers = []
    pool = ThreadPoolExecutor(2)
    try:
        for _ in range(2):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                port = listener.getsockname()[1]
                fd = listener.fileno()
                process = subprocess.Popen(
                    [sys.executable, "-m", "tests.test_chat_turn_processes", str(fd), str(tmp_path)],
                    cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(ROOT)}, pass_fds=(fd,),
                )
            workers.append((process, f"http://127.0.0.1:{port}"))

        def query(worker, method, route, **kwargs):
            return httpx.request(method, workers[worker][1] + route, trust_env=False, timeout=8, **kwargs)

        def ready(worker):
            try:
                return query(worker, "GET", "/api/health").status_code == 200
            except httpx.ConnectError:
                return False

        for worker in range(2):
            wait_for(lambda: ready(worker))

        def start(message, both):
            turn, conversation = uuid4(), uuid4()
            route = f"/api/chat/turns/{turn}"
            params = {"conversation_id": str(conversation), "create_conversation": "true"}
            futures = {
                pool.submit(query, index, "POST", route, params=params, json={"message": message}): index
                for index in range(2 if both else 1)
            }
            return turn, route, params, futures

        def counts(turn):
            return psql(f"""select t.status, u.status, count(m.id)
                from public.chat_turns t join public.usage_events u on u.id=t.usage_event_id
                left join public.conversation_messages m on m.id=t.assistant_message_id
                where t.id='{turn}' group by t.status,u.status""")

        turn, route, _, futures = start("claim", both=True)
        wait_for(lambda: list(tmp_path.glob("claim-[0-9]*")))
        duplicate = wait_for(lambda: next((f for f in futures if f.done()), None))
        assert duplicate.result().status_code == 202
        (tmp_path / "claim-release").touch()
        assert sorted(f.result().status_code for f in futures) == [200, 202]
        assert len(list(tmp_path.glob("claim-[0-9]*"))) == 1
        assert counts(turn) == "completed|completed|1"

        turn, conversation = uuid4(), uuid4()
        route = f"/api/chat/turns/{turn}"
        port = int(workers[0][1].rsplit(":", 1)[1])
        body = b'{"message":"socket"}'
        with socket.create_connection(("127.0.0.1", port), timeout=4) as client:
            client.sendall(
                f"POST {route}?conversation_id={conversation}&create_conversation=true HTTP/1.1\r\n"
                f"Host: localhost\r\nX-Test-Disconnect: 1\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n".encode() + body
            )
            wait_for(lambda: list(tmp_path.glob("socket-[0-9]*")))
            client.shutdown(socket.SHUT_RDWR)
        wait_for(lambda: (tmp_path / "socket-waiter-cancelled").exists())
        (tmp_path / "socket-release").touch()
        recovered = wait_for(lambda: (response if (response := query(1, "GET", route)).status_code == 200 else None))
        assert recovered.json()["response"]["summary"] == "Persisted"
        assert len(list(tmp_path.glob("socket-[0-9]*"))) == 1
        assert counts(turn) == "completed|completed|1"

        turn, route, params, futures = start("stop", both=False)
        wait_for(lambda: list(tmp_path.glob("stop-[0-9]*")))
        workers[0][0].kill()
        workers[0][0].wait(timeout=3)
        with pytest.raises(httpx.TransportError):
            next(iter(futures)).result()
        assert query(1, "POST", route, params=params, json={"message": "stop"}).status_code == 202
        assert counts(turn) == "processing|reserved|0"
        psql(f"update public.chat_turns set created_at=now()-interval '4 minutes' where id='{turn}'")
        assert query(1, "GET", route).json()["failure_code"] == "execution_interrupted"
        assert counts(turn) == "unknown|failed|0"
        assert len(list(tmp_path.glob("stop-[0-9]*"))) == 1
    finally:
        for process, _ in workers:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        pool.shutdown(wait=True)


if __name__ == "__main__":
    serve(int(sys.argv[1]), Path(sys.argv[2]))
