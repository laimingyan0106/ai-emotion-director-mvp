from __future__ import annotations

from copy import deepcopy
from typing import Any


def shot_relevant_world_context(world: dict[str, Any]) -> dict[str, Any]:
    immutable = world.get("immutable_rules") or {}
    mutable = world.get("mutable_state") or {}
    return {
        "name": world.get("name"),
        "location": world.get("location"),
        "visual_style": world.get("visual_style"),
        "palette": world.get("palette"),
        "lighting": world.get("lighting"),
        "architecture": immutable.get("architecture"),
        "technology": immutable.get("technology"),
        "materials": immutable.get("materials"),
        "cinematography": immutable.get("cinematography"),
        "visual_exclusions": immutable.get("visual_exclusions"),
        "weather": mutable.get("weather"),
        "time_of_day": mutable.get("time_of_day"),
        "active_location": mutable.get("active_location"),
    }


def prompt_context_for_task(
    task: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(context)
    if task == "shots":
        world = result.get("assets", {}).get("world")
        if isinstance(world, dict):
            result["assets"]["world"] = shot_relevant_world_context(world)
    return result
