#!/usr/bin/env python3
"""Run unit tests with coverage and print a package/file report.

    python scripts/run_coverage.py
    python scripts/run_coverage.py --quiet
    python scripts/run_coverage.py -- tests/test_role_scores.py

Writes ``htmlcov/index.html``, ``coverage.xml``, and ``coverage.json``.
On GitHub Actions, also appends a markdown table to ``$GITHUB_STEP_SUMMARY``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_JSON = ROOT / "coverage.json"
HTML_DIR = ROOT / "htmlcov"
PACKAGES = ("scoring", "services", "config")


def _require_dev_deps() -> None:
    missing = []
    for mod in ("pytest", "pytest_cov", "coverage"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod.replace("_", "-"))
    if missing:
        sys.exit(
            "Missing "
            + ", ".join(missing)
            + ". Install test deps: pip install -r requirements-dev.txt"
        )


def _package_of(path: str) -> str:
    return Path(path).parts[0] if path else ""


def _load_coverage(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def package_rows(data: dict) -> list[dict[str, object]]:
    """Roll coverage.json totals up to top-level packages."""
    buckets: dict[str, dict[str, float]] = defaultdict(
        lambda: {"statements": 0, "covered": 0, "missing": 0}
    )
    for filename, info in (data.get("files") or {}).items():
        pkg = _package_of(filename)
        if pkg not in PACKAGES:
            continue
        summary = info.get("summary") or {}
        stmts = int(summary.get("num_statements") or 0)
        covered = int(summary.get("covered_lines") or 0)
        buckets[pkg]["statements"] += stmts
        buckets[pkg]["covered"] += covered
        buckets[pkg]["missing"] += max(stmts - covered, 0)

    rows = []
    for pkg in PACKAGES:
        stats = buckets.get(pkg)
        if not stats or not stats["statements"]:
            continue
        stmts = int(stats["statements"])
        covered = int(stats["covered"])
        rows.append(
            {
                "package": pkg,
                "statements": stmts,
                "covered": covered,
                "missing": int(stats["missing"]),
                "percent": 100.0 * covered / stmts if stmts else 0.0,
            }
        )
    return rows


def file_rows(data: dict, *, limit: int = 25) -> list[dict[str, object]]:
    """Lowest-coverage files first; skip untouched (0%) and fully covered files."""
    rows = []
    for filename, info in (data.get("files") or {}).items():
        if _package_of(filename) not in PACKAGES:
            continue
        summary = info.get("summary") or {}
        stmts = int(summary.get("num_statements") or 0)
        if stmts <= 0:
            continue
        covered = int(summary.get("covered_lines") or 0)
        percent = float(summary.get("percent_covered") or 0.0)
        if percent >= 100.0 or covered == 0:
            continue
        rows.append(
            {
                "file": filename,
                "statements": stmts,
                "covered": covered,
                "missing": max(stmts - covered, 0),
                "percent": percent,
            }
        )
    rows.sort(key=lambda row: (row["percent"], -row["statements"], row["file"]))
    return rows[:limit]


def format_text(data: dict) -> str:
    totals = data.get("totals") or {}
    stmts = int(totals.get("num_statements") or 0)
    covered = int(totals.get("covered_lines") or 0)
    percent = float(totals.get("percent_covered") or 0.0)
    lines = [
        "",
        "Coverage by package",
        f"{'Package':<12} {'Stmts':>8} {'Cover':>8} {'Miss':>8} {'Cover%':>8}",
        "-" * 48,
    ]
    for row in package_rows(data):
        lines.append(
            f"{row['package']:<12} {row['statements']:>8} {row['covered']:>8} "
            f"{row['missing']:>8} {row['percent']:>7.1f}%"
        )
    lines.append("-" * 48)
    lines.append(f"{'TOTAL':<12} {stmts:>8} {covered:>8} {max(stmts - covered, 0):>8} {percent:>7.1f}%")
    lines.append("")
    lines.append(f"HTML report: {HTML_DIR / 'index.html'}")
    return "\n".join(lines)


def format_markdown(data: dict) -> str:
    totals = data.get("totals") or {}
    stmts = int(totals.get("num_statements") or 0)
    covered = int(totals.get("covered_lines") or 0)
    percent = float(totals.get("percent_covered") or 0.0)
    lines = [
        "## Unit test coverage",
        "",
        f"**{percent:.1f}%** — {covered} of {stmts} statements",
        "",
        "| Package | Statements | Covered | Missing | Coverage |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in package_rows(data):
        lines.append(
            f"| `{row['package']}` | {row['statements']} | {row['covered']} | "
            f"{row['missing']} | {row['percent']:.1f}% |"
        )
    lines.append(f"| **Total** | **{stmts}** | **{covered}** | **{max(stmts - covered, 0)}** | **{percent:.1f}%** |")
    weakest = file_rows(data)
    if weakest:
        lines.extend(
            [
                "",
                "<details>",
                "<summary>Lowest-coverage files</summary>",
                "",
                "| File | Statements | Covered | Coverage |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row in weakest:
            lines.append(
                f"| `{row['file']}` | {row['statements']} | {row['covered']} | {row['percent']:.1f}% |"
            )
        lines.extend(["", "</details>"])
    return "\n".join(lines) + "\n"


def write_github_summary(data: dict) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as fh:
        fh.write(format_markdown(data))


def run_pytest(extra: list[str], *, quiet: bool) -> int:
    args = [
        sys.executable,
        "-m",
        "pytest",
        "--cov",
        "--cov-report=term:skip-covered",
        f"--cov-report=html:{HTML_DIR}",
        f"--cov-report=xml:{ROOT / 'coverage.xml'}",
        f"--cov-report=json:{COVERAGE_JSON}",
    ]
    if quiet:
        args.append("-q")
    args.extend(extra or ["tests"])
    return subprocess.call(args, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-q", "--quiet", action="store_true", help="Less pytest output")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra pytest args after --")
    opts = parser.parse_args(argv)
    extra = list(opts.pytest_args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    _require_dev_deps()
    code = run_pytest(extra, quiet=opts.quiet)
    if COVERAGE_JSON.exists():
        data = _load_coverage(COVERAGE_JSON)
        print(format_text(data), flush=True)
        write_github_summary(data)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
