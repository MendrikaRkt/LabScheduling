"""Security utilities: input validation, sanitization and rate limiting.

These helpers are intentionally dependency-free (standard library only) so they
work in any deployment target (Streamlit Cloud, Docker, bare metal). They guard
the boundaries where untrusted input enters the application: uploaded file
names, free-text fields and numeric parameters coming from the UI.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import PurePath
from typing import Deque, Dict

from infrastructure.errors import ValidationError

# Allowed spreadsheet extensions for uploads.
ALLOWED_UPLOAD_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# Hard upper bound on uploaded file size (bytes). 25 MB by default.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


# --- Text sanitization -------------------------------------------------------
def sanitize_text(value: str, max_length: int = 500) -> str:
    """Strip control characters, normalize unicode and bound the length.

    Does not alter legitimate content (accents, Spanish names) but removes
    control characters that could be used for log injection or display issues.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHARS_RE.sub("", value)
    value = value.strip()
    if len(value) > max_length:
        value = value[:max_length]
    return value


def sanitize_filename(filename: str) -> str:
    """Return a safe base file name (prevents path traversal).

    Keeps only the final path component and replaces unsafe characters.
    """
    if not filename:
        raise ValidationError("Empty file name", "Please provide a valid file name.")
    # Keep only the final component to defeat path traversal (../, absolute).
    base = PurePath(filename.replace("\\", "/")).name
    safe = _SAFE_FILENAME_RE.sub("_", base).strip("._") or "file"
    return safe


# --- File validation ---------------------------------------------------------
def validate_upload(filename: str, size_bytes: int | None = None) -> str:
    """Validate an uploaded file and return its sanitized name.

    Raises:
        ValidationError: if the extension is not allowed or the file is too big.
    """
    safe = sanitize_filename(filename)
    suffix = PurePath(safe).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise ValidationError(
            f"Disallowed extension: {suffix}",
            f"Unsupported file type. Allowed types: {allowed}.")
    if size_bytes is not None and size_bytes > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(
            f"File too large: {size_bytes} bytes",
            f"The file is too large. Maximum allowed size is {mb} MB.")
    return safe


# --- Numeric validation ------------------------------------------------------
def validate_int(value, name: str, minimum: int | None = None,
                maximum: int | None = None) -> int:
    """Validate and coerce an integer within optional bounds."""
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{name} is not an integer: {value!r}",
            f"{name} must be a whole number.")
    if minimum is not None and ivalue < minimum:
        raise ValidationError(
            f"{name} below minimum {minimum}: {ivalue}",
            f"{name} must be at least {minimum}.")
    if maximum is not None and ivalue > maximum:
        raise ValidationError(
            f"{name} above maximum {maximum}: {ivalue}",
            f"{name} must be at most {maximum}.")
    return ivalue


# --- Rate limiting -----------------------------------------------------------
class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Limits the number of allowed actions per key within a time window. Intended
    to throttle expensive operations (such as launching the solver) per user
    session in production.
    """

    def __init__(self, max_calls: int, period_seconds: float):
        if max_calls <= 0 or period_seconds <= 0:
            raise ValueError("max_calls and period_seconds must be positive")
        self.max_calls = max_calls
        self.period = period_seconds
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str = "global") -> bool:
        """Return True if the action is allowed, recording it if so."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - self.period
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.max_calls:
                return False
            events.append(now)
            return True

    def retry_after(self, key: str = "global") -> float:
        """Seconds to wait before the next call would be allowed (0 if now)."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            if len(events) < self.max_calls or not events:
                return 0.0
            return max(0.0, self.period - (now - events[0]))
