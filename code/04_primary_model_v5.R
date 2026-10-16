out_dir <- "analysis/gamewell_primary_model_2026-10-16"
input <- "analysis/gamewell_interval_dataset_2026-10-15/gamewell_daily_intervals.csv.gz"
plan_file <- "analysis/gamewell_analysis_plan_2026-10-15/ANALYSIS_PLAN_v1.md"
add1_file <- "analysis/gamewell_analysis_plan_2026-10-15/ADDENDUM_1_2026-10-15.md"
add2_file <- "analysis/gamewell_analysis_plan_2026-10-15/ADDENDUM_2_2026-10-16.md"
mapping_file <- "analysis/gamewell_analysis_plan_2026-10-15/VARIABLE_MAPPING.csv"
hash_file <- file.path(out_dir, "PREFIT_HASH_CHECKS.csv")
outputs <- c("cohort_gate.csv", "fixed_effects.csv", "cr2_coef_test.csv", "cr2_conf_int.csv", "cr2_fixed_effects.csv", "b1_summary.csv", "fit_status.csv", "residual_summary.csv", "residual_bins_by_fitted.csv", "random_effect_summary.csv", "residual_histogram.svg", "residual_qq.svg", "residuals_by_fitted.svg", "REPORT.md", "sessionInfo.txt")
if (!dir.exists(out_dir)) stop("Output folder missing; pre-fit gate cannot proceed.")
existing <- outputs[file.exists(file.path(out_dir, outputs))]
if (length(existing)) stop(paste("Refusing to overwrite existing output(s):", paste(existing, collapse = ", ")))
if (!file.exists(hash_file)) stop("PRE-FIT GATE FAILED: PREFIT_HASH_CHECKS.csv is missing.")
hashes <- read.csv(hash_file, stringsAsFactors = FALSE, check.names = FALSE)
if (nrow(hashes) != 4L || !all(tolower(as.character(hashes$match)) == "true")) stop("PRE-FIT GATE FAILED: required manifest hash checks did not all pass.")
if (!requireNamespace("lme4", quietly = TRUE) || !requireNamespace("lmerTest", quietly = TRUE) || !requireNamespace("clubSandwich", quietly = TRUE)) stop("Required package missing; no installation attempted.")
for (p in c(input, plan_file, add1_file, add2_file, mapping_file)) if (!file.exists(p)) stop(paste("Required input missing:", p))

plan <- paste(readLines(plan_file, warn = FALSE), collapse = "\n")
add1 <- paste(readLines(add1_file, warn = FALSE), collapse = "\n")
add2 <- paste(readLines(add2_file, warn = FALSE), collapse = "\n")
mapping <- read.csv(mapping_file, stringsAsFactors = FALSE, check.names = FALSE)
mapped <- trimws(unlist(strsplit(paste(mapping$source_column, collapse = ";"), ";", fixed = TRUE)))
required <- c("participant_id", "prior_affective_valence", "later_affective_valence", "interval_duration_hours", "xbox_linked", "nintendo_linked", "recorded_linked_console_minutes_unique")
if (!all(required %in% mapped)) stop("PRE-FIT GATE FAILED: required source variables do not match VARIABLE_MAPPING.csv.")
if (!grepl("duration is <= 48 hours", plan, fixed = TRUE) || !grepl("exposure is non-missing", plan, fixed = TRUE) || !grepl("participant's mean exposure over their eligible intervals", plan, fixed = TRUE)) stop("PRE-FIT GATE FAILED: Plan v1 cohort or derivation text did not match.")
if (!grepl("pooled SD of (later valence minus that participant's own mean later valence)", add1, fixed = TRUE)) stop("PRE-FIT GATE FAILED: Addendum 1 SD definition did not match.")
if (!grepl("plus or minus 0.5 valence points per hour", add2, fixed = TRUE) || !grepl("the wider of the model-based", add2, fixed = TRUE)) stop("PRE-FIT GATE FAILED: Addendum 2 interpretation rule did not match.")

