# Code guide

This guide is for a reader with basic Python and pandas experience. The scripts are copied unchanged from the analysis workspace; their paths assume the original project layout and need adjustment in a standalone copy. Follow the numbered order below when reproducing the workflow. The analysis scripts were generated with Codex AI assistance and reviewed; the Open Play data-processing pipeline is the dataset authors’ work.

## Scripts, inputs, outputs, and order

### 01_build_intervals.mjs
Reads the existing cleaned daily survey, intake, Xbox, and Nintendo tables, plus the raw daily survey only for an aggregate row count. It pairs consecutive retained surveys, intersects already-cleaned sessions with the intervals, unions overlapping platform minutes, and writes the interval dataset, summaries, plots, and report. It is the interval-construction stage; it does not redo the upstream cleaning.

- Inputs: cleaned survey/intake/Xbox/Nintendo tables and the raw daily survey aggregate-count source.
- Outputs: interval dataset and aggregate artifacts in the interval-build analysis folder.

### 02_diagnose_intervals.mjs
Independently checks the interval dataset and dictionary and computes aggregate outcome-only and exposure-only diagnostics, including separate univariate plots. It does not fit a model or compare exposure with outcomes. It follows interval construction as an independent design-diagnostics stage.

- Inputs: interval dataset, data dictionary, interval-builder script.
- Outputs: aggregate diagnostic CSVs, SVG histograms, and report.

### 03_power_simulation_final.R
Builds the prespecified primary cohort, fits an outcome-only calibration model, and simulates later valence under a grid of assumed within-person exposure effects. Real later valence is used for calibration and its scale only; simulated later values are used in the exposure-containing fits. It is the blinded power-planning stage before the primary analysis.

- Inputs: interval dataset, plan, Addendum 1, variable mapping, and installed R packages lme4/lmerTest.
- Outputs: per-replication and aggregate simulation CSVs, MDE summary, report, session information.

### 04_primary_model_v5.R
Checks the pre-fit hashes and cohort gate, derives the plan variables, then fits the prespecified primary affective-valence mixed model once and saves model-based and CR2 aggregate results and diagnostics. The exposure-within estimate is a within-person association; exposure-between is reported separately. It is the primary analysis stage.

- Inputs: interval dataset, Plan v1, Addenda 1 and 2, variable mapping, hash-check file, and lme4/lmerTest/clubSandwich.
- Outputs: primary fixed-effects, CR2, fit-status, diagnostic, report, and session-info files.

### 05_refit_identical.R
Rebuilds the same primary cohort and fits the identical primary specification once, as permitted by Addendum 3. It saves the fitted object and compares estimates and standard errors with the original table. This is a diagnostics-enabling identity check, not a replacement result.

- Inputs: interval dataset and original fixed-effects CSV.
- Outputs: saved model object and aggregate identity-check CSVs.

### 06_diagnostics.R
Loads the saved refit object without fitting again. It summarizes fit status, residuals, random effects, and residual patterns and writes aggregate plots. It follows the identity check.

- Inputs: saved primary refit RDS and lme4.
- Outputs: diagnostic CSVs, SVG plots, session information, diagnostic report.

### 07_run_sensitivities.R
Runs the prespecified primary-outcome sensitivity specifications, including interval cutoffs, exposure transformations, platform subsets, participant-count restrictions, zero-score exclusion, random slope, and leave-one-participant-out fits. It writes aggregate results and fit notices; some branches report counts without fitting when the prespecified threshold is unmet. It follows the primary fit and diagnostics.

- Inputs: interval dataset, pre-fit gate, saved primary outputs, and lme4/lmerTest/clubSandwich.
- Outputs: sensitivity fit results, summary, errors/notices, and initial report artifacts.

### 08_correct_7a_reporting.R
Recomputes the four 7a interval-cutoff fits without applying the primary 48-hour cap, records the corrected results, and prepares corrected summary materials. The earlier 7a results are marked discarded in the audit trail. It is the correction stage after the initial sensitivity runner.

- Inputs: interval dataset, sensitivity outputs, and the prespecified plan context.
- Outputs: corrected 7a results, corrected sensitivity summary, and report artifacts.

### 09_finalize_sensitivity_report.R
Reads the corrected and retained sensitivity outputs, calculates the prespecified robustness label, and writes the final aggregate sensitivity report and session information. It does not replace the primary model. It follows the 7a correction.

