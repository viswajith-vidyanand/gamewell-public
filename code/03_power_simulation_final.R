out_dir <- "analysis/gamewell_power_simulation_2026-10-15"
input <- "analysis/gamewell_interval_dataset_2026-10-15/gamewell_daily_intervals.csv.gz"
mapping_file <- "analysis/gamewell_analysis_plan_2026-10-15/VARIABLE_MAPPING.csv"
plan_file <- "analysis/gamewell_analysis_plan_2026-10-15/ANALYSIS_PLAN_v1.md"
addendum_file <- "analysis/gamewell_analysis_plan_2026-10-15/ADDENDUM_1_2026-10-15.md"
rep_file <- file.path(out_dir, "simulation_replications_v2.csv")
summary_file <- file.path(out_dir, "simulation_summary_v2.csv")
metrics_file <- file.path(out_dir, "simulation_metrics_v2.csv")
mde_file <- file.path(out_dir, "mde_estimate_v2.csv")
report_file <- file.path(out_dir, "REPORT_v2.md")
session_file <- file.path(out_dir, "ENVIRONMENT_SESSIONINFO_v2.txt")
needed <- c(rep_file, summary_file, metrics_file, mde_file, report_file, session_file)
if (any(file.exists(needed))) stop("Refusing to overwrite an existing output file.")
if (!requireNamespace("lme4", quietly = TRUE) || !requireNamespace("lmerTest", quietly = TRUE)) stop("Required package missing; no installation attempted.")
stopifnot(file.exists(input), file.exists(mapping_file), file.exists(plan_file), file.exists(addendum_file))

mapping <- read.csv(mapping_file, stringsAsFactors = FALSE, check.names = FALSE)
mapped <- trimws(unlist(strsplit(paste(mapping$source_column, collapse = ";"), ";", fixed = TRUE)))
cols <- c("participant_id", "prior_affective_valence", "later_affective_valence", "interval_duration_hours", "xbox_linked", "nintendo_linked", "recorded_linked_console_minutes_unique")
if (!all(cols %in% mapped)) stop("Column mapping verification failed.")
plan <- paste(readLines(plan_file, warn = FALSE), collapse = "\n")
addendum <- paste(readLines(addendum_file, warn = FALSE), collapse = "\n")
if (!grepl("duration is <= 48 hours", plan, fixed = TRUE) || !grepl("exposure is non-missing", plan, fixed = TRUE) || !grepl("participant's mean exposure over their eligible intervals", plan, fixed = TRUE)) stop("Plan section check failed.")
if (!grepl("pooled SD of (later valence minus that participant's own mean later valence)", addendum, fixed = TRUE)) stop("Addendum SD definition check failed.")

d <- read.csv(gzfile(input), stringsAsFactors = FALSE, check.names = FALSE)
if (!all(cols %in% names(d))) stop("One or more mapped columns are missing from interval data.")
is_linked <- function(x) tolower(trimws(as.character(x))) %in% c("true", "1", "yes")
keep <- (is_linked(d$xbox_linked) | is_linked(d$nintendo_linked)) &
  !is.na(d$interval_duration_hours) & d$interval_duration_hours <= 48 &
  !is.na(d$prior_affective_valence) & !is.na(d$later_affective_valence) &
  !is.na(d$recorded_linked_console_minutes_unique)
raw_counts <- c(intervals = sum(keep), participants = length(unique(as.character(d$participant_id[keep]))))
dat <- d[keep, cols, drop = FALSE]
dat$participant <- factor(as.character(dat$participant_id))
dat$exposure_hours <- dat$recorded_linked_console_minutes_unique / 60
dat$exposure_between <- ave(dat$exposure_hours, dat$participant, FUN = mean)
dat$exposure_within <- dat$exposure_hours - dat$exposure_between
dat$prior_between <- ave(dat$prior_affective_valence, dat$participant, FUN = mean)
dat$prior_within <- dat$prior_affective_valence - dat$prior_between
dat$log_interval_c <- log(dat$interval_duration_hours) - mean(log(dat$interval_duration_hours))
variation <- vapply(split(dat$exposure_hours, dat$participant), function(x) length(unique(x)) > 1L, logical(1))
raw_counts <- c(raw_counts, participants_any_exposure_variation = sum(variation))
expected <- c(intervals = 5076L, participants = 371L, participants_any_exposure_variation = 171L)
if (!identical(as.integer(raw_counts), as.integer(expected))) {
  stop(paste0("STOP before simulation: cohort gate counts differed. Observed: ", paste(names(raw_counts), raw_counts, sep="=", collapse="; ")))
}

