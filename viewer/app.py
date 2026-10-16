"""Streamlit viewer for aggregate files in results/ only."""
from __future__ import annotations

from io import BytesIO

import matplotlib
import numpy as np
import pandas as pd
import streamlit as st

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from viewer import charts, data_access


PAGES = [
    "Overview", "Main result and robustness", "Life satisfaction",
    "Who is in the analysis", "Power and diagnostics", "Fit ledger",
    "Explore any table", "How to use",
]
ROBUSTNESS_IDS = {
    "7a_30h", "7a_36h", "7a_72h", "7a_no_cutoff", "7b_i_log1p_minutes",
    "7b_ii_cap_99", "7e_min5_intervals", "7f_no_zero_valence",
    "7g_random_slope", "7h_CR2_primary_no_refit",
}


def _truth(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _plot(fig, count=None):
    st.pyplot(fig, clear_figure=False)
    plt.close(fig)
    if count is not None:
        st.caption(f"{count['plotted']} rows plotted / {count['excluded']} rows excluded because of missing values")


def _metric_ci(heading: str, estimate: float, lower: float, upper: float, unit: str):
    st.metric(heading, f"{estimate:.2f} {unit}", f"95% interval {lower:.2f} to {upper:.2f}")


def _primary_frame(headline: dict) -> pd.DataFrame:
    p = headline["valence_primary"]
    lo, hi = p["wider_CI"]
    return pd.DataFrame([{"label": "Within-person recorded play", "estimate": p["estimate"], "lower": lo, "upper": hi}])


def render_overview():
    claims = data_access.load_claims()
    headline = data_access.load_json()
    st.title("GameWell results viewer")
    st.info("This viewer shows aggregate study results only. Participant-level data are not included in this repository.")
    st.subheader("Research question")
    st.write(claims["C1"])
    st.subheader("Primary result")
    st.write(claims["C2"])
    p = headline["valence_primary"]
    _metric_ci("Within-person estimate", p["estimate"], *p["wider_CI"], "points per hour")
    c1, c2, c3 = st.columns(3)
    c1.metric("Intervals", f"{p['cohort_counts']['intervals']:,}")
    c2.metric("Participants", f"{p['cohort_counts']['participants']:,}")
    c3.metric("Participants with exposure variation", f"{p['cohort_counts']['participants_with_exposure_variation']:,}")


def render_main_result():
    headline = data_access.load_json()
    sensitivity = data_access.load_csv("sensitivity_results.csv")
    p = headline["valence_primary"]
    st.title("Main result and robustness")
    st.write(data_access.load_claims()["C2"])
    _metric_ci("Primary within-person estimate", p["estimate"], *p["wider_CI"], "valence points per hour")
    frame = _primary_frame(headline)
    fig, count = charts.plot_interval(frame, "label", "estimate", "lower", "upper",
                                      "Primary result", "headline.json", band=0.5,
                                      ylabel="Valence points per hour")
    _plot(fig, count)
    st.caption("Shading shows the prespecified +/-0.5 points-per-hour band.")

    ids = sensitivity["analysis_id"].astype(str)
    sensitivity = sensitivity.copy()
    if "in_robustness_label" in sensitivity:
        sensitivity["counts_toward_robustness"] = sensitivity["in_robustness_label"].map(_truth)
    else:
        sensitivity["counts_toward_robustness"] = ids.isin(ROBUSTNESS_IDS)
    sensitivity["plot_label"] = sensitivity["analysis_id"].astype(str) + sensitivity["counts_toward_robustness"].map(lambda x: " *" if x else "")
    st.markdown("* Rows marked with an asterisk count toward the prespecified robustness label.")
    per_hour = sensitivity.loc[~ids.isin(["7b_i_log1p_minutes", "7c_any_play"])].copy()
    st.markdown("#### Per-hour sensitivity analyses")
    fig, count = charts.plot_interval(per_hour, "plot_label", "estimate", "wider_CI_lower", "wider_CI_upper",
                                      "Per-hour specifications", "sensitivity_results.csv", band=0.5,
                                      ylabel="Valence points per hour")
    _plot(fig, count)
    logrow = sensitivity.loc[ids.eq("7b_i_log1p_minutes")].copy()
    st.markdown("#### Log exposure: per 1 SD of within-person log exposure")
    fig, count = charts.plot_interval(logrow, "plot_label", "estimate", "wider_CI_lower", "wider_CI_upper",
                                      "Log exposure specification", "sensitivity_results.csv",
                                      ylabel="Valence points per SD of log exposure")
    _plot(fig, count)
    anyrow = sensitivity.loc[ids.eq("7c_any_play")].copy()
    st.markdown("#### Any recorded play versus none")
    fig, count = charts.plot_interval(anyrow, "plot_label", "estimate", "wider_CI_lower", "wider_CI_upper",
                                      "Any-play specification", "sensitivity_results.csv",
                                      ylabel="Valence points")
    _plot(fig, count)
    st.dataframe(sensitivity[["analysis_id", "estimate", "wider_CI_lower", "wider_CI_upper", "counts_toward_robustness", "fit_status"]], use_container_width=True)


def render_life_satisfaction():
    headline = data_access.load_json()
    fixed = data_access.load_csv("fixed_effects_ls.csv")
    ls = headline["life_satisfaction"]["fit1"]
    st.title("Life satisfaction")
    st.warning("Secondary analysis; life satisfaction is kept separate from mood (affective valence).")
    st.write(data_access.load_claims()["C6"])
    _metric_ci("Secondary within-person estimate", ls["estimate"], *ls["wider_CI"], "points per hour")
    frame = pd.DataFrame([{"label": "Fit 1: full eligible cohort", "estimate": ls["estimate"], "lower": ls["wider_CI"][0], "upper": ls["wider_CI"][1]}])
    fig, count = charts.plot_interval(frame, "label", "estimate", "lower", "upper",
                                      "Life-satisfaction secondary result", "headline.json", band=0.5,
                                      ylabel="Life-satisfaction points per hour")
    _plot(fig, count)
    st.caption("Fixed effects table from results/fixed_effects_ls.csv")
    st.dataframe(fixed, use_container_width=True)


def render_cohort():
    st.title("Who is in the analysis")
    flow = data_access.load_csv("cohort_flow.csv")
    gaps = data_access.load_csv("gap_cutoff_counts.csv")
    groups = data_access.load_csv("exposure_by_linkage_group.csv")
    st.subheader("Cohort flow")
    st.dataframe(flow, use_container_width=True)
    st.subheader("Interval gap cutoffs")
    st.dataframe(gaps, use_container_width=True)
    st.subheader("Recorded zero sessions by linked platform group")
    st.info("Zero recorded sessions is shown separately from missing exposure. A recorded zero does not certify complete telemetry capture.")
    st.dataframe(groups, use_container_width=True)
    for file_name in ["descriptive_exposure.csv", "descriptive_outcomes.csv", "DESCRIPTIVE_COHORT_AGGREGATES.csv"]:
        st.subheader(file_name)
        st.dataframe(data_access.load_csv(file_name), use_container_width=True)
    for file_name in ["affective_valence_histogram.svg", "life_satisfaction_histogram.svg", "console_minutes_histogram.svg", "linked_console_exposure_histogram.svg"]:
        st.caption(charts.CAPTION_TEMPLATE.format(file=file_name))
        st.html(data_access.load_text(file_name))


def render_power_diagnostics():
    st.title("Power and diagnostics")
    power = data_access.load_csv("power_simulation_summary.csv")
    headline = data_access.load_json()
    p = headline["valence_primary"]
    mde = float(p["MDE_80_points_per_hour"])
    fig, count = charts.plot_line(power, "true_b1", "empirical_power", "Simulated power by assumed within-person value",
                                 "power_simulation_summary.csv", horizontal=0.8)
    fig.axes[0].axvline(mde, color="#9b4f67", linestyle=":", linewidth=1.5, label=f"80% MDE: {mde:.2f}")
    fig.axes[0].legend(frameon=False)
    _plot(fig, count)
    st.caption(f"80% minimum detectable estimate from headline.json: {mde:.3f} valence points per hour.")
    st.dataframe(power, use_container_width=True)
    diag = data_access.load_csv("diagnostics_summary.csv")
    st.subheader("Residual diagnostics summaries")
    model = st.selectbox("Diagnostic model", sorted(diag["model"].dropna().astype(str).unique()), key="diag_model")
    st.dataframe(diag.loc[diag["model"].astype(str).eq(model)], use_container_width=True)


def render_ledger():
    ledger = data_access.load_csv("FIT_LEDGER.csv")
    st.title("Fit ledger")
    stages = ["All"] + sorted(ledger["stage"].dropna().astype(str).unique().tolist())
    stage = st.selectbox("Filter by stage", stages, key="ledger_stage")
    shown = ledger if stage == "All" else ledger.loc[ledger["stage"].astype(str).eq(stage)]
    st.dataframe(shown, use_container_width=True)


def render_explorer():
    st.title("Explore any results table")
    files = data_access.list_result_files(".csv")
    preferred = "sensitivity_results.csv" if "sensitivity_results.csv" in files else files[0]
    file_name = st.selectbox("CSV file", files, index=files.index(preferred), key="explore_file")
    original = data_access.load_csv(file_name)
    descriptions = data_access.column_descriptions(file_name)
    st.dataframe(pd.DataFrame({"column": original.columns, "description": [descriptions.get(c, "") for c in original.columns]}), use_container_width=True)
    st.dataframe(original.head(20), use_container_width=True)
    frame = original.copy()
    filter_col = st.selectbox("Optional row filter column", ["(none)"] + frame.columns.astype(str).tolist(), key="filter_col")
    filter_text = st.text_input("Keep rows containing this text (blank means no filter)", key="filter_text")
    if filter_col != "(none)" and filter_text:
        mask = frame[filter_col].astype("string").str.contains(filter_text, case=False, na=False)
        frame = frame.loc[mask].copy()
    kind = st.selectbox("Chart type", ["bar", "line", "scatter", "histogram", "point-with-interval"], key="chart_kind")
    numeric = frame.select_dtypes(include=[np.number]).columns.astype(str).tolist()
    all_columns = frame.columns.astype(str).tolist()
    x = st.selectbox("X / label column", all_columns, key="chart_x")
    ys = st.multiselect("Y column(s)", numeric, default=numeric[:1], key="chart_y")
    color_options = ["(none)"] + all_columns
    group = st.selectbox("Optional group / colour column", color_options, key="chart_group")
    group = None if group == "(none)" else group
    title = st.text_input("Chart title", value=f"{file_name}: {kind}", key="chart_title")
    x_label = st.text_input("X axis label", value=x, key="x_label")
    y_label = st.text_input("Y axis label", value=(ys[0] if ys else "Value"), key="y_label")
    zero_line = st.checkbox("Show zero reference line", value=True, key="zero_line")
    if kind == "bar":
        st.checkbox("Y-axis starts at zero (enforced for bars)", value=True, disabled=True, key="bar_zero")
        log_y = st.checkbox("Logarithmic y-axis", value=False, key="bar_log")
    else:
        log_y = st.checkbox("Logarithmic y-axis", value=False, key="other_log")
    if log_y:
        st.warning("Log scale displays only positive values; zero, negative, and missing values are excluded from the plot.")
    use_band = st.checkbox("Shade +/-0.5 band", value=False, key="band")
    if use_band:
        st.caption("This band applies to per-hour analyses only. Do not use it for other units.")

    if file_name == "sensitivity_results.csv" and "analysis_id" in frame:
        ids = set(frame["analysis_id"].astype(str))
        if {"7b_i_log1p_minutes", "7c_any_play"}.issubset(ids):
            st.warning("This selection includes 7b_i and 7c, which use different units. Plot them in separate panels.")

    figures = []
    counts = []
    if kind == "histogram":
        if ys:
            fig, summary = charts.plot_histogram(frame, ys[0], title, file_name, group=group)
            figures.append((fig, summary))
    elif kind == "point-with-interval":
        estimate = st.selectbox("Estimate column", numeric, key="est_col")
        lower = st.selectbox("Lower bound column", numeric, key="lo_col")
        upper = st.selectbox("Upper bound column", numeric, key="hi_col")
        band = 0.5 if use_band else None
        fig, summary = charts.plot_interval(frame, x, estimate, lower, upper, title, file_name,
                                            band=band, zero_line=zero_line, ylabel=y_label, group=group)
        figures.append((fig, summary))
    else:
        for y in ys:
            chart_title = title if len(ys) == 1 else f"{title}: {y}"
            if kind == "bar":
                fig, summary = charts.plot_bar(frame, x, y, chart_title, file_name, group=group, y_zero=True)
            elif kind == "line":
                fig, summary = charts.plot_line(frame, x, y, chart_title, file_name, group=group,
                                                band=(0.5 if use_band else None), zero_line=zero_line, log_y=log_y)
            else:
                fig, summary = charts.plot_scatter(frame, x, y, chart_title, file_name, group=group,
                                                   log_y=log_y, zero_line=zero_line)
            figures.append((fig, summary))
    if not figures:
        st.info("Choose a numeric y column to draw a chart.")
    for fig, summary in figures:
        _plot(fig, summary)
        counts.append(summary)
        png, svg = charts.save_png_svg(fig, "download")
        st.download_button("Download PNG", png, file_name="gamewell_chart.png", mime="image/png")
        st.download_button("Download SVG", svg, file_name="gamewell_chart.svg", mime="image/svg+xml")
    st.download_button("Download filtered CSV", frame.to_csv(index=False, na_rep=""), file_name=file_name, mime="text/csv")


def render_how_to_use():
    st.title("How to use")
    st.markdown("""
1. Use the sidebar to choose a page.
2. Start with Overview for the registered wording and headline figures.
3. Use Main result and robustness or Life satisfaction to view estimates and intervals.
4. Use Who is in the analysis, Power and diagnostics, and Fit ledger for the aggregate source tables.
5. In Explore any table, choose a results CSV, filter rows if needed, then choose a chart type and fields.
6. Use the download buttons to save a chart or filtered aggregate table.

The viewer reads files from results/ only. It does not accept uploads or load participant-level files.
""")


PAGE_RENDERERS = {
    "Overview": render_overview,
    "Main result and robustness": render_main_result,
    "Life satisfaction": render_life_satisfaction,
    "Who is in the analysis": render_cohort,
    "Power and diagnostics": render_power_diagnostics,
    "Fit ledger": render_ledger,
    "Explore any table": render_explorer,
    "How to use": render_how_to_use,
}


def main():
    st.set_page_config(page_title="GameWell aggregate viewer", layout="wide")
    st.sidebar.title("GameWell")
    page = st.sidebar.selectbox("Page", PAGES, key="page")
    PAGE_RENDERERS[page]()


if __name__ == "__main__":
    main()