d <- read.csv(gzfile(input), stringsAsFactors = FALSE, check.names = FALSE)
if (!all(required %in% names(d))) stop("PRE-FIT GATE FAILED: expected columns missing from interval data.")
as_linked <- function(x) tolower(trimws(as.character(x))) %in% c("true", "1", "yes")
eligible <- (as_linked(d$xbox_linked) | as_linked(d$nintendo_linked)) &
  !is.na(d$interval_duration_hours) & d$interval_duration_hours <= 48 &
  !is.na(d$prior_affective_valence) & !is.na(d$later_affective_valence) &
  !is.na(d$recorded_linked_console_minutes_unique)
cohort <- d[eligible, , drop = FALSE]
if (any(!is.finite(cohort$interval_duration_hours)) || any(cohort$interval_duration_hours <= 0)) stop("PRE-FIT GATE FAILED: eligible interval duration is invalid.")
if (anyNA(cohort$participant_id) || any(!nzchar(as.character(cohort$participant_id)))) stop("PRE-FIT GATE FAILED: eligible participant ID is missing.")
cohort$participant <- factor(as.character(cohort$participant_id))
cohort$exposure_hours <- cohort$recorded_linked_console_minutes_unique / 60
cohort$exposure_between <- ave(cohort$exposure_hours, cohort$participant, FUN = mean)
cohort$exposure_within <- cohort$exposure_hours - cohort$exposure_between
cohort$prior_between <- ave(cohort$prior_affective_valence, cohort$participant, FUN = mean)
cohort$prior_within <- cohort$prior_affective_valence - cohort$prior_between
cohort$log_interval_c <- log(cohort$interval_duration_hours) - mean(log(cohort$interval_duration_hours))
cohort$later_valence <- cohort$later_affective_valence
variation <- vapply(split(cohort$exposure_hours, cohort$participant), function(x) length(unique(x)) > 1L, logical(1))
gate <- data.frame(metric=c("eligible_intervals","participants","participants_with_exposure_variation"), observed=c(nrow(cohort), nlevels(cohort$participant), sum(variation)), expected=c(5076L,371L,171L), stringsAsFactors=FALSE)
gate$match <- gate$observed == gate$expected
write.csv(gate, file.path(out_dir, "cohort_gate.csv"), row.names=FALSE)
cat("Pre-fit cohort counts: ", paste(gate$metric, gate$observed, sep="=", collapse="; "), "\n", sep="")
if (!all(gate$match)) stop("PRE-FIT GATE FAILED: cohort counts differ from 5,076 intervals, 371 participants, and 171 participants with exposure variation. No model was fitted.")

# The single prespecified primary fit. No alternative fit is attempted.
fit <- tryCatch(
  lmerTest::lmer(later_valence ~ exposure_within + exposure_between + prior_within + prior_between + log_interval_c + (1|participant), data = cohort, REML = TRUE),
  error = function(e) stop(paste0("PRIMARY MODEL TECHNICAL ERROR; no retry was attempted: ", conditionMessage(e)))
)

sm <- summary(fit)$coefficients
model_fx <- data.frame(term=rownames(sm), estimate=sm[,"Estimate"], SE=sm[,"Std. Error"], df_Satterthwaite=sm[,"df"], t=sm[,"t value"], p=sm[,"Pr(>|t|)"], stringsAsFactors=FALSE)
model_fx$CI_lower <- model_fx$estimate - stats::qt(.975, model_fx$df_Satterthwaite) * model_fx$SE
model_fx$CI_upper <- model_fx$estimate + stats::qt(.975, model_fx$df_Satterthwaite) * model_fx$SE
write.csv(model_fx, file.path(out_dir, "fixed_effects.csv"), row.names=FALSE)

