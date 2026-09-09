"""Shared implementation for OpenAI-compatible chat-completions endpoints.

Groq's hosted API and most frontier keys expose the same ``/chat/completions``
contract, so both providers are thin configurations of this class.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)
from app.providers.observability import RetryNotice, notify_retry

logger = logging.getLogger(__name__)

_RETRY_AFTER_IN_BODY = re.compile(r"try again in ([\d.]+)s", re.I)
_MAX_BACKOFF_SECONDS = 60.0


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        default_temperature: float,
        default_max_tokens: int,
        timeout_seconds: float,
        require_key: bool = True,
        max_retries: int = 5,
        max_concurrency: int = 1,
        min_request_interval: float = 0.0,
    ) -> None:
        if require_key and not api_key:
            raise ProviderError(f"{name} provider selected but no API key configured")
        self.name = name
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._max_retries = max_retries
        # keep within a free-tier tokens-per-minute budget: cap in-flight
        # requests and space them out so a burst of parallel calls does not
        # instantly blow the limit
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._min_interval = max(0.0, min_request_interval)
        self._last_request_at = 0.0
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout_seconds,
        )

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self._default_temperature
            ),
            "max_tokens": request.max_tokens or self._default_max_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": request.json_schema,
                    "strict": True,
                },
            }
        return payload

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("retry-after")
        if header:
            try:
                return min(float(header), _MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        match = _RETRY_AFTER_IN_BODY.search(response.text)
        if match:
            return min(float(match.group(1)) + 0.5, _MAX_BACKOFF_SECONDS)
        return min(2.0**attempt, _MAX_BACKOFF_SECONDS)

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        now = asyncio.get_event_loop().time()
        wait = self._last_request_at + self._min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_at = asyncio.get_event_loop().time()

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        async with self._semaphore:
            await self._pace()
            return await self._complete_once(request)

    async def _complete_once(self, request: CompletionRequest) -> CompletionResult:
        payload = self._payload(request)
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2.0**attempt, _MAX_BACKOFF_SECONDS))
                    continue
                raise ProviderTimeoutError(f"{self.name} timed out: {exc}") from exc
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2.0**attempt, _MAX_BACKOFF_SECONDS))
                    continue
                raise ProviderError(f"{self.name} transport error: {exc}") from exc

            transient = response.status_code == 429 or response.status_code >= 500
            if transient and attempt < self._max_retries:
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "%s %d, retrying in %.1fs (attempt %d/%d)",
                    self.name,
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await notify_retry(
                    RetryNotice(
                        provider=self.name,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        max_attempts=self._max_retries,
                        delay_seconds=delay,
                    )
                )
                await asyncio.sleep(delay)
                continue
            break

        if response.status_code == 429:
            raise RateLimitError(
                f"{self.name} rate limited after {self._max_retries} retries: "
                f"{response.text[:300]}"
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"{self.name} rejected credentials ({response.status_code}): "
                f"{response.text[:300]}"
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} returned {response.status_code}: {response.text[:300]}"
            )
        body = response.json()
        try:
            choice = body["choices"][0]
            usage = body.get("usage") or {}
            return CompletionResult(
                text=choice["message"]["content"] or "",
                model=body.get("model", self._model),
                provider=self.name,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                finish_reason=choice.get("finish_reason"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} malformed response: {body}") from exc

    async def health_check(self) -> bool:
        result = await self.complete(
            CompletionRequest(
                system="You are a health probe.",
                user="Reply with the single word: ok",
                max_tokens=5,
            )
        )
        if "ok" not in result.text.lower():
            raise ProviderError(f"{self.name} health check unexpected reply: {result.text!r}")
        return True

    async def aclose(self) -> None:
        await self._client.aclose()
