from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain import ShotSetAsset


class ShotEditError(ValueError):
    pass


def canonicalize_shot_set(
    payload: dict[str, Any],
    *,
    target_duration: float,
) -> ShotSetAsset:
    updated = deepcopy(payload)
    shots = updated.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ShotEditError("ShotSet must contain at least one shot")
    cursor = 0.0
    for shot in shots:
        if not isinstance(shot, dict):
            raise ShotEditError("Every shot must be an object")
        shot["start"] = round(cursor, 3)
        shot["start_ms"] = round(cursor * 1000)
        cursor += float(shot.get("duration", 0))
    cursor = round(cursor, 3)
    if abs(cursor - target_duration) > 0.001:
        raise ShotEditError(
            f"Shot durations total {cursor:g}, expected project duration "
            f"{target_duration:g}"
        )
    updated["duration"] = target_duration
    return ShotSetAsset.model_validate(updated)


def preserve_locked_shots(
    current: dict[str, Any],
    generated: dict[str, Any],
) -> ShotSetAsset:
    locked_by_id = {
        shot["id"]: deepcopy(shot)
        for shot in current.get("shots", [])
        if shot.get("locked")
    }
    updated = deepcopy(generated)
    preserved: list[dict[str, Any]] = []
    for generated_shot in updated.get("shots", []):
        locked = locked_by_id.get(generated_shot["id"])
        if not locked:
            preserved.append(generated_shot)
            continue
        locked["character_ids"] = deepcopy(generated_shot["character_ids"])
        locked["character_refs"] = deepcopy(generated_shot["character_refs"])
        preserved.append(locked)
    updated["shots"] = preserved
    return canonicalize_shot_set(
        updated,
        target_duration=float(generated["duration"]),
    )


def replace_single_shot(
    current: dict[str, Any],
    shot_id: str,
    generated_shot: dict[str, Any],
    *,
    target_duration: float,
) -> ShotSetAsset:
    updated = deepcopy(current)
    index = next(
        (
            index
            for index, shot in enumerate(updated.get("shots", []))
            if shot["id"] == shot_id
        ),
        None,
    )
    if index is None:
        raise ShotEditError(f"Shot not found: {shot_id}")
    original = updated["shots"][index]
    if original.get("locked"):
        raise ShotEditError(f"Unlock {shot_id} before regenerating it")
    replacement = deepcopy(generated_shot)
    for field in (
        "id",
        "start",
        "start_ms",
        "duration",
        "character_ids",
        "character_refs",
        "locked",
    ):
        replacement[field] = deepcopy(original[field])
    updated["shots"][index] = replacement
    return canonicalize_shot_set(updated, target_duration=target_duration)
