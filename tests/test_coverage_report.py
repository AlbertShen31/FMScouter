"""Formatter for scripts/run_coverage.py package tables."""
from __future__ import annotations

import scripts.run_coverage as cov


def _sample() -> dict:
    return {
        "totals": {
            "num_statements": 100,
            "covered_lines": 70,
            "percent_covered": 70.0,
        },
        "files": {
            "scoring/utils.py": {
                "summary": {
                    "num_statements": 40,
                    "covered_lines": 40,
                    "percent_covered": 100.0,
                }
            },
            "scoring/role_scorer.py": {
                "summary": {
                    "num_statements": 40,
                    "covered_lines": 20,
                    "percent_covered": 50.0,
                }
            },
            "services/export_library.py": {
                "summary": {
                    "num_statements": 20,
                    "covered_lines": 10,
                    "percent_covered": 50.0,
                }
            },
            "pages/stats_page.py": {
                "summary": {
                    "num_statements": 100,
                    "covered_lines": 0,
                    "percent_covered": 0.0,
                }
            },
            "components/player_table.py": {
                "summary": {
                    "num_statements": 50,
                    "covered_lines": 10,
                    "percent_covered": 20.0,
                }
            },
        },
    }


def test_package_rows_roll_up_by_top_level():
    rows = {row["package"]: row for row in cov.package_rows(_sample())}
    assert rows["scoring"]["statements"] == 80
    assert rows["scoring"]["covered"] == 60
    assert rows["scoring"]["percent"] == 75.0
    assert rows["services"]["statements"] == 20
    assert "pages" not in rows
    assert "components" not in rows


def test_file_rows_skip_fully_covered_and_sort_lowest_first():
    rows = cov.file_rows(_sample())
    assert [row["file"] for row in rows] == [
        "scoring/role_scorer.py",
        "services/export_library.py",
    ]
    assert "pages/stats_page.py" not in [row["file"] for row in rows]
    assert "components/player_table.py" not in [row["file"] for row in rows]


def test_markdown_includes_total_and_weak_files():
    text = cov.format_markdown(_sample())
    assert "**70.0%**" in text
    assert "`scoring`" in text
    assert "`scoring/role_scorer.py`" in text
    assert "`scoring/utils.py`" not in text
