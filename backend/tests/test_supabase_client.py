import asyncio
from types import SimpleNamespace

import pytest

from app.clients.supabase import SupabaseAuthVerifier


class FakeAuth:
    def __init__(self, result: object) -> None:
        self.result = result

    def get_claims(self, *, jwt: str) -> object:
        return self.result


class FakeClient:
    def __init__(self, result: object) -> None:
        self.auth = FakeAuth(result)


def verify(result: object) -> dict[str, object]:
    verifier = SupabaseAuthVerifier(client=FakeClient(result))
    return asyncio.run(verifier.verify_claims("test-token"))


def test_verify_claims_unwraps_dict_response() -> None:
    claims = {"sub": "user-id", "email": "user@example.com"}

    assert verify({"claims": claims, "headers": {}, "signature": b"signature"}) == claims


def test_verify_claims_unwraps_object_response() -> None:
    claims = {"sub": "user-id", "email": "user@example.com"}

    assert verify(SimpleNamespace(claims=claims)) == claims


def test_verify_claims_accepts_direct_dict() -> None:
    claims = {"sub": "user-id", "email": "user@example.com"}

    assert verify(claims) == claims


def test_verify_claims_rejects_non_dict_claims() -> None:
    with pytest.raises(ValueError, match="Invalid Supabase claims response"):
        verify({"claims": ["not", "claims"]})
