"""Player-count preview helpers for the Uploads library."""
from __future__ import annotations

import services.export_library as lib
from services.upload_cache import _n_players_from_payload


def test_count_csv_players_skips_blank_and_nameless():
    text = (
        "Name,Club,Age\n"
        "Ada,City,22\n"
        "\n"
        ",Town,21\n"
        "Bea,City,24\n"
    )
    assert lib.count_csv_players(text) == 2


def test_count_csv_players_uses_player_column_and_semicolon():
    text = "Player;Club\nOne;A\nTwo;B\n"
    assert lib.count_csv_players(text) == 2


def test_count_csv_players_empty():
    assert lib.count_csv_players("") == 0
    assert lib.count_csv_players("Name,Club\n") == 0


def test_player_count_of_prefers_entry_then_cache():
    assert lib.player_count_of({"player_count": 12, "cache": {"n_players": 3}}) == 12
    assert lib.player_count_of({"cache": {"n_players": 8}}) == 8
    assert lib.player_count_of({}) is None
    assert lib.player_count_of(None) is None


def test_player_count_phrase_and_suffix():
    assert lib.player_count_phrase(None) == ""
    assert lib.player_count_phrase(1) == "1 player"
    assert lib.player_count_phrase(1247) == "1,247 players"
    assert lib.player_count_suffix({"player_count": 4}) == " · 4 players"
    assert lib.player_count_suffix({}) == ""


def test_csv_player_keys_unique_across_files():
    year3 = "Name,Unique ID\nAda,1\nBea,2\n"
    year2 = "Name,Unique ID\nAda,1\nCal,3\n"
    assert lib.csv_player_keys(year3) == {"Ada|1", "Bea|2"}
    union = lib.csv_player_keys(year3) | lib.csv_player_keys(year2)
    assert union == {"Ada|1", "Bea|2", "Cal|3"}
    assert len(union) == 3


def test_n_players_from_payload_prefers_role_then_stats():
    assert _n_players_from_payload(
        {"role_scores": {"n_players": 10}, "stats": {"n_players": 9}}
    ) == 10
    assert _n_players_from_payload({"stats": {"n_players": 9}}) == 9
    assert _n_players_from_payload({"players": [{}, {}]}) == 2
    assert _n_players_from_payload({}) is None
