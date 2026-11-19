# Stage 3 — candidate measurement discovery (not yet evidence qualification)

The Stage 2.1 characteristic evaluation remains authoritative for the current pilot and its unmodified source data. Stage 3 adds a conservative, source-cell-specific *discovery* layer for identifying candidate metrics in other worksheets.

Usage (source and output paths MUST be outside this public repository):

    python -m traffic_annotation.discovery --workbook /private/path/annotated_B4.xlsx --out /private/path/stage3_candidates

The command creates candidate_measurements.json, candidate_measurements.csv, and discovery_summary.csv. It reports every potential metric with the exact source sheet, label cell, numeric cells, and, when there is an exact catalogue parent-sheet match, dataset IDs.

**Important:** A keyword/label match is not a validated characteristic mapping. It does not prove measurement layer, direction, unit, denominator, underlying campaign, contributing organization, independence, or comparability. It cannot change any previous workbook status or CROSSCHECK result. Sheets or characteristics with zero candidates may require specialized parser rules; zero matches is not evidence of absence. Real measurements and generated candidate files must remain outside the public repository.

To promote a candidate to characteristic evidence, the rapporteur must confirm the source cells and definitions, source TDocs and organization, measurement layer, units, denominators, network conditions, and dependence/derivation. Only then should a source-cited evidence item be added to the private Stage 2 evidence specification and the Stage 2 evaluator rerun.

For future automation, implement specific extractor adapters per table layout (row-oriented profile tables, column-oriented campaign summaries, time-series, and reported distributions), verify them on synthetic workbooks, and explicitly handle units and campaign identity. Do not use inferred organizations or deduced units as verification.

No Google Sheets writes or source workbook edits are performed.
