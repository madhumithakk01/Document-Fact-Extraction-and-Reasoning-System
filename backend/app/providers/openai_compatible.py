"""Shared implementation for OpenAI-compatible chat-completions endpoints.

Groq's hosted API and most frontier keys expose the same ``/chat/completions``
contract, so both providers are thin configurations of this class.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ProviderError,
)


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
    ) -> None:
        if require_key and not api_key:
            raise ProviderError(f"{name} provider selected but no API key configured")
        self.name = name
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
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

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.post("/chat/completions", json=self._payload(request))
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} transport error: {exc}") from exc
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
