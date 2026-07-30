from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain import WorldAsset


class WorldEditError(ValueError):
    pass


def _get_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise WorldEditError(f"Locked field does not exist: {path}")
        value = value[part]
    return deepcopy(value)


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    target = payload
    parts = path.split(".")
    for part in parts[:-1]:
        existing = target.get(part)
        if not isinstance(existing, dict):
            existing = {}
            target[part] = existing
        target = existing
    target[parts[-1]] = deepcopy(value)


def _merge(target: dict[str, Any], changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _leaf_paths(payload: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.extend(_leaf_paths(value, path))
        else:
            paths.append(path)
    return paths


def edit_world(
    current: dict[str, Any],
    *,
    changes: dict[str, Any],
    locked_fields: list[str] | None,
) -> WorldAsset:
    final_locks = list(
        dict.fromkeys(
            current.get("locked_fields", [])
            if locked_fields is None
            else locked_fields
        )
    )
    changed_paths = _leaf_paths(changes)
    for path in changed_paths:
        blocking_lock = next(
            (
                locked
                for locked in final_locks
                if path == locked or path.startswith(f"{locked}.")
            ),
            None,
        )
        if blocking_lock:
            raise WorldEditError(
                f"Unlock {blocking_lock} before editing {path}"
            )
    updated = deepcopy(current)
    _merge(updated, changes)
    updated["locked_fields"] = final_locks
    return WorldAsset.model_validate(updated)


def preserve_locked_world_fields(
    current: dict[str, Any],
    generated: dict[str, Any],
) -> WorldAsset:
    result = deepcopy(generated)
    locks = list(dict.fromkeys(current.get("locked_fields", [])))
    for path in locks:
        _set_path(result, path, _get_path(current, path))
    result["locked_fields"] = locks
    return WorldAsset.model_validate(result)
