from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx


class ProviderRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class OpenAIResponsesClient:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: int,
        http_retries: int,
        api_style: str = "responses",
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_retries = http_retries
        self._api_style = api_style
        self._transport = transport
        self._sleeper = sleeper

    def create_structured(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        if self._api_style == "chat_completions":
            endpoint = f"{self._base_url}/chat/completions"
            request_body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
        elif self._api_style == "responses":
            endpoint = f"{self._base_url}/responses"
            request_body = {
                "model": model,
                "instructions": instructions,
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                    "verbosity": "low",
                },
                "reasoning": {"effort": "low"},
                "store": False,
            }
        else:
            raise ProviderRequestError(
                f"Unsupported LLM API style: {self._api_style}"
            )
        response_data: dict[str, Any] | None = None
        for attempt in range(self._http_retries + 1):
            try:
                with httpx.Client(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = client.post(
                        endpoint,
                        headers={
                            "authorization": f"Bearer {self._api_key}",
                            "content-type": "application/json",
                        },
                        json=request_body,
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self._http_retries:
                        retry_after = response.headers.get("retry-after")
                        delay = (
                            min(float(retry_after), 5)
                            if retry_after
                            else min(0.5 * (2**attempt), 4)
                        )
                        self._sleeper(delay)
                        continue
                    raise ProviderRequestError(
                        f"Provider request failed after retries ({response.status_code})",
                        status_code=response.status_code,
                        retryable=True,
                    )
                if response.status_code >= 400:
                    raise ProviderRequestError(
                        f"Provider rejected request ({response.status_code})",
                        status_code=response.status_code,
                        retryable=False,
                    )
                response_data = response.json()
                break
            except httpx.TimeoutException as error:
                if attempt < self._http_retries:
                    self._sleeper(min(0.5 * (2**attempt), 4))
                    continue
                raise ProviderRequestError(
                    "Provider request timed out",
                    retryable=True,
                ) from error
            except (httpx.HTTPError, json.JSONDecodeError) as error:
                raise ProviderRequestError(
                    f"Provider response transport error: {error.__class__.__name__}",
                    retryable=False,
                ) from error
        if response_data is None:
            raise ProviderRequestError("Provider returned no response")
        output_text = response_data.get("output_text")
        if self._api_style == "chat_completions":
            try:
                output_text = response_data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                output_text = None
        if not output_text:
            for item in response_data.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        output_text = content["text"]
                        break
                if output_text:
                    break
        if not isinstance(output_text, str):
            raise ProviderRequestError("Provider returned no structured output text")
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as error:
            raise ProviderRequestError(
                "Provider returned malformed structured output",
            ) from error
        if not isinstance(parsed, dict):
            raise ProviderRequestError("Provider structured output must be an object")
        return parsed
