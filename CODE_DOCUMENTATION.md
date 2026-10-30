# GameWell analysis script: code documentation

## 1. What this document covers

This document explains `code/gamewell_analysis.py`, a single-file Python
implementation of the prespecified **primary** GameWell analysis:

> Among participants with linked Xbox and/or Nintendo accounts, is recorded
> linked-console play between two consecutive daily-survey completions
> associated with affective valence at the later survey?

The analysis is observational. The script estimates an association; it does
not estimate a causal effect.

The script implements the primary affective-valence model only. It does not
run the secondary life-satisfaction model, the sensitivity analyses, the
power simulation, or the leave-one-participant-out analysis that exist in the
wider R pipeline. Those analyses are outside the scope of this file.

### Provenance note

The requested `gamewell_analysis.py` was **not present** in the repository,
in the git index, or anywhere on the machine when this work started. With the
user's approval, this file was reconstructed from the frozen R pipeline
(`code/04_primary_model_v5.R`), the analysis plan (`plan/ANALYSIS_PLAN_v1.md`),
and the saved R reference outputs. It is therefore a reconstruction, not the
original missing file. The reconstruction was checked against the saved R
results; the real-data estimates and intervals agree to numerical precision
(see Section 9).

No data file was modified, cleaned, filtered, recoded, or imputed on disk.
All filtering happens in memory. No participant identifiers are written to
console output, tables, figures, or reports.

---

## 2. Quick start

### Environment

The repository already contained a `.venv`. Its interpreter is Python 3.14.6.
The system `python` command on this machine is a Microsoft Store alias and
does not launch Python, so the virtual-environment interpreter was used
explicitly:

```powershell
.\.venv\Scripts\python.exe --version
```

Installed analysis packages (also pinned in `requirements.txt`):

| Package | Version |
|---|---:|
| numpy | 2.5.4 |
| pandas | 3.0.6 |
| scipy | 1.18.1 |
| statsmodels | 0.15.0 |
| patsy | 1.0.3 |
| matplotlib | 3.11.2 |
| scikit-learn | 1.9.1 |

### Commands

Demo (synthetic data; all numbers are meaningless):

```powershell
.\.venv\Scripts\python.exe code\gamewell_analysis.py --demo --out demo_outputs
```

Real interval file:

```powershell
.\.venv\Scripts\python.exe code\gamewell_analysis.py `
  --data "E:\Code\ids\digital-wellbeing-open-play-511bc60\analysis\gamewell_interval_dataset_2026-10-15\gamewell_daily_intervals.csv.gz" `
  --out outputs
```

`--demo` and `--data` are mutually exclusive. `--out` defaults to `outputs`.
The script creates the output directory and a `figures/` subdirectory if they
do not exist. It overwrites its own named output files on a repeated run, but
it does not delete unrelated files.

---

## 3. Input data and the column map

### Real interval file

The real file used here is:

```
E:\Code\ids\digital-wellbeing-open-play-511bc60\analysis\gamewell_interval_dataset_2026-10-15\gamewell_daily_intervals.csv.gz
```

It contains 15,062 interval rows and 25 columns. Each row is one interval
between two consecutive clean daily-survey completions for one participant.

### `COL` dictionary

At the top of the script, `COL` maps the analysis's internal names to the
column names in the input file:

```python
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
```

This is the only place where raw column names should need editing. If a
different release of the interval file renames columns, edit `COL` and leave
the rest of the script unchanged. `load_intervals()` checks that every mapped
column exists and stops with a clear message if one is missing.

### Linkage encoding

The real file stores `xbox_linked` and `nintendo_linked` as true/false values
with some missing values. `as_linked()` accepts `true`, `1`, `yes`, `y`, and
`t` in any capitalization, and treats everything else, including missing
values, as not linked. This mirrors the R helper:

```r
as_linked <- function(x) tolower(trimws(as.character(x))) %in% c("true", "1", "yes")
```

---

## 4. Step-by-step analysis pipeline

### Step 1: Read the file

`load_intervals()` reads the CSV or gzipped CSV with `pandas.read_csv()`. It
does not alter the file. It returns a data frame in memory.

### Step 2: Apply the prespecified cohort rule

`prepare_cohort()` keeps intervals where all of the following are true:

