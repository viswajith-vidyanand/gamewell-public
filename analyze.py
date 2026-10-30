#!/usr/bin/env python3
r"""
Simple GameWell analysis.

This is a compact, self-contained project:

    data/gamewell_daily_intervals.csv.gz  ->  analyze.py  ->  outputs/

It uses pandas for data handling, matplotlib for graphs, and scikit-learn
for a simple predictive comparison:

    * mean baseline
    * linear regression
    * random forest

The question is whether recorded linked-console play is associated with
later affective valence. The models are predictive/exploratory; they do not
establish causation.

Run:
    ..\.venv\Scripts\python.exe analyze.py
or:
    python analyze.py

No data file is modified. Only aggregate results are written.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

# ---------------------------------------------------------------------------
# Paths and settings
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "gamewell_daily_intervals.csv.gz"
OUT = ROOT / "outputs"
FIG = OUT / "figures"

RANDOM_STATE = 42
TEST_SIZE = 0.20
SESOI = 0.5  # smallest effect size of interest, valence points per hour

FEATURES = [
    "prior_valence",
    "exposure_within",
    "exposure_between",
    "duration_hours",
]

FEATURE_LABELS = {
    "prior_valence": "Prior valence",
    "exposure_within": "Exposure: within person",
    "exposure_between": "Exposure: person average",
    "duration_hours": "Interval duration",
}


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------
def as_linked(series: pd.Series) -> pd.Series:
    """Interpret common true/false encodings; missing becomes not linked."""
    text = series.astype("string").str.strip().str.lower()
    return text.isin(["true", "1", "yes", "y", "t"]).fillna(False)


def load_and_prepare() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the interval file and build the analysis cohort."""
    if not DATA.exists():
        raise FileNotFoundError(f"Data file not found: {DATA}")

    raw = pd.read_csv(DATA)

    required = [
        "participant_id",
        "xbox_linked",
        "nintendo_linked",
        "interval_duration_hours",
        "prior_affective_valence",
        "later_affective_valence",
        "recorded_linked_console_minutes_unique",
    ]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    participant = raw["participant_id"].astype("string").str.strip()
    duration = pd.to_numeric(raw["interval_duration_hours"], errors="coerce")
    prior = pd.to_numeric(raw["prior_affective_valence"], errors="coerce")
    later = pd.to_numeric(raw["later_affective_valence"], errors="coerce")
    exposure_minutes = pd.to_numeric(
        raw["recorded_linked_console_minutes_unique"], errors="coerce"
    )

    linked = as_linked(raw["xbox_linked"]) | as_linked(raw["nintendo_linked"])
    valence_ok = prior.notna() & later.notna()
    duration_ok = duration.notna() & (duration > 0) & (duration <= 48)
    exposure_ok = exposure_minutes.notna()

    masks = [
        ("All intervals in file", pd.Series(True, index=raw.index)),
        ("Linked Xbox and/or Nintendo", linked),
        ("Valence at both endpoints", linked & valence_ok),
        ("Duration 0-48 hours", linked & valence_ok & duration_ok),
        (
            "Exposure non-missing (analysis cohort)",
            linked & valence_ok & duration_ok & exposure_ok,
        ),
    ]

    flow_rows = []
    for label, mask in masks:
        flow_rows.append(
            {
                "stage": label,
                "intervals": int(mask.sum()),
                "participants": int(participant[mask].nunique()),
            }
        )
    flow = pd.DataFrame(flow_rows)

    cohort_mask = masks[-1][1]
    cohort = pd.DataFrame(
        {
            "participant": participant[cohort_mask].astype(str),
            "prior_valence": prior[cohort_mask].astype(float),
            "later_valence": later[cohort_mask].astype(float),
            "exposure_hours": exposure_minutes[cohort_mask].astype(float) / 60.0,
            "duration_hours": duration[cohort_mask].astype(float),
        }
    ).reset_index(drop=True)

    if cohort.empty:
        raise ValueError("The analysis cohort is empty.")

    # Within-person and between-person exposure.
    cohort["exposure_between"] = cohort.groupby("participant")[
        "exposure_hours"
    ].transform("mean")
    cohort["exposure_within"] = (
        cohort["exposure_hours"] - cohort["exposure_between"]
    )

    # Participant-mean prior valence, used only for descriptive context.
    cohort["prior_between"] = cohort.groupby("participant")[
        "prior_valence"
    ].transform("mean")
    cohort["prior_within"] = cohort["prior_valence"] - cohort["prior_between"]

    return cohort, flow


