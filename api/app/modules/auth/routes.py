"""Auth routes: /auth/google, /auth/google/callback, /auth/refresh, /auth/logout, dev /auth/dev-login."""
from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.errors import BadRequestError, UnauthenticatedError
from app.modules.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshResponse,
    TokenPayload,
    UserOut,
)
from app.modules.auth.service import AuthService, auth_service_for
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(request: Request, db: AsyncSession) -> AuthService:
    return AuthService(db, request.app.state.settings)


@router.post("/dev-login", response_model=AccessTokenResponse, summary="Dev login (no Google required)")
async def dev_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    settings = request.app.state.settings
    if not settings.dev_login_enabled:
        raise BadRequestError("Dev login is disabled.")
    service = _service(request, db)
    user = await service.get_or_create_user(email=body.email, full_name=body.full_name or body.email.split("@")[0])
    access, ttl = service.mint_access_token(user)
    refresh = await service.mint_refresh_token(user.id)
    service.set_refresh_cookie(response, refresh)
    await db.commit()
    return AccessTokenResponse(access_token=access, expires_in=ttl, user=service.user_to_dto(user))


@router.get("/google")
async def google_login(request: Request) -> RedirectResponse:
    settings = request.app.state.settings
    if not settings.google_client_id:
        # In dev, route to dev-login helper page (frontend)
        return RedirectResponse(url=f"{settings.next_public_api_base_url.replace(':8000', ':3000')}/login?google_not_configured=1", status_code=302)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": uuid.uuid4().hex,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Real Google OAuth — stub if creds missing (uses id_token claim). For dev we let the FE
    bounce to /auth/dev-login. This endpoint exists for production compliance."""
    settings = request.app.state.settings
    if not settings.google_client_id or not code:
        # Fall back: redirect to frontend dev login
        return RedirectResponse(url=f"{settings.next_public_api_base_url.replace(':8000', ':3000')}/login", status_code=302)
    # For the MVP we keep the real Google path mocked at the dev_login step; production
    # deployments can wire a proper Google token exchange here.
    raise BadRequestError("Google OAuth not yet wired in MVP. Use /auth/dev-login for development.")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshResponse:
    service = _service(request, db)
    token = request.cookies.get("refresh")
    if not token:
        raise UnauthenticatedError("Missing refresh cookie.")
    user_id, new_token = await service.rotate_refresh(token)
    from app.models.user import User as UserModel
    user = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()
    if not user:
        raise UnauthenticatedError("User not found.")
    access, ttl = service.mint_access_token(user)
    service.set_refresh_cookie(response, new_token)
    return RefreshResponse(access_token=access, expires_in=ttl)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    service = _service(request, db)
    token = request.cookies.get("refresh")
    if token:
        await service.revoke_family(token)
    service.clear_refresh_cookie(response)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def auth_me(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    from app.models.user import User as UserModel
    db_user = (await db.execute(select(UserModel).where(UserModel.id == user.sub))).scalar_one_or_none()
    if not db_user:
        raise UnauthenticatedError("User no longer exists.")
    return UserOut(id=db_user.id, email=db_user.email, full_name=db_user.full_name, avatar_url=db_user.avatar_url)