1. Xbox and/or Nintendo is linked;
2. `interval_duration_hours` is non-missing and **at most 48 hours**;
3. `prior_affective_valence` is non-missing;
4. `later_affective_valence` is non-missing;
5. `recorded_linked_console_minutes_unique` is non-missing.

These are the Plan v1 cohort rules. Missing linkage or exposure is never
treated as zero. If an eligible interval has a non-positive duration, or a
missing participant ID, the function stops with an error, matching the R
pre-fit gate's refusal to proceed.

The function also builds a sequential cohort-flow table. The stages are:

| Stage | Intervals | Participants |
|---|---:|---:|
| All intervals in file | 15,062 | 1,104 |
| Linked Xbox and/or Nintendo | 5,904 | 419 |
| Valence present at both endpoints | 5,774 | 406 |
| Interval duration <= 48 h | 5,076 | 371 |
| Exposure non-missing (primary cohort) | 5,076 | 371 |

The final primary cohort is therefore **5,076 intervals from 371
participants**. Of these 371 participants, **171** have more than one distinct
exposure value and therefore contribute within-person exposure variation.

### Step 3: Derive the model variables

For each interval, let:

- `E_i` = recorded linked-console minutes / 60, in hours;
- `P_i` = prior affective valence;
- `Y_i` = later affective valence;
- `D_i` = interval duration in hours.

For participant `p`, the script computes:

```
exposure_between_p = mean of E_i over that participant's eligible intervals
exposure_within_i  = E_i - exposure_between_p

prior_between_p    = mean of P_i over that participant's eligible intervals
prior_within_i     = P_i - prior_between_p

log_interval_c_i   = log(D_i) - mean(log(D)) over the whole cohort
later_valence_i    = Y_i
```

The within-person terms answer "is this interval above or below this
participant's own usual level?" The between-person term answers "is this
participant's usual level higher or lower than other participants' usual
levels?" They are not interchangeable.

### Step 4: Fit the mixed model

`fit_primary_model()` fits, once, the prespecified linear mixed model with
REML and a random intercept for participant:

```
later_valence ~ exposure_within + exposure_between + prior_within
                + prior_between + log_interval_c + (1 | participant)
```

The model has six fixed effects: an intercept, `exposure_within`,
`exposure_between`, `prior_within`, `prior_between`, and `log_interval_c`.
The random intercept allows each participant to have a different baseline
later-valence level after accounting for the fixed covariates.

The primary estimate is the coefficient on `exposure_within`, denoted `b1`.
It is the estimated difference in later valence associated with a one-hour
increase in a participant's interval exposure relative to that participant's
own mean exposure, holding the other covariates fixed.

### Step 5: Compute model-based and CR2 inference

The script reports two 95% confidence intervals for every fixed effect:

1. **Model-based interval**: uses the mixed model's fixed-effect standard
   error and a t distribution. The degrees of freedom are `n - p`
   (observations minus fixed-effect parameters). For the real data this is
   5,070. The R fit was singular with a random-intercept SD of zero, and
   lmerTest's Satterthwaite approximation also gave approximately 5,070, so
   the two agree here. For a non-singular fit this is an approximation.

2. **CR2 cluster-robust interval**: treats participants as independent
   clusters and allows arbitrary within-participant correlation. The CR2
   adjustment is a finite-sample correction that accounts for each
   participant's leverage. The Satterthwaite degrees of freedom follow
   clubSandwich's `P`-array formula. This is the same type of inference used
   by `clubSandwich::coef_test(..., vcov = "CR2", test = "Satterthwaite")` in
   the R analysis.

The interpretation interval is the **wider** of the model-based and CR2
intervals. The script records which one was wider.

### Step 6: Apply the SESOI interpretation rule

The smallest effect size of interest (SESOI) is **+/-0.5 valence points per
hour**, fixed before the real exposure-outcome estimate existed. Given the
wider interval `[L, U]`, the Addendum 2 category is:

| Category | Condition | Wording |
|---|---|---|
| a | `L > -0.5` and `U < 0.5` | interval entirely within +/-0.5: no association larger than the SESOI is supported |
| b | interval excludes 0 and extends beyond +/-0.5 | association of potentially meaningful size |
| c | interval excludes 0 but lies entirely within +/-0.5 | statistically detectable but small |
| d | otherwise (includes 0 and extends beyond +/-0.5) | inconclusive |

