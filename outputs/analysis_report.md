# GameWell primary analysis report

Data source: `E:\Code\ids\digital-wellbeing-open-play-511bc60\analysis\gamewell_interval_dataset_2026-10-15\gamewell_daily_intervals.csv.gz`

## Cohort

| stage | interval_count | participant_count |
| --- | --- | --- |
| All intervals in file | 15062 | 1104 |
| Linked Xbox and/or Nintendo | 5904 | 419 |
| Valence present at both endpoints | 5774 | 406 |
| Interval duration <= 48 h | 5076 | 371 |
| Exposure non-missing (primary cohort) | 5076 | 371 |

Primary cohort: **5,076 intervals** from **371 participants**; **171** participants have more than one distinct exposure value.

Reference comparison (R analysis):

| metric | observed | reference |
| --- | --- | --- |
| eligible_intervals | 5076 | 5076 |
| participants | 371 | 371 |
| participants_with_exposure_variation | 171 | 171 |

## Model

The prespecified model was fitted once with REML and a participant random intercept:

```
later_valence ~ exposure_within + exposure_between + prior_within
               + prior_between + log_interval_c + (1 | participant)
```

| term | estimate | model_SE | model_CI_lower | model_CI_upper | CR2_SE | CR2_df_Satterthwaite | CR2_CI_lower | CR2_CI_upper |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Intercept | 1.353502 | 0.675058 | 0.030097 | 2.676906 | 0.509670 | 47.861352 | 0.328666 | 2.378338 |
| exposure_within | 0.073059 | 0.106107 | -0.134956 | 0.281075 | 0.107572 | 54.349835 | -0.142579 | 0.288697 |
| exposure_between | -0.000715 | 0.083771 | -0.164942 | 0.163512 | 0.055114 | 33.211686 | -0.112818 | 0.111388 |
| prior_within | 0.172901 | 0.014381 | 0.144708 | 0.201093 | 0.032944 | 109.114326 | 0.107608 | 0.238193 |
| prior_between | 0.984500 | 0.009378 | 0.966115 | 1.002886 | 0.006392 | 55.413195 | 0.971692 | 0.997309 |
| log_interval_c | 0.414813 | 0.775976 | -1.106436 | 1.936061 | 0.859058 | 154.512930 | -1.282202 | 2.111827 |

## Primary within-person association

The `exposure_within` estimate is **0.073059 valence points per hour**. Model-based 95% CI: [-0.134956, 0.281075]. CR2 95% CI: [-0.142579, 0.288697]. The wider interval is the CR2 cluster-robust interval [-0.142579, 0.288697].

Addendum 2 category: **a** - interval entirely within +/-0.5: no association larger than the SESOI is supported.

Within-person valence SD: 12.0559028; scaled estimate: 0.006060 SD units per hour. Within-person exposure SD: 1.665101 hours; effect per 1 SD of exposure_within: 0.121651 valence points.

## Fit status and diagnostics

Observations: 5,076; participants: 371; singular fit: True; random-intercept SD: 0.000000; residual SD: 12.439660; ICC: 0.000000.

Boundary solution applied: True. Raw statsmodels random-intercept variance: 0.0038297978; CR2 working rho: 0.0000000000.

Residual and random-effect summaries are in the CSV files listed below. All outputs are aggregate; no participant identifiers are included.

## Figures

- `figures/fig1_cohort_flow.png`: Cohort flow: intervals and participants remaining at each filtering stage.
- `figures/fig2_exposure_distribution.png`: Distribution of recorded linked-console exposure in the primary cohort (clipped at the 99th percentile; zero-exposure count in the title).
- `figures/fig3_exposure_within_distribution.png`: Distribution of within-person exposure (interval exposure minus participant mean).
- `figures/fig4_b1_forest.png`: Primary exposure_within estimate with model-based and CR2 95% intervals; dashed lines mark the +/-0.5 SESOI.
- `figures/fig5_residual_histogram.png`: Histogram of primary-model residuals.
- `figures/fig6_residual_qq.png`: Normal Q-Q plot of primary-model residuals.
- `figures/fig7_residuals_by_fitted.png`: Mean residual in each decile bin of fitted values.

## Limitations

- Zero recorded sessions are interpreted only under the source's maximal-coverage-on-linkage assumption; there is no interval-level capture flag, so missing capture cannot be distinguished from genuine no-play.
- Nintendo telemetry covers first-party titles; Steam, mobile and unlinked-platform play are excluded from recorded exposure.
- Recorded valence values of 0 occur despite the instrument description's lower bound of 1; they are retained as recorded in the primary analysis.
- Survey timestamps are treated as UTC instants; original export settings remain unverified.
- The model is observational; estimates describe associations and do not establish causation or the direction of any relationship.
- The primary cohort is restricted to linked Xbox/Nintendo participants with usable intervals; results may not generalise to other players or platforms.
- Model-based degrees of freedom are approximated as n - p. The R fit was singular (random-intercept SD = 0), where this equals the lmerTest Satterthwaite df; for non-singular fits this is an approximation.

## Files

- `cohort_flow.csv`
- `cohort_gate.csv`
- `descriptives.csv`
- `fixed_effects.csv`
- `b1_summary.csv`
- `fit_status.csv`
- `residual_summary.csv`
- `residual_bins_by_fitted.csv`
- `random_effect_summary.csv`
- `analysis_report.md`
- `session_info.txt`
- `run_metadata.json`
- `figures/fig1_cohort_flow.png`
- `figures/fig2_exposure_distribution.png`
- `figures/fig3_exposure_within_distribution.png`
- `figures/fig4_b1_forest.png`
- `figures/fig5_residual_histogram.png`
- `figures/fig6_residual_qq.png`
- `figures/fig7_residuals_by_fitted.png`