- Inputs: corrected sensitivity tables, fit ledger/report inputs, and plan rules.
- Outputs: final sensitivity report and session information.

### 10_fit_secondary_ls.R
Builds the secondary life-satisfaction cohorts and fits the two prespecified life-satisfaction mixed models once each, including the zero-score exclusion sensitivity. It exports model-based and CR2 results, fit information, and saved model objects. It is a distinct secondary-outcome stage, not a combined well-being score.

- Inputs: interval dataset, plan/addenda, hash and cohort gates, and lme4/lmerTest/clubSandwich.
- Outputs: aggregate results, fixed effects, fit status, CR2 table, saved model objects, session information.

### 11_diagnostics_fit1.R
Loads the saved full-cohort life-satisfaction Fit 1 object without refitting. It calculates residual summaries and fitted-value bins, then writes three aggregate SVG diagnostics. It follows the secondary fits.

- Inputs: saved Fit 1 RDS.
- Outputs: residual summary and bins CSVs, histogram, Q-Q plot, residuals-versus-fitted plot.

### 12_write_report.R
Reads the secondary life-satisfaction aggregate result, fit, and diagnostic tables and assembles the final report. It does not fit a model. It completes the secondary-analysis reporting stage.

- Inputs: secondary aggregate CSVs, diagnostics CSVs, and cohort gate.
- Outputs: secondary analysis report.

### 13_build_descriptive_aggregates.mjs
Reads the interval dataset to calculate the prespecified descriptive cohort counts and interval-duration median, and compares initial versus corrected 7a cohort counts. It writes aggregate tables only. It is the descriptive step used when assembling the public results bundle.

- Inputs: interval dataset and sensitivity fit tables.
- Outputs: descriptive cohort aggregates and the 7a count comparison.

### 14_build_site_input_release_v2.mjs
Copies the prior site-input release and applies the recorded C1/C2/C6 wording and methods-note corrections, then writes the site-input manifest. It does not rerun analyses. It is the final site-input packaging stage.

- Inputs: prior site-input release files and its claims/methods text.
- Outputs: site_input_release_v2 files and SHA-256 manifest.

### 15_create_addendum6.mjs
Writes Addendum 6 and its one-file hash manifest, after checking that neither target exists. The addendum records the approved descriptive aggregates and presentation corrections. It is a documentation stage.

- Inputs: fixed text embedded in the script.
- Outputs: Addendum 6 markdown and its manifest.

### 16_create_addendum7.mjs
Writes Addendum 7 and its one-file hash manifest, after checking that neither target exists. It records presentation-only corrections to the bundle. It is the last dated documentation stage in this release.

- Inputs: fixed text embedded in the script.
- Outputs: Addendum 7 markdown and its manifest.

## Glossary

- **Interval:** the time between two consecutive completed daily surveys; the earlier response is prior and the later response is the endpoint outcome.
- **Within-person:** whether a participant’s interval exposure differs from that participant’s own average. **Between-person:** whether participants with different average exposure differ, conditional on model covariates.
- **Mixed model / random intercept:** a regression that includes participant-specific intercepts to account for repeated observations from the same person.
- **REML:** restricted maximum likelihood, the estimation setting used for the specified mixed models.
- **CR2 cluster-robust standard errors:** an adjustment for uncertainty when observations are grouped within participants, with participant as the cluster.
- **Singular fit:** a boundary variance estimate in the random-effects structure, such as a random-intercept variance estimated at zero.
- **SESOI:** smallest effect size of interest, the prespecified threshold used to describe whether an association is large enough to matter for this project’s interpretation rule.
- **Sensitivity analysis:** a prespecified re-analysis that checks how results behave under a stated alternative analytic choice.
- **Hash / manifest:** a SHA-256 digest is a file fingerprint; a manifest records file paths, sizes, and fingerprints to check integrity.

## What is mine and what came from the dataset authors

The cleaned survey and console tables came from the Open Play project’s own processing pipeline, documented in data-process.qmd. That upstream code was inspected and not modified. The scripts in this folder start from those cleaned tables or from aggregate outputs; they do not claim authorship of the dataset authors’ processing pipeline. The GameWell analysis and packaging scripts were generated with Codex AI assistance and reviewed.