The wording is kept exactly as in the R analysis. The category is a reporting
rule, not a causal claim.

### Step 7: Diagnostics

`build_diagnostics()` produces aggregate summaries of:

- residuals: mean, SD, skewness, excess kurtosis, and quantiles;
- residuals grouped into ten bins by fitted value;
- participant random-intercept estimates: mean, SD, and quantiles.

`build_fit_status()` records the number of observations and participants,
convergence, singularity, variance components, ICC, the raw statsmodels
variance estimate, and the working `rho` used by CR2.

### Step 8: Figures and report

`make_figures()` writes seven aggregate PNG figures. `write_report()` writes
`analysis_report.md` with the cohort flow, model table, primary estimate,
fit status, figure list, and limitations. `write_session_info()` records the
Python and package versions and the exact command. `run_metadata.json` records
the key aggregate results for machine reading.

---

## 5. Function reference

This section explains every function in the script.

### `parse_args(argv=None)`

- **What it does**: Defines and parses the command-line interface.
- **Inputs**: Optional argument list (defaults to `sys.argv`).
- **Outputs**: An `argparse.Namespace` with `demo`, `data`, and `out`.
- **Statistical idea**: None; it only selects the data source and output
  directory. `--demo` and `--data` cannot be used together.

### `as_linked(series)`

- **What it does**: Converts a linkage column to a boolean Series.
- **Inputs**: A pandas Series that may contain booleans, strings such as
  `"true"`/`"false"`, numbers such as `1`/`0`, or missing values.
- **Outputs**: A boolean Series; missing and unrecognized values become
  `False` (not linked).
- **Statistical idea**: This is a data-encoding convenience, not a statistical
  transformation. It ensures the same true/false interpretation as the R
  helper. Missing linkage is not treated as evidence of no console; it simply
  fails the linkage requirement and is excluded from the linked cohort.

### `load_intervals(path)`

- **What it does**: Reads the interval file and validates the column map.
- **Inputs**: A path to a `.csv` or `.csv.gz` file.
- **Outputs**: A pandas DataFrame.
- **Statistical idea**: None; it only loads data. It stops with a clear error
  if the file is missing or if any `COL`-mapped column is absent, rather than
  silently guessing.

### `make_demo_data(seed=20261030, n_participants=160)`

- **What it does**: Builds an in-memory synthetic interval table.
- **Inputs**: Random seed and number of synthetic participants.
- **Outputs**: A DataFrame with the same columns used by the real analysis,
  including some deliberately missing values and some intervals longer than
  48 hours.
- **Statistical idea**: The generator gives each synthetic participant a
  typical exposure level and a random baseline valence, then makes later
  valence depend on prior valence, baseline, a small within-person exposure
  term, the participant random effect, and noise. The generator is only a
  smoke test; its estimates are not meaningful and must never be interpreted
  as study findings.

### `prepare_cohort(df)`

- **What it does**: Applies the primary cohort rule and derives the
  within-person/between-person variables.
- **Inputs**: The raw interval DataFrame.
- **Outputs**: A tuple `(cohort, flow)`, where `cohort` contains only eligible
  intervals with the derived model columns, and `flow` is the sequential
  cohort-flow table.
- **Statistical idea**: This is the crucial "within-person" step. Centering
  exposure and prior valence at each participant's own mean separates
  within-person variation from between-person differences. Centering log
  duration at the cohort mean makes the intercept easier to interpret but does
  not change the `exposure_within` estimate.

### `fit_primary_model(cohort)`

- **What it does**: Fits the mixed model once and prepares the fixed-effect
  and variance-component information needed for inference and diagnostics.
- **Inputs**: The prepared cohort DataFrame.
- **Outputs**: A dictionary containing the fitted object, design matrix,
  outcome, coefficient names, fixed-effect estimates, model covariance,
  residual and fitted values, random effects, variance components, boundary
  flag, convergence status, and captured warning messages.
