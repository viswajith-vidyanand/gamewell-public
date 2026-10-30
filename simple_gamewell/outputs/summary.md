# Simple GameWell analysis

## What was analysed

The analysis uses consecutive daily-survey intervals from participants
with a linked Xbox and/or Nintendo account. An interval is included when
both valence values are present, the interval is no longer than 48 hours,
and recorded linked-console exposure is non-missing.

- Analysis cohort: **5,076 intervals** from **371 participants**.
- Zero recorded exposure: **66.8%** of intervals.
- Correlation between within-person exposure and later valence: **r = 0.008** (descriptive only).

## Cohort flow

| Stage | Intervals | Participants |
|---|---:|---:|
| All intervals in file | 15,062 | 1,104 |
| Linked Xbox and/or Nintendo | 5,904 | 419 |
| Valence at both endpoints | 5,774 | 406 |
| Duration 0-48 hours | 5,076 | 371 |
| Exposure non-missing (analysis cohort) | 5,076 | 371 |

## Descriptive statistics

| Measure | Value | Unit |
|---|---:|---|
| n_intervals | 5076 | intervals |
| n_participants | 371 | participants |
| participants_with_exposure_variation | 171 | participants |
| interval_duration_median | 24.4265 | hours |
| exposure_mean | 1.2020 | hours |
| exposure_SD | 2.6686 | hours |
| exposure_median | 0.0000 | hours |
| exposure_zero_percent | 66.7652 | percent |
| prior_valence_mean | 68.5971 | points |
| prior_valence_SD | 22.2331 | points |
| later_valence_mean | 68.8865 | points |
| later_valence_SD | 22.2505 | points |
| within_person_valence_SD | 12.0559 | points |
| exposure_within_SD | 1.6651 | hours |
| min_intervals_per_participant | 1 | intervals |
| median_intervals_per_participant | 14.0000 | intervals |
| max_intervals_per_participant | 29 | intervals |

## Model comparison

The data were split by participant: 80% of participants for training
and 20% for testing. Keeping participants separate prevents the same
person appearing in both sets.

| Model | Train R-squared | Test R-squared | Test MAE | Test RMSE |
|---|---:|---:|---:|---:|
| Mean baseline | 0.0000 | -0.0730 | 18.1896 | 22.5518 |
| Linear regression | 0.5580 | 0.4913 | 11.1399 | 15.5282 |
| Random forest | 0.7451 | 0.4838 | 11.2104 | 15.6414 |

The best test R-squared was **0.491** for the **Linear regression**, with a test MAE of **11.14** valence points.

## Most important predictors

Permutation importance measures how much the random forest's test
error increases when a feature is shuffled. Larger values mean the
feature mattered more for prediction.

| Feature | Importance (MAE increase) | SD |
|---|---:|---:|
| Prior valence | 9.9588 | 0.3261 |
| Interval duration | 0.1785 | 0.0960 |
| Exposure: person average | 0.1467 | 0.0946 |
| Exposure: within person | 0.1008 | 0.0626 |

## Important caveat

This is an exploratory predictive analysis, not a causal analysis.
A random forest can find patterns that predict later valence, but it
cannot show that gaming caused a change in valence. The formal
within-person mixed-model analysis is a separate, more specialised
analysis.

## Files

- `cohort_flow.csv` - counts at each filtering step
- `descriptives.csv` - aggregate descriptive statistics
- `model_metrics.csv` - train/test performance for all models
- `feature_importance.csv` - random-forest permutation importance
- `linear_coefficients.csv` - linear-regression coefficients
- `figures/fig1_cohort_flow.png` ... `figures/fig7_residuals.png`
