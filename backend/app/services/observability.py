from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


logger = logging.getLogger("emotion_director")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

_PROJECT_PATH = re.compile(r"/projects?/([0-9a-fA-F-]{36})(?:/|$)")
_SENSITIVE = re.compile(
    r"(?i)(bearer\s+)[^\s,;]+|"
    r"\bsk-[A-Za-z0-9_-]{8,}\b|"
    r"((?:api[_-]?key|token|password|authorization)\s*[=:]\s*)[^\s,;]+|"
    r"(postgres(?:ql)?://[^:\s]+:)[^@\s]+@"
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(
                r"(?i)(?:^|_)(?:api_?key|secret|token|password|authorization)(?:$|_)",
                key,
            )
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    return _SENSITIVE.sub(
        lambda match: (
            f"{match.group(1)}[REDACTED]"
            if match.group(1)
            else "[REDACTED]"
        ),
        value,
    )


def public_error(error: Exception, fallback: str) -> str:
    sanitized = str(redact(str(error))).strip()
    if not sanitized:
        return fallback
    return sanitized[:500]


def log_event(
    event: str,
    *,
    project_id: str | None = None,
    job_id: str | None = None,
    provider: str | None = None,
    **fields: Any,
) -> None:
    record = {
        "timestamp": time.time(),
        "level": "info",
        "event": event,
        "project_id": project_id,
        "job_id": job_id,
        "provider": provider,
        **fields,
    }
    logger.info(json.dumps(redact(record), ensure_ascii=False, separators=(",", ":")))


class StructuredRequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or uuid4().hex
        match = _PROJECT_PATH.search(request.url.path)
        project_id = match.group(1) if match else None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            log_event(
                "http_request",
                project_id=project_id,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
