"""Local Ollama provider. Same interface as the hosted path, zero external
dependency, slower. Selected with ``LLM_PROVIDER=ollama``."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ProviderError,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        default_temperature: float,
        default_max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "options": {
                "temperature": (
                    request.temperature
                    if request.temperature is not None
                    else self._default_temperature
                ),
                "num_predict": request.max_tokens or self._default_max_tokens,
            },
        }
        if request.stop:
            payload["options"]["stop"] = request.stop
        if request.json_schema is not None:
            # Ollama accepts a JSON Schema directly in the `format` field.
            payload["format"] = request.json_schema
        return payload

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.post("/api/chat", json=self._payload(request))
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama transport error: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"ollama returned {response.status_code}: {response.text[:300]}")
        body = response.json()
        try:
            return CompletionResult(
                text=body["message"]["content"] or "",
                model=body.get("model", self._model),
                provider=self.name,
                prompt_tokens=body.get("prompt_eval_count"),
                completion_tokens=body.get("eval_count"),
                finish_reason=body.get("done_reason"),
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"ollama malformed response: {body}") from exc

    async def health_check(self) -> bool:
        try:
            tags = await self._client.get("/api/tags")
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama unreachable: {exc}") from exc
        if tags.status_code >= 400:
            raise ProviderError(f"ollama /api/tags returned {tags.status_code}")
        available = {m.get("name", "").split(":")[0] for m in tags.json().get("models", [])}
        if available and self._model.split(":")[0] not in available:
            raise ProviderError(
                f"ollama model {self._model!r} not pulled; run: ollama pull {self._model}"
            )
        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def parse_json(text: str) -> Any:
        return json.loads(text)
