# Stage 1: annotated-workbook CROSSCHECK

Stage 1 checks an Annex B.4 annotated collated-results workbook against

* the original collated-results workbook it was derived from,
* the dataset-management rules (B.4.3 status, B.4.4 dataset metadata,
  B.4.5 characteristic evidence), and
* optionally, the quantitative claims in the contribution that proposes the
  annotation.

It never changes a status or a result. It reports a decision for each check.

## Decisions

| Decision | Meaning | Typical follow-up |
|---|---|---|
| PASS | rule satisfied | none |
| ACCEPT | deviation acceptable as-is, documented in the report | none, or editorial |
| REVIEW | ambiguity or proposal that needs a rapporteur or contributor decision | listed under *Open Ambiguities* |
| FAIL | rule violated | correct the annotation before agreement |

## What is compared

| Area | Checks | Basis |
|---|---|---|
| Integrity | C01, C02, C03, C17, C18 | sheet set, cell values (relative float round-off ≤ 1e-12), Index changes limited to the Status column, encoding damage, version label |
| Catalogue | C04, C06, C07, C08, C09 | B.4.4 column order, unique IDs, parent-sheet resolution, coverage of every result sheet, recomputed completeness |
| Status rules | C10, C11, C12, C13, C16 | STABLE needs agreement evidence; CANDIDATE needs complete mandatory metadata; `CROSS_CHECKED` is never inferred; register, catalogue and Index agree; provenance resolves |
| Characteristic evidence | C14, C15 | source count = listed organizations, flag follows the count, derived datasets are not counted, spread recorded; candidate proposals are REVIEW only |
| Contribution claims | C05 | claimed counts = parsed counts = independent raw row counts |

Placeholders such as `TBD`, `–` or `not identified` count as missing
metadata.

## Outputs

All outputs go to the `--out` directory, which must lie outside this repository:

* `crosscheck_review.xlsx`: Summary, Source Inventory, Sheet Count Comparison,
  Claimed vs Extracted, Dataset Mapping, B.4.4 Completeness, Characteristic
  Check, Crosscheck Decisions, Open Ambiguities
* `crosscheck_report.md`: full report with source mappings, ambiguities and decisions
* `crosscheck_normalized_catalogue.json`: annotation metadata, no measurement values

## Where results for a specific workbook live

Reports for a specific contribution name contributors, datasets and source
values. They are kept with the source documents, outside this public
repository, and are distributed through the normal contribution process. This
repository holds only the generic implementation, synthetic tests and generic
documentation.