cr2_test <- as.data.frame(clubSandwich::coef_test(fit, vcov="CR2", cluster=cohort$participant, test="Satterthwaite"))
cr2_test$term <- rownames(cr2_test)
rownames(cr2_test) <- NULL
cr2_ci <- as.data.frame(clubSandwich::conf_int(fit, vcov="CR2", cluster=cohort$participant, test="Satterthwaite"))
cr2_ci$term <- rownames(cr2_ci)
rownames(cr2_ci) <- NULL
write.csv(cr2_test, file.path(out_dir, "cr2_coef_test.csv"), row.names=FALSE)
write.csv(cr2_ci, file.path(out_dir, "cr2_conf_int.csv"), row.names=FALSE)
if (!all(c("term","CI_L","CI_U") %in% names(cr2_ci))) stop("Post-fit reporting error: unexpected clubSandwich conf_int column names; model has already been fitted once.")
robust <- merge(cr2_test, cr2_ci[,c("term","CI_L","CI_U")], by="term", all.x=TRUE, sort=FALSE)
write.csv(robust, file.path(out_dir, "cr2_fixed_effects.csv"), row.names=FALSE)

within_valence <- cohort$later_affective_valence - ave(cohort$later_affective_valence, cohort$participant, FUN=mean)
within_valence_sd <- stats::sd(within_valence)
if (abs(within_valence_sd - 12.0559) > 0.00005) stop(sprintf("Post-fit confirmation failed: recomputed Addendum 1 SD %.10f differs from 12.0559; model has already been fitted once.", within_valence_sd))
exposure_within_sd <- stats::sd(cohort$exposure_within)
b1 <- model_fx[model_fx$term == "exposure_within",]
b1_cr2 <- robust[robust$term == "exposure_within",]
cr2_l <- as.numeric(b1_cr2$CI_L); cr2_u <- as.numeric(b1_cr2$CI_U)
model_width <- b1$CI_upper - b1$CI_lower
cr2_width <- cr2_u - cr2_l
if (cr2_width > model_width) { wider_source <- "CR2 cluster-robust"; wider_l <- cr2_l; wider_u <- cr2_u } else { wider_source <- "model-based Satterthwaite"; wider_l <- b1$CI_lower; wider_u <- b1$CI_upper }
if (wider_l > -0.5 && wider_u < 0.5) category <- "a"
else if ((wider_u < 0 || wider_l > 0) && (wider_l < -0.5 || wider_u > 0.5)) category <- "b"
else if ((wider_u < 0 || wider_l > 0) && wider_l >= -0.5 && wider_u <= 0.5) category <- "c"
else category <- "d"
category_wording <- switch(category,
  a="interval entirely within +/-0.5: no association larger than the SESOI is supported",
  b="interval excludes 0 and extends beyond +/-0.5: association of potentially meaningful size",
  c="interval excludes 0 but lies entirely within +/-0.5: statistically detectable but small",
  d="interval includes 0 and extends beyond +/-0.5: inconclusive")
b1_out <- data.frame(term="exposure_within", estimate=b1$estimate, model_CI_lower=b1$CI_lower, model_CI_upper=b1$CI_upper,
  CR2_CI_lower=cr2_l, CR2_CI_upper=cr2_u, wider_interval_source=wider_source, wider_CI_lower=wider_l, wider_CI_upper=wider_u,
  within_person_valence_SD=within_valence_sd, scaled_estimate_SD_units=b1$estimate/within_valence_sd,
  exposure_within_SD_hours=exposure_within_sd, effect_per_1_SD_exposure=b1$estimate*exposure_within_sd,
  SESOI_points_per_hour=0.5, Addendum2_category=category, category_wording=category_wording, stringsAsFactors=FALSE)
write.csv(b1_out, file.path(out_dir, "b1_summary.csv"), row.names=FALSE)