# Deliberately pass the outcome-only model a frame that contains no exposure columns.
outcome_data <- data.frame(
  later_valence = dat$later_affective_valence,
  prior_within = dat$prior_within,
  prior_between = dat$prior_between,
  log_interval_c = dat$log_interval_c,
  participant = dat$participant
)
outcome_fit <- lme4::lmer(later_valence ~ prior_within + prior_between + log_interval_c + (1 | participant), data = outcome_data, REML = TRUE, control = lme4::lmerControl(check.conv.singular = "ignore"))
fix <- lme4::fixef(outcome_fit)
fixed_prediction <- unname(fix["(Intercept)"] + fix["prior_within"] * dat$prior_within + fix["prior_between"] * dat$prior_between + fix["log_interval_c"] * dat$log_interval_c)
random_intercept_sd <- as.numeric(attr(lme4::VarCorr(outcome_fit)$participant, "stddev"))
residual_sd <- as.numeric(stats::sigma(outcome_fit))
later_centered <- dat$later_affective_valence - ave(dat$later_affective_valence, dat$participant, FUN = mean)
within_person_valence_sd <- stats::sd(later_centered)
exposure_within_sd <- stats::sd(dat$exposure_within)
participant_exposure_means <- unique(data.frame(participant=dat$participant, exposure_between=dat$exposure_between))$exposure_between
exposure_between_sd <- stats::sd(participant_exposure_means)
if (any(!is.finite(c(random_intercept_sd, residual_sd, within_person_valence_sd, exposure_within_sd, exposure_between_sd)))) stop("A required model or scale estimate is not finite.")
if (residual_sd <= 0 || within_person_valence_sd <= 0 || exposure_within_sd <= 0) stop("A required residual variance or scale estimate is nonpositive.")

fixed_rows <- data.frame(term=names(fix), estimate=as.numeric(fix), stringsAsFactors=FALSE)
metrics <- data.frame(
  metric=c("eligible_intervals","participants","participants_any_exposure_variation","random_intercept_sd","residual_sd","within_person_valence_sd_addendum1","pooled_sd_exposure_within_hours","sd_exposure_between_hours_participant_weighted","exposure_between_sd_definition"),
  value=c(nrow(dat), nlevels(dat$participant), sum(variation), random_intercept_sd, residual_sd, within_person_valence_sd, exposure_within_sd, exposure_between_sd, NA),
  stringsAsFactors=FALSE
)
metrics$value[metrics$metric == "exposure_between_sd_definition"] <- "SD across unique participant means (each participant weighted once)"
metrics$metric <- as.character(metrics$metric)
metrics$fixed_term <- NA_character_
metrics$fixed_estimate <- NA_real_
fixed_metrics <- data.frame(metric="outcome_only_fixed_effect", value=NA, fixed_term=fixed_rows$term, fixed_estimate=fixed_rows$estimate, stringsAsFactors=FALSE)
metrics_out <- rbind(metrics, fixed_metrics)
write.csv(metrics_out, metrics_file, row.names=FALSE, na="")

