import hmac
import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, status

from app.clients.supabase import SupabaseAuthVerifier
from app.core.config import settings

IdentityKind = Literal["guest", "authenticated"]
Plan = Literal["guest", "free", "premium"]


@dataclass(frozen=True)
class RequestIdentity:
    kind: IdentityKind
    user_id: UUID | None
    anonymous_id_hash: str | None
    plan: Plan
    email: str | None


def hash_anonymous_id(raw_id: str, pepper: str) -> str:
    digest = hmac.new(
        pepper.encode("utf-8"),
        raw_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"guest_{digest}"


def _secret_value(value: object | None, fallback: str) -> str:
    if value is None:
        return fallback
    if hasattr(value, "get_secret_value"):
        return str(value.get_secret_value())
    return str(value)


async def resolve_request_identity(
    authorization: str | None = Header(default=None),
    x_anonymous_id: str | None = Header(default=None, alias="X-Anonymous-ID"),
) -> RequestIdentity:
    if authorization:
        return await resolve_authenticated_identity(authorization)
    return resolve_guest_identity(x_anonymous_id)


async def resolve_authenticated_identity(
    authorization: str,
    verifier: SupabaseAuthVerifier | None = None,
    profile_plan_loader: object | None = None,
) -> RequestIdentity:
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")

    try:
        verifier = verifier or SupabaseAuthVerifier()
        claims = await verifier.verify_claims(token.strip())
        user_id = UUID(str(claims.get("sub")))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.") from exc

    email = claims.get("email")
    plan: Plan = "free"
    if profile_plan_loader is not None and hasattr(profile_plan_loader, "get_plan_for_user"):
        loaded_plan = await profile_plan_loader.get_plan_for_user(user_id)
        plan = "premium" if loaded_plan == "premium" else "free"

    return RequestIdentity(
        kind="authenticated",
        user_id=user_id,
        anonymous_id_hash=None,
        plan=plan,
        email=email if isinstance(email, str) else None,
    )


def resolve_guest_identity(raw_anonymous_id: str | None) -> RequestIdentity:
    if not raw_anonymous_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing anonymous identity.")
    try:
        parsed = UUID(raw_anonymous_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed anonymous identity.") from exc

    pepper = _secret_value(settings.anonymous_id_pepper, "development-pepper")
    return RequestIdentity(
        kind="guest",
        user_id=None,
        anonymous_id_hash=hash_anonymous_id(str(parsed), pepper),
        plan="guest",
        email=None,
    )
