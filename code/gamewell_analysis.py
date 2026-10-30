#!/usr/bin/env python3
"""
GameWell primary analysis: within-person recorded linked-console play and
later affective valence.

This is a single-file, read-only analysis of the pre-built GameWell daily
interval dataset.  It implements the prespecified primary model from the R
pipeline (04_primary_model_v5.R): a linear mixed model with a participant
random intercept, REML, a <=48-hour interval restriction, and the wider of
the model-based and CR2 cluster-robust 95% intervals for interpretation.
The smallest effect size of interest (SESOI) is +/-0.5 valence points per
hour.  No data are edited, recoded, imputed or filtered on disk.

Usage
-----
    python code/gamewell_analysis.py --demo --out demo_outputs
    python code/gamewell_analysis.py --data path/to/gamewell_daily_intervals.csv.gz --out outputs

The demo mode creates an in-memory synthetic dataset with the same column
structure as the real file.  Its numbers are deliberately meaningless; it
only exercises the code path.

Important limitations (carried from the R analysis documentation)
------------------------------------------------------------------
* Zero recorded sessions are interpreted only under the source's
  maximal-coverage-on-linkage assumption.  There is no interval-level
  capture flag, so missing capture cannot be distinguished from genuine
  no-play.
* Nintendo telemetry covers first-party titles only; Steam, mobile and
  unlinked-platform play are excluded from recorded exposure.
* Recorded valence values of 0 occur despite the instrument description's
  lower bound of 1; they are retained as recorded in the primary analysis.
* Survey timestamps are treated as UTC instants; the original export clock
  configuration remains unverified.
* The model is observational.  Estimates describe associations, not causal
  effects, and do not locate the mood response relative to each session
  within an interval.
* The primary cohort is restricted to participants with linked Xbox and/or
  Nintendo accounts and usable intervals; results may not generalise to
  other players or platforms.
* Model-based degrees of freedom are approximated as n - p.  The R fit was
  singular (random-intercept SD = 0), where this equals the lmerTest
  Satterthwaite df; for non-singular fits this is an approximation.

Only aggregate results are written.  Participant identifiers never appear
in console output, tables, figures or reports.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import statsmodels
import statsmodels.formula.api as smf
from scipy import stats

# ---------------------------------------------------------------------------
# Column map.  Edit ONLY this dictionary if the real interval file uses
# different column names.  The analysis itself uses the internal names on
# the left-hand side.
# ---------------------------------------------------------------------------
COL = {
    "participant_id": "participant_id",
    "interval_duration_hours": "interval_duration_hours",
    "prior_valence": "prior_affective_valence",
    "later_valence": "later_affective_valence",
    "xbox_linked": "xbox_linked",
    "nintendo_linked": "nintendo_linked",
    "exposure_minutes": "recorded_linked_console_minutes_unique",
    "interval_start": "interval_start_utc",
    "interval_end": "interval_end_utc",
    "interval_sequence": "interval_sequence",
}

MAX_INTERVAL_HOURS = 48.0
SESOI_POINTS_PER_HOUR = 0.5
BOUNDARY_RHO_TOL = 1e-4
MODEL_FORMULA = (
    "later_valence ~ exposure_within + exposure_between + "
    "prior_within + prior_between + log_interval_c"
)
REFERENCE_COHORT = {
    "eligible_intervals": 5076,
    "participants": 371,
    "participants_with_exposure_variation": 171,
}


# ---------------------------------------------------------------------------
# Data loading and cohort construction
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GameWell primary within-person analysis (read-only)."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--demo",
        action="store_true",
        help="Use an in-memory synthetic dataset (numbers are meaningless).",
    )
    source.add_argument(
        "--data",
        type=str,
        help="Path to gamewell_daily_intervals.csv.gz (or .csv).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="outputs",
        help="Output directory (default: outputs).",
    )
    return parser.parse_args(argv)


def as_linked(series: pd.Series) -> pd.Series:
    """Return a boolean Series for linkage flags.

    Accepts true/false, 1/0, yes/no, y/n, and missing values.  Missing
    linkage is treated as not linked, matching the R helper
    ``tolower(trimws(as.character(x))) %in% c("true", "1", "yes")``.
    """
    text = series.astype("string").str.strip().str.lower()
    return text.isin(["true", "1", "yes", "y", "t"]).fillna(False).astype(bool)


def load_intervals(path: str | Path) -> pd.DataFrame:
    """Read the interval file and check that all mapped columns exist."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Interval file not found: {path}\n"
            "Pass the real file with --data, or use --demo."
        )
    df = pd.read_csv(path)
    missing = [col for col in COL.values() if col not in df.columns]
    if missing:
        raise ValueError(
            "The interval file is missing mapped column(s): "
            + ", ".join(missing)
            + ".\nEdit the COL dictionary at the top of this script if the "
              "real file uses different column names."
        )
    return df