b_grid <- c(0, 0.25, 0.5, 1, 1.5, 2, 3)
n_grid <- ifelse(b_grid == 0, 1000L, 500L)
set.seed(20261015)
results <- vector("list", sum(n_grid))
cursor <- 0L
ids <- levels(dat$participant)
id_index <- as.integer(dat$participant)
for (g in seq_along(b_grid)) {
  b <- b_grid[g]
  for (r in seq_len(n_grid[g])) {
    cursor <- cursor + 1L
    sim_y <- fixed_prediction + b * dat$exposure_within + rnorm(length(ids), 0, random_intercept_sd)[id_index] + rnorm(nrow(dat), 0, residual_sd)
    simdat <- data.frame(sim_valence=sim_y, exposure_within=dat$exposure_within, exposure_between=dat$exposure_between,
      prior_within=dat$prior_within, prior_between=dat$prior_between, log_interval_c=dat$log_interval_c, participant=dat$participant)
    warning_text <- character()
    fit <- tryCatch(withCallingHandlers(
      lmerTest::lmer(sim_valence ~ exposure_within + exposure_between + prior_within + prior_between + log_interval_c + (1 | participant), data=simdat, REML=TRUE, control=lme4::lmerControl(check.conv.singular="ignore")),
      warning=function(w) { warning_text <<- c(warning_text, conditionMessage(w)); invokeRestart("muffleWarning") }), error=function(e) e)
    est <- se <- lo <- hi <- pval <- df <- NA_real_
    conv <- FALSE
    singular <- NA
    fit_error <- FALSE
    if (inherits(fit, "error")) {
      fit_error <- TRUE
    } else {
      co <- summary(fit)$coefficients
      est <- unname(co["exposure_within", "Estimate"])
      se <- unname(co["exposure_within", "Std. Error"])
      df <- unname(co["exposure_within", "df"])
      pval <- unname(co["exposure_within", "Pr(>|t|)"])
      crit <- stats::qt(0.975, df=df)
      lo <- est - crit * se
      hi <- est + crit * se
      conv_codes <- fit@optinfo$conv$opt
      conv_messages <- fit@optinfo$conv$lme4$messages
      conv <- (length(conv_codes) == 0L || all(conv_codes == 0)) && length(conv_messages) == 0L
      singular <- lme4::isSingular(fit, tol=1e-4)
    }
    results[[cursor]] <- data.frame(true_b1=b, replication=r, estimate=est, se=se, ci_lower=lo, ci_upper=hi, p_value=pval,
      satterthwaite_df=df, converged=conv, singular=singular, fit_error=fit_error, stringsAsFactors=FALSE)
  }
  cat(sprintf("Completed b1=%s (%d replications)\n", format(b, trim=TRUE), n_grid[g]))
}
replications <- do.call(rbind, results)
write.csv(replications, rep_file, row.names=FALSE, na="")

summaries <- lapply(split(replications, factor(replications$true_b1, levels=b_grid)), function(x) {
  ok <- is.finite(x$estimate) & is.finite(x$p_value)
  data.frame(true_b1=x$true_b1[1], replications=nrow(x), successful_fits=sum(ok), empirical_power=mean(x$p_value[ok] < .05),
    mean_estimate=mean(x$estimate[ok]), bias=mean(x$estimate[ok]) - x$true_b1[1], empirical_sd=stats::sd(x$estimate[ok]),
    mean_se=mean(x$se[ok]), ci_coverage=mean(x$ci_lower[ok] <= x$true_b1[1] & x$ci_upper[ok] >= x$true_b1[1]),
    mean_ci_half_width=mean((x$ci_upper[ok]-x$ci_lower[ok])/2), convergence_rate=mean(x$converged),
    singular_fit_rate=mean(x$singular %in% TRUE), fit_error_rate=mean(x$fit_error), stringsAsFactors=FALSE)
})
summary_df <- do.call(rbind, summaries)
write.csv(summary_df, summary_file, row.names=FALSE, na="")
above <- which(summary_df$empirical_power >= .80)
mde <- NA_real_
if (length(above)) {
  j <- above[1]
  if (j == 1L) mde <- summary_df$true_b1[j]
  else {
    x0 <- summary_df$true_b1[j-1]; x1 <- summary_df$true_b1[j]
    p0 <- summary_df$empirical_power[j-1]; p1 <- summary_df$empirical_power[j]
    mde <- if (p1 == p0) x1 else x0 + (.80-p0)*(x1-x0)/(p1-p0)
  }
}
null_mean_se <- summary_df$mean_se[summary_df$true_b1 == 0]
mde_out <- data.frame(
  metric=c("interpolated_mde_80_valence_points_per_hour","mde_in_within_person_valence_sd_units_per_hour","mde_per_1_sd_exposure_within","2.8_times_mean_se_at_b1_zero_valence_points_per_hour"),
  value=c(mde, mde/within_person_valence_sd, mde*exposure_within_sd, 2.8*null_mean_se), stringsAsFactors=FALSE)
