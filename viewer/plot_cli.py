"""Command-line plotting for aggregate CSV files in results/."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from viewer import charts, data_access


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Plot one aggregate GameWell results CSV.")
    p.add_argument("--file", required=True, help="CSV basename from results/")
    p.add_argument("--kind", required=True, choices=["bar", "line", "scatter", "histogram", "interval"])
    p.add_argument("--x", help="X/category column")
    p.add_argument("--y", help="Y/numeric column")
    p.add_argument("--group", help="Optional group/colour column")
    p.add_argument("--label", help="Interval plot label column")
    p.add_argument("--est", help="Interval estimate column")
    p.add_argument("--lo", help="Interval lower-bound column")
    p.add_argument("--hi", help="Interval upper-bound column")
    p.add_argument("--title", default=None)
    p.add_argument("--band", type=float, default=None)
    p.add_argument("--out", required=True, help="PNG or SVG output path")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    frame = data_access.load_csv(args.file)
    title = args.title or f"{args.file}: {args.kind}"
    if args.kind == "interval":
        required = [args.label, args.est, args.lo, args.hi]
        if any(value is None for value in required):
            raise SystemExit("interval plots require --label, --est, --lo, and --hi")
        fig, stats = charts.plot_interval(frame, args.label, args.est, args.lo, args.hi,
                                          title, args.file, band=args.band)
    elif args.kind == "histogram":
        if not args.y:
            raise SystemExit("histogram requires --y")
        fig, stats = charts.plot_histogram(frame, args.y, title, args.file)
    else:
        if not args.x or not args.y:
            raise SystemExit(f"{args.kind} requires --x and --y")
        if args.kind == "bar":
            fig, stats = charts.plot_bar(frame, args.x, args.y, title, args.file, group=args.group, y_zero=True)
        elif args.kind == "line":
            fig, stats = charts.plot_line(frame, args.x, args.y, title, args.file, group=args.group, band=args.band)
        else:
            fig, stats = charts.plot_scatter(frame, args.x, args.y, title, args.file, group=args.group)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dpi = 300 if output.suffix.lower() == ".png" else None
    fig.savefig(output, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved chart; {stats['plotted']} rows plotted, {stats['excluded']} excluded for missing values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
