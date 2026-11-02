"""Current vs historical export comparison helpers."""
from __future__ import annotations

from scoring import comparison as cmp


def test_players_lookup_and_compare_name_key():
    players = [
        {"Name": "Ada", "Unique ID": "1"},
        {"name": "Ben", "unique_id": "2"},
        {"Name": ""},
    ]
    lookup = cmp.players_lookup(players, cmp.compare_name_key)
    assert set(lookup) == {"Ada|1", "Ben|2"}
    assert cmp.compare_name_key({"Name": "Ada", "Unique ID": "1"}) == "Ada|1"


def test_strip_cell_text_and_cell_number():
    assert cmp.strip_cell_text('<span class="x">12.5%</span>') == "12.5%"
    assert cmp.strip_cell_text(None) == ""
    assert cmp.cell_number("12.5%") == 12.5
    assert cmp.cell_number("1,250") == 1250.0
    assert cmp.cell_number("-") is None
    assert cmp.cell_number("n/a") is None


def test_delta_html_score_and_wage_tones():
    up = cmp.delta_html(1.2, decimals=1)
    assert "↑+1.2" in up
    assert "cmp-delta-up" in up
    assert "cmp-delta-block" in up
    down = cmp.delta_html(-2.0, decimals=0, kind="wage", stacked=False)
    assert "↓" in down
    assert "cmp-delta-wage-down" in down
    assert "cmp-delta-block" not in down
    assert cmp.delta_html(0.01, min_abs=0.05) == ""
    assert cmp.delta_html(0.4, percent=True) == ""  # rounds to 0%
    assert "+3%" in cmp.delta_html(3.2, percent=True)
    assert cmp.delta_html(None) == ""


def test_wrap_append_and_score_display():
    wrapped = cmp.wrap_cell_with_delta("14.2", '<span class="cmp-delta">↑+0.5</span>')
    assert 'class="cmp-cell"' in wrapped
    assert "14.2" in wrapped
    assert cmp.wrap_cell_with_delta("14.2", "") == "14.2"

    assert cmp.append_delta_html("14.2", 14.2, 13.0, enabled=False) == "14.2"
    with_delta = cmp.append_delta_html("14.2", 14.2, 13.0, enabled=True)
    assert with_delta.startswith("14.2")
    assert "↑+1.2" in with_delta
    assert cmp.append_delta_html("—", None, 10, enabled=True) == "—"

    assert cmp.score_display(None) == "-"
    assert cmp.score_display("na") == "na"
    plain = cmp.score_display(14.2)
    assert "14.2" in plain
    assert "rs-score-cell" in plain
    colored = cmp.score_display(14.2, color="#0f0")
    assert "color:#0f0" in colored
    diffed = cmp.score_display(14.2, 13.0, enabled=True)
    assert "cmp-delta" in diffed
    assert cmp.score_display(14.2, "x", enabled=True).endswith("</span>")


def test_money_delta_span():
    assert cmp.money_delta_span(None, enabled=True) is None
    assert cmp.money_delta_span(1000, enabled=False) is None
    assert cmp.money_delta_span(0.1, enabled=True) is None
    up = cmp.money_delta_span(25_000, enabled=True)
    assert up is not None
    assert "wage-up" in up.className
    assert "↑" in up.children
    down = cmp.money_delta_span(-1_000, enabled=True)
    assert "wage-down" in down.className
