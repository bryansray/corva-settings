from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from typing import Any


def deep_merge(
    base: Mapping[str, Any] | None, override: Mapping[str, Any] | None
) -> dict[str, Any]:
    if base is None and override is None:
        return {}
    if base is None:
        return deepcopy(dict(override or {}))
    if override is None:
        return deepcopy(dict(base))

    merged: MutableMapping[str, Any] = deepcopy(dict(base))
    return _deep_merge_into(merged, override)


def _deep_merge_into(
    target: MutableMapping[str, Any], override: Mapping[str, Any]
) -> dict[str, Any]:
    for key, value in override.items():
        current = target.get(key)
        if isinstance(current, MutableMapping) and isinstance(value, Mapping):
            target[key] = _deep_merge_into(current, value)
            continue
        target[key] = deepcopy(value)
    return dict(target)


def apply_patch(document: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    updated = deepcopy(dict(document))
    for dotted_path, value in patch.items():
        if not dotted_path:
            raise ValueError("Patch paths must be non-empty dotted paths")
        _set_dotted_path(updated, dotted_path, value)
    return updated


def delete_paths(document: Mapping[str, Any], paths: Sequence[str]) -> dict[str, Any]:
    updated = deepcopy(dict(document))
    for dotted_path in paths:
        if not dotted_path:
            raise ValueError("Delete paths must be non-empty dotted paths")
        _delete_dotted_path(updated, dotted_path)
    return updated


def _set_dotted_path(document: MutableMapping[str, Any], dotted_path: str, value: Any) -> None:
    keys = dotted_path.split(".")
    cursor: MutableMapping[str, Any] = document
    for key in keys[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, MutableMapping):
            next_value = {}
            cursor[key] = next_value
        cursor = next_value
    cursor[keys[-1]] = deepcopy(value)


def _delete_dotted_path(document: MutableMapping[str, Any], dotted_path: str) -> None:
    keys = dotted_path.split(".")
    cursor: MutableMapping[str, Any] = document
    parents: list[tuple[MutableMapping[str, Any], str]] = []

    for key in keys[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, MutableMapping):
            return
        parents.append((cursor, key))
        cursor = next_value

    if keys[-1] not in cursor:
        return

    del cursor[keys[-1]]

    while parents:
        parent, key = parents.pop()
        child = parent.get(key)
        if isinstance(child, MutableMapping) and not child:
            del parent[key]
            continue
        break