write.csv(mde_out, mde_file, row.names=FALSE, na="")

writeLines(capture.output(sessionInfo()), session_file, useBytes=TRUE)
fmt <- function(x, digits=4) ifelse(is.finite(x), formatC(x, digits=digits, format="f"), "not reached on tested grid")
report <- c(
  "# GameWell blinded power simulation",
  "",
  "## Gate and execution",
  "",
  sprintf("The primary cohort matched the prespecified gate: %d intervals, %d participants, and %d participants with any within-person exposure variation.", nrow(dat), nlevels(dat$participant), sum(variation)),
  "The cohort was defined from the frozen Plan v1 section 2 and variables listed in VARIABLE_MAPPING.csv. Exposure was required to be non-missing; missing exposure was not treated as zero.",
  "",
  "## Blinding statement",
  "",
  "Real later valence was used only in the outcome-only model and to calculate the Addendum 1 within-person valence SD. The outcome-only model's data frame contained no exposure columns. No model containing both real later valence and exposure was fitted, and no exposure-outcome relationship was computed.",
  "All exposure-outcome model fits used simulated later-valence outcomes. The real exposure and covariates supplied design structure only.",
  "",
  "## Outcome-only calibration",
  "",
  "The real-data calibration model was lme4::lmer(later_valence ~ prior_within + prior_between + log_interval_c + (1|participant), REML=TRUE). Fixed effects, random-intercept SD, residual SD, and scale quantities are in simulation_metrics_v2.csv.",
  sprintf("Addendum 1 within-person SD of later valence: %s points. Pooled SD of exposure_within: %s hours. SD of exposure_between across unique participant means: %s hours.", fmt(within_person_valence_sd), fmt(exposure_within_sd), fmt(exposure_between_sd)),
  "The exposure_between SD weights each participant once; exposure_within SD is calculated across eligible interval rows.",
  "",
  "## Simulation",
  "",
  "For each replication, simulated later valence equals the outcome-only fixed-effect prediction plus the specified within-person exposure effect, a newly drawn participant random intercept, and independent normally distributed residual error. The between-person exposure effect is zero. The primary model was fitted with lmerTest::lmer using REML and Satterthwaite inference.",
  "The tested within-person effects were 0, 0.25, 0.5, 1, 1.5, 2, and 3 valence points/hour; there were 1,000 replications at zero and 500 at each other value. Seed: 20261015.",
  "Per-replication estimates, SEs, confidence intervals, p-values, convergence, singular-fit, and error flags are in simulation_replications_v2.csv. Aggregate power and operating characteristics are in simulation_summary_v2.csv.",
  sprintf("Interpolated 80%% MDE: %s valence points/hour; %s within-person SD units/hour; %s valence points per 1 SD of exposure_within. Cross-check 2.8 times mean SE under b1=0: %s points/hour.", fmt(mde), fmt(mde/within_person_valence_sd), fmt(mde*exposure_within_sd), fmt(2.8*null_mean_se)),
  "",
  "## Limitations",
  "",
  "- Prior valence and other covariates are real while later valence is simulated.",
  "- Normal independent residual errors are assumed.",
  "- The data-generating model has a random intercept only; it omits random exposure slopes and other forms of heterogeneity.",
  "- Power estimates are conditional on the observed cohort, exposure distribution, covariates, and outcome-only variance estimates.",
  "- This simulation assesses operating characteristics only; it is not an estimate of the study's exposure-outcome association.",
  "",
  "## Executed and not executed",
  "",
  "Executed: cohort-count gate; outcome-only calibration model; simulated-outcome mixed models; aggregate summaries; sessionInfo capture.",
  "Not executed: any model using real later valence together with exposure; any exposure-outcome association calculation on real outcomes; data cleaning, package installation, file replacement, deployment, or website build."
)
writeLines(report, report_file, useBytes=TRUE)
cat("Simulation completed. Aggregate summary written; no study data rows were printed.\n")
