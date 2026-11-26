from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class FaktSureError(Exception):
    """Base exception for expected FaktSure domain errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(FaktSureError):
    """Raised when a requested entity does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, 404)


class ConflictError(FaktSureError):
    """Raised when an operation conflicts with existing state."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 409)


class ServiceUnavailableError(FaktSureError):
    """Raised when a required external dependency is unavailable."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 503)


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent JSON handlers for API exceptions."""

    @app.exception_handler(FaktSureError)
    async def fakt_sure_error_handler(_request: Request, exc: FaktSureError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
