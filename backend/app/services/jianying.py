from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .keyframes import manifest_document
from .storage import MediaStorage


def build_jianying_prompt(context: dict[str, Any]) -> str:
    project = context["project"]
    segment = context["assets"]["segment"]
    shots = context["assets"]["shots"]["shots"]
    lines = [
        "请根据压缩包内的音频与关键帧，直接生成一条可交付成片。",
        f"项目：{project['name']}",
        f"成片时长：{segment['duration']:.3f} 秒",
        "画幅：16:9；帧率：24fps；输出：1080p MP4。",
        (
            f"音频只使用 source/ 里的原文件从 {segment['start']:.3f}s "
            f"到 {segment['end']:.3f}s 的区间，并从成片 0 秒开始对齐。"
        ),
        "必须保持 keyframes/ 中角色身份、服装、场景、色板和光线连续，不添加文字、水印或额外角色。",
        "按照 timeline.json 的 start_ms、duration、camera、action、emotion 顺序制作镜头；关键帧作为各镜头视觉锚点。",
        "转场应服务音乐节奏，避免无理由炫技；不要更改音乐速度、音高或节拍位置。",
        "",
        "镜头摘要：",
    ]
    lines.extend(
        f"- {shot['id']} | {shot['start_ms']}ms | {shot['duration']:.3f}s | "
        f"{shot['camera']} | {shot['action']} | {shot['emotion']}"
        for shot in shots
    )
    return "\n".join(lines)


async def build_jianying_package(
    *,
    audio: dict[str, Any],
    keyframe_asset: dict[str, Any],
    context: dict[str, Any],
    media_storage: MediaStorage,
) -> bytes:
    segment = context["assets"]["segment"]
    shots = context["assets"]["shots"]["shots"]
    manifest = manifest_document(keyframe_asset, context)
    audio_content = await media_storage.read(audio["storage_path"])
    timeline = {
        "schema": "ai-emotion-director/jianying-handoff/v1",
        "project_id": str(keyframe_asset["project_id"]),
        "project_name": context["project"]["name"],
        "output": {"aspect_ratio": "16:9", "fps": 24, "resolution": "1920x1080"},
        "audio": {
            "filename": audio["filename"],
            "trim_start_seconds": segment["start"],
            "trim_end_seconds": segment["end"],
            "duration_seconds": segment["duration"],
            "sha256": hashlib.sha256(audio_content).hexdigest(),
        },
        "shots": [
            {
                **shot,
                "keyframe_file": next(
                    (
                        task["file"]
                        for task in manifest["tasks"]
                        if task["shot_id"] == shot["id"]
                    ),
                    None,
                ),
            }
            for shot in shots
        ],
    }
    extension = Path(audio["filename"]).suffix.lower() or ".audio"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("剪映小助手提示词.txt", build_jianying_prompt(context).encode("utf-8"))
        archive.writestr(
            "timeline.json",
            json.dumps(timeline, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "keyframes-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(f"source/audio{extension}", audio_content)
        for task in keyframe_asset["payload"]["tasks"]:
            result = task.get("result")
            if not result:
                continue
            content = await media_storage.read(result["storage_path"])
            if hashlib.sha256(content).hexdigest() != result["sha256"]:
                raise ValueError(f"{task['shot_id']} keyframe checksum mismatch")
            file_name = next(
                item["file"]
                for item in manifest["tasks"]
                if item["shot_id"] == task["shot_id"]
            )
            archive.writestr(file_name, content)
    return output.getvalue()
