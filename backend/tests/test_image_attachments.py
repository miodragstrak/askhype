import asyncio
import io
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.main import app
from app.schemas.attachments import ImageAttachment, ImageAttachmentError, MAX_IMAGE_BYTES, validate_image
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.hype_retrieval import HypeContext
from app.services.public_sources import PublicSourceContext, SourceFailure


def image_bytes(format_name: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format=format_name)
    return output.getvalue()


def response() -> ChatResponse:
    return ChatResponse(conversation_id="conv", provider="mock", answer_type="recommendations", summary="ok", recommendations=[], follow_up_actions=[], sources=[], generated_at=datetime.now(UTC))


async def post(files, payload=None, anonymous_id=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/chat",
            headers={"X-Anonymous-ID": anonymous_id or str(uuid4())},
            data={"request": json.dumps(payload or {"message": "Analiziraj"})},
            files=files,
        )


@pytest.mark.parametrize(("format_name", "mime"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_supported_images_reach_provider(monkeypatch, format_name: str, mime: str) -> None:
    captured = []

    async def generate(self, request, images=None):
        captured.extend(images or [])
        return response()

    monkeypatch.setattr(ChatService, "generate_response", generate)
    result = asyncio.run(post([("images", (f"test.{format_name.lower()}", image_bytes(format_name), mime))]))
    assert result.status_code == 200
    assert [item.content_type for item in captured] == [mime]


@pytest.mark.parametrize("files", [
    [("images", ("test.gif", b"GIF89a", "image/gif"))],
    [("images", ("fake.jpg", image_bytes("PNG"), "image/jpeg"))],
    [("images", ("broken.png", b"not-an-image", "image/png"))],
])
def test_invalid_image_is_rejected_before_provider(monkeypatch, files) -> None:
    async def no_provider(*args, **kwargs):
        pytest.fail("invalid image reached provider")
    monkeypatch.setattr(ChatService, "generate_response", no_provider)
    assert asyncio.run(post(files)).status_code == 400


def test_oversized_and_too_many_images_are_rejected() -> None:
    with pytest.raises(ImageAttachmentError, match="10 MB"):
        validate_image(b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg")
    valid = image_bytes("PNG")
    too_many = asyncio.run(post([("images", (f"{index}.png", valid, "image/png")) for index in range(4)]))
    assert too_many.status_code == 400
    assert "3 slike" in too_many.text


def test_image_only_and_multiple_images_preserve_order_and_count_one_prompt(monkeypatch) -> None:
    captured = {}
    anonymous_id = str(uuid4())

    async def generate(self, request, images=None):
        captured["message"] = request.message
        captured["types"] = [item.content_type for item in images or []]
        return response()

    monkeypatch.setattr(ChatService, "generate_response", generate)
    result = asyncio.run(post([
        ("images", ("one.png", image_bytes("PNG"), "image/png")),
        ("images", ("two.jpg", image_bytes("JPEG"), "image/jpeg")),
    ], {"message": ""}, anonymous_id))
    assert result.status_code == 200
    assert captured["message"].startswith("Analiziraj priloženu")
    assert captured["types"] == ["image/png", "image/jpeg"]
    assert result.headers["X-AskHype-Usage-Used"] == "1"


def test_hype_request_with_image_keeps_hype_context() -> None:
    class Retriever:
        async def retrieve(self, message):
            return HypeContext("shows", datetime.now(UTC).date())

    class Provider:
        provider_name = "mock"
        async def generate_chat_response(self, request, **kwargs):
            assert kwargs["hype_context"].topic == "shows"
            assert kwargs["images"][0].content_type == "image/png"
            return response()

    attachment = ImageAttachment("image/png", image_bytes("PNG"), "hype.png")
    result = asyncio.run(ChatService(provider=Provider(), retriever=Retriever()).generate_response(ChatRequest(message="Hype TV program"), [attachment]))
    assert result.summary == "ok"


def test_failed_public_source_does_not_discard_attached_image() -> None:
    class Reader:
        async def retrieve(self, message):
            return PublicSourceContext(failures=[SourceFailure("https://example.org/x", "timeout")])

    class Provider:
        provider_name = "gemini"
        async def generate_chat_response(self, request, **kwargs):
            assert kwargs["source_context"].failures
            assert len(kwargs["images"]) == 1
            return response()

    attachment = ImageAttachment("image/png", image_bytes("PNG"), "source.png")
    result = asyncio.run(ChatService(provider=Provider(), source_reader=Reader()).generate_response(
        ChatRequest(message="Analiziraj https://example.org/x i sliku"), [attachment]
    ))
    assert result.summary == "ok"
