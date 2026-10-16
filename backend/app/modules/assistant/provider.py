"""Bounded, local-only Ollama HTTP adapter. Never logs prompts or response bodies."""

import json
import math

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.core.errors import BusinessException
from app.modules.assistant.schemas import ModelAnswer
from app.schemas.errors import ErrorCode

MAX_RESPONSE_BYTES = 1_048_576


class Ollama:
    def __init__(self, config: Settings, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.transport = transport

    def _request(
        self, method: str, path: str, body: dict | None = None, timeout: float | None = None
    ) -> dict:
        try:
            with httpx.Client(
                base_url=self.config.assistant_ollama_url,
                timeout=httpx.Timeout(timeout or self.config.assistant_timeout_seconds, connect=5),
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client, client.stream(method, path, json=body) as response:
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise ValueError("Oversized provider response")
            result = json.loads(payload)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("Malformed provider response")
            return result
        except httpx.TimeoutException:
            raise BusinessException(ErrorCode.ASSISTANT_TIMEOUT) from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise BusinessException(ErrorCode.ASSISTANT_UNAVAILABLE) from None

    def available_models(self) -> set[str]:
        payload = self._request("GET", "/api/tags", timeout=3)
        models = payload.get("models")
        if not isinstance(models, list):
            raise BusinessException(ErrorCode.ASSISTANT_UNAVAILABLE)
        return {row["name"] for row in models
                if isinstance(row, dict) and isinstance(row.get("name"), str)}

    def chat(self, messages: list[dict[str, str]]) -> ModelAnswer:
        payload = self._request("POST", "/api/chat", {
            "model": self.config.assistant_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": ModelAnswer.model_json_schema(),
            "keep_alive": "5m",
            "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 700},
        })
        try:
            if payload.get("done") is not True or payload.get("done_reason") == "length":
                raise ValueError("Incomplete generation")
            answer = ModelAnswer.model_validate_json(payload["message"]["content"])
            if not answer.answer.strip():
                raise ValueError("Blank answer")
            return answer
        except (KeyError, TypeError, ValueError, ValidationError):
            raise BusinessException(ErrorCode.ASSISTANT_INVALID_RESPONSE) from None

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = self._request("POST", "/api/embed", {
            "model": self.config.assistant_embedding_model,
            "input": texts,
            "truncate": False,
            "keep_alive": "5m",
        })
        try:
            vectors = payload["embeddings"]
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("Embedding count mismatch")
            normalized = []
            dimensions = None
            for vector in vectors:
                if not isinstance(vector, list) or not 32 <= len(vector) <= 4096:
                    raise ValueError("Invalid embedding dimension")
                numbers = [float(value) for value in vector]
                if not all(math.isfinite(value) for value in numbers):
                    raise ValueError("Invalid embedding values")
                norm = math.sqrt(sum(value * value for value in numbers))
                if not norm or dimensions not in {None, len(numbers)}:
                    raise ValueError("Invalid embedding shape")
                dimensions = len(numbers)
                normalized.append([value / norm for value in numbers])
            return normalized
        except (KeyError, ValueError, TypeError, OverflowError):
            raise BusinessException(ErrorCode.ASSISTANT_INVALID_RESPONSE) from None
