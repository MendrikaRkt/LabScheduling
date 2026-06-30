"""Application error types and user-friendly error handling.

Defines a small hierarchy of domain-aware exceptions and a helper that maps any
exception to a safe, user-friendly message. Internal details are logged (with
stack traces) but never shown to end users, which avoids leaking sensitive
information in production.
"""
from __future__ import annotations

import functools
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AppError(Exception):
    """Base class for expected application errors.

    The ``user_message`` is safe to display to end users; ``args[0]`` keeps the
    technical message for logs.
    """

    user_message = "An unexpected error occurred. Please try again."

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        if user_message:
            self.user_message = user_message


class ConfigurationError(AppError):
    user_message = "The configuration is invalid. Please check config.yaml."


class ValidationError(AppError):
    user_message = "Some inputs are invalid. Please review and try again."


class DataIngestionError(AppError):
    user_message = "The input file could not be read. Please check its format."


class SolverError(AppError):
    user_message = "The scheduler could not produce a solution for these inputs."


def friendly_message(exc: Exception) -> str:
    """Return a safe, user-facing message for any exception."""
    if isinstance(exc, AppError):
        return exc.user_message
    if isinstance(exc, FileNotFoundError):
        return "A required file was not found. Please check the file path."
    if isinstance(exc, (ValueError, KeyError)):
        return "Some inputs are invalid. Please review and try again."
    return "An unexpected error occurred. Please try again later."


def handle_errors(default_user_message: str | None = None) -> Callable:
    """Decorator that logs exceptions and re-raises them as ``AppError``.

    Keeps the technical detail in the logs while ensuring callers only ever see
    a safe, user-friendly message.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except AppError:
                raise
            except Exception as exc:
                logger.exception("Error in %s: %s", func.__name__, exc)
                msg = default_user_message or friendly_message(exc)
                raise AppError(str(exc), user_message=msg) from exc

        return wrapper

    return decorator
