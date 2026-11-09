"""Server-side Role Scores view cache."""
from __future__ import annotations

import services.role_scores_view_cache as cache


def _reset(monkeypatch):
    monkeypatch.setattr(cache, "_VIEWS", {})
    monkeypatch.setattr(cache, "_ORDER", [])
    monkeypatch.setattr(cache, "_seq", __import__("itertools").count(1))


def test_put_get_and_evict(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(cache, "_MAX_VIEWS", 2)
    first = cache.put_rows([{"Name": "Ada", "BPD": 14}], meta={"file": "a"})
    second = cache.put_rows([{"Name": "Ben", "BPD": 12}])
    assert first.startswith("rsv-")
    assert cache.get(first)["meta"]["file"] == "a"  # also LRUs-touches first
    third = cache.put_rows([{"Name": "Cara"}])
    # After get(first), second is oldest and is evicted when third is stored.
    assert cache.get(second) is None
    assert cache.get(first) is not None
    assert cache.get(third) is not None
    assert cache.get("") is None
    assert cache.get("missing") is None


def test_rows_from_payload_and_has_scores(monkeypatch):
    _reset(monkeypatch)
    assert cache.rows_from_payload(None) == []
    assert cache.payload_has_scores(None) is False
    inline = [{"Name": "Ada"}]
    assert cache.rows_from_payload({"rows": inline}) == inline
    assert cache.payload_has_scores({"rows": []}) is True
    assert cache.payload_has_scores({"rows": "x"}) is False

    cid = cache.put_rows([{"Name": "Ben", "BPD": 11}])
    assert cache.payload_has_scores({"cache_id": cid}) is True
    assert cache.rows_from_payload({"cache_id": cid}) == [{"Name": "Ben", "BPD": 11}]
    assert cache.rows_from_payload({"cache_id": "gone"}) == []


def test_project_role_rows_keeps_identity_and_roles():
    rows = [
        {
            "Name": "Ada",
            "Unique ID": "1",
            "Club": "City",
            "BPD": 14.2,
            "BPD eligible": True,
            "noise": "drop-me",
            "Salary": "$100K",
        },
        "skip",
        {"Name": "Ben", "VOL": 10},
    ]
    projected = cache.project_role_rows(rows, role_labels=["BPD", "", "VOL"])
    assert projected[0] == {
        "Name": "Ada",
        "Unique ID": "1",
        "Club": "City",
        "BPD": 14.2,
        "BPD eligible": True,
        "Salary": "$100K",
    }
    assert projected[1] == {"Name": "Ben", "VOL": 10}
    with_extra = cache.project_role_rows(
        [{"Name": "Ada", "Inf": "Inj Prone"}],
        role_labels=[],
        extra_keys={"Inf"},
    )
    assert with_extra == [{"Name": "Ada", "Inf": "Inj Prone"}]


def test_clear_markdown(monkeypatch):
    _reset(monkeypatch)
    cid = cache.put_rows([{"Name": "Ada"}])
    view = cache.get(cid)
    view["markdown_sig"] = "sig"
    view["markdown_by_key"] = {"Ada|1": "x"}
    view["tips_by_key"] = {"Ada|1": "tip"}
    cache.clear_markdown(cid)
    refreshed = cache.get(cid)
    assert refreshed["markdown_sig"] is None
    assert refreshed["markdown_by_key"] == {}
    assert refreshed["tips_by_key"] == {}
    cache.clear_markdown("missing")  # no-op
