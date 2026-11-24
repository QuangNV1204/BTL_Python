
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.shared.error.codes import ErrorCode, default_message, status_of
from app.shared.error.exceptions import ApiException, StorageException
from app.shared.error.request_id import current_request_id

logger = logging.getLogger("learningai.errors")


def _body(
    code: ErrorCode,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code.value, "message": message}
    if details:
        payload["details"] = details
    request_id = current_request_id()
    if request_id is not None:
        payload["request_id"] = request_id
    return payload


def _response(code: ErrorCode, message: str | None = None,
              details: list[dict[str, str]] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_of(code),
        content=_body(code, message or default_message(code), details),
    )


_ERROR_CODE_BY_NAME = {item.value: item for item in ErrorCode}


def api_error_response(exc: ApiException) -> JSONResponse:
    details = [item.to_json() for item in exc.details] if exc.details else None
    return _response(exc.code, exc.message, details)


def _detail_for(error: dict[str, Any]) -> dict[str, str]:
    loc = [part for part in error.get("loc", ()) if part not in ("body", "query", "path")]
    field_name = ".".join(str(part) for part in loc) or "body"
    return {"field": field_name, "message": error.get("msg", "Invalid value")}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def _api_exception(_: Request, exc: ApiException) -> JSONResponse:
        details = [item.to_json() for item in exc.details] if exc.details else None
        return _response(exc.code, exc.message, details)

    @app.exception_handler(StorageException)
    async def _storage(_: Request, exc: StorageException) -> JSONResponse:
        logger.error("Storage failure", exc_info=exc)
        return _response(ErrorCode.UNCATEGORIZED_EXCEPTION)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _response(
            ErrorCode.VALIDATION_ERROR,
            default_message(ErrorCode.VALIDATION_ERROR),
            [_detail_for(error) for error in exc.errors()],
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _response(ErrorCode.NOT_FOUND)
        if exc.status_code == 413:
            return _response(ErrorCode.FILE_TOO_LARGE)
        if exc.status_code == 405:

            return _response(ErrorCode.FORBIDDEN)
        if 400 <= exc.status_code < 500:
            return _response(
                ErrorCode.VALIDATION_ERROR,
                exc.detail if isinstance(exc.detail, str) else None,
            )
        logger.error("Unhandled HTTP failure: %s", exc.detail, exc_info=exc)
        return _response(ErrorCode.UNCATEGORIZED_EXCEPTION)

    @app.exception_handler(ClientDisconnect)
    async def _disconnect(_: Request, __: ClientDisconnect) -> JSONResponse:
        return _response(ErrorCode.VALIDATION_ERROR, "Client disconnected")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled request failure", exc_info=exc)
        return _response(ErrorCode.UNCATEGORIZED_EXCEPTION)