vc <- as.data.frame(lme4::VarCorr(fit))
ri_sd <- vc$sdcor[vc$grp == "participant" & vc$var1 == "(Intercept)"][1]
resid_sd <- stats::sigma(fit)
icc <- ri_sd^2/(ri_sd^2+resid_sd^2)
conv_code <- fit@optinfo$conv$opt
conv_message <- fit@optinfo$conv$lme4$messages
conv_text <- if (length(conv_message)) paste(as.character(conv_message), collapse=" | ") else if (length(conv_code) && any(conv_code != 0)) paste("optimizer code", paste(conv_code, collapse=",")) else "none"
fit_status <- data.frame(model_fits=1L, observations=nrow(cohort), participants=nlevels(cohort$participant), optimizer="default lme4 optimizer", convergence_code=paste(conv_code, collapse=","), convergence_messages=conv_text, singular_fit=lme4::isSingular(fit, tol=1e-4), random_intercept_SD=ri_sd, residual_SD=resid_sd, ICC=icc, stringsAsFactors=FALSE)
write.csv(fit_status, file.path(out_dir, "fit_status.csv"), row.names=FALSE)

res <- stats::residuals(fit); fitted_values <- stats::fitted(fit)
res_summary <- data.frame(n=length(res), mean=mean(res), SD=stats::sd(res), skewness=mean((res-mean(res))^3)/stats::sd(res)^3,
  excess_kurtosis=mean((res-mean(res))^4)/stats::sd(res)^4-3, q0=unname(quantile(res,0)), q05=unname(quantile(res,.05)), q25=unname(quantile(res,.25)),
  median=unname(quantile(res,.5)), q75=unname(quantile(res,.75)), q95=unname(quantile(res,.95)), q100=unname(quantile(res,1)))
write.csv(res_summary, file.path(out_dir, "residual_summary.csv"), row.names=FALSE)
bin_id <- pmin(10L, ceiling(rank(fitted_values, ties.method="average")/length(fitted_values)*10))
bins <- do.call(rbind, lapply(sort(unique(bin_id)), function(k) { z <- bin_id == k; data.frame(fitted_bin=k,n=sum(z),fitted_mean=mean(fitted_values[z]),residual_mean=mean(res[z]),residual_SD=stats::sd(res[z])) }))
write.csv(bins, file.path(out_dir, "residual_bins_by_fitted.csv"), row.names=FALSE)
re <- lme4::ranef(fit)$participant[[1]]
re_summary <- data.frame(n_participants=length(re),mean=mean(re),SD=stats::sd(re),q0=unname(quantile(re,0)),q05=unname(quantile(re,.05)),q25=unname(quantile(re,.25)),median=unname(quantile(re,.5)),q75=unname(quantile(re,.75)),q95=unname(quantile(re,.95)),q100=unname(quantile(re,1)))
write.csv(re_summary, file.path(out_dir, "random_effect_summary.csv"), row.names=FALSE)

grDevices::svg(file.path(out_dir,"residual_histogram.svg"), width=7, height=5); hist(res, breaks="FD", main="Primary model residuals", xlab="Residual", col="grey80", border="white"); grDevices::dev.off()
grDevices::svg(file.path(out_dir,"residual_qq.svg"), width=7, height=5); qqnorm(res, main="Normal Q-Q plot of primary model residuals"); qqline(res, col="red", lwd=2); grDevices::dev.off()
grDevices::svg(file.path(out_dir,"residuals_by_fitted.svg"), width=7, height=5); plot(bins$fitted_mean,bins$residual_mean,pch=19,xlab="Mean fitted value (decile bins)",ylab="Mean residual",main="Residuals by fitted value"); abline(h=0,col="red",lwd=2); grDevices::dev.off()

