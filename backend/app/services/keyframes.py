from __future__ import annotations

import hashlib
import base64
import ipaddress
import io
import json
import re
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from ..config import Settings, get_settings
from ..domain import KeyframeResult, KeyframeTask
from .storage import MediaStorage


@dataclass(frozen=True)
class GeneratedKeyframe:
    content: bytes
    content_type: str
    width: int
    height: int
    provider: str
    model: str
    provider_task_id: str


class KeyframeImageAdapter(ABC):
    provider = "unknown"
    model = "unknown"
    fallback_reason: str | None = None

    @abstractmethod
    async def generate(self, *, shot_id: str, prompt: str) -> GeneratedKeyframe:
        raise NotImplementedError


class DemoKeyframeImageAdapter(KeyframeImageAdapter):
    """Deterministic SVG adapter used by demo mode and automated acceptance tests."""

    provider = "demo-keyframe"
    model = "deterministic-svg-v1"

    def __init__(
        self,
        fail_shot_ids: set[str] | None = None,
        fallback_reason: str | None = None,
    ) -> None:
        self.fail_shot_ids = fail_shot_ids or set()
        self.fallback_reason = fallback_reason

    async def generate(self, *, shot_id: str, prompt: str) -> GeneratedKeyframe:
        if shot_id in self.fail_shot_ids:
            raise RuntimeError(f"Mock provider rejected {shot_id}")
        width, height = 1280, 720
        digest = hashlib.sha256(f"{shot_id}:{prompt}".encode("utf-8")).hexdigest()
        accent = f"#{digest[:6]}"
        safe_prompt = escape(prompt[:180])
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="#071011"/><stop offset=".56" stop-color="#17373d"/><stop offset="1" stop-color="{accent}"/>
  </linearGradient>
</defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<circle cx="910" cy="250" r="165" fill="#e4ad59" fill-opacity=".18"/>
<path d="M0 590 Q250 470 470 565 T900 530 T1280 570 V720 H0Z" fill="#081615"/>
<path d="M120 565 L470 340 L850 560" fill="none" stroke="#8ca4a3" stroke-width="8" stroke-opacity=".62"/>
<g fill="none" stroke="#e4ad59" stroke-opacity=".42"><path d="M42 42h140M42 42v90M1238 42h-140M1238 42v90"/><path d="M42 678h140M42 678v-90M1238 678h-140M1238 678v-90"/></g>
<text x="58" y="95" fill="#e4ad59" font-family="monospace" font-size="30">{escape(shot_id)} · KEYFRAME</text>
<text x="58" y="635" fill="#d8d2c2" font-family="sans-serif" font-size="20">{safe_prompt}</text>
</svg>"""
        return GeneratedKeyframe(
            content=svg.encode("utf-8"),
            content_type="image/svg+xml",
            width=width,
            height=height,
            provider=self.provider,
            model=self.model,
            provider_task_id=f"demo:{shot_id}:{digest[:16]}",
        )


class OpenAIKeyframeImageAdapter(KeyframeImageAdapter):
    provider = "openai"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        api_key = settings.resolved_image_api_key
        if not api_key:
            raise ValueError("OpenAI image API key is not configured")
        self.api_key = api_key
        self.model = settings.image_model
        self.base_url = settings.resolved_image_base_url
        self.auth_style = settings.image_auth_style
        self.quality = settings.image_quality
        self.size = settings.image_size
        self.timeout = settings.image_timeout_seconds
        self.transport = transport

    async def generate(self, *, shot_id: str, prompt: str) -> GeneratedKeyframe:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers={
                    "Authorization": (
                        self.api_key
                        if self.auth_style == "raw"
                        else f"Bearer {self.api_key}"
                    ),
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "size": self.size,
                    "n": 1,
                },
            )
        if response.status_code >= 400:
            request_id = response.headers.get("x-request-id", "unknown")
            detail = sanitize_provider_error(
                RuntimeError(response.text[:500] or "empty response")
            )
            raise RuntimeError(
                f"OpenAI image request failed with HTTP {response.status_code}; "
                f"request_id={request_id}; detail={detail}"
            )
        try:
            payload = response.json()
            item = payload["data"][0]
            if item.get("b64_json"):
                content = base64.b64decode(item["b64_json"], validate=True)
            elif item.get("url"):
                image_url = _validated_remote_image_url(item["url"])
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    transport=self.transport,
                ) as image_client:
                    image_response = await image_client.get(image_url)
                    image_response.raise_for_status()
                    if len(image_response.content) > 25 * 1024 * 1024:
                        raise ValueError("generated image exceeds 25MB")
                    content = image_response.content
            else:
                raise KeyError("b64_json/url")
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            httpx.HTTPError,
        ) as error:
            raise RuntimeError("OpenAI image response did not contain valid image data") from error
        width, height = (int(part) for part in self.size.split("x", maxsplit=1))
        request_id = response.headers.get("x-request-id")
        return GeneratedKeyframe(
            content=content,
            content_type="image/png",
            width=width,
            height=height,
            provider=self.provider,
            model=self.model,
            provider_task_id=request_id or f"openai:{shot_id}:{uuid4().hex[:16]}",
        )


def _validated_remote_image_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("generated image URL must be a string")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("generated image URL must be an unauthenticated HTTPS URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        raise ValueError("generated image URL cannot target a private address")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".localhost"):
        raise ValueError("generated image URL cannot target localhost")
    return value


def get_keyframe_image_adapter(
    settings: Settings | None = None,
) -> KeyframeImageAdapter:
    resolved_settings = settings or get_settings()
    if resolved_settings.resolved_image_adapter_mode == "provider":
        if resolved_settings.resolved_image_api_key:
            return OpenAIKeyframeImageAdapter(resolved_settings)
        return DemoKeyframeImageAdapter(
            fallback_reason="Provider mode requested but IMAGE_API_KEY/OPENAI_API_KEY is missing"
        )
    if resolved_settings.resolved_image_adapter_mode == "demo":
        return DemoKeyframeImageAdapter()
    return DemoKeyframeImageAdapter(
        fallback_reason=(
            "Unsupported IMAGE_ADAPTER_MODE: "
            f"{resolved_settings.resolved_image_adapter_mode}"
        )
    )


def build_keyframe_prompt(
    *,
    shot: dict[str, Any],
    world: dict[str, Any],
    character: dict[str, Any],
) -> str:
    selected_references = [
        {
            "id": reference.get("id"),
            "framing": reference.get("framing"),
            "storage_path": reference.get("storage_path"),
        }
        for reference in character.get("reference_images", [])
        if reference.get("selected")
    ]
    prompt_context = {
        "shot": {
            "id": shot["id"],
            "size": shot["size"],
            "camera": shot["camera"],
            "action": shot["action"],
            "emotion": shot["emotion"],
            "prompt": shot["prompt"],
        },
        "world": {
            "name": world["name"],
            "visual_style": world["visual_style"],
            "palette": world["palette"],
            "lighting": world["lighting"],
            "immutable_rules": world["immutable_rules"],
            "mutable_state": world["mutable_state"],
        },
        "character": {
            "id": character["id"],
            "appearance": character["appearance"],
            "continuity_lock": character["continuity_lock"],
            "negative_constraints": character["negative_constraints"],
            "selected_references": selected_references,
        },
    }
    return (
        "Create one production keyframe. Preserve the supplied world rules, "
        "character identity and shot composition exactly. No text, watermark or "
        "unlisted character. CONTEXT:\n"
        + json.dumps(prompt_context, ensure_ascii=False, separators=(",", ":"))
    )


def source_snapshot(
    *,
    shot: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    versions = context["asset_versions"]
    return {
        "shots": versions["shots"],
        "world": versions["world"],
        "character": versions["character"],
        "shot_sha256": hashlib.sha256(
            json.dumps(shot, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def sanitize_provider_error(error: Exception) -> str:
    message = str(error)
    message = re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[:= ]+\S+", r"\1=[REDACTED]", message)
    message = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", message)
    return message[:1000] or "Keyframe provider failed"


async def generate_keyframe_task(
    *,
    project_id: str,
    shot: dict[str, Any],
    context: dict[str, Any],
    adapter: KeyframeImageAdapter,
    media_storage: MediaStorage,
    attempt: int = 1,
) -> KeyframeTask:
    prompt = build_keyframe_prompt(
        shot=shot,
        world=context["assets"]["world"],
        character=context["assets"]["character"],
    )
    pending_task_id = f"queued:{shot['id']}:{uuid4().hex[:16]}"
    source = source_snapshot(shot=shot, context=context)
    try:
        generated = await adapter.generate(shot_id=shot["id"], prompt=prompt)
        extension = {
            "image/svg+xml": "svg",
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
        }[generated.content_type]
        object_revision = uuid4().hex[:12]
        storage_path = await media_storage.put(
            (
                f"projects/{project_id}/keyframes/"
                f"{shot['id']}-a{attempt}-{object_revision}.{extension}"
            ),
            io.BytesIO(generated.content),
            content_type=generated.content_type,
        )
        result = KeyframeResult(
            storage_path=storage_path,
            content_type=generated.content_type,
            width=generated.width,
            height=generated.height,
            sha256=hashlib.sha256(generated.content).hexdigest(),
        )
        return KeyframeTask(
            shot_id=shot["id"],
            provider_task_id=generated.provider_task_id,
            status="succeeded",
            provider=generated.provider,
            model=generated.model,
            prompt=prompt,
            attempt=attempt,
            confirmed=False,
            result=result,
            source=source,
        )
    except Exception as error:  # provider failures belong in the persisted task
        return KeyframeTask(
            shot_id=shot["id"],
            provider_task_id=pending_task_id,
            status="failed",
            provider=adapter.provider,
            model=adapter.model,
            prompt=prompt,
            attempt=attempt,
            confirmed=False,
            error=sanitize_provider_error(error),
            source=source,
        )


def keyframe_progress(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(tasks), "queued": 0, "running": 0, "succeeded": 0, "failed": 0, "confirmed": 0}
    for task in tasks:
        status = str(task["status"])
        if status in counts:
            counts[status] += 1
        if task.get("confirmed"):
            counts["confirmed"] += 1
    return counts


def keyframe_consistency_warnings(
    *,
    payload: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    versions = context["asset_versions"]
    if payload["shots_asset_id"] != versions["shots"]["asset_id"]:
        warnings.append("关键帧基于旧的 ShotSet 版本，请重新生成未确认镜头。")
    for task in payload["tasks"]:
        if task["status"] == "failed":
            warnings.append(f"{task['shot_id']} 关键帧生成失败，可单独重试。")
        source = task.get("source", {})
        for kind in ("world", "character"):
            expected = source.get(kind, {})
            current = versions.get(kind, {})
            if expected.get("asset_id") and expected.get("asset_id") != current.get("asset_id"):
                warnings.append(f"{task['shot_id']} 使用了旧的 {kind} 资产。")
    return sorted(set(warnings))


def manifest_document(asset: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    payload = asset["payload"]
    tasks = []
    for task in payload["tasks"]:
        result = task.get("result")
        tasks.append(
            {
                "shot_id": task["shot_id"],
                "status": task["status"],
                "confirmed": bool(task.get("confirmed")),
                "provider_task_id": task["provider_task_id"],
                "provider": task["provider"],
                "model": task["model"],
                "attempt": task["attempt"],
                "prompt": task["prompt"],
                "error": task.get("error"),
                "file": (
                    f"keyframes/{task['shot_id']}.{_content_extension(result['content_type'])}"
                    if result
                    else None
                ),
                "sha256": result.get("sha256") if result else None,
                "source": task.get("source", {}),
            }
        )
    return {
        "schema": "ai-emotion-director/keyframes-manifest/v1",
        "project_id": str(asset["project_id"]),
        "project_name": str(context["project"]["name"]),
        "keyframe_asset_id": asset["id"],
        "keyframe_version": asset["version"],
        "shots_asset_id": payload["shots_asset_id"],
        "shots_version": payload["shots_version"],
        "progress": keyframe_progress(payload["tasks"]),
        "warnings": keyframe_consistency_warnings(payload=payload, context=context),
        "tasks": tasks,
    }


def _content_extension(content_type: str) -> str:
    return {
        "image/svg+xml": "svg",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }[content_type]


def render_manifest_pdf(manifest: dict[str, Any]) -> bytes:
    lines = [
        "AI EMOTION DIRECTOR - KEYFRAME MANIFEST",
        f"Project: {manifest['project_name']}",
        f"Keyframe asset: {manifest['keyframe_asset_id']} v{manifest['keyframe_version']}",
        f"Shots asset: {manifest['shots_asset_id']} v{manifest['shots_version']}",
        (
            "Progress: "
            f"{manifest['progress']['succeeded']}/{manifest['progress']['total']} succeeded, "
            f"{manifest['progress']['failed']} failed"
        ),
    ]
    lines.extend(
        f"{item['shot_id']}  {item['status']}  attempt={item['attempt']}  "
        f"confirmed={'yes' if item['confirmed'] else 'no'}  {item['provider_task_id']}"
        for item in manifest["tasks"]
    )
    safe_lines = [
        line.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    stream = "BT /F1 10 Tf 48 792 Td 14 TL " + " T* ".join(
        f"({line}) Tj" for line in safe_lines
    ) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream".encode("latin-1"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return output.getvalue()


async def build_keyframe_zip(
    *,
    asset: dict[str, Any],
    context: dict[str, Any],
    media_storage: MediaStorage,
) -> bytes:
    manifest = manifest_document(asset, context)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr("manifest.pdf", render_manifest_pdf(manifest))
        for task in asset["payload"]["tasks"]:
            result = task.get("result")
            if not result:
                continue
            content = await media_storage.read(result["storage_path"])
            if hashlib.sha256(content).hexdigest() != result["sha256"]:
                raise ValueError(f"{task['shot_id']} keyframe checksum mismatch")
            archive.writestr(
                f"keyframes/{task['shot_id']}.{_content_extension(result['content_type'])}",
                content,
            )
    return output.getvalue()
