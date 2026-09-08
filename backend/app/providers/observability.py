"""A task-local hook for reporting provider retries to whoever started the work.

The LLM provider is a process-wide singleton and knows nothing about documents.
When it backs off on a rate limit, it calls :func:`notify_retry`; a caller such
as the document pipeline installs an observer with :func:`set_retry_observer`
(a :class:`contextvars.ContextVar`, so concurrent tasks each see their own) to
turn that into a visible "rate limited, retrying 3/5" status.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetryNotice:
    provider: str
    status_code: int
    attempt: int
    max_attempts: int
    delay_seconds: float


RetryObserver = Callable[[RetryNotice], Awaitable[None]]

_retry_observer: ContextVar[RetryObserver | None] = ContextVar("retry_observer", default=None)


def set_retry_observer(observer: RetryObserver | None) -> Token[RetryObserver | None]:
    return _retry_observer.set(observer)


def reset_retry_observer(token: Token[RetryObserver | None]) -> None:
    _retry_observer.reset(token)


async def notify_retry(notice: RetryNotice) -> None:
    observer = _retry_observer.get()
    if observer is None:
        return
    try:
        await observer(notice)
    except Exception:  # noqa: BLE001 - a broken observer must not derail a retry
        logger.debug("retry observer failed", exc_info=True)
