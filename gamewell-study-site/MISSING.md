# Missing values

- `cohort_flow.csv` does not provide a participant count for **All valid consecutive survey intervals**; the cohort flow leaves that field blank.
- `cohort_flow.csv` does not provide a participant count for **Linked intervals with life satisfaction at both endpoints before duration limit**; the cohort flow leaves that field blank.
- `headline.json` records the life-satisfaction `MDE_80_points_per_hour` as **not available in existing outputs**; it is not displayed.
- `sensitivity_results.csv` provides no estimate or interval for `7d_both_linked` because it is counts-only; it is not plotted and its missing estimate is not treated as zero.
