out_dir <- "analysis/gamewell_primary_model_2026-10-16"
rds_file <- file.path(out_dir, "primary_model_refit.rds")
outputs <- c("diagnostic_fit_status.csv", "residual_summary.csv", "residuals_by_fitted_bins.csv", "random_effect_summary.csv", "diagnostic_residual_histogram.svg", "diagnostic_residual_qq.svg", "diagnostic_residuals_by_fitted.svg", "diagnostics_sessionInfo.txt", "DIAGNOSTICS_REPORT.md")
if (!file.exists(rds_file)) stop("Saved refit object is missing; diagnostics cannot proceed.")
if (any(file.exists(file.path(out_dir, outputs)))) stop("Refusing to overwrite existing diagnostics output.")
fit <- readRDS(rds_file)
if (!inherits(fit, "lmerMod")) stop("Saved RDS is not an lmer model object.")

opt_code <- fit@optinfo$conv$opt
opt_messages <- fit@optinfo$conv$lme4$messages
optimizer_messages <- fit@optinfo$warnings
collapse_or_none <- function(x) if (length(x)) paste(as.character(x), collapse = " | ") else "none"
vc <- as.data.frame(lme4::VarCorr(fit))
ri_sd <- vc$sdcor[vc$grp == "participant" & vc$var1 == "(Intercept)"][1]
resid_sd <- stats::sigma(fit)
icc <- ri_sd^2 / (ri_sd^2 + resid_sd^2)
mf <- stats::model.frame(fit)
participant_name <- if ("participant" %in% names(mf)) "participant" else stop("Participant grouping column unavailable in saved model frame.")
fit_status <- data.frame(model_fits=1L, observations=stats::nobs(fit), participants=length(unique(mf[[participant_name]])),
  convergence_code=collapse_or_none(opt_code), convergence_messages=collapse_or_none(opt_messages), optimizer_messages=collapse_or_none(optimizer_messages),
  singular_fit=lme4::isSingular(fit, tol=1e-4), random_intercept_SD=ri_sd, residual_SD=resid_sd, ICC=icc, stringsAsFactors=FALSE)
write.csv(fit_status, file.path(out_dir,"diagnostic_fit_status.csv"), row.names=FALSE, na="")

res <- stats::residuals(fit)
fv <- stats::fitted(fit)
q <- stats::quantile(res, probs=c(.01,.05,.25,.50,.75,.95,.99), names=FALSE)
res_sd <- stats::sd(res)
res_summary <- data.frame(n=length(res), mean=mean(res), SD=res_sd,
  skewness=mean((res-mean(res))^3)/(res_sd^3), excess_kurtosis=mean((res-mean(res))^4)/(res_sd^4)-3,
  q01=q[1],q05=q[2],q25=q[3],q50=q[4],q75=q[5],q95=q[6],q99=q[7])
write.csv(res_summary,file.path(out_dir,"residual_summary.csv"),row.names=FALSE)

bin_id <- pmin(10L, ceiling(rank(fv, ties.method="average") / length(fv) * 10))
bin_rows <- lapply(1:10,function(k){idx<-bin_id==k;if(!any(idx))return(data.frame(fitted_bin=k,n=0L,fitted_mean=NA_real_,residual_mean=NA_real_,residual_SD=NA_real_));data.frame(fitted_bin=k,n=sum(idx),fitted_mean=mean(fv[idx]),residual_mean=mean(res[idx]),residual_SD=stats::sd(res[idx]))})
bins <- do.call(rbind,bin_rows)
write.csv(bins,file.path(out_dir,"residuals_by_fitted_bins.csv"),row.names=FALSE,na="")

re <- lme4::ranef(fit)$participant[[1]]
rq <- stats::quantile(re,probs=c(.01,.05,.25,.50,.75,.95,.99),names=FALSE)
re_summary <- data.frame(n_participants=length(re),mean=mean(re),SD=stats::sd(re),q01=rq[1],q05=rq[2],q25=rq[3],q50=rq[4],q75=rq[5],q95=rq[6],q99=rq[7])
write.csv(re_summary,file.path(out_dir,"random_effect_summary.csv"),row.names=FALSE)

grDevices::svg(file.path(out_dir,"diagnostic_residual_histogram.svg"),width=7,height=5)
hist(res,breaks="FD",main="Residual histogram",xlab="Residual",col="grey80",border="white")
grDevices::dev.off()
grDevices::svg(file.path(out_dir,"diagnostic_residual_qq.svg"),width=7,height=5)
stats::qqnorm(res,main="Residual normal Q-Q plot");stats::qqline(res,col="red",lwd=2)
grDevices::dev.off()
grDevices::svg(file.path(out_dir,"diagnostic_residuals_by_fitted.svg"),width=7,height=5)
plot(bins$fitted_mean,bins$residual_mean,pch=19,xlab="Mean fitted value within bin",ylab="Mean residual",main="Residuals by fitted value (10 bins)");abline(h=0,col="red",lwd=2)
grDevices::dev.off()

writeLines(capture.output(sessionInfo()),file.path(out_dir,"diagnostics_sessionInfo.txt"),useBytes=TRUE)
report <- c("# Primary model diagnostics","",
  "Script 2 loaded the saved diagnostic refit from primary_model_refit.rds; it did not refit the model. The identical refit reproduced the original saved fixed-effect estimates within the prespecified 1e-6 tolerance (see REFIT_IDENTITY_SUMMARY.csv). No b1 interpretation is added here.",
  "", "## Fit status", "", "See diagnostic_fit_status.csv for convergence code and messages, singularity, variance components, ICC, and denominators.",
  "", "## Residual diagnostics", "", "See residual_summary.csv for aggregate residual moments and quantiles; residuals_by_fitted_bins.csv for 10-bin summaries; and random_effect_summary.csv for the random-intercept distribution. Three aggregate SVG diagnostic plots are provided.",
  "", "All outputs are aggregate and contain no participant identifiers. The fit remains an association model for recorded linked-console play and affective valence; these diagnostics do not establish causality.")
writeLines(report,file.path(out_dir,"DIAGNOSTICS_REPORT.md"),useBytes=TRUE)
cat("Loaded saved refit and wrote aggregate diagnostics; no model refit.\n")