def make_demo_data(seed: int = 20261030, n_participants: int = 160) -> pd.DataFrame:
    """Create a synthetic interval table for a code-path smoke test.

    The generator is intentionally simple: participants have a typical
    exposure level, intervals are mostly about one day long, and later
    valence depends on prior valence, the participant's baseline, a small
    within-person exposure term, and noise.  Some duration, valence,
    exposure and linkage values are made missing so that the cohort filter
    is exercised.  These numbers are not meaningful.
    """
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2025-01-01T00:00:00Z")
    rows: list[dict] = []

    for i in range(n_participants):
        pid = f"DEMO{i:04d}"
        n_intervals = int(rng.integers(4, 15))
        typical_exposure = float(rng.gamma(1.4, 1.0))
        baseline = float(rng.normal(62.0, 11.0))
        participant_effect = float(rng.normal(0.0, 5.0))
        prior = float(np.clip(rng.normal(baseline, 8.0), 0.0, 100.0))

        xbox = "true" if rng.random() < 0.65 else "false"
        nintendo = "true" if rng.random() < 0.45 else "false"
        if xbox == "false" and nintendo == "false" and rng.random() < 0.70:
            xbox = "true"
        if rng.random() < 0.03:
            xbox = np.nan
        if rng.random() < 0.03:
            nintendo = np.nan

        start = t0 + pd.Timedelta(days=float(rng.uniform(0.0, 20.0)))
        for k in range(n_intervals):
            duration = float(
                np.clip(rng.lognormal(mean=np.log(23.5), sigma=0.30), 3.0, 47.0)
            )
            if rng.random() < 0.06:
                duration = float(rng.uniform(49.0, 96.0))
            if rng.random() < 0.01:
                duration = np.nan

            if rng.random() < 0.78:
                exposure_hours = max(
                    0.0, float(rng.gamma(1.2, typical_exposure / 1.2)) - 0.1
                )
            else:
                exposure_hours = 0.0

            later = (
                0.45 * prior
                + 0.55 * baseline
                + participant_effect
                + 0.09 * (exposure_hours - typical_exposure)
                + float(rng.normal(0.0, 8.0))
            )
            later = float(np.clip(later, 0.0, 100.0))

            prior_out = prior if rng.random() > 0.04 else np.nan
            later_out = later if rng.random() > 0.04 else np.nan
            exposure_out = (
                exposure_hours * 60.0 if rng.random() > 0.02 else np.nan
            )
            duration_out = duration

            ls_prior = float(
                np.clip(0.5 * prior + 0.5 * baseline + rng.normal(0.0, 7.0), 0.0, 100.0)
            )
            ls_later = float(
                np.clip(
                    0.5 * ls_prior
                    + 0.5 * baseline
                    + 0.05 * (exposure_hours - typical_exposure)
                    + rng.normal(0.0, 7.0),
                    0.0,
                    100.0,
                )
            )

            end = start + pd.Timedelta(
                hours=float(duration_out) if np.isfinite(duration_out) else 24.0
            )
            rows.append(
                {
                    "participant_id": pid,
                    "interval_sequence": k + 1,
                    "prior_survey_wave": k + 1,
                    "later_survey_wave": k + 2,
                    "interval_start_utc": start.isoformat(),
                    "interval_end_utc": end.isoformat(),
                    "interval_duration_minutes": (
                        float(duration_out) * 60.0
                        if np.isfinite(duration_out)
                        else np.nan
                    ),
                    "interval_duration_hours": duration_out,
                    "prior_affective_valence": prior_out,
                    "later_affective_valence": later_out,
                    "prior_life_satisfaction": ls_prior,
                    "later_life_satisfaction": ls_later,
                    "xbox_linked": xbox,
                    "nintendo_linked": nintendo,
                    "participant_linkage_status": (
                        "xbox_and_nintendo"
                        if xbox == "true" and nintendo == "true"
                        else "xbox_only"
                        if xbox == "true"
                        else "nintendo_only"
                        if nintendo == "true"
                        else "no_console_link"
                    ),
                    "timestamp_status": "valid",
                    "xbox_gaming_minutes": np.nan,
                    "nintendo_gaming_minutes": np.nan,
                    "recorded_linked_console_minutes_unique": exposure_out,
                    "concurrent_minutes_removed": 0.0,
                    "recorded_linked_console_minutes_per_24h": (
                        exposure_out / float(duration_out) * 24.0
                        if np.isfinite(exposure_out) and np.isfinite(duration_out)
                        else np.nan
                    ),
                    "telemetry_status": "synthetic",
                    "telemetry_coverage_basis": "synthetic demo",
                }
            )
            # Carry some autocorrelation forward, but do not make the next
            # prior equal to the previous outcome; this keeps the synthetic
            # participant random effect identifiable.
            prior = float(
                np.clip(0.30 * prior + 0.70 * baseline + rng.normal(0.0, 4.0), 0.0, 100.0)
            )
            start = end

    return pd.DataFrame(rows)


