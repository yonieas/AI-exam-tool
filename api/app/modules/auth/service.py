"""Auth service: JWT + refresh tokens + dev login."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Request, Response
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.errors import BadRequestError, NotFoundError, UnauthenticatedError
from app.models.user import User
from app.modules.auth.schemas import AccessTokenResponse, TokenPayload, UserOut


# Refresh tokens are stored hashed in Redis under `refresh:{hash}` -> family_id, user_id, exp
class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._redis = None  # lazy

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as redis_async
                self._redis = redis_async.from_url(self.settings.redis_url, decode_responses=True)
            except Exception:
                self._redis = None
        return self._redis

    # --- JWT access tokens ---
    def mint_access_token(self, user: User) -> tuple[str, int]:
        iat = int(time.time())
        exp = iat + self.settings.jwt_access_ttl_seconds
        claims = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.full_name,
            "iat": iat,
            "exp": exp,
        }
        token = jwt.encode(claims, self.settings.jwt_signing_key, algorithm=self.settings.jwt_algorithm)
        return token, self.settings.jwt_access_ttl_seconds

    def verify_access_token(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(token, self.settings.jwt_signing_key, algorithms=[self.settings.jwt_algorithm])
        except JWTError as e:
            raise UnauthenticatedError("Invalid or expired token.") from e
        return TokenPayload(**data)

    # --- Refresh tokens ---
    async def mint_refresh_token(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(48)
        r = self._get_redis()
        if r is not None:
            try:
                family = secrets.token_urlsafe(8)
                digest = hashlib.sha256(token.encode()).hexdigest()
                await r.set(
                    f"refresh:{digest}",
                    f"{family}|{user_id}|{int(time.time()) + self.settings.jwt_refresh_ttl_seconds}",
                    ex=self.settings.jwt_refresh_ttl_seconds,
                )
                await r.set(f"refresh_family:{family}", str(user_id), ex=self.settings.jwt_refresh_ttl_seconds)
            except Exception:
                pass
        return token

    async def rotate_refresh(self, token: str) -> tuple[UUID, str]:
        """Rotate refresh; raise if token was already used (family revoked)."""
        r = self._get_redis()
        if r is None:
            # Dev: accept any opaque token
            raise UnauthenticatedError("Refresh token store unavailable.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        raw = await r.get(f"refresh:{digest}")
        if not raw:
            raise UnauthenticatedError("Invalid refresh token.")
        family, uid, _exp = raw.split("|")
        # Reuse detection: delete the old token; if it was already deleted, the family is compromised.
        deleted = await r.delete(f"refresh:{digest}")
        if not deleted:
            # already rotated out — revoke the whole family
            await r.delete(f"refresh_family:{family}")
            raise UnauthenticatedError("Refresh token reuse detected. Please re-authenticate.")
        new_token = await self.mint_refresh_token(UUID(uid))
        return UUID(uid), new_token

    async def revoke_family(self, token: str) -> None:
        r = self._get_redis()
        if r is None:
            return
        digest = hashlib.sha256(token.encode()).hexdigest()
        raw = await r.get(f"refresh:{digest}")
        if raw:
            family = raw.split("|")[0]
            await r.delete(f"refresh_family:{family}")
            await r.delete(f"refresh:{digest}")

    # --- User ops ---
    async def get_or_create_user(self, email: str, full_name: str, avatar_url: Optional[str] = None) -> User:
        existing = (await self.session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if existing:
            existing.last_login_at = datetime.utcnow()
            if avatar_url and not existing.avatar_url:
                existing.avatar_url = avatar_url
            if full_name and not existing.full_name:
                existing.full_name = full_name
            await self.session.flush()
            return existing
        user = User(
            id=uuid.uuid4(),
            email=email.lower(),
            full_name=full_name or email.split("@")[0],
            avatar_url=avatar_url,
            settings={"default_confidence_threshold": 0.7},
            last_login_at=datetime.utcnow(),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_user(self, user_id: UUID) -> User:
        user = (await self.session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            raise NotFoundError("User not found.")
        return user

    def user_to_dto(self, user: User) -> UserOut:
        return UserOut(id=user.id, email=user.email, full_name=user.full_name, avatar_url=user.avatar_url)

    # --- Cookies ---
    def set_refresh_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key="refresh",
            value=token,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            max_age=self.settings.jwt_refresh_ttl_seconds,
            path="/api/v1/auth",
            domain=self.settings.cookie_domain or None,
        )

    def clear_refresh_cookie(self, response: Response) -> None:
        response.delete_cookie("refresh", path="/api/v1/auth", domain=self.settings.cookie_domain or None)


def get_auth_service() -> "AuthService":
    """Factory used as a dependency. Returns a service that lazily binds the session."""
    # The session is per-request; the routes pass it explicitly via `_with_session`.
    raise RuntimeError("Use auth_service(request) inside routes")


# Helper for routes: returns an AuthService bound to the request's session
def auth_service_for(request: Request) -> AuthService:
    return AuthService(request.state.db, get_settings())