- **Statistical idea**: The model is a random-intercept linear mixed model
  fitted by REML. REML is a likelihood method that estimates variance
  components after accounting for the fixed effects; it is the same fitting
  approach as the R `lmerTest::lmer(..., REML = TRUE)` call.

  **Boundary handling.** In the real data, lme4 estimated the
  participant random-intercept SD as exactly zero (a singular fit). The Python
  mixed-model optimizer returned a very small positive variance instead
  (`rho = tau^2 / sigma^2 = 2.47e-5`). If `rho < 1e-4`, the script treats the
  fit as being at the same boundary and evaluates the fixed effects and
  model-based covariance at the boundary OLS solution. This is not a
  different model: at `tau^2 = 0` the mixed model reduces to ordinary least
  squares. The choice is recorded in `fit_status.csv` as
  `boundary_solution_applied = True`, together with the raw statsmodels
  variance. For a clearly non-zero random-intercept variance, the script uses
  the mixed-model estimates and covariance directly.

### `_inverse_sqrt_symmetric(matrix)`

- **What it does**: Computes a symmetric inverse square root of a square
  matrix.
- **Inputs**: A symmetric matrix.
- **Outputs**: A matrix `A` such that `A @ matrix @ A` is approximately the
  identity, using an eigenvalue decomposition and a small eigenvalue floor.
- **Statistical idea**: The CR2 adjustment needs
  `(I - H_gg)^(-1/2)`, where `H_gg` is a participant's leverage matrix. The
  inverse square root is computed symmetrically so the adjustment is
  invariant to the ordering of intervals within a participant. The floor
  prevents numerical division by zero when a leverage eigenvalue is at the
  boundary.

### `cr2_inference(X, y, beta, groups, sigma2, tau2)`

- **What it does**: Computes the participant-clustered CR2 covariance matrix,
  CR2 standard errors, Satterthwaite degrees of freedom, and the working
  `rho`.
- **Inputs**: Fixed-effect design matrix `X`, outcome `y`, fixed-effect
  estimates `beta`, participant labels, residual variance `sigma2`, and
  random-intercept variance `tau2`.
- **Outputs**: A dictionary with the CR2 covariance, standard errors,
  degrees of freedom, `rho_used`, and number of clusters.
- **Statistical idea**: The working covariance for participant `g` is
  `sigma2 * (I + rho * J)`, where `J` is a matrix of ones. The CR2 adjustment
  is the finite-sample correction

  ```
  A_g = (I - H_gg)^(-1/2)          when rho = 0

  when rho > 0, with Theta = I + rho * J = U'U,
  U = chol(Theta) (upper triangular) and L = U':
  G_g = U (I - H_gg) Theta U'
  A_g = L G_g^(-1/2) U
  ```

  where `H_gg = X_g (X' W X)^(-1) X_g' W_g`. The cluster score contributions are
  `s_g = X_g' W_g A_g e_g`; the meat is `sum_g s_g s_g'`; and the sandwich
  covariance is `B meat B` with `B = (X' W X)^(-1)`.

  The Satterthwaite df for coefficient `i` uses the `P` matrix:

  ```
  P_i = -H_i' H_i + diag(sum_g ||G_g[i, :]||^2)
  df_i = trace(P_i)^2 / sum(P_i^2)
  ```

  This reproduces the clubSandwich CR2/Satterthwaite calculation used in the
  R analysis. On the real data it gives `df = 54.3498351850827` for
  `exposure_within`, matching the saved R value `54.3498351850823`.

### `interpret_category(lower, upper)`

- **What it does**: Maps a confidence interval to an Addendum 2 category.
- **Inputs**: Lower and upper bounds of the wider 95% interval.
- **Outputs**: A one-letter category (`a`, `b`, `c`, or `d`) and the exact
  wording from the R analysis.
- **Statistical idea**: This is a pre-specified equivalence/indeterminacy
  reporting rule based on the +/-0.5 SESOI. It is not a new test and does not
  change the interval.

### `build_tables(cohort, model, cr2)`

- **What it does**: Assembles the fixed-effect table, the primary `b1`
  summary, and the cohort-gate table.
- **Inputs**: Cohort, fitted-model dictionary, and CR2 dictionary.
- **Outputs**: A dictionary with `fixed_effects`, `b1_summary`,
  `cohort_gate`, the chosen category and wording, the wider interval source,
  and the wider bounds.
