from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
DIRECT_LOAD_EXTENSIONS = {".wav", ".flac", ".ogg"}


def _resolve_ffmpeg() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def _decode_for_analysis(
    source: Path,
    *,
    max_duration_seconds: int,
    timeout_seconds: int,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if source.suffix.lower() in DIRECT_LOAD_EXTENSIONS:
        return source, None
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_unavailable_for_compressed_audio")
    temporary = tempfile.TemporaryDirectory(prefix="emotion-director-audio-")
    decoded = Path(temporary.name) / "decoded.wav"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(source),
            "-t",
            str(max_duration_seconds),
            "-ac",
            "1",
            "-ar",
            "22050",
            "-f",
            "wav",
            str(decoded),
        ],
        capture_output=True,
        check=True,
        timeout=timeout_seconds,
    )
    return decoded, temporary


def _resample_curve(values: Any, points: int = 100) -> list[float]:
    import numpy as np

    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return [0.0] * points
    low = float(np.min(array))
    high = float(np.max(array))
    normalized = np.zeros_like(array) if math.isclose(low, high) else (array - low) / (high - low)
    positions = np.linspace(0, max(array.size - 1, 0), num=points)
    sampled = np.interp(positions, np.arange(array.size), normalized)
    return [round(float(value), 4) for value in sampled]


def _silence_segments(
    rms: Any,
    *,
    sample_rate: int,
    hop_length: int,
    duration: float,
) -> list[dict[str, float]]:
    import numpy as np

    values = np.asarray(rms, dtype=float)
    if values.size == 0:
        return []
    threshold = max(float(np.max(values)) * 0.03, 1e-6)
    silent = values <= threshold
    segments: list[dict[str, float]] = []
    start: int | None = None
    for index, is_silent in enumerate([*silent.tolist(), False]):
        if is_silent and start is None:
            start = index
        elif not is_silent and start is not None:
            start_time = start * hop_length / sample_rate
            end_time = min(index * hop_length / sample_rate, duration)
            if end_time - start_time >= 0.2:
                segments.append(
                    {
                        "start": round(start_time, 3),
                        "end": round(end_time, 3),
                        "duration": round(end_time - start_time, 3),
                    }
                )
            start = None
    return segments


