from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ..domain import validate_domain_asset
from .adapters import DirectorAdapter


@dataclass
class GenerationResult:
    model: BaseModel
    validation_errors: list[dict[str, Any]]


class AssetGenerationError(RuntimeError):
    def __init__(
        self,
        kind: str,
        validation_errors: list[dict[str, Any]],
        last_payload: dict[str, Any],
    ) -> None:
        super().__init__(f"{kind} generation failed schema validation")
        self.kind = kind
        self.validation_errors = validation_errors
        self.last_payload = last_payload


def _normalize_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        raise TypeError("Director output must be a JSON object")
    return parsed


def _validation_details(error: Exception, attempt: int) -> list[dict[str, Any]]:
    if isinstance(error, ValidationError):
        return [
            {
                "attempt": attempt,
                "location": [str(part) for part in item["loc"]],
                "type": item["type"],
                "message": item["msg"],
            }
            for item in error.errors(include_url=False)
        ]
    return [
        {
            "attempt": attempt,
            "location": [],
            "type": error.__class__.__name__,
            "message": str(error),
        }
    ]


def generate_validated_asset(
    adapter: DirectorAdapter,
    kind: str,
    context: dict[str, Any],
    *,
    retry_attempts: int,
) -> GenerationResult:
    validation_errors: list[dict[str, Any]] = []
    last_payload: dict[str, Any] = {}
    previous_raw: Any = None
    for attempt in range(1, retry_attempts + 2):
        try:
            if attempt == 1:
                raw = adapter.generate(kind, context)
            else:
                raw = adapter.repair(
                    kind,
                    previous_raw,
                    validation_errors,
                    context,
                )
            previous_raw = raw
            payload = _normalize_output(raw)
            last_payload = payload
            model = validate_domain_asset(kind, payload, context)
            return GenerationResult(
                model=model,
                validation_errors=validation_errors,
            )
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
            previous_raw = locals().get("raw", previous_raw)
            if isinstance(previous_raw, dict):
                last_payload = previous_raw
            elif previous_raw is not None:
                last_payload = {"raw_output": str(previous_raw)[:10_000]}
            validation_errors.extend(_validation_details(error, attempt))
    raise AssetGenerationError(kind, validation_errors, last_payload)
