"""Export aggregate-only presentation charts as 300 dpi PNG and SVG."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from viewer import charts, data_access


EXPORT_DIR = Path(__file__).resolve().parent / "exports"


def _save(stem: str, fig):
    charts.save_png_svg(fig, stem, str(EXPORT_DIR))
    plt.close(fig)


def _headline_frame(section: dict, label: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "label": label,
        "estimate": section["estimate"],
        "lower": section["wider_CI"][0],
        "upper": section["wider_CI"][1],
    }])


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if any(EXPORT_DIR.iterdir()):
        raise FileExistsError("viewer/exports is not empty; refusing to overwrite.")
    headline = data_access.load_json()
    sensitivity = data_access.load_csv("sensitivity_results.csv")
    claims = data_access.load_claims()
    sensitivity["counts_toward_robustness"] = sensitivity.get("in_robustness_label", pd.Series(False, index=sensitivity.index)).astype(str).str.lower().isin(["true", "1", "yes"])
    sensitivity["plot_label"] = sensitivity["analysis_id"].astype(str) + sensitivity["counts_toward_robustness"].map(lambda x: " *" if x else "")

    p = headline["valence_primary"]
    fig, _ = charts.plot_interval(_headline_frame(p, "Primary within-person estimate"), "label", "estimate", "lower", "upper",
                                  "Primary result", "headline.json", band=0.5, ylabel="Valence points per hour")
    _save("primary_result_forest", fig)

    per_hour_ids = ~sensitivity["analysis_id"].astype(str).isin(["7b_i_log1p_minutes", "7c_any_play"])
    per_hour = sensitivity.loc[per_hour_ids]
    fig, _ = charts.plot_interval(per_hour, "plot_label", "estimate", "wider_CI_lower", "wider_CI_upper",
                                  "Per-hour sensitivity analyses", "sensitivity_results.csv", band=0.5,
                                  ylabel="Valence points per hour")
    _save("per_hour_sensitivity_forest", fig)

    logrow = sensitivity.loc[sensitivity["analysis_id"].astype(str).eq("7b_i_log1p_minutes")]
    anyrow = sensitivity.loc[sensitivity["analysis_id"].astype(str).eq("7c_any_play")]
    fig, _ = charts.plot_interval_panels([
        {"frame": logrow, "label": "plot_label", "estimate": "estimate", "lower": "wider_CI_lower", "upper": "wider_CI_upper",
         "title": "7b_i: log exposure, per 1 SD", "xlabel": "Valence points per SD of log exposure"},
        {"frame": anyrow, "label": "plot_label", "estimate": "estimate", "lower": "wider_CI_lower", "upper": "wider_CI_upper",
         "title": "7c: any recorded play vs none", "xlabel": "Valence points"},
    ], "sensitivity_results.csv", "Separate-unit sensitivity panel")
    _save("separate_unit_panel", fig)

    ls = headline["life_satisfaction"]["fit1"]
    fig, _ = charts.plot_interval(_headline_frame(ls, "Life-satisfaction Fit 1"), "label", "estimate", "lower", "upper",
                                  "Life satisfaction (secondary)", "headline.json", band=0.5,
                                  ylabel="Life-satisfaction points per hour")
    _save("life_satisfaction_result", fig)

    flow = data_access.load_csv("cohort_flow.csv")
    flow["interval_count"] = pd.to_numeric(flow["interval_count"], errors="coerce")
    fig, _ = charts.plot_bar(flow, "stage", "interval_count", "Cohort flow: interval counts", "cohort_flow.csv", y_zero=True)
    _save("cohort_funnel", fig)

    gaps = data_access.load_csv("gap_cutoff_counts.csv")
    fig, _ = charts.plot_bar(gaps, "maximum_interval_length", "eligible_intervals", "Eligible intervals by gap cutoff",
                             "gap_cutoff_counts.csv", y_zero=True)
    _save("gap_cutoff_counts", fig)

    linkage = data_access.load_csv("exposure_by_linkage_group.csv")
    fig, _ = charts.plot_bar(linkage, "linkage_group", "zero_share", "Intervals with zero recorded sessions",
                             "exposure_by_linkage_group.csv", y_zero=True)
    _save("zero_share_by_linkage_group", fig)

    power = data_access.load_csv("power_simulation_summary.csv")
    mde = float(p["MDE_80_points_per_hour"])
    fig, _ = charts.plot_line(power, "true_b1", "empirical_power", "Simulated power by assumed value",
                              "power_simulation_summary.csv", horizontal=0.8)
    fig.axes[0].axvline(mde, color="#9b4f67", linestyle=":", linewidth=1.5, label=f"80% MDE: {mde:.2f}")
    fig.axes[0].legend(frameon=False)
    _save("power_curve", fig)

    index = """# Slide chart exports

All figures are generated from aggregate files in results/. PNG files are 300 dpi; each also has an SVG version. No model is fitted and no values are re-estimated.

| Image stem | Source file | Numbers shown |
|---|---|---|
| primary_result_forest | results/headline.json | Primary estimate and wider 95% interval; +/-0.5 band; zero reference |
| per_hour_sensitivity_forest | results/sensitivity_results.csv | Per-hour sensitivity estimates and wider intervals; robustness rows marked with * |
| separate_unit_panel | results/sensitivity_results.csv | 7b_i log-exposure per-SD estimate and 7c any-play estimate, on separate axes |
| life_satisfaction_result | results/headline.json | Secondary life-satisfaction estimate and wider interval; +/-0.5 band |
| cohort_funnel | results/cohort_flow.csv | Interval counts by cohort-flow stage |
| gap_cutoff_counts | results/gap_cutoff_counts.csv | Eligible intervals by maximum interval length |
| zero_share_by_linkage_group | results/exposure_by_linkage_group.csv | Zero-recorded-session share by linked-platform group |
| power_curve | results/power_simulation_summary.csv and headline.json | Simulated empirical power by assumed value, 80% line, and 80% MDE marker |

The claim wording displayed in the app is loaded verbatim from results/CLAIMS_REGISTER.csv.
"""
    (EXPORT_DIR / "INDEX.md").write_text(index, encoding="utf-8")
    print("Exported 8 chart pairs and INDEX.md.")


if __name__ == "__main__":
    main()