def _peak_candidates(curve: list[float], duration: float) -> list[dict[str, float | str]]:
    if len(curve) < 3:
        return []
    candidates = [
        (value, index)
        for index, value in enumerate(curve[1:-1], start=1)
        if value >= curve[index - 1] and value > curve[index + 1]
    ]
    selected: list[tuple[float, int]] = []
    minimum_distance = max(len(curve) // 12, 1)
    for value, index in sorted(candidates, reverse=True):
        if all(abs(index - existing) >= minimum_distance for _, existing in selected):
            selected.append((value, index))
        if len(selected) == 8:
            break
    return [
        {
            "time": round(index / (len(curve) - 1) * duration, 3),
            "energy": round(value, 4),
            "label": "能量峰值候选",
        }
        for value, index in sorted(selected, key=lambda item: item[1])
    ]


def analyze_audio_file(
    path: Path,
    *,
    max_duration_seconds: int = 600,
    decode_timeout_seconds: int = 30,
) -> dict[str, Any]:
    started = time.perf_counter()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        import librosa
        import numpy as np

        decoded, temporary = _decode_for_analysis(
            path,
            max_duration_seconds=max_duration_seconds,
            timeout_seconds=decode_timeout_seconds,
        )
        signal, sample_rate = librosa.load(
            decoded,
            sr=22050,
            mono=True,
            duration=max_duration_seconds,
        )
        if signal.size == 0:
            raise ValueError("audio_contains_no_samples")
        duration = float(librosa.get_duration(y=signal, sr=sample_rate))
        hop_length = 512
        tempo, beat_frames = librosa.beat.beat_track(
            y=signal,
            sr=sample_rate,
            hop_length=hop_length,
        )
        onset_frames = librosa.onset.onset_detect(
            y=signal,
            sr=sample_rate,
            hop_length=hop_length,
            backtrack=False,
        )
        rms = librosa.feature.rms(y=signal, hop_length=hop_length)[0]
        centroid = librosa.feature.spectral_centroid(
            y=signal,
            sr=sample_rate,
            hop_length=hop_length,
        )[0]
        chroma = librosa.feature.chroma_stft(
            y=signal,
            sr=sample_rate,
            hop_length=hop_length,
        )
        chroma_profile = np.mean(chroma, axis=1)
        chroma_total = float(np.sum(chroma_profile))
        if chroma_total > 0:
            chroma_profile = chroma_profile / chroma_total
        dominant_pitch_class = PITCH_CLASSES[int(np.argmax(chroma_profile))]
        energy_curve = _resample_curve(rms)
        centroid_curve = _resample_curve(centroid)
        peaks = _peak_candidates(energy_curve, duration)
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "analysis_version": "librosa-v1",
            "degraded": False,
            "degraded_reason": None,
            "duration": round(duration, 3),
            "truncated": duration >= max_duration_seconds - 0.01,
            "bpm": round(float(np.asarray(tempo).reshape(-1)[0]), 3),
            "beats": [
                round(float(value), 3)
                for value in librosa.frames_to_time(
                    beat_frames,
                    sr=sample_rate,
                    hop_length=hop_length,
                )
            ],
            "onsets": [
                round(float(value), 3)
                for value in librosa.frames_to_time(
                    onset_frames,
                    sr=sample_rate,
                    hop_length=hop_length,
                )
            ],
            "rms": {
                "mean": round(float(np.mean(rms)), 6),
                "max": round(float(np.max(rms)), 6),
            },
            "spectral_centroid": {
                "mean_hz": round(float(np.mean(centroid)), 3),
                "curve": centroid_curve,
            },
            "chroma": {
                "dominant_pitch_class": dominant_pitch_class,
                "profile": [round(float(value), 5) for value in chroma_profile],
            },
            "key": f"{dominant_pitch_class} (chroma dominant)",
            "energy": round(float(np.mean(energy_curve)), 4),
            "energy_curve": energy_curve,
            "emotion_curve": [round(value * 100) for value in energy_curve],
            "silence_segments": _silence_segments(
                rms,
                sample_rate=sample_rate,
                hop_length=hop_length,
                duration=duration,
            ),
            "peak_candidates": peaks,
            "peaks": peaks,
            "primary_emotion": "未进行心理学意义的情绪识别",
            "emotion_arc": "仅提供基于能量与频谱的音乐结构信号",
            "sample_rate": sample_rate,
            "channels": 1,
            "source_sha256": source_hash,
            "processing_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except (
        ImportError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as error:
        return demo_analysis(degraded=True, reason=str(error))
    finally:
        if temporary is not None:
            temporary.cleanup()


def probe_audio(path: Path) -> dict[str, Any]:
    return analyze_audio_file(path)


def demo_analysis(
    *,
    degraded: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    energy_curve = [
        0.14,
        0.18,
        0.27,
        0.38,
        0.34,
        0.48,
        0.62,
        0.58,
        0.76,
        0.88,
        0.72,
        0.91,
        0.68,
        0.54,
        0.47,
        0.62,
        0.44,
        0.31,
        0.24,
        0.18,
    ]
    peaks = [
        {"time": 9, "energy": 0.76, "label": "第一处能量抬升"},
        {"time": 17, "energy": 0.91, "label": "能量峰值候选"},
        {"time": 24, "energy": 0.62, "label": "尾段留白候选"},
    ]
    return {
        "analysis_version": "demo-v1",
        "degraded": degraded,
        "degraded_reason": reason,
        "duration": 30.0,
        "truncated": False,
        "bpm": 112,
        "beats": [],
        "onsets": [],
        "rms": {"mean": 0.0, "max": 0.0},
        "spectral_centroid": {"mean_hz": 0.0, "curve": []},
        "chroma": {"dominant_pitch_class": "D", "profile": []},
        "key": "D minor (demo)",
        "energy": 0.74,
        "energy_curve": energy_curve,
        "emotion_curve": [round(value * 100) for value in energy_curve],
        "silence_segments": [],
        "peak_candidates": peaks,
        "peaks": peaks,
        "primary_emotion": "未进行心理学意义的情绪识别",
        "emotion_arc": "Demo 能量结构，仅用于降级演示",
        "sample_rate": 0,
        "channels": 0,
        "source_sha256": None,
        "processing_ms": 0.0,
    }
