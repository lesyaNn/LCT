"""Import v2 pure-unit: normalization, sheet dispatch, value coercion (no DB)."""

import pytest

from app.modules.imports.service import (
    ImportValidationError,
    RowError,
    _to_date,
    _transfer_status,
    normalize_header,
    resolve_sheet_kind,
    stage_upload,
)


def test_normalize_header_variants():
    assert normalize_header("Название ВУЗа") == "название вуза"
    assert normalize_header("Продукт_Направление") == "продукт направление"
    assert normalize_header("ИТ-продукт") == "ит продукт"
    assert normalize_header("  Код   направления  ") == "код направления"
    assert normalize_header("Ёмкость") == "емкость"
    assert normalize_header(None) == ""


def test_resolve_all_known_sheets():
    assert resolve_sheet_kind("ВУЗы") == "вузы"
    assert resolve_sheet_kind("ИТ-продукты") == "ит продукты"
    assert resolve_sheet_kind("Ответственные ВУЗа") == "ответственные вуза"
    assert resolve_sheet_kind("Договоры и лицензии") == "договоры и лицензии"
    assert resolve_sheet_kind("Направления") == "направления"
    assert resolve_sheet_kind("Программы") == "программы"
    assert resolve_sheet_kind("Продукт_Направление") == "продукт направление"


def test_resolve_unknown_sheet_fails_loudly():
    with pytest.raises(ImportValidationError):
        resolve_sheet_kind("Лист1")


def test_transfer_status_normalization():
    assert _transfer_status("Действует") == "accepted"
    assert _transfer_status("Передан") == "accepted"
    assert _transfer_status("В работе") == "pending"
    assert _transfer_status(None) == "pending"
    assert _transfer_status("  ") == "pending"
    with pytest.raises(RowError):
        _transfer_status("Что-то странное")


def test_to_date_values():
    from datetime import date, datetime

    assert _to_date(datetime(2026, 1, 20, 12, 0), "f") == date(2026, 1, 20)
    assert _to_date(date(2026, 1, 20), "f") == date(2026, 1, 20)
    assert _to_date("20.01.2026", "f") == date(2026, 1, 20)
    assert _to_date("2026-01-20", "f") == date(2026, 1, 20)
    with pytest.raises(RowError):
        _to_date(None, "f")
    with pytest.raises(RowError):
        _to_date("когда-нибудь", "f")


def test_stage_upload_validation(tmp_path, monkeypatch):
    import app.modules.imports.service as svc

    monkeypatch.setattr(svc, "STAGING_DIR", str(tmp_path))
    with pytest.raises(ImportValidationError):
        stage_upload("data.csv", b"x")
    with pytest.raises(ImportValidationError):
        stage_upload("data.xlsx", b"")
    with pytest.raises(ImportValidationError):
        stage_upload("data.xlsx", b"not a workbook at all....")


def test_stage_upload_roundtrip(tmp_path, monkeypatch):
    import openpyxl

    import app.modules.imports.service as svc

    monkeypatch.setattr(svc, "STAGING_DIR", str(tmp_path))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ВУЗы"
    ws.append(["Название ВУЗа", "Город"])
    ws.append(["Тестовый вуз", "Тестоград"])
    path = tmp_path / "src.xlsx"
    wb.save(path)
    file_id = stage_upload("src.xlsx", path.read_bytes())
    assert len(file_id) == 32
    sheets = svc.list_sheets(file_id)
    assert sheets == [{"id": "ВУЗы", "label": "ВУЗы", "row_count": 1}]
    preview = svc.preview_sheet(file_id, "ВУЗы")
    assert preview["headers"] == ["Название ВУЗа", "Город"]
    assert preview["preview"] == [{"Название ВУЗа": "Тестовый вуз", "Город": "Тестоград"}]
    assert preview["row_count"] == 1
