import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def probe_audio(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return demo_analysis()
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,bit_rate:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20)
        metadata = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return demo_analysis()
    stream = (metadata.get("streams") or [{}])[0]
    format_info = metadata.get("format") or {}
    return {
        **demo_analysis(),
        "duration": round(float(format_info.get("duration", 30)), 2),
        "codec": stream.get("codec_name", "unknown"),
        "sample_rate": int(stream.get("sample_rate", 0) or 0),
        "channels": stream.get("channels", 0),
        "bit_rate": int(format_info.get("bit_rate", 0) or 0),
    }


def demo_analysis() -> dict[str, Any]:
    return {
        "duration": 30.0,
        "bpm": 112,
        "key": "D minor",
        "energy": 0.74,
        "primary_emotion": "克制的思念",
        "emotion_arc": "克制 → 失控 → 释然",
        "emotion_curve": [14, 18, 27, 38, 34, 48, 62, 58, 76, 88, 72, 91, 68, 54, 47, 62, 44, 31, 24, 18],
        "peaks": [{"time": 9, "label": "第一次抬升"}, {"time": 17, "label": "情绪峰值"}, {"time": 24, "label": "留白"}],
    }