def make_descriptives(cohort: pd.DataFrame) -> pd.DataFrame:
    """Aggregate descriptive statistics for the cohort."""
    within_valence = cohort["later_valence"] - cohort.groupby("participant")[
        "later_valence"
    ].transform("mean")
    group_sizes = cohort.groupby("participant").size()

    rows = [
        ("n_intervals", len(cohort), "intervals"),
        ("n_participants", cohort["participant"].nunique(), "participants"),
        (
            "participants_with_exposure_variation",
            int((cohort.groupby("participant")["exposure_hours"].nunique() > 1).sum()),
            "participants",
        ),
        ("interval_duration_median", cohort["duration_hours"].median(), "hours"),
        ("exposure_mean", cohort["exposure_hours"].mean(), "hours"),
        ("exposure_SD", cohort["exposure_hours"].std(ddof=1), "hours"),
        ("exposure_median", cohort["exposure_hours"].median(), "hours"),
        (
            "exposure_zero_percent",
            100.0 * (cohort["exposure_hours"] == 0).mean(),
            "percent",
        ),
        ("prior_valence_mean", cohort["prior_valence"].mean(), "points"),
        ("prior_valence_SD", cohort["prior_valence"].std(ddof=1), "points"),
        ("later_valence_mean", cohort["later_valence"].mean(), "points"),
        ("later_valence_SD", cohort["later_valence"].std(ddof=1), "points"),
        ("within_person_valence_SD", within_valence.std(ddof=1), "points"),
        ("exposure_within_SD", cohort["exposure_within"].std(ddof=1), "hours"),
        ("min_intervals_per_participant", int(group_sizes.min()), "intervals"),
        ("median_intervals_per_participant", group_sizes.median(), "intervals"),
        ("max_intervals_per_participant", int(group_sizes.max()), "intervals"),
    ]
    return pd.DataFrame(rows, columns=["measure", "value", "unit"], dtype=object)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def fit_models(cohort: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Fit baseline, linear and random-forest models on a participant split."""
    x = cohort[FEATURES].to_numpy(dtype=float)
    y = cohort["later_valence"].to_numpy(dtype=float)
    groups = cohort["participant"].to_numpy()

    splitter = GroupShuffleSplit(
        n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    train_index, test_index = next(splitter.split(x, y, groups))

    x_train, x_test = x[train_index], x[test_index]
    y_train, y_test = y[train_index], y[test_index]

    models = {
        "Mean baseline": DummyRegressor(strategy="mean"),
        "Linear regression": LinearRegression(),
        "Random forest": RandomForestRegressor(
            n_estimators=400,
            min_samples_leaf=5,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
    }

    metric_rows = []
    predictions = {}
    for name, model in models.items():
        model.fit(x_train, y_train)
        train_prediction = model.predict(x_train)
        test_prediction = model.predict(x_test)
        predictions[name] = test_prediction

        metric_rows.append(
            {
                "model": name,
                "train_R2": r2_score(y_train, train_prediction),
                "test_R2": r2_score(y_test, test_prediction),
                "test_MAE": mean_absolute_error(y_test, test_prediction),
                "test_RMSE": float(
                    np.sqrt(mean_squared_error(y_test, test_prediction))
                ),
                "n_train": len(train_index),
                "n_test": len(test_index),
                "participants_train": int(
                    cohort.iloc[train_index]["participant"].nunique()
                ),
                "participants_test": int(
                    cohort.iloc[test_index]["participant"].nunique()
                ),
            }
        )

    metrics = pd.DataFrame(metric_rows)

    # Permutation importance: how much test error increases when a feature
    # is shuffled. This works for any model, including the random forest.
    permutation = permutation_importance(
        models["Random forest"],
        x_test,
        y_test,
        n_repeats=20,
        random_state=RANDOM_STATE,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
    )
    importance = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance_mean": permutation.importances_mean,
            "importance_sd": permutation.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)

    linear_coefficients = pd.DataFrame(
        {
            "feature": FEATURES,
            "coefficient": models["Linear regression"].coef_,
        }
    )

    context = {
        "models": models,
        "predictions": predictions,
        "x_test": x_test,
        "y_test": y_test,
        "train_index": train_index,
        "test_index": test_index,
    }
    return metrics, importance, linear_coefficients, context


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=160, bbox_inches="tight")
    plt.close(fig)


def make_figures(
    cohort: pd.DataFrame,
    flow: pd.DataFrame,
    metrics: pd.DataFrame,
    importance: pd.DataFrame,
    context: dict,
) -> None:
    """Create the presentation figures."""
    FIG.mkdir(parents=True, exist_ok=True)

    # 1. Cohort flow.
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labels = flow["stage"].tolist()
    positions = np.arange(len(labels))
    for ax, column, title in zip(
        axes,
        ["intervals", "participants"],
        ["Intervals", "Participants"],
    ):
        values = flow[column].to_numpy()
        ax.barh(positions, values, color="#4C78A8")
        ax.set_yticks(positions)
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Count")
        for position, value in zip(positions, values):
            ax.text(value, position, f" {int(value):,}", va="center", fontsize=8)
    save(fig, "fig1_cohort_flow.png")

    # 2. Exposure distribution.
    exposure = cohort["exposure_hours"].to_numpy()
    upper = max(1.0, float(np.quantile(exposure, 0.99)))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(
        np.clip(exposure, 0, upper),
        bins=40,
        color="#4C78A8",
        edgecolor="white",
    )
    zero_count = int((exposure == 0).sum())
    ax.set_xlabel(f"Recorded linked-console exposure (hours; clipped at {upper:.1f})")
    ax.set_ylabel("Intervals")
    ax.set_title(f"Exposure distribution (zero-play intervals: {zero_count:,})")
    save(fig, "fig2_exposure_distribution.png")

    # 3. Within-person exposure vs later valence.
    within = cohort["exposure_within"].to_numpy()
    later = cohort["later_valence"].to_numpy()
    lower, upper = np.quantile(within, [0.01, 0.99])
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.scatter(
        np.clip(within, lower, upper),
        later,
        s=10,
        alpha=0.25,
        color="#4C78A8",
        edgecolors="none",
    )
    slope, intercept = np.polyfit(within, later, 1)
    line_x = np.linspace(lower, upper, 100)
    ax.plot(line_x, intercept + slope * line_x, color="#E45756", linewidth=2)
    correlation = float(np.corrcoef(within, later)[0, 1])
    ax.set_xlabel("Within-person exposure (hours; clipped at 1st/99th percentile)")
    ax.set_ylabel("Later affective valence")
    ax.set_title(f"Within-person exposure and later valence (r = {correlation:.3f})")
    save(fig, "fig3_exposure_vs_valence.png")

    # 4. Model comparison.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    model_names = metrics["model"].tolist()
    positions = np.arange(len(model_names))
    colors = ["#9E9E9E", "#4C78A8", "#F58518"]

    axes[0].bar(positions, metrics["test_R2"], color=colors)
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(model_names, rotation=15, ha="right")
    axes[0].set_ylabel("Test R-squared")
    axes[0].set_title("Predictive fit (higher is better)")
    axes[0].axhline(0, color="black", linewidth=1)
    for position, value in zip(positions, metrics["test_R2"]):
        axes[0].text(position, value, f"{value:.3f}", ha="center", va="bottom", fontsize=8)

    axes[1].bar(positions, metrics["test_MAE"], color=colors)
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels(model_names, rotation=15, ha="right")
    axes[1].set_ylabel("Test MAE (valence points)")
    axes[1].set_title("Average prediction error (lower is better)")
    for position, value in zip(positions, metrics["test_MAE"]):
        axes[1].text(position, value, f"{value:.2f}", ha="center", va="bottom", fontsize=8)
    save(fig, "fig4_model_comparison.png")

    # 5. Actual vs predicted for the random forest.
    y_test = context["y_test"]
    predicted = context["predictions"]["Random forest"]
    test_metrics = metrics.loc[metrics["model"] == "Random forest"].iloc[0]
    fig, ax = plt.subplots(figsize=(6, 5.5))
    ax.scatter(y_test, predicted, s=12, alpha=0.35, color="#F58518", edgecolors="none")
    low = min(float(y_test.min()), float(predicted.min()))
    high = max(float(y_test.max()), float(predicted.max()))
    ax.plot([low, high], [low, high], color="black", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Actual later valence")
    ax.set_ylabel("Predicted later valence")
    ax.set_title(
        "Random forest: actual vs predicted\n"
        f"test R-squared = {test_metrics['test_R2']:.3f}, "
        f"MAE = {test_metrics['test_MAE']:.2f}"
    )
    save(fig, "fig5_actual_vs_predicted.png")

    # 6. Permutation importance.
    ordered = importance.sort_values("importance_mean")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.barh(
        [FEATURE_LABELS.get(name, name) for name in ordered["feature"]],
        ordered["importance_mean"],
        xerr=ordered["importance_sd"],
        color="#4C78A8",
        capsize=4,
    )
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("Increase in test MAE when feature is shuffled")
    ax.set_title("Random-forest permutation importance")
    save(fig, "fig6_feature_importance.png")

    # 7. Residuals vs predicted.
    residuals = y_test - predicted
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.scatter(predicted, residuals, s=12, alpha=0.35, color="#4C78A8", edgecolors="none")
    ax.axhline(0, color="black", linewidth=1.5)
    ax.set_xlabel("Predicted later valence")
    ax.set_ylabel("Residual (actual minus predicted)")
    ax.set_title("Random forest: residuals vs predictions")
    save(fig, "fig7_residuals.png")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def write_summary(
    cohort: pd.DataFrame,
    flow: pd.DataFrame,
    descriptives: pd.DataFrame,
    metrics: pd.DataFrame,
    importance: pd.DataFrame,
) -> None:
    """Write a short plain-language summary of the results."""
    best = metrics.sort_values("test_R2", ascending=False).iloc[0]
    top_features = importance.head(2)["feature"].tolist()
    zero_share = 100.0 * (cohort["exposure_hours"] == 0).mean()
    correlation = float(
        np.corrcoef(cohort["exposure_within"], cohort["later_valence"])[0, 1]
    )

    description_table = descriptives.copy()
    description_table["value"] = description_table["value"].map(
        lambda value: f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value)
    )

    metric_table = metrics.copy()
    for column in ["train_R2", "test_R2", "test_MAE", "test_RMSE"]:
        metric_table[column] = metric_table[column].map(lambda value: f"{value:.4f}")

    importance_table = importance.copy()
    for column in ["importance_mean", "importance_sd"]:
        importance_table[column] = importance_table[column].map(
            lambda value: f"{value:.4f}"
        )

    lines = [
        "# Simple GameWell analysis",
        "",
        "## What was analysed",
        "",
        "The analysis uses consecutive daily-survey intervals from participants",
        "with a linked Xbox and/or Nintendo account. An interval is included when",
        "both valence values are present, the interval is no longer than 48 hours,",
        "and recorded linked-console exposure is non-missing.",
        "",
        f"- Analysis cohort: **{len(cohort):,} intervals** from "
        f"**{cohort['participant'].nunique():,} participants**.",
        f"- Zero recorded exposure: **{zero_share:.1f}%** of intervals.",
        f"- Correlation between within-person exposure and later valence: "
        f"**r = {correlation:.3f}** (descriptive only).",
        "",
        "## Cohort flow",
        "",
        "| Stage | Intervals | Participants |",
        "|---|---:|---:|",
    ]
    for _, row in flow.iterrows():
        lines.append(
            f"| {row['stage']} | {int(row['intervals']):,} | "
            f"{int(row['participants']):,} |"
        )

    lines += [
        "",
        "## Descriptive statistics",
        "",
        "| Measure | Value | Unit |",
        "|---|---:|---|",
    ]
    for _, row in description_table.iterrows():
        lines.append(f"| {row['measure']} | {row['value']} | {row['unit']} |")

    lines += [
        "",
        "## Model comparison",
        "",
        "The data were split by participant: 80% of participants for training",
        "and 20% for testing. Keeping participants separate prevents the same",
        "person appearing in both sets.",
        "",
        "| Model | Train R-squared | Test R-squared | Test MAE | Test RMSE |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in metric_table.iterrows():
        lines.append(
            f"| {row['model']} | {row['train_R2']} | {row['test_R2']} | "
            f"{row['test_MAE']} | {row['test_RMSE']} |"
        )

    lines += [
        "",
        f"The best test R-squared was **{best['test_R2']:.3f}** for the "
        f"**{best['model']}**, with a test MAE of **{best['test_MAE']:.2f}** "
        "valence points.",
        "",
        "## Most important predictors",
        "",
        "Permutation importance measures how much the random forest's test",
        "error increases when a feature is shuffled. Larger values mean the",
        "feature mattered more for prediction.",
        "",
        "| Feature | Importance (MAE increase) | SD |",
        "|---|---:|---:|",
    ]
    for _, row in importance_table.iterrows():
        lines.append(
            f"| {FEATURE_LABELS.get(row['feature'], row['feature'])} | "
            f"{row['importance_mean']} | {row['importance_sd']} |"
        )

    lines += [
        "",
        "## Important caveat",
        "",
        "This is an exploratory predictive analysis, not a causal analysis.",
        "A random forest can find patterns that predict later valence, but it",
        "cannot show that gaming caused a change in valence. The formal",
        "within-person mixed-model analysis is a separate, more specialised",
        "analysis.",
        "",
        "## Files",
        "",
        "- `cohort_flow.csv` - counts at each filtering step",
        "- `descriptives.csv` - aggregate descriptive statistics",
        "- `model_metrics.csv` - train/test performance for all models",
        "- `feature_importance.csv` - random-forest permutation importance",
        "- `linear_coefficients.csv` - linear-regression coefficients",
        "- `figures/fig1_cohort_flow.png` ... `figures/fig7_residuals.png`",
        "",
    ]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    cohort, flow = load_and_prepare()
    descriptives = make_descriptives(cohort)
    metrics, importance, linear_coefficients, context = fit_models(cohort)

    flow.to_csv(OUT / "cohort_flow.csv", index=False)
    descriptives.to_csv(OUT / "descriptives.csv", index=False)
    metrics.to_csv(OUT / "model_metrics.csv", index=False)
    importance.to_csv(OUT / "feature_importance.csv", index=False)
    linear_coefficients.to_csv(OUT / "linear_coefficients.csv", index=False)

    make_figures(cohort, flow, metrics, importance, context)
    write_summary(cohort, flow, descriptives, metrics, importance)

    # Aggregate console output only; no participant identifiers.
    print(f"Data: {DATA}")
    print(
        f"Cohort: {len(cohort):,} intervals from "
        f"{cohort['participant'].nunique():,} participants"
    )
    print("\nModel performance:")
    print(metrics[["model", "test_R2", "test_MAE", "test_RMSE"]].to_string(index=False))
    print("\nTop predictors (random forest permutation importance):")
    print(
        importance[["feature", "importance_mean"]]
        .head(4)
        .to_string(index=False)
    )
    print(f"\nGraphs and tables written to: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
