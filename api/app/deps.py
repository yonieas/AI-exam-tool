"""FastAPI dependency helpers."""
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.auth.service import AuthService
from app.modules.auth.schemas import TokenPayload
from app.errors import UnauthenticatedError

security = HTTPBearer(auto_error=False)


def _make_auth_service() -> AuthService:
    """Standalone helper — settings are read once at call time."""
    from app.config import get_settings
    return AuthService(session=None, settings=get_settings())


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> TokenPayload | None:
    if not credentials:
        return None
    try:
        return _make_auth_service().verify_access_token(credentials.credentials)
    except Exception:
        return None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> TokenPayload:
    if not credentials:
        raise UnauthenticatedError("Missing authentication.")
    try:
        return _make_auth_service().verify_access_token(credentials.credentials)
    except Exception:
        raise UnauthenticatedError("Invalid or expired token.")


CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]
OptionalUser = Annotated[TokenPayload | None, Depends(get_current_user_optional)]
