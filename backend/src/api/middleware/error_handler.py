from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas.errors import ErrorBody, ErrorResponse
from domain.errors import DomainError, EntityNotFoundError, ForbiddenError, InfrastructureError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(_: Request, exc: EntityNotFoundError) -> JSONResponse:
        return _error_response(404, "NOT_FOUND", str(exc))

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(403, "FORBIDDEN", str(exc))

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return _error_response(400, "BAD_REQUEST", str(exc))

    @app.exception_handler(InfrastructureError)
    async def infrastructure_error_handler(_: Request, exc: InfrastructureError) -> JSONResponse:
        return _error_response(502, "UPSTREAM_ERROR", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(part) for part in err["loc"][1:]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _error_response(
            422,
            "VALIDATION_ERROR",
            "Request body validation failed.",
            details={"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _status_to_code(exc.status_code)
        message = str(exc.detail) if exc.detail else "Request failed"
        if isinstance(exc.detail, dict):
            message = str(exc.detail.get("message", message))
        return _error_response(exc.status_code, code, message)


def _status_to_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "UPSTREAM_ERROR",
    }
    return mapping.get(status_code, "INTERNAL_ERROR")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=body.model_dump())
