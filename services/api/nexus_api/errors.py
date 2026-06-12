from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_payload(
    code: str,
    message: str,
    *,
    details: Any | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    if request_id:
        payload["request_id"] = request_id
    return payload


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            error_payload(
                code,
                message,
                details=details,
                request_id=request_id,
            )
        ),
        headers=headers,
    )


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_payload(code, message, details=details)["error"],
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
        details = detail.get("details")
    else:
        code = _default_code_for_status(exc.status_code)
        message = str(detail)
        details = None

    return error_response(
        exc.status_code,
        code,
        message,
        details=details,
        request_id=_request_id(request),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return error_response(
        422,
        "validation_error",
        "Request validation failed",
        details=exc.errors(),
        request_id=_request_id(request),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        500,
        "internal_server_error",
        "Internal server error",
        request_id=_request_id(request),
    )


def _default_code_for_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        429: "rate_limited",
    }.get(status_code, "http_error")


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id")
