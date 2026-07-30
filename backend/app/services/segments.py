from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from ..domain import ConfirmedSegmentAsset


class SegmentSelectionError(ValueError):
    pass


def recommend_segments(
    analysis: dict[str, Any],
    *,
    target_duration: float,
) -> list[dict[str, Any]]:
    duration = float(analysis.get("duration") or 0)
    if duration + 0.001 < target_duration:
        raise SegmentSelectionError(
            f"Audio duration {duration:g}s is shorter than target {target_duration:g}s"
        )
    energy = [
        float(value)
        for value in (
            analysis.get("energy_curve")
            or analysis.get("emotion_curve")
            or []
        )
    ]
    if not energy:
        energy = [0.0, 0.0]
    if max(energy, default=0) > 1:
        energy = [value / 100 for value in energy]
    window_size = min(
        len(energy),
        max(1, math.ceil(target_duration / max(duration, 0.001) * len(energy))),
    )
    windows: list[dict[str, float | int]] = []
    for index in range(0, max(len(energy) - window_size + 1, 1)):
        values = energy[index : index + window_size]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        change = abs(values[-1] - values[0]) + (max(values) - min(values))
        max_start = max(duration - target_duration, 0)
        denominator = max(len(energy) - window_size, 1)
        start = max_start * index / denominator
        windows.append(
            {
                "index": index,
                "start": start,
                "mean": mean,
                "variance": variance,
                "change": change,
            }
        )

    highlight = max(windows, key=lambda item: (item["mean"], item["variance"]))
    turn = max(windows, key=lambda item: (item["change"], item["variance"]))
    stable = min(windows, key=lambda item: (item["variance"], -item["mean"]))
    definitions = [
        (
            "highlight",
            "高潮候选",
            highlight,
            "窗口平均能量最高，适合强视觉段落",
        ),
        (
            "turn",
            "叙事转折候选",
            turn,
            "窗口首尾变化与内部动态最大，适合剧情转折",
        ),
        (
            "stable",
            "平稳候选",
            stable,
            "窗口能量方差最低，适合克制或铺陈段落",
        ),
    ]
    return [
        {
            "category": category,
            "label": label,
            "start": round(float(window["start"]), 3),
            "end": round(float(window["start"]) + target_duration, 3),
            "duration": round(target_duration, 3),
            "score": round(
                float(
                    window["mean"]
                    if category == "highlight"
                    else window["change"]
                    if category == "turn"
                    else 1 / (1 + window["variance"])
                ),
                4,
            ),
            "reason": reason,
        }
        for category, label, window, reason in definitions
    ]


def validate_confirmed_segment(
    *,
    start: float,
    end: float,
    category: str,
    label: str,
    target_duration: float,
    audio_duration: float,
    audio_id: str,
    audio_analysis_asset_id: int,
) -> ConfirmedSegmentAsset:
    if abs((end - start) - target_duration) > 0.01:
        raise SegmentSelectionError(
            f"Segment duration must equal project target {target_duration:g}s"
        )
    if start < 0 or end > audio_duration + 0.001:
        raise SegmentSelectionError(
            f"Segment must stay within audio bounds 0-{audio_duration:g}s"
        )
    return ConfirmedSegmentAsset.model_validate(
        {
            "start": start,
            "end": end,
            "duration": target_duration,
            "category": category,
            "label": label,
            "confirmed": True,
            "audio_id": audio_id,
            "audio_analysis_asset_id": audio_analysis_asset_id,
        }
    )


def restrict_context_to_confirmed_segment(
    context: dict[str, Any],
) -> dict[str, Any]:
    segment = context.get("assets", {}).get("segment")
    analysis = context.get("assets", {}).get("audio_analysis")
    if not isinstance(segment, dict) or not segment.get("confirmed"):
        raise SegmentSelectionError("Confirm a segment before generating director assets")
    if not isinstance(analysis, dict):
        raise SegmentSelectionError("Analyze audio before generating director assets")

    start = float(segment["start"])
    end = float(segment["end"])
    source_duration = float(analysis.get("duration") or end)
    sliced = deepcopy(analysis)
    sliced["source_duration"] = source_duration
    sliced["duration"] = float(segment["duration"])
    sliced["segment"] = deepcopy(segment)
    for key in ("beats", "onsets"):
        values = analysis.get(key) or []
        sliced[key] = [
            round(float(value) - start, 3)
            for value in values
            if start <= float(value) <= end
        ]
    for key in ("peak_candidates", "peaks"):
        values = analysis.get(key) or []
        sliced[key] = [
            {
                **value,
                "source_time": value.get("time"),
                "time": round(float(value.get("time", 0)) - start, 3),
            }
            for value in values
            if start <= float(value.get("time", 0)) <= end
        ]
    for key in ("energy_curve", "emotion_curve"):
        values = list(analysis.get(key) or [])
        if values:
            first = max(0, min(len(values) - 1, round(start / source_duration * (len(values) - 1))))
            last = max(first + 1, min(len(values), round(end / source_duration * (len(values) - 1)) + 1))
            sliced[key] = values[first:last]
    result = deepcopy(context)
    result["assets"]["audio_analysis"] = sliced
    return result
