from __future__ import annotations

import json

from backend.app.catalog import directory_entry, directory_for, object_types
from scripts.import_stage_directory import TARGET, build


def test_every_excel_row_is_covered_once_and_file_is_current() -> None:
    import pytest

    pytest.importorskip("openpyxl")
    data = build()
    rows = [row["row"] for stage in data["stages"] for row in stage["source_rows"]]
    assert len(rows) == len(set(rows)) == data["source_row_count"]
    assert json.loads(TARGET.read_text(encoding="utf-8")) == json.loads(
        json.dumps(data, ensure_ascii=False)
    ), "config/stages/stage-directory.v2.json устарел: запустите scripts/import_stage_directory.py"


def test_directory_rules_for_cameras_and_inspection() -> None:
    assert object_types()[0] == "Жильё" and len(object_types()) == 9
    for stage in directory_for("Жильё") + directory_for("Дороги"):
        assert stage["observability"] in {"yes", "partial", "no"}
        if stage["observability"] == "no":
            assert stage["confirmation_method"] == "inspection"
        if stage["confirmation_method"] == "cameras":
            assert stage["profile"]["strong_signs"], stage["code"]
    roof = directory_entry("Жильё", code="12.4.31")
    assert "Устройство кровли. Тип 3" in roof["includes"]
    assert directory_entry("Дороги", code="12.4.31") is None
    assert directory_entry("Жилой комплекс", name="Разработка котлована")["code"] == "12.3.1"