- **Statistical idea**: For each fixed effect it combines the estimate, model
  SE, model df, model t and p, model CI, CR2 SE, CR2 Satterthwaite df, CR2 t
  and p, and CR2 CI. For `b1` it also computes the within-person valence SD,
  the estimate scaled by that SD, the within-person exposure SD, and the
  effect per one SD of exposure. The wider interval is selected by comparing
  interval widths.

### `build_diagnostics(cohort, model)`

- **What it does**: Produces aggregate residual and random-effect summaries.
- **Inputs**: Cohort and fitted-model dictionary.
- **Outputs**: Three DataFrames: `residual_summary`, `residual_bins`, and
  `random_effect_summary`.
- **Statistical idea**: Residual summaries check the distributional shape of
  the model residuals (mean, SD, skewness, kurtosis, quantiles). The decile
  bins show whether the mean residual changes across the fitted-value range,
  a simple check for systematic lack of fit. The random-effect summary shows
  the distribution of participant intercepts; in the real data all are zero
  because the fitted random-intercept variance is at the boundary.

### `build_fit_status(cohort, model, cr2)`

- **What it does**: Builds a one-row aggregate fit-status table.
- **Inputs**: Cohort, fitted-model dictionary, and CR2 dictionary.
- **Outputs**: A DataFrame with observations, participants, exposure
  variation, convergence, singularity, variance components, ICC, raw and
  working `rho`, group-size range, and warning text.
- **Statistical idea**: The ICC is `tau^2 / (tau^2 + sigma^2)`, the share of
  outcome variance attributed to participant-level differences. In the real
  data both `tau^2` and the ICC are zero because the random intercept is at
  the boundary.

### `_save_figure(fig, path)`

- **What it does**: Tightens the layout, saves a figure at 160 dpi, and closes
  it.
- **Inputs**: A matplotlib figure and an output path.
- **Outputs**: A PNG file.
- **Statistical idea**: None; it is a file-handling helper.

### `make_figures(cohort, flow, tables, diagnostics, figure_dir)`

- **What it does**: Creates the seven aggregate figures described in Section
  7.
- **Inputs**: Cohort, cohort flow, table dictionary, diagnostics dictionary,
  and figure directory.
- **Outputs**: A list of figure filenames.
- **Statistical idea**: The figures visualise cohort attrition, exposure
  distributions, the primary estimate and its two intervals, and residual
  diagnostics. They contain no participant identifiers.

### `write_csv(df, path)`

- **What it does**: Writes a DataFrame to CSV without the index.
- **Inputs**: DataFrame and path.
- **Outputs**: CSV file.
- **Statistical idea**: None.

### `package_version(name)`

- **What it does**: Looks up an installed package version.
- **Inputs**: Package name.
- **Outputs**: Version string or `"not installed"`.
- **Statistical idea**: None; reproducibility metadata.

### `write_session_info(path, argv, data_label)`

- **What it does**: Writes Python, platform, command, data source, and package
  versions.
- **Inputs**: Output path, command-line arguments, data label.
- **Outputs**: `session_info.txt`.
- **Statistical idea**: None; reproducibility metadata.

### `markdown_table(df, columns, floatfmt="{:.6g}")`

- **What it does**: Formats a DataFrame as a GitHub-flavoured Markdown table.
- **Inputs**: DataFrame, column list, float format.
- **Outputs**: Markdown string.
- **Statistical idea**: None; reporting helper.

### `write_report(...)`

- **What it does**: Writes the human-readable `analysis_report.md`.
- **Inputs**: Output path, data label, cohort, flow, tables, diagnostics,
  fit status, figure list, and optional R reference counts.
- **Outputs**: Markdown report.
- **Statistical idea**: None beyond presenting the model results and the
  pre-specified interpretation rule.

### `write_descriptives(path, cohort)`

- **What it does**: Writes aggregate descriptive statistics.
- **Inputs**: Output path and cohort.
- **Outputs**: `descriptives.csv`.
- **Statistical idea**: Summarises interval duration, exposure, prior and
  later valence, within-person valence SD, exposure-within SD, and
  participant group sizes. It contains no participant-level rows.

### `main(argv=None)`

