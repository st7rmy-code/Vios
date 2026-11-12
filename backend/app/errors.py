"""Ошибки API в формате {detail: "текст на русском", code: "машинный_код"} (спецификация, 5.5)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "file_too_large",
    422: "validation_error",
}


class ErrorOut(BaseModel):
    detail: str
    code: str


class ApiError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str | None = None, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or DEFAULT_CODES.get(status_code, "error")


def _field_label(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts)


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = getattr(exc, "code", None) or DEFAULT_CODES.get(exc.status_code, "error")
        detail = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        return JSONResponse({"detail": detail, "code": code}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        text = "; ".join(
            f"{_field_label(e.get('loc', ()))}: {e.get('msg', '')}".strip(": ") for e in errors[:5]
        )
        return JSONResponse(
            {"detail": f"Проверьте поля: {text}", "code": "validation_error",
             "errors": [{"field": _field_label(e.get("loc", ())), "message": e.get("msg", "")} for e in errors]},
            status_code=422,
        )


ERROR_RESPONSES = {
    s: {"model": ErrorOut, "description": d}
    for s, d in {401: "Нужен вход", 403: "Недостаточно прав", 404: "Не найдено", 409: "Конфликт состояния",
                 422: "Ошибка в данных"}.items()
}
