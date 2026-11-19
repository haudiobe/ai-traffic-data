# B.4 dataset metadata audit and candidate extraction

This repository contains **two deliberately distinct read-only processes**:

1. `traffic_annotation.discovery` discovers *candidate* measurements from the annotated Excel workbook and outputs exact worksheet/cell references. Candidate rows are not verified characteristic evidence.
2. `traffic_annotation.metadata` audits the B.4.4 `Dataset Catalogue` against its mandatory fields and reports missing/placeholder values by field and by dataset without changing workbook status.

For the working source folder on Windows:

```powershell
$src = 'G:\Meine Ablage\Projects\AI Traffic Data'
$book = Join-Path $src 'S4-262210-Collated_AI_Traffic_Results_B4.xlsx'
$orig = Join-Path $src 'S4-262210 Collated_AI_Traffic_Results_note_0_6_3.xlsx'
$out = Join-Path $src '_stage3'
python -m traffic_annotation.discovery --workbook "$book" --out (Join-Path $out 'discovery')
python -m traffic_annotation.metadata --workbook "$book" --out (Join-Path $out 'metadata')
python -m pytest -q
```

Run these commands from the project environment in the **GitHub clone**, with private source/output paths outside that clone. The tools check SHA-256 before and after reading the workbook.

Metadata outputs:

- `missing_metadata_by_field.csv`: per-field missing total, historical agreed gap count, and new/unconfirmed gap count
- `dataset_metadata_review.csv`: per-dataset source row, unchanged assigned status, missing fields, and structural issues
- `metadata_audit.json`: normalized machine-readable audit and source hash

The metadata audit recognizes placeholders such as "Not identified in workbook" as missing. Existing `STABLE` records with prior-agreement evidence remain `STABLE`, and their unavailable historical metadata is reported as `HISTORICAL_QUALIFIED_GAP`, not as a fresh per-record requirement. Other records are labelled `NEW_OR_UNCONFIRMED_METADATA_GAP`. The audit does not establish whether every contributor can provide the historical information.

Known caution: parent sheet names may differ by spacing, accents, hyphens or similar spelling; unresolved references are flagged as structural issues, not silently mapped to evidence. Dataset IDs are checked separately for uniqueness. The audit is not a replacement for the source TDocs, the agreement record, or the full Stage 2 comparability review.

To promote a candidate to evidence, reviewers verify the characteristic definition, units, measurement layer, traffic direction, scenario, baseline, network conditions, denominator and source organization; they then add a source-cited mapping to the private evidence specification and rerun:

```powershell
python -m traffic_annotation.characteristics --original "$orig" --annotated "$book" --spec "<private evidence specification JSON>" --out (Join-Path $out 'evaluation') --sheets-dry-run
```

Do not commit the generated source-derived candidate files, metadata audit, private evidence specifications, or measurement workbooks to this public repo. Only generic code, synthetic tests, and methodology documentation belong here.
