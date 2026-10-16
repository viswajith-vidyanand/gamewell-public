# GameWell: recorded console play and daily well-being

We examined whether, within the same person, a day with more recorded Xbox/Nintendo play than that person's usual was associated with a different mood (affective valence, 0-100) at the next survey. Per additional hour of recorded linked-console play above a person's own usual, later mood differed by 0.07 points (95% interval -0.14 to 0.29) on the 0-100 scale. The interval lies entirely within +/-0.5 points per hour, the smallest effect we pre-set as meaningful, so associations larger than that are not supported in this cohort. Life satisfaction (satisfaction with life that day, a separate measure) was analyzed the same way as a secondary analysis: the estimate was 0.16 points per hour (95% interval -0.04 to 0.35), also entirely within +/-0.5. It was not stress-tested like the primary analysis.

## What this does and does not show

These findings concern recorded play on linked Xbox/Nintendo accounts only, not gaming overall; intervals with no recorded session are not proof of no gaming.

This is observational data: associations do not show that gaming changes mood, and a small association is not ruled out.

## Folder guide

- **plan/** contains Analysis Plan v1, dated addenda, integrity manifests, methods and limitations, and the fit ledger.
- **results/** contains the aggregate-only site-input release and its original manifest.
- **code/** contains the final numbered scripts and CODE_GUIDE.md.
- **docs/** is reserved for project documentation.
- **.gitignore** excludes common data, model-object, environment, and build files.

## Data source and credit

The source is the Open Play dataset. The project references are [Zenodo record 21478405](https://zenodo.org/records/21478405) and [the Open Play GitHub repository](https://github.com/digital-wellbeing/open-play). The reviewed repository LICENSE contains no mandatory attribution or citation condition; use these references when describing or citing the source dataset.

## Data are not included

Participant-level files are deliberately excluded. Reproducing the analyses requires downloading the Open Play data separately and following the dataset’s applicable access and use terms. The scripts expect the cleaned input tables and, for some stages, the interval file produced earlier in the workflow.

## Reproducing

The recorded environment used R 4.6.1 and Node.js v24 on Windows. The scripts were run from the original project layout with machine-specific paths; adjust paths for your environment. Run R scripts with --vanilla. The numbered order is interval construction, independent diagnostics, blinded power simulation, primary fit, permitted identical diagnostic refit and diagnostics, prespecified sensitivities and 7a correction/final report, secondary life-satisfaction fit/diagnostics/report, descriptive aggregates, site-input release, then Addenda 6 and 7. Do not run model-fitting scripts unless the required data and approvals are in place.

## Frozen plan and audit trail

Analysis Plan v1 was hashed before analysis. Dated addenda record later clarifications and decisions. FIT_LEDGER.csv lists every study-data model fit, including the four discarded initial 7a runs.

[TODO for author: add a statement of tools and AI assistance used, according to your course rules]
