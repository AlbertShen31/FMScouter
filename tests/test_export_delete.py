"""Bulk delete for the Uploads library."""
from __future__ import annotations

import json

import services.export_library as lib


def _patch_uploads(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(lib, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(lib, "UPLOADS_INDEX_PATH", uploads / "index.json")
    return uploads


def _write_index(uploads, entries: list[dict]) -> None:
    (uploads / "index.json").write_text(
        json.dumps(entries, indent=2) + "\n",
        encoding="utf-8",
    )


def _single(uploads, file_id: str, name: str) -> dict:
    stored = f"{file_id}_{name}.csv"
    (uploads / stored).write_text("Name,Club,Age\nAda,City,22\n", encoding="utf-8")
    return {
        "id": file_id,
        "kind": "single",
        "original_name": f"{name}.csv",
        "display_name": name,
        "stored_name": stored,
        "saved_at": "2026-01-01T00:00:00+00:00",
        "pages": ["role_scores"],
        "role_scores": True,
        "stats": False,
    }


def _pack(file_id: str, name: str, years: dict[str, str]) -> dict:
    return {
        "id": file_id,
        "kind": "multi_year",
        "original_name": name,
        "display_name": name,
        "stored_name": "",
        "saved_at": "2026-01-02T00:00:00+00:00",
        "pages": ["role_scores"],
        "role_scores": True,
        "stats": False,
        "years": years,
        "weights": {"1": 0.5, "2": 0.75, "3": 1.0},
    }


def test_delete_files_removes_selected_csvs(tmp_path, monkeypatch):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    a = _single(uploads, "aaa111aaa111", "season-a")
    b = _single(uploads, "bbb222bbb222", "season-b")
    c = _single(uploads, "ccc333ccc333", "season-c")
    _write_index(uploads, [a, b, c])

    result = lib.delete_files(["aaa111aaa111", "ccc333ccc333"])
    remaining = {e["id"] for e in lib.list_files()}
    assert remaining == {"bbb222bbb222"}
    assert result["removed"] == 2
    assert result["cascaded"] == 0
    assert not (uploads / a["stored_name"]).exists()
    assert (uploads / b["stored_name"]).exists()


def test_preview_and_delete_cascade_referencing_pack(tmp_path, monkeypatch):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    y3 = _single(uploads, "y3y3y3y3y3y3", "year-3")
    y2 = _single(uploads, "y2y2y2y2y2y2", "year-2")
    pack = _pack("packpackpack", "Liga pack", {"3": y3["id"], "2": y2["id"], "1": None})
    extra = _single(uploads, "exexexexexex", "other")
    _write_index(uploads, [y3, y2, pack, extra])

    preview = lib.preview_delete([y3["id"]])
    assert [e["id"] for e in preview["selected"]] == [y3["id"]]
    assert [e["id"] for e in preview["cascaded"]] == [pack["id"]]

    result = lib.delete_files([y3["id"]])
    remaining = {e["id"] for e in lib.list_files()}
    assert remaining == {y2["id"], extra["id"]}
    assert result["removed"] == 2
    assert result["cascaded"] == 1


def test_delete_files_selected_pack_and_source_does_not_double_count(tmp_path, monkeypatch):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    y3 = _single(uploads, "y3y3y3y3y3y3", "year-3")
    pack = _pack("packpackpack", "Liga pack", {"3": y3["id"], "2": None, "1": None})
    _write_index(uploads, [y3, pack])

    preview = lib.preview_delete([y3["id"], pack["id"]])
    assert {e["id"] for e in preview["selected"]} == {y3["id"], pack["id"]}
    assert preview["cascaded"] == []

    result = lib.delete_files([y3["id"], pack["id"]])
    assert lib.list_files() == []
    assert result["removed"] == 2
    assert result["cascaded"] == 0


def test_delete_files_empty_or_unknown(tmp_path, monkeypatch):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    kept = _single(uploads, "keepkeepkeep", "keep")
    _write_index(uploads, [kept])
    result = lib.delete_files(["missing", "", None])  # type: ignore[list-item]
    assert result["removed"] == 0
    assert [e["id"] for e in lib.list_files()] == [kept["id"]]
    assert lib.delete_files([])["removed"] == 0
