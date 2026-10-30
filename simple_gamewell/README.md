# Simple GameWell analysis

A small, self-contained project with one dataset and one Python program.

## Run it

From `E:\Code\ids\gamewell-public`:

```powershell
.\.venv\Scripts\python.exe simple_gamewell\analyze.py
```

Or from inside `simple_gamewell`:

```powershell
..\.venv\Scripts\python.exe analyze.py
```

The program reads `data/gamewell_daily_intervals.csv.gz`, writes graphs and
tables to `outputs/`, and prints a short aggregate summary. It does not modify
the data file.

## What the program does

1. Loads the daily interval dataset with pandas.
2. Keeps intervals where:
   - Xbox and/or Nintendo is linked;
   - interval duration is between 0 and 48 hours;
   - prior and later affective valence are present;
   - recorded linked-console exposure is present.
3. Builds within-person and between-person exposure variables.
4. Compares three predictive models:
   - mean baseline;
   - linear regression;
   - random forest.
5. Splits the data by participant so the same person is not in both the
   training and test sets.
6. Produces seven graphs and five aggregate CSV tables.

## Outputs

```text
outputs/
├── cohort_flow.csv
├── descriptives.csv
├── model_metrics.csv
├── feature_importance.csv
├── linear_coefficients.csv
├── summary.md
└── figures/
    ├── fig1_cohort_flow.png
    ├── fig2_exposure_distribution.png
    ├── fig3_exposure_vs_valence.png
    ├── fig4_model_comparison.png
    ├── fig5_actual_vs_predicted.png
    ├── fig6_feature_importance.png
    └── fig7_residuals.png
```

## Important caveat

This is an exploratory predictive analysis. It shows how well prior valence,
recorded play and interval duration predict later valence. It does **not**
estimate a causal effect of gaming. The formal within-person mixed-model
analysis is a separate, more specialised analysis.