writeLines(capture.output(sessionInfo()), file.path(out_dir,"sessionInfo.txt"), useBytes=TRUE)
fx_lines <- apply(model_fx, 1, function(x) paste(x, collapse=" | "))
rob_lines <- apply(robust, 1, function(x) paste(x, collapse=" | "))
report <- c("# GameWell primary model report", "", "## Gate", "",
  sprintf("Hash checks passed for Plan v1, Addenda 1 and 2, and the interval dataset. The primary cohort matched all required counts: %d intervals, %d participants, and %d participants with exposure variation.",nrow(cohort),nlevels(cohort$participant),sum(variation)),
  "", "## Model and results", "", "The prespecified primary model was fitted once: lmerTest::lmer(later_valence ~ exposure_within + exposure_between + prior_within + prior_between + log_interval_c + (1|participant), data=cohort, REML=TRUE), using the default optimizer. All estimates are associations with recorded linked-console play; no causal interpretation is made.",
  "", "### Model-based fixed effects", "", "Term | Estimate | SE | Satterthwaite df | t | p | 95% CI", "--- | ---: | ---: | ---: | ---: | ---: | ---: ", fx_lines,
  "", "### CR2 cluster-robust inference", "", "CR2 standard errors and Satterthwaite-type degrees of freedom are clustered by participant. See cr2_coef_test.csv and cr2_conf_int.csv for the full coef_test and conf_int output.", "", "### Primary within-person association", "",
  sprintf("The exposure_within estimate is %.6f valence points/hour. Model-based 95%% CI: [%.6f, %.6f]. CR2 95%% CI: [%.6f, %.6f]. The wider interval is the %s interval [%.6f, %.6f].",b1$estimate,b1$CI_lower,b1$CI_upper,cr2_l,cr2_u,wider_source,wider_l,wider_u),
  sprintf("Recomputed Addendum 1 within-person valence SD: %.7f (documented rounded value 12.0559; confirmed within 0.00005). The scaled estimate is %.6f within-person SD units per hour. Exposure_within SD is %.6f hours; the effect per 1 SD of exposure_within is %.6f valence points.",within_valence_sd,b1$estimate/within_valence_sd,exposure_within_sd,b1$estimate*exposure_within_sd),
  sprintf("Addendum 2 category: %s â€” %s.",category,category_wording),
  "", "The exposure_between coefficient is reported separately as a between-person association; it is not combined with or interpreted as the within-person estimate.",
  "", "### Fit status and diagnostics", "",
  sprintf("Fit status: one model fit; %d observations from %d participants; singular fit=%s; random-intercept SD=%.6f; residual SD=%.6f; ICC=%.6f. Convergence messages: %s.",nrow(cohort),nlevels(cohort$participant),fit_status$singular_fit,ri_sd,resid_sd,icc,conv_text),
  "Residual distribution summaries are in residual_summary.csv; random-effect distribution summaries are in random_effect_summary.csv; residual-by-fitted bins and aggregate SVG diagnostics are included in this folder.",
  "", "## Limitations", "",
  "- Zero recorded sessions are interpreted only under the source's maximal-coverage-on-linkage assumption; there is no interval-level capture flag, so missing capture cannot be distinguished from genuine no-play.",
  "- Nintendo telemetry covers first-party titles; Steam, mobile and unlinked-platform play are excluded from the recorded exposure.",
  "- Recorded valence values of 0 occur despite the instrument description's lower bound of 1; Plan v1 retains them as recorded in the primary analysis.",
  "- Survey timestamps are treated as UTC instants; original export settings remain unverified. Participants without intake linkage are outside the linked cohort.",
  "- The blinded power simulation assumed independent normal residuals and a random-intercept-only data-generating model; the estimated random-intercept SD was zero and the MDE is best-case under those assumptions.",
  "- These observational estimates describe associations only and do not establish causation.",
  "", "## Execution record", "",
  "This was the first and only fit of the Plan v1 primary model. No sensitivity analysis, secondary-outcome analysis, alternative model, optimizer, transformation, or exclusion was run. No study data rows or participant identifiers were written to output.")
writeLines(report, file.path(out_dir,"REPORT.md"), useBytes=TRUE)
cat("Primary model fit once; aggregate outputs and diagnostics saved.\n")
