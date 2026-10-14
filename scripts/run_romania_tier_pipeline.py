#!/usr/bin/env python3
"""Run load_fmsave_frames, then generate_romania_tier_reports.

Each step remains runnable on its own::

    .venv/bin/python scripts/load_fmsave_frames.py …
    .venv/bin/python scripts/generate_romania_tier_reports.py …

Pipeline (export required so reports have input CSVs)::

    .venv/bin/python scripts/run_romania_tier_pipeline.py \\
        -n 164 --export-names "scripts/exports/YR 100/100yr_romania_year.csv"
    # → reports land in scripts/exports/YR 100/reports/

    .venv/bin/python scripts/run_romania_tier_pipeline.py \\
        -n 164 --export-names "scripts/exports/YR 100/100yr_romania_year.csv" \\
        --output-dir "scripts/exports/YR 100/custom-reports"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "scripts" / "load_fmsave_frames.py"
REPORTS = ROOT / "scripts" / "generate_romania_tier_reports.py"


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--export-names",
        type=Path,
        required=True,
        metavar="NAME",
        help="Same as load_fmsave_frames --export-names; parent dir becomes "
        "report --input-dir (and default --output-dir parent/reports).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Report output directory (default: <export-names parent>/reports).",
    )
    parser.add_argument(
        "--tiers",
        type=int,
        nargs="+",
        default=None,
        help="Tiers for generate_romania_tier_reports (default: that script's default).",
    )
    # Remaining args (e.g. -n, -t) are forwarded to load_fmsave_frames.
    return parser.parse_known_args(argv)


def resolve_path(path: Path) -> Path:
    path = path.expanduser()
    return path if path.is_absolute() else ROOT / path


def run_step(script: Path, args: list[str]) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"\n=== {' '.join(cmd)} ===\n", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> None:
    args, load_extra = parse_args(argv)
    export_names = resolve_path(args.export_names)
    input_dir = export_names.parent
    output_dir = (
        resolve_path(args.output_dir)
        if args.output_dir is not None
        else input_dir / "reports"
    )

    load_args = ["--export-names", str(export_names), *load_extra]
    run_step(LOAD, load_args)

    report_args = [
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
    ]
    if args.tiers is not None:
        report_args.extend(["--tiers", *map(str, args.tiers)])
    run_step(REPORTS, report_args)


if __name__ == "__main__":
    main()
