"""Squad vs scouting export merge helpers."""
from __future__ import annotations

from scoring import export_sources as src


def test_normalize_and_labels():
    assert src.normalize_export_source("scout") == src.SOURCE_SCOUTING
    assert src.normalize_export_source("transfer") == src.SOURCE_SCOUTING
    assert src.normalize_export_source("SQUAD") == src.SOURCE_SQUAD
    assert src.normalize_export_source(None) == src.SOURCE_SQUAD
    assert src.source_label("scouting") == "Scouting"
    assert src.source_label("club") == "Squad"


def test_name_with_source_html_and_legend():
    assert src.name_with_source_html("Ada") == "Ada"
    assert src.name_with_source_html("", highlight=True).startswith('<span class="src-name')
    highlighted = src.name_with_source_html("Ada <X>", "scouting", highlight=True)
    assert 'src-name-scouting' in highlighted
    assert "Ada &lt;X&gt;" in highlighted
    assert src.export_source_legend(active=False) is None
    legend = src.export_source_legend(active=True)
    assert legend is not None
    assert legend.className == "rs-source-legend"


def test_merge_prefers_squad_on_duplicate_keys():
    squad = [
        {"name": "Ada", "unique_id": "1", "club": "City", "minutes": 900},
        {"name": "Ada", "unique_id": "1", "club": "City", "minutes": 100},  # dupe
        "skip",
    ]
    scouting = [
        {"name": "Ada", "unique_id": "1", "club": "Rivals", "minutes": 800},
        {"name": "Ben", "unique_id": "2", "club": "Town", "minutes": 700},
    ]
    merged = src.merge_squad_and_scouting(
        squad,
        scouting,
        squad_file_id="squad-a",
        scouting_file_id="scout-b",
    )
    assert len(merged) == 2
    ada = merged[0]
    assert ada["_export_source"] == "squad"
    assert ada["_source_file_id"] == "squad-a"
    assert ada["minutes"] == 900
    ben = merged[1]
    assert ben["_export_source"] == "scouting"
    assert ben["_source_file_id"] == "scout-b"
    assert src.has_scouting_rows(merged) is True
    assert src.has_scouting_rows([ada]) is False
    assert src.has_scouting_rows(None) is False


def test_merge_without_keys_keeps_all_rows():
    rows = src.merge_squad_and_scouting(
        [{"name": ""}],
        [{"name": ""}],
        key_fn=lambda _p: "",
    )
    assert len(rows) == 2
    assert rows[0]["_export_source"] == "squad"
    assert rows[1]["_export_source"] == "scouting"
