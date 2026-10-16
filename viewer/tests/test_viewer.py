from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from viewer import charts, data_access


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "viewer" / "app.py"


def test_every_results_csv_loads_and_has_no_participant_id_columns():
    id_like = re.compile(r"^(?:pid|participant(?:_id)?|user(?:_id)?)$", re.I)
    csv_files = data_access.list_result_files(".csv")
    assert csv_files
    for name in csv_files:
        frame = data_access.load_csv(name)
        assert isinstance(frame, pd.DataFrame)
        assert not any(id_like.fullmatch(str(col).strip()) for col in frame.columns), name


@pytest.mark.parametrize("kind", ["bar", "line", "scatter", "histogram", "interval"])
def test_each_chart_type_renders(kind):
    frame = pd.DataFrame({
        "label": ["A", "B", "C"], "x": [1, 2, 3], "y": [2.0, 3.0, 4.0],
        "lo": [1.0, 2.0, 3.0], "hi": [3.0, 4.0, 5.0], "group": ["g1", "g1", "g2"],
    })
    if kind == "bar":
        fig, _ = charts.plot_bar(frame, "label", "y", "bar", "test.csv", group="group")
    elif kind == "line":
        fig, _ = charts.plot_line(frame, "x", "y", "line", "test.csv", group="group")
    elif kind == "scatter":
        fig, _ = charts.plot_scatter(frame, "x", "y", "scatter", "test.csv", group="group")
    elif kind == "histogram":
        fig, _ = charts.plot_histogram(frame, "y", "histogram", "test.csv")
    else:
        fig, _ = charts.plot_interval(frame, "label", "y", "lo", "hi", "interval", "test.csv", band=0.5)
    assert fig.axes
    plt.close(fig)


def test_forest_draws_zero_line_and_sesoi_band():
    frame = pd.DataFrame({"label": ["estimate"], "est": [0.1], "lo": [-0.1], "hi": [0.3]})
    fig, _ = charts.plot_interval(frame, "label", "est", "lo", "hi", "forest", "headline.json", band=0.5)
    ax = fig.axes[0]
    assert any(np.allclose(line.get_xdata(), [0, 0]) for line in ax.lines)
    assert any(patch.get_alpha() == pytest.approx(0.35) for patch in ax.patches)
    plt.close(fig)


def test_primary_chart_values_match_headline():
    headline = data_access.load_json()
    result = headline["valence_primary"]
    frame = pd.DataFrame([{
        "label": "primary", "estimate": result["estimate"],
        "lo": result["wider_CI"][0], "hi": result["wider_CI"][1],
    }])
    fig, stats = charts.plot_interval(frame, "label", "estimate", "lo", "hi", "primary", "headline.json")
    plotted = stats["data"].iloc[0]
    assert plotted["estimate"] == result["estimate"]
    assert plotted["lo"] == result["wider_CI"][0]
    assert plotted["hi"] == result["wider_CI"][1]
    plt.close(fig)


def test_missing_values_are_excluded_not_zero_filled():
    frame = pd.DataFrame({"category": ["observed", "missing"], "value": [4.0, np.nan]})
    fig, result = charts.plot_bar(frame, "category", "value", "missingness", "test.csv")
    assert result["plotted"] == 1
    assert result["excluded"] == 1
    assert result["data"]["value"].tolist() == [4.0]
    plt.close(fig)


@pytest.mark.parametrize("page", [
    "Overview", "Main result and robustness", "Life satisfaction",
    "Who is in the analysis", "Power and diagnostics", "Fit ledger",
    "Explore any table", "How to use",
])
def test_streamlit_page_runs_without_exception(page):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    app.selectbox(key="page").set_value(page).run()
    assert not app.exception, page
