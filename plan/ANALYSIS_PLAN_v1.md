# GameWell Analysis Plan v1
Frozen before any exposure-outcome analysis. Deviations must be recorded in a dated addendum, never by editing this file.

## 1. Question and estimand
Among participants with linked Xbox and/or Nintendo accounts, is recorded linked-console play between consecutive daily-survey completions associated with affective valence at the later survey? The primary estimand is the WITHIN-PERSON association: the expected difference in later valence (0-100 scale) when a participant's recorded play in an interval is 1 hour above their own typical level, holding their prior valence and interval length fixed. This is an association in observational data, not a causal effect. Exposure is recorded linked-console play only, not total gaming.

## 2. Primary cohort
Intervals where: Xbox and/or Nintendo is linked; interval duration is <= 48 hours; valence is present at both endpoints; exposure is non-missing. Missing linkage or exposure is never treated as zero. Report counts at each filtering step.

## 3. Variables
- Outcome: later-survey affective valence.
- Exposure: recorded linked-console minutes in the interval (union across platforms), converted to hours.
- exposure_between = participant's mean exposure over their eligible intervals.
- exposure_within = interval exposure minus exposure_between.
- prior valence is decomposed the same way: prior_between (participant mean of prior valence) and prior_within (prior valence minus that mean).
- Interval length: log(interval hours), centred at the cohort mean.

## 4. Primary model
Linear mixed model, REML, random intercept for participant:
later_valence = b0 + b1*exposure_within + b2*exposure_between + b3*prior_within + b4*prior_between + b5*log_interval_c + u_participant + error.
b1 is the primary estimate. b2 is reported separately and labelled a between-person association; the two are never combined or described interchangeably.

## 5. Inference and interpretation
Report b1 with a 95% confidence interval in valence points per hour, and also scaled by the within-person SD of valence. A p-value alone is never presented as evidence of an important effect. The smallest effect of interest and the minimum detectable effect from a blinded power simulation will be recorded in a dated addendum BEFORE the primary model is fitted. Results are described only in association language.

## 6. Secondary analysis
Life satisfaction (separate construct, "satisfied with my life today") is analysed with the same model in its own cohort (life satisfaction present at both endpoints). It is labelled secondary. No combined well-being score is created.

## 7. Sensitivity analyses (all prespecified)
a) Maximum interval 30h, 36h, 72h, and no cutoff (interval length remains a covariate).
b) Exposure as log(1 + minutes), and exposure capped at the 99th percentile.
c) Any-play indicator (exposure > 0) instead of hours.
d) Platform subsets: Xbox-only-linked, Nintendo-only-linked (both-linked reported descriptively only if too small).
e) Excluding participants with fewer than 5 eligible intervals.
f) Excluding rows where either valence endpoint equals 0.
g) Random slope for exposure_within added.
h) Cluster-robust standard errors.
i) Leave-one-participant-out influence check, reported in aggregate.

## 8. Diagnostics
Residual and random-effect distribution checks, convergence and singularity status, ICC, influence summary. Aggregate outputs only.

## 9. Known issues carried forward
- Coverage assumption: zero recorded sessions means zero captured activity on linked platforms, not zero gaming; there is no interval-level capture flag.
- Nintendo telemetry is first-party titles only; Steam and mobile are excluded from exposure.
- Valence/life satisfaction values of 0 exist although the documented range starts at 1; kept as recorded in the primary analysis (sensitivity 7f).
- Survey timestamps are treated as UTC instants; original export settings are unverified.
- 67 daily-survey participants have no intake match and are outside the linked cohort.

## 10. Exploratory rules
Any analysis not listed above is exploratory, labelled as such, and cannot support confirmatory claims.

## 11. Outputs and privacy
Only aggregate results leave the analysis environment. No participant-level data in reports, figures, or the website.