def prepare_cohort(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the prespecified cohort rule and derive model variables.

    Cohort (identical to 04_primary_model_v5.R):
      * Xbox and/or Nintendo linked;
      * interval duration non-missing and <= 48 hours;
      * prior and later affective valence non-missing;
      * recorded linked-console exposure non-missing.

    Derived variables:
      exposure_hours       = unique linked-console minutes / 60
      exposure_between     = participant mean of exposure_hours
      exposure_within      = exposure_hours - exposure_between
      prior_between        = participant mean of prior valence
      prior_within         = prior valence - prior_between
      log_interval_c       = log(duration hours) - cohort mean of that log
      later_valence        = later affective valence
    """
    participant = df[COL["participant_id"]].astype("string").str.strip()
    duration = pd.to_numeric(df[COL["interval_duration_hours"]], errors="coerce")
    prior = pd.to_numeric(df[COL["prior_valence"]], errors="coerce")
    later = pd.to_numeric(df[COL["later_valence"]], errors="coerce")
    exposure_minutes = pd.to_numeric(df[COL["exposure_minutes"]], errors="coerce")
    linked = as_linked(df[COL["xbox_linked"]]) | as_linked(df[COL["nintendo_linked"]])

    duration_ok = duration.notna() & (duration <= MAX_INTERVAL_HOURS)
    valence_ok = prior.notna() & later.notna()
    exposure_ok = exposure_minutes.notna()

    flow_rows = []

    def add_flow(label: str, mask: pd.Series) -> None:
        flow_rows.append(
            {
                "stage": label,
                "interval_count": int(mask.sum()),
                "participant_count": int(participant[mask].nunique()),
            }
        )

    add_flow("All intervals in file", pd.Series(True, index=df.index))
    add_flow("Linked Xbox and/or Nintendo", linked)
    add_flow("Valence present at both endpoints", linked & valence_ok)
    add_flow(
        f"Interval duration <= {MAX_INTERVAL_HOURS:g} h",
        linked & valence_ok & duration_ok,
    )
    eligible = linked & valence_ok & duration_ok & exposure_ok
    add_flow("Exposure non-missing (primary cohort)", eligible)

    if (duration[eligible] <= 0).any():
        raise ValueError(
            "Eligible interval duration is invalid (<= 0); the R pre-fit gate "
            "would stop here. No model was fitted."
        )
    if participant[eligible].isna().any() or (participant[eligible] == "").any():
        raise ValueError(
            "Eligible participant ID is missing; the R pre-fit gate would "
            "stop here. No model was fitted."
        )

    cohort = pd.DataFrame(
        {
            "participant": participant[eligible].astype(str),
            "interval_duration_hours": duration[eligible].astype(float),
            "prior_affective_valence": prior[eligible].astype(float),
            "later_affective_valence": later[eligible].astype(float),
            "exposure_minutes": exposure_minutes[eligible].astype(float),
        }
    ).copy()

    if cohort.empty:
        raise ValueError("The primary cohort is empty; no model can be fitted.")

    cohort["later_valence"] = cohort["later_affective_valence"]
    cohort["exposure_hours"] = cohort["exposure_minutes"] / 60.0
    cohort["exposure_between"] = cohort.groupby("participant")[
        "exposure_hours"
    ].transform("mean")
    cohort["exposure_within"] = (
        cohort["exposure_hours"] - cohort["exposure_between"]
    )
    cohort["prior_between"] = cohort.groupby("participant")[
        "prior_affective_valence"
    ].transform("mean")
    cohort["prior_within"] = (
        cohort["prior_affective_valence"] - cohort["prior_between"]
    )
    log_duration = np.log(cohort["interval_duration_hours"])
    cohort["log_interval_c"] = log_duration - log_duration.mean()

    flow = pd.DataFrame(flow_rows)
    return cohort, flow


# ---------------------------------------------------------------------------
# Model fitting and inference
# ---------------------------------------------------------------------------
def fit_primary_model(cohort: pd.DataFrame) -> dict:
    """Fit the prespecified participant-random-intercept model once.

    statsmodels MixedLM is used with REML.  If the estimated random-intercept
    variance is at the boundary (rho = tau^2 / sigma^2 < 1e-4, as in the R
    fit where the lme4 random-intercept SD was exactly zero), the fixed
    effects and model-based covariance are evaluated at the boundary OLS
    solution.  This mirrors the singular lme4 fit rather than inventing a
    different model.  The CR2 calculation then uses the same boundary value.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fit = smf.mixedlm(
            MODEL_FORMULA, data=cohort, groups=cohort["participant"]
        ).fit(reml=True)
    warning_messages = [str(w.message) for w in caught]

    X = np.asarray(fit.model.exog, dtype=float)
    y = np.asarray(fit.model.endog, dtype=float)
    names = list(fit.fe_params.index)
    n, p = X.shape

    sigma2_mixed = float(fit.scale)
    tau2_mixed = float(np.asarray(fit.cov_re).ravel()[0])
    rho_mixed = tau2_mixed / sigma2_mixed if sigma2_mixed > 0 else 0.0
    boundary = (not bool(fit.converged)) or (rho_mixed < BOUNDARY_RHO_TOL)

    if boundary:
        # lme4 put the random-intercept variance on the boundary (SD = 0).
        # The fixed-effect estimates and covariance are then the OLS ones.
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        marginal_resid = y - X @ beta
        sigma2 = float(marginal_resid @ marginal_resid / (n - p))
        cov_model = sigma2 * np.linalg.inv(X.T @ X)
        se_model = np.sqrt(np.diag(cov_model))
        df_model = float(n - p)
        residuals = marginal_resid
        fitted = X @ beta
        random_effects = np.zeros(cohort["participant"].nunique(), dtype=float)
        tau2 = 0.0
        rho = 0.0
    else:
        beta = np.asarray(fit.fe_params, dtype=float)
        # MixedLM.cov_params() appends variance-component rows/columns; keep
        # the fixed-effect block only.
        cov_model = np.asarray(fit.cov_params(), dtype=float)[:p, :p]
        se_model = np.sqrt(np.diag(cov_model))
        df_model = float(n - p)
        residuals = np.asarray(fit.resid, dtype=float)
        fitted = np.asarray(fit.fittedvalues, dtype=float)
        re_values = []
        for group in cohort["participant"].drop_duplicates():
            effect = fit.random_effects.get(group)
            if effect is None:
                effect = fit.random_effects.get(str(group))
            re_values.append(float(np.asarray(effect).ravel()[0]))
        random_effects = np.asarray(re_values, dtype=float)
        sigma2 = sigma2_mixed
        tau2 = tau2_mixed
        rho = rho_mixed

    return {
        "fit": fit,
        "X": X,
        "y": y,
        "names": names,
        "beta": beta,
        "cov_model": cov_model,
        "se_model": se_model,
        "df_model": df_model,
        "residuals": residuals,
        "fitted": fitted,
        "random_effects": random_effects,
        "sigma2": sigma2,
        "tau2": tau2,
        "rho": rho,
        "sigma2_mixed": sigma2_mixed,
        "tau2_mixed": tau2_mixed,
        "rho_mixed": rho_mixed,
        "boundary": boundary,
        "converged": bool(fit.converged),
        "warning_messages": warning_messages,
        "n": n,
        "p": p,
    }


def _inverse_sqrt_symmetric(matrix: np.ndarray) -> np.ndarray:
    """Symmetric inverse square root with a small eigenvalue floor."""
    vals, vecs = np.linalg.eigh((matrix + matrix.T) / 2.0)
    vals = np.clip(vals, 1e-12, None)
    return vecs @ np.diag(vals ** -0.5) @ vecs.T


def cr2_inference(
    X: np.ndarray,
    y: np.ndarray,
    beta: np.ndarray,
    groups: np.ndarray,
    sigma2: float,
    tau2: float,
) -> dict:
    """Participant-clustered CR2 covariance and Satterthwaite df.

    This mirrors clubSandwich::vcovCR(type = "CR2") for a random-intercept
    model.  The working covariance within a participant is
    sigma2 * (I + rho * J), with rho = tau2 / sigma2.  At rho = 0 the CR2
    adjustment is A_g = (I - H_gg)^(-1/2).  When rho > 0, let
    Theta = I + rho * J = U'U with U = chol(Theta) upper and L = U'.  The
    adjustment is
        G_g = U (I - H_gg) Theta U'
        A_g = L G_g^(-1/2) U.
    The Satterthwaite degrees of freedom follow clubSandwich's P-array
    formula:
        df = trace(P)^2 / sum(P^2).
    """
    groups = np.asarray(groups, dtype=str)
    levels = sorted(pd.unique(groups))
    p = X.shape[1]
    rho = 0.0 if sigma2 <= 0 else max(0.0, tau2 / sigma2)

    # B_unit = (X' W X)^-1 with W the unit-residual working covariance.
    bread = np.zeros((p, p), dtype=float)
    cluster_indices: list[np.ndarray] = []
    for level in levels:
        idx = np.where(groups == level)[0]
        cluster_indices.append(idx)
        Xg = X[idx, :]
        ng = len(idx)
        Wg = np.eye(ng) - (rho / (1.0 + ng * rho)) * np.ones((ng, ng))
        bread += Xg.T @ Wg @ Xg
    bread = np.linalg.inv(bread)
    bread_chol = np.linalg.cholesky(bread)  # lower, = t(chol(bread)) in R

    n_clusters = len(levels)
    H_array = np.zeros((p, p, n_clusters), dtype=float)
    Gnorm2 = np.zeros((p, n_clusters), dtype=float)
    meat = np.zeros((p, p), dtype=float)

    for j, idx in enumerate(cluster_indices):
        Xg = X[idx, :]
        ng = len(idx)
        Wg = np.eye(ng) - (rho / (1.0 + ng * rho)) * np.ones((ng, ng))
        theta = np.eye(ng) + rho * np.ones((ng, ng))
        # R's chol() is upper; numpy's cholesky() is lower.
        theta_upper = np.linalg.cholesky(theta).T
        theta_lower = theta_upper.T

        Hjj = Xg @ bread @ Xg.T @ Wg
        Iminus = np.eye(ng) - Hjj
        # clubSandwich's Theta-metric CR2 adjustment.
        Gmat = theta_upper @ Iminus @ theta @ theta_upper.T
        adjustment = theta_lower @ _inverse_sqrt_symmetric(Gmat) @ theta_upper

        E = Xg.T @ Wg @ adjustment  # p x n_g
        ME = bread @ E
        H_array[:, :, j] = ME @ Xg @ bread_chol
        Gj = ME @ theta_lower
        Gnorm2[:, j] = np.sum(Gj ** 2, axis=1)

        marginal_resid = y[idx] - Xg @ beta
        score = E @ marginal_resid
        meat += np.outer(score, score)

    cov_cr2 = bread @ meat @ bread
    se_cr2 = np.sqrt(np.diag(cov_cr2))

    df_cr2 = np.empty(p, dtype=float)
    for i in range(p):
        Hi = H_array[i, :, :]  # p x n_clusters
        P = -Hi.T @ Hi
        P[np.diag_indices(n_clusters)] += Gnorm2[i, :]
        denom = float(np.sum(P ** 2))
        df_cr2[i] = float(np.trace(P) ** 2 / denom) if denom > 0 else float(
            n_clusters - 1
        )

    return {
        "cov": cov_cr2,
        "se": se_cr2,
        "df": df_cr2,
        "rho_used": rho,
        "n_clusters": n_clusters,
    }


def interpret_category(lower: float, upper: float) -> tuple[str, str]:
    """Apply the Addendum 2 interpretation rule (wording unchanged)."""
    if lower > -SESOI_POINTS_PER_HOUR and upper < SESOI_POINTS_PER_HOUR:
        category = "a"
    elif (upper < 0 or lower > 0) and (
        lower < -SESOI_POINTS_PER_HOUR or upper > SESOI_POINTS_PER_HOUR
    ):
        category = "b"
    elif (
        (upper < 0 or lower > 0)
        and lower >= -SESOI_POINTS_PER_HOUR
        and upper <= SESOI_POINTS_PER_HOUR
    ):
        category = "c"
    else:
        category = "d"

    wording = {
        "a": "interval entirely within +/-0.5: no association larger than the SESOI is supported",
        "b": "interval excludes 0 and extends beyond +/-0.5: association of potentially meaningful size",
        "c": "interval excludes 0 but lies entirely within +/-0.5: statistically detectable but small",
        "d": "interval includes 0 and extends beyond +/-0.5: inconclusive",
    }[category]
    return category, wording


def build_tables(cohort: pd.DataFrame, model: dict, cr2: dict) -> dict:
    """Build fixed-effect, b1-summary, cohort-gate and diagnostic tables."""
    names = model["names"]
    beta = model["beta"]
    se_model = model["se_model"]
    df_model = model["df_model"]
    se_cr2 = cr2["se"]
    df_cr2 = cr2["df"]

    t_crit_model = stats.t.ppf(0.975, df_model)
    model_lo = beta - t_crit_model * se_model
    model_hi = beta + t_crit_model * se_model
    t_crit_cr2 = stats.t.ppf(0.975, df_cr2)
    cr2_lo = beta - t_crit_cr2 * se_cr2
    cr2_hi = beta + t_crit_cr2 * se_cr2

    fixed = pd.DataFrame(
        {
            "term": names,
            "estimate": beta,
            "model_SE": se_model,
            "model_df": df_model,
            "model_t": beta / se_model,
            "model_p": 2.0 * stats.t.sf(np.abs(beta / se_model), df_model),
            "model_CI_lower": model_lo,
            "model_CI_upper": model_hi,
            "CR2_SE": se_cr2,
            "CR2_df_Satterthwaite": df_cr2,
            "CR2_t": beta / se_cr2,
            "CR2_p": 2.0 * stats.t.sf(np.abs(beta / se_cr2), df_cr2),
            "CR2_CI_lower": cr2_lo,
            "CR2_CI_upper": cr2_hi,
        }
    )

    idx = names.index("exposure_within")
    model_width = float(model_hi[idx] - model_lo[idx])
    cr2_width = float(cr2_hi[idx] - cr2_lo[idx])
    if cr2_width > model_width:
        wider_source = "CR2 cluster-robust"
        wider_lo = float(cr2_lo[idx])
        wider_hi = float(cr2_hi[idx])
    else:
        wider_source = "model-based Satterthwaite"
        wider_lo = float(model_lo[idx])
        wider_hi = float(model_hi[idx])

    within_valence = cohort["later_valence"] - cohort.groupby("participant")[
        "later_valence"
    ].transform("mean")
    within_valence_sd = float(within_valence.std(ddof=1))
    exposure_within_sd = float(cohort["exposure_within"].std(ddof=1))
    category, wording = interpret_category(wider_lo, wider_hi)

    b1 = pd.DataFrame(
        {
            "term": ["exposure_within"],
            "estimate": [float(beta[idx])],
            "model_CI_lower": [float(model_lo[idx])],
            "model_CI_upper": [float(model_hi[idx])],
            "CR2_CI_lower": [float(cr2_lo[idx])],
            "CR2_CI_upper": [float(cr2_hi[idx])],
            "wider_interval_source": [wider_source],
            "wider_CI_lower": [wider_lo],
            "wider_CI_upper": [wider_hi],
            "within_person_valence_SD": [within_valence_sd],
            "scaled_estimate_SD_units": [
                float(beta[idx]) / within_valence_sd
                if within_valence_sd > 0
                else np.nan
            ],
            "exposure_within_SD_hours": [exposure_within_sd],
            "effect_per_1_SD_exposure": [
                float(beta[idx]) * exposure_within_sd
            ],
            "SESOI_points_per_hour": [SESOI_POINTS_PER_HOUR],
            "Addendum2_category": [category],
            "category_wording": [wording],
        }
    )

    variation = (
        cohort.groupby("participant")["exposure_hours"].nunique() > 1
    ).sum()
    gate = pd.DataFrame(
        {
            "metric": [
                "eligible_intervals",
                "participants",
                "participants_with_exposure_variation",
            ],
            "observed": [
                int(len(cohort)),
                int(cohort["participant"].nunique()),
                int(variation),
            ],
        }
    )

    return {
        "fixed_effects": fixed,
        "b1_summary": b1,
        "cohort_gate": gate,
        "category": category,
        "wording": wording,
        "wider_source": wider_source,
        "wider_lo": wider_lo,
        "wider_hi": wider_hi,
    }


def build_diagnostics(cohort: pd.DataFrame, model: dict) -> dict:
    """Aggregate residual, fitted-value-bin and random-effect summaries."""
    residuals = np.asarray(model["residuals"], dtype=float)
    fitted = np.asarray(model["fitted"], dtype=float)
    res_sd = float(np.std(residuals, ddof=1))
    res_mean = float(np.mean(residuals))
    residual_summary = pd.DataFrame(
        {
            "n": [int(len(residuals))],
            "mean": [res_mean],
            "SD": [res_sd],
            "skewness": [
                float(np.mean((residuals - res_mean) ** 3) / res_sd ** 3)
                if res_sd > 0
                else np.nan
            ],
            "excess_kurtosis": [
                float(np.mean((residuals - res_mean) ** 4) / res_sd ** 4 - 3.0)
                if res_sd > 0
                else np.nan
            ],
            "q0": [float(np.quantile(residuals, 0.0))],
            "q05": [float(np.quantile(residuals, 0.05))],
            "q25": [float(np.quantile(residuals, 0.25))],
            "median": [float(np.quantile(residuals, 0.50))],
            "q75": [float(np.quantile(residuals, 0.75))],
            "q95": [float(np.quantile(residuals, 0.95))],
            "q100": [float(np.quantile(residuals, 1.0))],
        }
    )

    ranks = stats.rankdata(fitted, method="average")
    bin_id = np.minimum(10, np.ceil(ranks / len(fitted) * 10.0)).astype(int)
    bin_rows = []
    for k in range(1, 11):
        mask = bin_id == k
        if not mask.any():
            bin_rows.append(
                {
                    "fitted_bin": k,
                    "n": 0,
                    "fitted_mean": np.nan,
                    "residual_mean": np.nan,
                    "residual_SD": np.nan,
                }
            )
        else:
            bin_rows.append(
                {
                    "fitted_bin": k,
                    "n": int(mask.sum()),
                    "fitted_mean": float(np.mean(fitted[mask])),
                    "residual_mean": float(np.mean(residuals[mask])),
                    "residual_SD": float(np.std(residuals[mask], ddof=1))
                    if mask.sum() > 1
                    else np.nan,
                }
            )
    residual_bins = pd.DataFrame(bin_rows)

    re = np.asarray(model["random_effects"], dtype=float)
    random_effect_summary = pd.DataFrame(
        {
            "n_participants": [int(len(re))],
            "mean": [float(np.mean(re))],
            "SD": [float(np.std(re, ddof=1)) if len(re) > 1 else np.nan],
            "q0": [float(np.quantile(re, 0.0))],
            "q05": [float(np.quantile(re, 0.05))],
            "q25": [float(np.quantile(re, 0.25))],
            "median": [float(np.quantile(re, 0.50))],
            "q75": [float(np.quantile(re, 0.75))],
            "q95": [float(np.quantile(re, 0.95))],
            "q100": [float(np.quantile(re, 1.0))],
        }
    )

    return {
        "residual_summary": residual_summary,
        "residual_bins": residual_bins,
        "random_effect_summary": random_effect_summary,
    }


def build_fit_status(cohort: pd.DataFrame, model: dict, cr2: dict) -> pd.DataFrame:
    """One-row aggregate fit-status table (no participant identifiers)."""
    n = model["n"]
    tau2 = model["tau2"]
    sigma2 = model["sigma2"]
    ri_sd = float(np.sqrt(max(tau2, 0.0)))
    resid_sd = float(np.sqrt(max(sigma2, 0.0)))
    icc = (
        float(tau2 / (tau2 + sigma2)) if (tau2 + sigma2) > 0 else np.nan
    )
    group_sizes = cohort.groupby("participant").size()
    warning_text = " | ".join(model["warning_messages"]) if model["warning_messages"] else "none"

    return pd.DataFrame(
        {
            "model_fits": [1],
            "observations": [int(n)],
            "participants": [int(cohort["participant"].nunique())],
            "participants_with_exposure_variation": [
                int(
                    (
                        cohort.groupby("participant")["exposure_hours"].nunique()
                        > 1
                    ).sum()
                )
            ],
            "optimizer": ["statsmodels MixedLM (default)"],
            "converged": [model["converged"]],
            "singular_fit": [bool(model["boundary"])],
            "boundary_solution_applied": [bool(model["boundary"])],
            "random_intercept_SD": [ri_sd],
            "residual_SD": [resid_sd],
            "ICC": [icc],
            "raw_MixedLM_random_intercept_variance": [model["tau2_mixed"]],
            "raw_MixedLM_residual_variance": [model["sigma2_mixed"]],
            "raw_MixedLM_rho": [model["rho_mixed"]],
            "CR2_working_rho": [cr2["rho_used"]],
            "min_intervals_per_participant": [int(group_sizes.min())],
            "max_intervals_per_participant": [int(group_sizes.max())],
            "convergence_warnings": [warning_text],
        }
    )


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def make_figures(
    cohort: pd.DataFrame,
    flow: pd.DataFrame,
    tables: dict,
    diagnostics: dict,
    figure_dir: Path,
) -> list[str]:
    """Create aggregate figures and return their filenames."""
    figure_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    # 1. Cohort flow.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    labels = flow["stage"].tolist()
    y = np.arange(len(labels))
    for ax, column, title in zip(
        axes,
        ["interval_count", "participant_count"],
        ["Intervals", "Participants"],
    ):
        values = flow[column].to_numpy()
        ax.barh(y, values, color="#4C78A8")
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.set_xlabel("Count")
        for yi, value in zip(y, values):
            ax.text(value, yi, f" {int(value):,}", va="center", fontsize=8)
    _save_figure(fig, figure_dir / "fig1_cohort_flow.png")
    files.append("fig1_cohort_flow.png")

    # 2. Exposure distribution.
    exposure = cohort["exposure_hours"].to_numpy()
    upper = max(1.0, float(np.quantile(exposure, 0.99)))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(np.clip(exposure, 0, upper), bins=40, color="#4C78A8", edgecolor="white")
    zero_n = int(np.sum(exposure == 0))
    ax.set_xlabel(f"Recorded linked-console exposure (hours; clipped at {upper:.1f})")
    ax.set_ylabel("Intervals")
    ax.set_title(f"Exposure distribution (zero-exposure intervals: {zero_n:,})")
    _save_figure(fig, figure_dir / "fig2_exposure_distribution.png")
    files.append("fig2_exposure_distribution.png")

    # 3. Within-person exposure distribution.
    within = cohort["exposure_within"].to_numpy()
    lo = float(np.quantile(within, 0.01))
    hi = float(np.quantile(within, 0.99))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(np.clip(within, lo, hi), bins=40, color="#F58518", edgecolor="white")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel(f"Within-person exposure (hours; clipped to [{lo:.2f}, {hi:.2f}])")
    ax.set_ylabel("Intervals")
    ax.set_title("Within-person exposure (interval minus participant mean)")
    _save_figure(fig, figure_dir / "fig3_exposure_within_distribution.png")
    files.append("fig3_exposure_within_distribution.png")

    # 4. b1 forest plot.
    b1 = tables["b1_summary"].iloc[0]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.errorbar(
        [b1["estimate"], b1["estimate"]],
        [1, 0],
        xerr=[
            [b1["estimate"] - b1["model_CI_lower"], b1["estimate"] - b1["CR2_CI_lower"]],
            [b1["model_CI_upper"] - b1["estimate"], b1["CR2_CI_upper"] - b1["estimate"]],
        ],
        fmt="o",
        color="#4C78A8",
        capsize=5,
    )
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(-SESOI_POINTS_PER_HOUR, color="grey", linestyle="--", linewidth=1)
    ax.axvline(SESOI_POINTS_PER_HOUR, color="grey", linestyle="--", linewidth=1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["CR2 cluster-robust", "Model-based"])
    ax.set_xlabel("Within-person estimate (valence points per hour)")
    ax.set_title("Primary exposure_within estimate and 95% intervals")
    _save_figure(fig, figure_dir / "fig4_b1_forest.png")
    files.append("fig4_b1_forest.png")

    # 5. Residual histogram.
    residuals = np.asarray(tables["_residuals"], dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(residuals, bins="fd", color="grey", edgecolor="white")
    ax.set_xlabel("Residual")
    ax.set_ylabel("Intervals")
    ax.set_title("Primary model residuals")
    _save_figure(fig, figure_dir / "fig5_residual_histogram.png")
    files.append("fig5_residual_histogram.png")

    # 6. Normal Q-Q plot.
    fig, ax = plt.subplots(figsize=(6, 5))
    stats.probplot(residuals, dist="norm", plot=ax)
    ax.set_title("Normal Q-Q plot of primary model residuals")
    _save_figure(fig, figure_dir / "fig6_residual_qq.png")
    files.append("fig6_residual_qq.png")

    # 7. Residuals by fitted-value decile.
    bins = diagnostics["residual_bins"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(bins["fitted_mean"], bins["residual_mean"], "o-", color="#4C78A8")
    ax.axhline(0, color="red", linewidth=1.5)
    ax.set_xlabel("Mean fitted value within decile bin")
    ax.set_ylabel("Mean residual")
    ax.set_title("Residuals by fitted value (10 bins)")
    _save_figure(fig, figure_dir / "fig7_residuals_by_fitted.png")
    files.append("fig7_residuals_by_fitted.png")

    return files


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------
def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def write_session_info(path: Path, argv: list[str], data_label: str) -> None:
    lines = [
        f"Python: {platform.python_version()}",
        f"Platform: {platform.platform()}",
        f"Command: {' '.join(argv)}",
        f"Data source: {data_label}",
        "",
        "Package versions:",
    ]
    for name in [
        "numpy",
        "pandas",
        "scipy",
        "statsmodels",
        "patsy",
        "matplotlib",
        "scikit-learn",
    ]:
        lines.append(f"  {name}: {package_version(name)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_table(df: pd.DataFrame, columns: list[str], floatfmt: str = "{:.6g}") -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            value = row[col]
            if isinstance(value, (float, np.floating)):
                cells.append(floatfmt.format(value))
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def write_report(
    path: Path,
    data_label: str,
    cohort: pd.DataFrame,
    flow: pd.DataFrame,
    tables: dict,
    diagnostics: dict,
    fit_status: pd.DataFrame,
    figures: list[str],
    reference: dict | None,
) -> None:
    b1 = tables["b1_summary"].iloc[0]
    fixed = tables["fixed_effects"]
    gate = tables["cohort_gate"]
    fs = fit_status.iloc[0]

    lines = [
        "# GameWell primary analysis report",
        "",
        f"Data source: `{data_label}`",
        "",
        "## Cohort",
        "",
        markdown_table(flow, ["stage", "interval_count", "participant_count"]),
        "",
        f"Primary cohort: **{len(cohort):,} intervals** from "
        f"**{cohort['participant'].nunique():,} participants**; "
        f"**{int((cohort.groupby('participant')['exposure_hours'].nunique() > 1).sum()):,}** "
        "participants have more than one distinct exposure value.",
        "",
    ]

    if reference is not None:
        lines += [
            "Reference comparison (R analysis):",
            "",
            markdown_table(
                gate.assign(reference=[reference[m] for m in gate["metric"]]),
                ["metric", "observed", "reference"],
            ),
            "",
        ]

    lines += [
        "## Model",
        "",
        "The prespecified model was fitted once with REML and a participant "
        "random intercept:",
        "",
        "```",
        "later_valence ~ exposure_within + exposure_between + prior_within",
        "               + prior_between + log_interval_c + (1 | participant)",
        "```",
        "",
        markdown_table(
            fixed,
            [
                "term",
                "estimate",
                "model_SE",
                "model_CI_lower",
                "model_CI_upper",
                "CR2_SE",
                "CR2_df_Satterthwaite",
                "CR2_CI_lower",
                "CR2_CI_upper",
            ],
            floatfmt="{:.6f}",
        ),
        "",
        "## Primary within-person association",
        "",
        f"The `exposure_within` estimate is **{b1['estimate']:.6f} valence "
        f"points per hour**. Model-based 95% CI: "
        f"[{b1['model_CI_lower']:.6f}, {b1['model_CI_upper']:.6f}]. "
        f"CR2 95% CI: [{b1['CR2_CI_lower']:.6f}, {b1['CR2_CI_upper']:.6f}]. "
        f"The wider interval is the {b1['wider_interval_source']} interval "
        f"[{b1['wider_CI_lower']:.6f}, {b1['wider_CI_upper']:.6f}].",
        "",
        f"Addendum 2 category: **{b1['Addendum2_category']}** - "
        f"{b1['category_wording']}.",
        "",
        f"Within-person valence SD: {b1['within_person_valence_SD']:.7f}; "
        f"scaled estimate: {b1['scaled_estimate_SD_units']:.6f} SD units per hour. "
        f"Within-person exposure SD: {b1['exposure_within_SD_hours']:.6f} hours; "
        f"effect per 1 SD of exposure_within: "
        f"{b1['effect_per_1_SD_exposure']:.6f} valence points.",
        "",
        "## Fit status and diagnostics",
        "",
        f"Observations: {int(fs['observations']):,}; participants: "
        f"{int(fs['participants']):,}; singular fit: {bool(fs['singular_fit'])}; "
        f"random-intercept SD: {fs['random_intercept_SD']:.6f}; "
        f"residual SD: {fs['residual_SD']:.6f}; ICC: {fs['ICC']:.6f}.",
        "",
        f"Boundary solution applied: {bool(fs['boundary_solution_applied'])}. "
        f"Raw statsmodels random-intercept variance: "
        f"{fs['raw_MixedLM_random_intercept_variance']:.10f}; "
        f"CR2 working rho: {fs['CR2_working_rho']:.10f}.",
        "",
        "Residual and random-effect summaries are in the CSV files listed "
        "below. All outputs are aggregate; no participant identifiers are "
        "included.",
        "",
        "## Figures",
        "",
    ]
    figure_descriptions = {
        "fig1_cohort_flow.png": "Cohort flow: intervals and participants remaining at each filtering stage.",
        "fig2_exposure_distribution.png": "Distribution of recorded linked-console exposure in the primary cohort (clipped at the 99th percentile; zero-exposure count in the title).",
        "fig3_exposure_within_distribution.png": "Distribution of within-person exposure (interval exposure minus participant mean).",
        "fig4_b1_forest.png": "Primary exposure_within estimate with model-based and CR2 95% intervals; dashed lines mark the +/-0.5 SESOI.",
        "fig5_residual_histogram.png": "Histogram of primary-model residuals.",
        "fig6_residual_qq.png": "Normal Q-Q plot of primary-model residuals.",
        "fig7_residuals_by_fitted.png": "Mean residual in each decile bin of fitted values.",
    }
    for name in figures:
        lines.append(f"- `figures/{name}`: {figure_descriptions.get(name, 'Aggregate figure.')}")
    lines += [
        "",
        "## Limitations",
        "",
        "- Zero recorded sessions are interpreted only under the source's maximal-coverage-on-linkage assumption; there is no interval-level capture flag, so missing capture cannot be distinguished from genuine no-play.",
        "- Nintendo telemetry covers first-party titles; Steam, mobile and unlinked-platform play are excluded from recorded exposure.",
        "- Recorded valence values of 0 occur despite the instrument description's lower bound of 1; they are retained as recorded in the primary analysis.",
        "- Survey timestamps are treated as UTC instants; original export settings remain unverified.",
        "- The model is observational; estimates describe associations and do not establish causation or the direction of any relationship.",
        "- The primary cohort is restricted to linked Xbox/Nintendo participants with usable intervals; results may not generalise to other players or platforms.",
        "- Model-based degrees of freedom are approximated as n - p. The R fit was singular (random-intercept SD = 0), where this equals the lmerTest Satterthwaite df; for non-singular fits this is an approximation.",
        "",
        "## Files",
        "",
        "- `cohort_flow.csv`",
        "- `cohort_gate.csv`",
        "- `descriptives.csv`",
        "- `fixed_effects.csv`",
        "- `b1_summary.csv`",
        "- `fit_status.csv`",
        "- `residual_summary.csv`",
        "- `residual_bins_by_fitted.csv`",
        "- `random_effect_summary.csv`",
        "- `analysis_report.md`",
        "- `session_info.txt`",
        "- `run_metadata.json`",
    ]
    lines += [f"- `figures/{name}`" for name in figures]
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_descriptives(path: Path, cohort: pd.DataFrame) -> None:
    exposure = cohort["exposure_hours"]
    within_valence = cohort["later_valence"] - cohort.groupby("participant")[
        "later_valence"
    ].transform("mean")
    group_sizes = cohort.groupby("participant").size()
    rows = [
        ("n_intervals", int(len(cohort)), "intervals"),
        ("n_participants", int(cohort["participant"].nunique()), "participants"),
        ("interval_duration_median_hours", float(cohort["interval_duration_hours"].median()), "hours"),
        ("interval_duration_q1_hours", float(cohort["interval_duration_hours"].quantile(0.25)), "hours"),
        ("interval_duration_q3_hours", float(cohort["interval_duration_hours"].quantile(0.75)), "hours"),
        ("exposure_mean_hours", float(exposure.mean()), "hours"),
        ("exposure_SD_hours", float(exposure.std(ddof=1)), "hours"),
        ("exposure_median_hours", float(exposure.median()), "hours"),
        ("exposure_zero_intervals", int((exposure == 0).sum()), "intervals"),
        ("exposure_zero_percent", float((exposure == 0).mean() * 100.0), "percent"),
        ("later_valence_mean", float(cohort["later_valence"].mean()), "points"),
        ("later_valence_SD", float(cohort["later_valence"].std(ddof=1)), "points"),
        ("prior_valence_mean", float(cohort["prior_affective_valence"].mean()), "points"),
        ("prior_valence_SD", float(cohort["prior_affective_valence"].std(ddof=1)), "points"),
        ("within_person_valence_SD", float(within_valence.std(ddof=1)), "points"),
        ("exposure_within_SD_hours", float(cohort["exposure_within"].std(ddof=1)), "hours"),
        ("participants_with_exposure_variation", int((cohort.groupby("participant")["exposure_hours"].nunique() > 1).sum()), "participants"),
        ("min_intervals_per_participant", int(group_sizes.min()), "intervals"),
        ("median_intervals_per_participant", float(group_sizes.median()), "intervals"),
        ("max_intervals_per_participant", int(group_sizes.max()), "intervals"),
    ]
    df = pd.DataFrame(rows, columns=["measure", "value", "unit"], dtype=object)
    write_csv(df, path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = out_dir / "figures"

    if args.demo:
        raw = make_demo_data()
        data_label = "synthetic demo data (numbers are meaningless)"
        reference = None
    else:
        raw = load_intervals(args.data)
        data_label = str(Path(args.data))
        reference = REFERENCE_COHORT

    cohort, flow = prepare_cohort(raw)
    model = fit_primary_model(cohort)
    cr2 = cr2_inference(
        model["X"],
        model["y"],
        model["beta"],
        cohort["participant"].to_numpy(),
        model["sigma2"],
        model["tau2"],
    )
    tables = build_tables(cohort, model, cr2)
    diagnostics = build_diagnostics(cohort, model)
    fit_status = build_fit_status(cohort, model, cr2)

    # Save CSVs.
    write_csv(flow, out_dir / "cohort_flow.csv")
    gate = tables["cohort_gate"].copy()
    if reference is not None:
        gate["reference"] = [reference[m] for m in gate["metric"]]
        gate["difference"] = gate["observed"] - gate["reference"]
        gate["match"] = gate["difference"] == 0
    write_csv(gate, out_dir / "cohort_gate.csv")
    write_csv(tables["fixed_effects"], out_dir / "fixed_effects.csv")
    write_csv(tables["b1_summary"], out_dir / "b1_summary.csv")
    write_csv(fit_status, out_dir / "fit_status.csv")
    write_csv(diagnostics["residual_summary"], out_dir / "residual_summary.csv")
    write_csv(diagnostics["residual_bins"], out_dir / "residual_bins_by_fitted.csv")
    write_csv(diagnostics["random_effect_summary"], out_dir / "random_effect_summary.csv")
    write_descriptives(out_dir / "descriptives.csv", cohort)

    # Figures need residuals; pass them through the diagnostics dict.
    diagnostics_with_residuals = dict(diagnostics)
    diagnostics_with_residuals["_residuals"] = model["residuals"]
    figures = make_figures(
        cohort,
        flow,
        {**tables, "_residuals": model["residuals"]},
        diagnostics_with_residuals,
        figure_dir,
    )

    write_session_info(out_dir / "session_info.txt", sys.argv, data_label)
    metadata = {
        "data_source": data_label,
        "mode": "demo" if args.demo else "real",
        "n_intervals": int(len(cohort)),
        "n_participants": int(cohort["participant"].nunique()),
        "boundary_solution_applied": bool(model["boundary"]),
        "b1_estimate": float(tables["b1_summary"].iloc[0]["estimate"]),
        "b1_wider_CI_lower": float(tables["wider_lo"]),
        "b1_wider_CI_upper": float(tables["wider_hi"]),
        "b1_category": tables["category"],
        "figures": figures,
    }
    (out_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    write_report(
        out_dir / "analysis_report.md",
        data_label,
        cohort,
        flow,
        tables,
        diagnostics,
        fit_status,
        figures,
        reference,
    )

    # Aggregate console output only: no participant identifiers or data rows.
    b1 = tables["b1_summary"].iloc[0]
    print(f"Data: {data_label}")
    print(
        f"Cohort: {len(cohort):,} intervals from "
        f"{cohort['participant'].nunique():,} participants; "
        f"{int((cohort.groupby('participant')['exposure_hours'].nunique() > 1).sum()):,} "
        "participants with exposure variation."
    )
    if reference is not None:
        for _, row in gate.iterrows():
            status = "MATCH" if bool(row["match"]) else "DIFFERS"
            print(
                f"Reference {row['metric']}: observed {int(row['observed']):,}; "
                f"reference {int(row['reference']):,}; {status}."
            )
    print(
        f"Primary exposure_within: {b1['estimate']:.6f} points/hour; "
        f"model 95% CI [{b1['model_CI_lower']:.6f}, {b1['model_CI_upper']:.6f}]; "
        f"CR2 95% CI [{b1['CR2_CI_lower']:.6f}, {b1['CR2_CI_upper']:.6f}]."
    )
    print(
        f"Wider interval ({b1['wider_interval_source']}): "
        f"[{b1['wider_CI_lower']:.6f}, {b1['wider_CI_upper']:.6f}]; "
        f"Addendum 2 category {b1['Addendum2_category']}."
    )
    print(f"Outputs written to: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