- **What it does**: Orchestrates the full run: parse arguments, load or
  generate data, prepare the cohort, fit the model, compute CR2 inference,
  build tables and diagnostics, write CSVs and figures, write the report and
  session metadata, and print an aggregate console summary.
- **Inputs**: Optional command-line argument list.
- **Outputs**: Process exit code 0 on success; files in the output directory.
- **Statistical idea**: None beyond calling the analysis steps in the correct
  order.

---

## 6. Statistical details

### Why a mixed model?

Daily survey responses from the same participant are likely correlated.
Ignoring that correlation would understate uncertainty. A random intercept
for participant lets each person have their own baseline later-valence level;
the fixed effects then describe associations conditional on that baseline.

### Why within-person and between-person exposure separately?

If a person generally plays a lot and also reports high valence, a simple
exposure coefficient mixes two different comparisons:

- **within-person**: Is this person's valence higher than usual in intervals
  when they played more than usual?
- **between-person**: Do people who usually play more also usually report
  higher valence?

These can differ. The primary estimand is the within-person association. The
model includes both terms so they are not conflated. The between-person term
is reported separately and is conditional on `prior_between`.

### Why REML?

REML estimates the variance components without treating the fixed-effect
estimates as known. It is the prespecified fitting method and the method used
by the R analysis. The script does not compare REML with ML or try alternative
optimizers.

### What is CR2?

Cluster-robust standard errors treat each participant as a cluster and allow
arbitrary correlation within a participant. The "CR2" correction improves
finite-sample behaviour by adjusting each cluster's residual for its leverage.
The Satterthwaite approximation converts the resulting variance estimate into
an effective degrees-of-freedom value for a t reference distribution. This
matters here because the number of participants (371) is much smaller than the
number of intervals (5,076).

### Why report the wider interval?

The analysis plan pre-specified that the interpretation interval is the wider
of the model-based and CR2 intervals. This avoids choosing the more favourable
interval after seeing the data. The script records which interval was wider.

### What the SESOI categories mean

The +/-0.5 points-per-hour band is a judgment-based smallest effect size of
interest, not a clinical or established standard. Category `a` means the whole
interval is inside the band, so an association larger than the SESOI is not
supported. Category `d` means the interval includes zero and extends beyond
the band, so the result is inconclusive. Categories `b` and `c` describe
intervals that exclude zero but differ in whether they extend beyond the band.

---

## 7. Figures and what each shows

All figures are aggregate and contain no participant identifiers.

