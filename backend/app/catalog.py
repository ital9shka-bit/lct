"""Справочник этапов: импортирован из Excel заказчика скриптом scripts/import_stage_directory.py."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DIRECTORY_PATH = Path(__file__).resolve().parents[2] / "config/stages/stage-directory.v2.json"

# Типы из ранних редакций: объекты, созданные до импорта, продолжают получать справочник.
LEGACY_OBJECT_TYPES = {
    "Жилой комплекс": "Жильё",
    "Общественное здание": "Административные здания",
}


@lru_cache
def _directory() -> dict[str, Any]:
    return json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))


def object_types() -> list[str]:
    return list(_directory()["object_types"])


def directory_version() -> str:
    return _directory()["version"]


def normalize_object_type(object_type: str) -> str:
    return LEGACY_OBJECT_TYPES.get(object_type, object_type)


def all_stages() -> list[dict[str, Any]]:
    return list(_directory()["stages"])


def directory_for(object_type: str) -> list[dict[str, Any]]:
    kind = normalize_object_type(object_type)
    return [item for item in _directory()["stages"] if kind in item["object_types"]]


def directory_entry(object_type: str, *, code: str = "", name: str = "") -> dict[str, Any] | None:
    wanted = name.casefold().strip()
    for item in directory_for(object_type):
        if code and item["code"] == code:
            return item
    if not wanted:
        return None
    for item in directory_for(object_type):
        names = [item["name"], *item.get("aliases", [])]
        if any(wanted == value.casefold() for value in names):
            return item
    return None
