"""Error handling middleware."""

from typing import Callable
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def add_error_handlers(app: FastAPI) -> None:
    """
    Add custom error handlers to FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handle validation errors (422).

        Args:
            request: HTTP request
            exc: Validation error

        Returns:
            JSON response with error details
        """
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": exc.errors(),
                "body": exc.body if hasattr(exc, "body") else None,
            }
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(
        request: Request,
        exc: IntegrityError
    ) -> JSONResponse:
        """
        Handle database integrity errors (409).

        Args:
            request: HTTP request
            exc: Integrity error

        Returns:
            JSON response with error details
        """
        # Check for unique constraint violations
        error_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)

        if "UNIQUE constraint failed" in error_msg or "duplicate key" in error_msg.lower():
            detail = "A record with this value already exists"

            # Extract field name if possible
            if "username" in error_msg.lower():
                detail = "Username already exists"
            elif "email" in error_msg.lower():
                detail = "Email already exists"

            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": detail}
            )

        # Generic integrity error
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Database integrity error"}
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        request: Request,
        exc: SQLAlchemyError
    ) -> JSONResponse:
        """
        Handle generic SQLAlchemy errors (500).

        Args:
            request: HTTP request
            exc: SQLAlchemy error

        Returns:
            JSON response with error details
        """
        # Don't expose internal database errors in production
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """
        Handle all other exceptions (500).

        Args:
            request: HTTP request
            exc: Exception

        Returns:
            JSON response with error details
        """
        # Don't expose internal errors in production
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )
