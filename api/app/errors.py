"""Error types and RFC 7807 exception handler."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    code: str = "INTERNAL"
    status: int = 500
    title: str = "Internal Server Error"

    def __init__(self, detail: str = "", *, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors or []


class UnauthenticatedError(AppError):
    code = "UNAUTHENTICATED"
    status = 401
    title = "Unauthenticated"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status = 403
    title = "Forbidden"


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status = 404
    title = "Not Found"


class ConflictError(AppError):
    code = "CONFLICT"
    status = 409
    title = "Conflict"


class ValidationError(AppError):
    code = "VALIDATION"
    status = 422
    title = "Validation Error"


class QuotaExceededError(AppError):
    code = "QUOTA_EXCEEDED"
    status = 429
    title = "Quota Exceeded"


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    status = 429
    title = "Rate Limited"


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status = 400
    title = "Bad Request"


def _problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    request: Request,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    body: dict[str, Any] = {
        "type": f"https://errors.example.com/{code.lower()}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": str(request.url.path),
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json", headers={"X-Request-Id": request_id})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(status=exc.status, code=exc.code, title=exc.title, detail=exc.detail, request=request, errors=exc.errors)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": e.get("msg", ""), "type": e.get("type")}
            for e in exc.errors()
        ]
        return _problem(
            status=422,
            code="VALIDATION",
            title="Validation Error",
            detail="Request validation failed.",
            request=request,
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:  # noqa: BLE001
        return _problem(status=500, code="INTERNAL", title="Internal Server Error", detail="An unexpected error occurred.", request=request)
