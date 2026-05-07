import time
from typing import Callable, TypeVar

import requests


DEFAULT_REQUEST_TIMEOUT = 15
DEFAULT_FETCH_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 1.0

T = TypeVar("T")

_original_session_request = requests.sessions.Session.request
_installed = False
_default_timeout_seconds = DEFAULT_REQUEST_TIMEOUT


def install_default_timeout(timeout_seconds: int | float = DEFAULT_REQUEST_TIMEOUT) -> None:
    """Apply a default timeout to requests calls that omit one."""
    global _default_timeout_seconds, _installed

    if timeout_seconds is None or timeout_seconds <= 0:
        return

    _default_timeout_seconds = timeout_seconds

    if _installed:
        return

    def request_with_default_timeout(self, method, url, **kwargs):
        kwargs.setdefault("timeout", _default_timeout_seconds)
        return _original_session_request(self, method, url, **kwargs)

    requests.sessions.Session.request = request_with_default_timeout
    _installed = True


def fetch_with_retries(
    operation: Callable[[], T],
    *,
    retries: int = DEFAULT_FETCH_RETRIES,
    delay_seconds: int | float = DEFAULT_RETRY_DELAY_SECONDS,
) -> T:
    attempts = max(0, retries) + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(delay_seconds * attempt)

    assert last_error is not None
    raise last_error


def format_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__
