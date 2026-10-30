#!/usr/bin/env python3
r"""Run the GameWell primary analysis and list the presentation files.

Usage:
    .\.venv\Scripts\python.exe run_analysis.py

This calls code/gamewell_analysis.py on the frozen interval dataset, writes
the figures and tables to outputs/, and prints a checklist of the files to
present. It never modifies the input data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "code" / "gamewell_analysis.py"
OUT = ROOT / "outputs"

DATA = Path(
    r"E:\Code\ids\digital-wellbeing-open-play-511bc60\analysis"
    r"\gamewell_interval_dataset_2026-10-15\gamewell_daily_intervals.csv.gz"
)

PRESENTATION_FILES = [
    "figures/fig1_cohort_flow.png",
    "figures/fig2_exposure_distribution.png",
    "figures/fig3_exposure_within_distribution.png",
    "figures/fig4_b1_forest.png",
    "figures/fig5_residual_histogram.png",
    "figures/fig6_residual_qq.png",
    "figures/fig7_residuals_by_fitted.png",
    "b1_summary.csv",
    "fixed_effects.csv",
    "cohort_flow.csv",
    "cohort_gate.csv",
    "fit_status.csv",
    "residual_summary.csv",
    "descriptives.csv",
    "analysis_report.md",
]


def main() -> int:
    if not ANALYSIS.exists():
        print(f"Missing analysis program: {ANALYSIS}")
        return 1
    if not DATA.exists():
        print(f"Missing interval data: {DATA}")
        return 1

    command = [
        sys.executable,
        str(ANALYSIS),
        "--data",
        str(DATA),
        "--out",
        str(OUT),
    ]
    print("Running:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"Analysis failed with exit code {result.returncode}.")
        return result.returncode

    print("\nPresentation files:")
    for relative_path in PRESENTATION_FILES:
        path = OUT / relative_path
        status = "OK" if path.exists() else "MISSING"
        print(f"  [{status}] {path}")

    print(f"\nAll outputs are in: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