| File | What it shows |
|---|---|
| `figures/fig1_cohort_flow.png` | Two horizontal bar panels showing how many intervals and participants remain at each cohort-filtering stage. |
| `figures/fig2_exposure_distribution.png` | Distribution of recorded linked-console exposure in the primary cohort, clipped at the 99th percentile for display; the title reports the number of zero-exposure intervals. |
| `figures/fig3_exposure_within_distribution.png` | Distribution of within-person exposure (interval exposure minus the participant's mean), with a vertical line at zero; clipped at the 1st and 99th percentiles for display. |
| `figures/fig4_b1_forest.png` | The primary `exposure_within` estimate with the model-based and CR2 95% intervals; dashed vertical lines mark zero and the +/-0.5 SESOI. |
| `figures/fig5_residual_histogram.png` | Histogram of the primary-model residuals using the Freedman-Diaconis bin rule. |
| `figures/fig6_residual_qq.png` | Normal Q-Q plot of the primary-model residuals, with a reference line. |
| `figures/fig7_residuals_by_fitted.png` | Mean residual in each of ten fitted-value decile bins, with a horizontal line at zero; a flat pattern is consistent with no strong systematic misfit. |

---

## 8. Output files

The script writes these files to the `--out` directory:

| File | Contents |
|---|---|
| `cohort_flow.csv` | Sequential interval and participant counts at each cohort stage. |
| `cohort_gate.csv` | Observed cohort counts; in real-data mode also the R reference counts, differences, and match flags. |
| `descriptives.csv` | Aggregate duration, exposure, valence, within-person SD, and group-size summaries. |
| `fixed_effects.csv` | All six fixed effects with model-based and CR2 SEs, dfs, t values, p values, and 95% CIs. |
| `b1_summary.csv` | Primary `exposure_within` estimate, both CIs, wider interval, scaled effect, SESOI, category, and wording. |
| `fit_status.csv` | Convergence, singularity, variance components, ICC, boundary handling, raw and working `rho`, group-size range, and warnings. |
| `residual_summary.csv` | Residual mean, SD, skewness, excess kurtosis, and quantiles. |
| `residual_bins_by_fitted.csv` | Ten fitted-value bins with interval count, mean fitted value, mean residual, and residual SD. |
| `random_effect_summary.csv` | Participant random-intercept mean, SD, and quantiles. |
| `analysis_report.md` | Human-readable report with cohort flow, model table, primary result, fit status, figures, limitations, and file list. |
| `session_info.txt` | Python/platform/package versions and the exact command. |
| `run_metadata.json` | Machine-readable key results and figure list. |
| `figures/fig1_cohort_flow.png` ... `figures/fig7_residuals_by_fitted.png` | The seven figures described in Section 7. |

---

## 9. Verification runs and exact results

### Demo run

Command:

```powershell
.\.venv\Scripts\python.exe code\gamewell_analysis.py --demo --out demo_outputs
```

Result (synthetic numbers are meaningless):

- Cohort: 1,045 intervals from 142 participants; 140 participants with
  exposure variation.
- Primary estimate: 0.343897 points/hour.
- Model 95% CI: [-0.003134, 0.690928].
- CR2 95% CI: [-0.009982, 0.697775].
- Wider interval: CR2 [-0.009982, 0.697775]; category d.
- Fit status: non-singular, random-intercept SD 3.876, residual SD 8.103,
  ICC 0.186. This run exercises the non-boundary code path.

The demo produced the full set of CSV, Markdown, JSON, text, and PNG files
listed in Section 8 under `demo_outputs/`.

### Real-data run

Command:

```powershell
.\.venv\Scripts\python.exe code\gamewell_analysis.py `
  --data "E:\Code\ids\digital-wellbeing-open-play-511bc60\analysis\gamewell_interval_dataset_2026-10-15\gamewell_daily_intervals.csv.gz" `
  --out outputs
```

Cohort gate:

| Metric | Python | R reference | Match |
|---|---:|---:|---|
| Eligible intervals | 5,076 | 5,076 | yes |
| Participants | 371 | 371 | yes |
| Participants with exposure variation | 171 | 171 | yes |

Primary result:

| Quantity | Python | R reference | Difference |
|---|---:|---:|---:|
| `exposure_within` estimate | 0.07305918934111699 | 0.0730591893411188 | ~1.8e-15 |
| Model 95% CI lower | -0.13495617693406003 | -0.13495617693406 | ~1e-15 |
| Model 95% CI upper | 0.281074555616294 | 0.281074555616298 | ~4e-15 |
| CR2 95% CI lower | -0.14257850285913293 | -0.142578502859132 | ~1e-15 |
| CR2 95% CI upper | 0.2886968815413669 | 0.288696881541369 | ~2e-15 |
| CR2 Satterthwaite df | 54.349835185082675 | 54.3498351850823 | ~4e-13 |
| Category | a | a | none |

The wider interval is the CR2 interval. The Addendum 2 wording is:
"interval entirely within +/-0.5: no association larger than the SESOI is
supported."

Other real-data checks:

- Model SE for `exposure_within`: 0.10610690219895884, matching the R value
  0.106106902198959.
- CR2 SE for `exposure_within`: 0.10757230222970654, matching the R value
  0.107572302229707.
- Within-person valence SD: 12.05590280500051, matching the R Addendum 1
  value 12.0559028050005.
- Within-person exposure SD: 1.6651006938313948 hours, matching the R value
  1.66510069383139.
- Effect per 1 SD of exposure_within: 0.12165090686265315 valence points,
  matching the R value 0.121650906862656.
- Residual SD: 12.439659734090412; residual summary mean approximately zero,
  SD 12.433530312809644, skewness -0.7532369593005072, excess kurtosis
  3.505462483453109. These match the saved R diagnostics to numerical
  precision.
- Random-intercept SD: 0.0; ICC: 0.0; singular fit: true. The R fit was also
  singular with random-intercept SD 0.

### Boundary solution note

The raw statsmodels MixedLM fit returned a tiny positive random-intercept
variance (0.003829797795296998) and `rho = 2.4749340278796825e-05`. The R
lme4 fit returned exactly zero. The script treats `rho < 1e-4` as the same
boundary and evaluates the fixed effects and model-based covariance at the
OLS boundary solution. This is why the Python fixed-effect estimates and
model-based SEs match the R values exactly. The raw statsmodels variance and
the boundary flag are recorded in `fit_status.csv`; nothing is hidden.

---

## 10. Limitations stated in the script docstring

The script's module docstring lists these limitations, and they are repeated
in `analysis_report.md`:

- Zero recorded sessions are interpreted only under the source's
  maximal-coverage-on-linkage assumption. There is no interval-level capture
  flag, so missing capture cannot be distinguished from genuine no-play.
- Nintendo telemetry covers first-party titles only; Steam, mobile and
  unlinked-platform play are excluded from recorded exposure.
- Recorded valence values of 0 occur despite the instrument description's
  lower bound of 1; they are retained as recorded in the primary analysis.
- Survey timestamps are treated as UTC instants; the original export clock
  configuration remains unverified.
- The model is observational. Estimates describe associations, not causal
  effects, and do not locate the mood response relative to each session within
  an interval.
- The primary cohort is restricted to participants with linked Xbox and/or
  Nintendo accounts and usable intervals; results may not generalise to other
  players or platforms.
- Model-based degrees of freedom are approximated as `n - p`. The R fit was
  singular (random-intercept SD = 0), where this equals the lmerTest
  Satterthwaite df; for non-singular fits this is an approximation.

Additional practical points:

- The analysis file is a derived interval dataset. It already reflects the
  source pipeline's cleaning, exclusions, timestamp handling, and platform
  union rules. This script does not re-clean or reconstruct those steps.
- The exposure measure is recorded linked-console time, not total gaming time.
  A zero means no intersecting cleaned session under the coverage assumption,
  not proof that no play occurred.
- The primary cohort is a selected subset of the full survey sample. The
  results apply to that linked and interval-eligible group.
- The CR2 implementation was checked against the saved R clubSandwich output
  on this dataset. It is not a general-purpose replacement for clubSandwich
  and was not validated on other models or datasets.

---

## 11. What to check by hand

1. **Confirm the data file is the intended frozen release.** The run used
   `gamewell_daily_intervals.csv.gz` from the sibling research repository
   `digital-wellbeing-open-play-511bc60`. Check its hash against the project
   manifest before treating the numbers as the final study results.
2. **Check column names if the data release changes.** Only `COL` should need
   editing. If a column is renamed, `load_intervals()` will stop rather than
   silently produce wrong results.
3. **Inspect the cohort flow.** The script reports 15,062 all intervals,
   5,904 linked, 5,774 with valence at both endpoints, and 5,076 in the
   primary cohort. These should match the frozen analysis pipeline.
4. **Inspect `fit_status.csv`.** The real fit is singular; the script applies
   the boundary solution and records the raw statsmodels variance. If a future
   data release yields a clearly non-zero random-intercept variance, the
   script will use the mixed-model covariance instead.
5. **Inspect the figures.** In particular, check the exposure distribution's
   zero spike and the residual Q-Q plot. The residuals are left-skewed and
   heavy-tailed; the model-based intervals rely on distributional
   approximations, which is one reason the CR2 interval is also reported.
6. **Confirm the R reference values.** The saved R outputs used for comparison
   are in
   `digital-wellbeing-open-play-511bc60/analysis/gamewell_primary_model_2026-10-16/`
   (`b1_summary.csv`, `fixed_effects.csv`, `cr2_coef_test.csv`,
   `cr2_conf_int.csv`, `cohort_gate.csv`).
7. **Check that no identifiers leaked.** A text search of the output directory
   for participant IDs should return nothing. The script only writes
   aggregate tables and figures.

---

## 12. Reproducibility notes

- Random seed for the demo: `20261030`.
- The real analysis is deterministic given the input file, the column map,
  and the package versions in `requirements.txt`.
- The script does not use `git`, does not write to the input file, and does
  not install packages at run time.
- `session_info.txt` records the exact command and environment used.
- The output directory can be regenerated with the commands in Section 2.
