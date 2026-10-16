"""Aggregate chart helpers. Missing observations are excluded, never zero-filled."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CAPTION_TEMPLATE = "Source: results/{file}. Aggregate study results; associations, not causal effects."
PALETTE = ["#315a7d", "#d17a22", "#4a8c73", "#9b4f67", "#7772a8", "#9a8b44"]


def _style(ax, title: str, xlabel: str, ylabel: str, source_file: str, zero_line: bool = False):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#dce2e8", linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    if zero_line:
        ax.axhline(0, color="#222222", linewidth=1, linestyle="--", zorder=1)
    ax.figure.text(0.01, 0.015, CAPTION_TEMPLATE.format(file=source_file), fontsize=8, color="#444444")
    ax.figure.tight_layout(rect=(0, 0.07, 1, 1))


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def plot_interval(frame: pd.DataFrame, label: str, estimate: str, lower: str, upper: str,
                  title: str, source_file: str, band: float | None = None,
                  zero_line: bool = True, ylabel: str = "Estimate", group: str | None = None):
    cols = [label, estimate, lower, upper] + ([group] if group else [])
    data = _numeric(frame[cols].copy(), [estimate, lower, upper])
    valid = data[[estimate, lower, upper] + ([group] if group else [])].notna().all(axis=1)
    data = data.loc[valid].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, max(3.4, 0.48 * len(data) + 1.4)))
    y = np.arange(len(data))
    if band is not None:
        ax.axvspan(-band, band, color="#f4d78c", alpha=0.35, zorder=0)
    group_names = data[group].astype(str).unique().tolist() if group else []
    for yi, (_, row) in zip(y, data.iterrows()):
        color_index = group_names.index(str(row[group])) if group else 0
        color = PALETTE[color_index % len(PALETTE)]
        ax.plot([row[lower], row[upper]], [yi, yi], color=color, linewidth=2, zorder=2)
        ax.scatter(row[estimate], yi, color=color, edgecolor="white", linewidth=0.7, s=48, zorder=3)
    if zero_line:
        ax.axvline(0, color="#222222", linewidth=1, linestyle="--", zorder=1)
    ax.set_yticks(y, data[label].astype(str).tolist())
    ax.invert_yaxis()
    ax.set_xlabel(ylabel)
    ax.set_ylabel("")
    if group:
        from matplotlib.lines import Line2D
        handles = [Line2D([0], [0], color=PALETTE[i % len(PALETTE)], label=name) for i, name in enumerate(group_names)]
        ax.legend(handles=handles, frameon=False)
    _style(ax, title, ylabel, "", source_file, zero_line=False)
    return fig, {"plotted": len(data), "excluded": len(frame) - len(data), "data": data}


def plot_bar(frame: pd.DataFrame, x: str, y: str, title: str, source_file: str,
             group: str | None = None, y_zero: bool = True):
    cols = [x, y] + ([group] if group else [])
    data = _numeric(frame[cols].copy(), [y])
    valid = data[[x, y] + ([group] if group else [])].notna().all(axis=1)
    data = data.loc[valid]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    if group:
        groups = data[group].astype(str).unique().tolist()
        cats = data[x].astype(str).unique().tolist()
        width = 0.8 / max(1, len(groups))
        for gi, g in enumerate(groups):
            sub = data.loc[data[group].astype(str).eq(g)].set_index(x)
            vals = [sub[y].iloc[0] if str(cat) in sub.index.astype(str) else np.nan for cat in cats]
            positions = np.arange(len(cats)) + (gi - (len(groups) - 1) / 2) * width
            ax.bar(positions, vals, width=width, label=g, color=PALETTE[gi % len(PALETTE)])
        ax.set_xticks(np.arange(len(cats)), cats, rotation=25, ha="right")
        ax.legend(frameon=False)
    else:
        ax.bar(data[x].astype(str), data[y], color=PALETTE[0])
        ax.tick_params(axis="x", rotation=25)
    if y_zero:
        ax.set_ylim(bottom=0)
    _style(ax, title, x, y, source_file)
    return fig, {"plotted": len(data), "excluded": len(frame) - len(data), "data": data}


def plot_line(frame: pd.DataFrame, x: str, y: str, title: str, source_file: str,
              group: str | None = None, horizontal: float | None = None,
              band: float | None = None, zero_line: bool = False, log_y: bool = False):
    cols = [x, y] + ([group] if group else [])
    data = _numeric(frame[cols].copy(), [x, y])
    valid = data[[x, y] + ([group] if group else [])].notna().all(axis=1)
    if log_y:
        valid &= data[y].gt(0)
    data = data.loc[valid].sort_values(x)
    fig, ax = plt.subplots(figsize=(8.5, 4.7))
    if group:
        groups = data[group].astype(str).unique().tolist()
        for i, g in enumerate(groups):
            sub = data.loc[data[group].astype(str).eq(g)]
            ax.plot(sub[x], sub[y], marker="o", label=g, color=PALETTE[i % len(PALETTE)])
        ax.legend(frameon=False)
    else:
        ax.plot(data[x], data[y], marker="o", color=PALETTE[0])
    if horizontal is not None:
        ax.axhline(horizontal, color=PALETTE[2], linestyle="--", linewidth=1.4)
    if band is not None:
        ax.axhspan(-band, band, color="#f4d78c", alpha=0.35)
    if zero_line:
        ax.axhline(0, color="#222222", linestyle="--", linewidth=1)
    if log_y:
        ax.set_yscale("log")
    _style(ax, title, x, y, source_file)
    return fig, {"plotted": len(data), "excluded": len(frame) - len(data), "data": data}


def plot_scatter(frame: pd.DataFrame, x: str, y: str, title: str, source_file: str,
                 group: str | None = None, log_y: bool = False, zero_line: bool = False):
    cols = [x, y] + ([group] if group else [])
    data = _numeric(frame[cols].copy(), [x, y])
    valid = data[[x, y] + ([group] if group else [])].notna().all(axis=1)
    if log_y:
        valid &= data[y].gt(0)
    data = data.loc[valid]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    if group:
        for i, g in enumerate(data[group].astype(str).unique()):
            sub = data.loc[data[group].astype(str).eq(g)]
            ax.scatter(sub[x], sub[y], label=g, alpha=0.8, color=PALETTE[i % len(PALETTE)])
        ax.legend(frameon=False)
    else:
        ax.scatter(data[x], data[y], color=PALETTE[0], alpha=0.8)
    if log_y:
        ax.set_yscale("log")
    if zero_line:
        ax.axhline(0, color="#222222", linestyle="--", linewidth=1)
    _style(ax, title, x, y, source_file)
    return fig, {"plotted": len(data), "excluded": len(frame) - len(data), "data": data}


def plot_histogram(frame: pd.DataFrame, x: str, title: str, source_file: str, bins: int = 20,
                   group: str | None = None):
    values = pd.to_numeric(frame[x], errors="coerce")
    valid = values.notna()
    if group:
        valid &= frame[group].notna()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    if group:
        groups = frame.loc[valid, group].astype(str).unique().tolist()
        for i, name in enumerate(groups):
            mask = valid & frame[group].astype(str).eq(name)
            ax.hist(values.loc[mask], bins=bins, alpha=0.6, color=PALETTE[i % len(PALETTE)],
                    edgecolor="white", label=name)
        ax.legend(frameon=False)
    else:
        ax.hist(values.loc[valid], bins=bins, color=PALETTE[0], edgecolor="white")
    _style(ax, title, x, "Count", source_file)
    return fig, {"plotted": int(valid.sum()), "excluded": int((~valid).sum()), "data": values.loc[valid]}


def save_png_svg(fig, stem: str, folder: str | None = None) -> tuple[bytes, bytes]:
    png = BytesIO()
    svg = BytesIO()
    fig.savefig(png, format="png", dpi=300, bbox_inches="tight")
    fig.savefig(svg, format="svg", bbox_inches="tight")
    if folder is not None:
        target = Path(folder)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{stem}.png").write_bytes(png.getvalue())
        (target / f"{stem}.svg").write_bytes(svg.getvalue())
    return png.getvalue(), svg.getvalue()


def plot_interval_panels(panels: list[dict], source_file: str, title: str):
    """Render differently scaled interval panels on separate axes."""
    height = max(3.2, max((len(p["frame"]) for p in panels), default=1) * 0.45 + 1.4)
    fig, axes = plt.subplots(len(panels), 1, figsize=(9, height * max(1, len(panels))), squeeze=False)
    counts = []
    for ax, panel in zip(axes.flat, panels):
        data = panel["frame"].copy()
        cols = [panel["label"], panel["estimate"], panel["lower"], panel["upper"]]
        data = _numeric(data[cols], [panel["estimate"], panel["lower"], panel["upper"]])
        valid = data[[panel["estimate"], panel["lower"], panel["upper"]]].notna().all(axis=1)
        data = data.loc[valid].reset_index(drop=True)
        if panel.get("band") is not None:
            ax.axvspan(-panel["band"], panel["band"], color="#f4d78c", alpha=0.35, zorder=0)
        for yi, (_, row) in enumerate(data.iterrows()):
            ax.plot([row[panel["lower"]], row[panel["upper"]]], [yi, yi], color=PALETTE[0], linewidth=2)
            ax.scatter(row[panel["estimate"]], yi, color=PALETTE[1], edgecolor="white", s=48, zorder=3)
        ax.axvline(0, color="#222222", linewidth=1, linestyle="--")
        ax.set_yticks(np.arange(len(data)), data[panel["label"]].astype(str).tolist())
        ax.invert_yaxis()
        ax.set_xlabel(panel["xlabel"])
        ax.set_title(panel["title"], loc="left", fontsize=12, fontweight="bold")
        ax.grid(axis="x", color="#dce2e8", linewidth=0.7)
        counts.append({"plotted": len(data), "excluded": len(panel["frame"]) - len(data), "data": data})
    fig.suptitle(title, x=0.01, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.01, 0.01, CAPTION_TEMPLATE.format(file=source_file), fontsize=8, color="#444444")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    return fig, counts
