# GameWell primary analysis report

Data source: `synthetic demo data (numbers are meaningless)`

## Cohort

| stage | interval_count | participant_count |
| --- | --- | --- |
| All intervals in file | 1420 | 160 |
| Linked Xbox and/or Nintendo | 1253 | 142 |
| Valence present at both endpoints | 1154 | 142 |
| Interval duration <= 48 h | 1062 | 142 |
| Exposure non-missing (primary cohort) | 1045 | 142 |

Primary cohort: **1,045 intervals** from **142 participants**; **140** participants have more than one distinct exposure value.

## Model

The prespecified model was fitted once with REML and a participant random intercept:

```
later_valence ~ exposure_within + exposure_between + prior_within
               + prior_between + log_interval_c + (1 | participant)
```

| term | estimate | model_SE | model_CI_lower | model_CI_upper | CR2_SE | CR2_df_Satterthwaite | CR2_CI_lower | CR2_CI_upper |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Intercept | 5.823487 | 2.326293 | 1.258719 | 10.388255 | 2.570643 | 44.928242 | 0.645717 | 11.001257 |
| exposure_within | 0.343897 | 0.176854 | -0.003134 | 0.690928 | 0.173175 | 29.585589 | -0.009982 | 0.697775 |
| exposure_between | 0.265546 | 0.427415 | -0.573150 | 1.104241 | 0.426377 | 21.764198 | -0.619261 | 1.150353 |
| prior_within | 0.469558 | 0.056370 | 0.358947 | 0.580170 | 0.057470 | 89.078080 | 0.355368 | 0.583749 |
| prior_between | 0.919793 | 0.036888 | 0.847410 | 0.992176 | 0.040479 | 47.940933 | 0.838402 | 1.001184 |
| log_interval_c | 0.189924 | 0.882597 | -1.541952 | 1.921800 | 0.888354 | 101.580073 | -1.572209 | 1.952057 |

## Primary within-person association

The `exposure_within` estimate is **0.343897 valence points per hour**. Model-based 95% CI: [-0.003134, 0.690928]. CR2 95% CI: [-0.009982, 0.697775]. The wider interval is the CR2 cluster-robust interval [-0.009982, 0.697775].

Addendum 2 category: **d** - interval includes 0 and extends beyond +/-0.5: inconclusive.

Within-person valence SD: 7.7928161; scaled estimate: 0.044130 SD units per hour. Within-person exposure SD: 1.426511 hours; effect per 1 SD of exposure_within: 0.490573 valence points.

## Fit status and diagnostics

Observations: 1,045; participants: 142; singular fit: False; random-intercept SD: 3.876264; residual SD: 8.102880; ICC: 0.186230.

Boundary solution applied: False. Raw statsmodels random-intercept variance: 15.0254214597; CR2 working rho: 0.2288483995.

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

