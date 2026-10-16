out_dir <- "analysis/gamewell_primary_model_2026-10-16"
input <- "analysis/gamewell_interval_dataset_2026-10-15/gamewell_daily_intervals.csv.gz"
fixed_file <- file.path(out_dir, "fixed_effects.csv")
rds_file <- file.path(out_dir, "primary_model_refit.rds")
identity_file <- file.path(out_dir, "REFIT_IDENTITY_CHECK.csv")
identity_summary_file <- file.path(out_dir, "REFIT_IDENTITY_SUMMARY.csv")
if (!requireNamespace("lme4", quietly = TRUE) || !requireNamespace("lmerTest", quietly = TRUE)) stop("Required modeling package missing; no installation attempted.")
if (!file.exists(input) || !file.exists(fixed_file)) stop("Required interval data or original fixed-effects table is missing.")
if (any(file.exists(c(rds_file, identity_file, identity_summary_file)))) stop("Refusing to overwrite any refit output.")

d <- read.csv(gzfile(input), stringsAsFactors = FALSE, check.names = FALSE)
required <- c("participant_id", "prior_affective_valence", "later_affective_valence", "interval_duration_hours", "xbox_linked", "nintendo_linked", "recorded_linked_console_minutes_unique")
if (!all(required %in% names(d))) stop("Required interval columns are missing.")
as_linked <- function(x) tolower(trimws(as.character(x))) %in% c("true", "1", "yes")
keep <- (as_linked(d$xbox_linked) | as_linked(d$nintendo_linked)) &
  !is.na(d$interval_duration_hours) & d$interval_duration_hours <= 48 &
  !is.na(d$prior_affective_valence) & !is.na(d$later_affective_valence) &
  !is.na(d$recorded_linked_console_minutes_unique)
cohort <- d[keep, , drop = FALSE]
if (any(!is.finite(cohort$interval_duration_hours)) || any(cohort$interval_duration_hours <= 0)) stop("Eligible cohort contains invalid interval duration.")
cohort$participant <- factor(as.character(cohort$participant_id))
cohort$exposure_hours <- cohort$recorded_linked_console_minutes_unique / 60
cohort$exposure_between <- ave(cohort$exposure_hours, cohort$participant, FUN = mean)
cohort$exposure_within <- cohort$exposure_hours - cohort$exposure_between
cohort$prior_between <- ave(cohort$prior_affective_valence, cohort$participant, FUN = mean)
cohort$prior_within <- cohort$prior_affective_valence - cohort$prior_between
cohort$log_interval_c <- log(cohort$interval_duration_hours) - mean(log(cohort$interval_duration_hours))
cohort$later_valence <- cohort$later_affective_valence
variation <- vapply(split(cohort$exposure_hours, cohort$participant), function(x) length(unique(x)) > 1L, logical(1))
if (nrow(cohort) != 5076L || nlevels(cohort$participant) != 371L || sum(variation) != 171L) stop("Refit cohort gate failed; no model was fitted.")

# The only model fit in this script; save the returned object immediately.
fit <- lmerTest::lmer(later_valence ~ exposure_within + exposure_between + prior_within + prior_between + log_interval_c + (1|participant), data = cohort, REML = TRUE)
saveRDS(fit, rds_file)

original <- read.csv(fixed_file, stringsAsFactors = FALSE, check.names = FALSE)
current_summary <- summary(fit)$coefficients
current <- data.frame(term = rownames(current_summary), estimate = current_summary[, "Estimate"], SE = current_summary[, "Std. Error"], stringsAsFactors = FALSE)
if (!setequal(original$term, current$term)) stop("Refit identity check failed: fixed-effect term sets differ. Model object remains saved; Script 2 must not run.")
current <- current[match(original$term, current$term), , drop = FALSE]
identity <- data.frame(term = original$term, original_estimate = original$estimate, refit_estimate = current$estimate,
  absolute_estimate_difference = abs(original$estimate - current$estimate), original_SE = original$SE, refit_SE = current$SE,
  absolute_SE_difference = abs(original$SE - current$SE), stringsAsFactors = FALSE)
max_est <- max(identity$absolute_estimate_difference)
max_se <- max(identity$absolute_SE_difference)
write.csv(identity, identity_file, row.names = FALSE)
summary <- data.frame(metric = c("maximum_absolute_estimate_difference", "maximum_absolute_SE_difference", "estimate_identity_tolerance", "estimate_identity_pass", "observations", "participants", "participants_with_exposure_variation"),
  value = c(max_est, max_se, 1e-6, max_est <= 1e-6, nrow(cohort), nlevels(cohort$participant), sum(variation)), stringsAsFactors = FALSE)
write.csv(summary, identity_summary_file, row.names = FALSE)
cat(sprintf("Refit identity check: max absolute estimate difference=%.12g; max absolute SE difference=%.12g; estimate tolerance pass=%s\n", max_est, max_se, max_est <= 1e-6))
if (max_est > 1e-6) stop("REFIT IDENTITY CHECK FAILED: at least one fixed-effect estimate differs by more than 1e-6. Do not run Script 2; original results stand.")
