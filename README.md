# ai-traffic-data — traffic annotation & CROSSCHECK pipeline

Automated checking of the collated AI traffic characterization workbook that
accompanies 3GPP TR 26.870 (FS_6G_MED) against the dataset-management rules of
Annex B.4 (B.4.3 status, B.4.4 dataset metadata, B.4.5 characteristic evidence).

Given

* the **original** collated results workbook,
* the **annotated** workbook (original + `Dataset Catalogue`, `Characteristic Evidence`,
  `Provenance History`, `Status Definitions`, `Dataset Status Register`), and
* optionally the **contribution** (.docx) that proposes the annotation,

the pipeline verifies that annotation did not alter any result, that every
result sheet is mapped to dataset records, that statuses and `CROSS_CHECKED`
follow the rules, that characteristic evidence flags follow the
independent-source count, and that the quantitative claims made in the
contribution match what is in the workbook.

It **never changes a status**. Each check yields a decision:

| Decision | Meaning |
|---|---|
| PASS | rule satisfied |
| ACCEPT | deviation acceptable as-is, documented |
| REVIEW | ambiguity or proposal for rapporteur / contributor decision |
| FAIL | rule violated |

## Usage

```bash
pip install -e .[dev]
python -m traffic_annotation \
    --original  "/path/outside/repo/Collated_AI_Traffic_Results.xlsx" \
    --annotated "/path/outside/repo/Collated_AI_Traffic_Results_B4.xlsx" \
    --contribution "/path/outside/repo/Data-Annotation.docx" \
    --out "/path/outside/repo/_review"      # --fail-on FAIL|REVIEW|never
```

Outputs (written to `--out`):

* `crosscheck_review.xlsx`: review workbook (Summary, Source Inventory, Sheet Count
  Comparison, Claimed vs Extracted, Dataset Mapping, B.4.4 Completeness,
  Characteristic Check, Crosscheck Decisions, Open Ambiguities)
* `crosscheck_report.md`: full Markdown report
* `crosscheck_normalized_catalogue.json`: normalized annotation metadata (no measurement values)

Exit code is `2` if findings at or above `--fail-on` exist (default `FAIL`).

## Checks

| ID | Check |
|---|---|
| C01 | Annotated sheet set = original sheets + the five annotation sheets |
| C02 | Every result sheet value-identical (float round-off ≤ 1e-12 relative accepted) |
| C03 | Index changes limited to Status column; status transitions (Agreed → STABLE per B.4.3 NOTE 3) |
| C04 | Catalogue column order: B.4.4 mandatory, then recommended |
| C05 | Contribution claims = parsed counts = independent raw row counts |
| C06 | Dataset IDs unique; single ID scheme |
| C07 | Catalogue parent-sheet references resolve (exact / normalized / clause / unresolved) |
| C08 | Every result sheet catalogued; multi-provider sheets split |
| C09 | Stated B.4.4 completeness = recomputed completeness (placeholders count as missing) |
| C10 | Status rules: STABLE needs agreement evidence, CANDIDATE needs complete mandatory metadata, supplementary blocks do not inherit STABLE |
| C11 | `CROSS_CHECKED=YES` only with a verifying contribution; never inferred |
| C12 | Status Register ↔ Catalogue consistency |
| C13 | Annotated Index status ↔ Catalogue consistency |
| C14 | Characteristic evidence: source count = organizations listed, flag follows count, IDs resolve, no derived datasets counted, spread recorded |
| C15 | Candidate dataset proposals for open characteristics (REVIEW only) |
| C16 | Provenance events resolve and are dated / high confidence |
| C17 | Encoding damage (U+FFFD) |
| C18 | Index version label vs file name version |

## Repository policy

Source workbooks, contributions and generated outputs are kept **outside**
this repository. `.gitignore` blocks Office/PDF/ZIP/CSV files, the CLI refuses
input or output paths inside the repo, and `tests/test_crosscheck.py::test_no_source_documents_are_tracked`
fails if such files are staged. Tests use synthetic workbooks built at test time.

```bash
python -m pytest -q
```

See [docs/stage1-crosscheck.md](docs/stage1-crosscheck.md) for decisions,
outputs and how to interpret them. Reports for a specific workbook are
source-derived and are kept outside this repository.

## Stage 2: characteristic-level CROSSCHECK

`python -m traffic_annotation.characteristics` evaluates characteristics
across independent organizations. It applies the CROSSCHECK states
`NOT_ASSESSED`, `SINGLE_SOURCE`, `MULTI_SOURCE_NOT_COMPARABLE`,
`CROSSCHECK_PENDING`, `CROSSCHECKED_CONSISTENT`, `CROSSCHECKED_MIXED` and
`CROSSCHECKED_CONFLICTING`, with explicit comparability over nine dimensions
and verbatim-citation checks, and writes a four-tab review XLSX.
Stage 2.1 separates trend agreement from magnitude agreement and labels
results by authority. Thresholds are experimental, so no CROSSCHECKED result
is authoritative under the packaged rules. Uncertain statistical evidence
keeps a characteristic pending. Denominator bases are distinguished, and
non-reproduced reported values are diagnosed without changing them.
`python -m traffic_annotation.publication` checks staged changes before a
commit (`check`) and scans the full Git history (`history`). See [docs/stage2-characteristic-crosscheck.md](docs/stage2-characteristic-crosscheck.md).
