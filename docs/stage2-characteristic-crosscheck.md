# Stage 2 — characteristic-level evidence evaluation

Stage 2 evaluates **characteristics** (e.g. "loss tolerance"), not datasets.
For each characteristic it determines how many independent organizations
contribute evidence, whether that evidence is demonstrably comparable, and, only
then, whether the sources agree. It never changes a status in the workbook.

```
evidence spec (outside repo) ─┐
original workbook ────────────┼─> resolve & verify ─> independence ─> comparability ─> outcome ─> state
annotated workbook ───────────┘     (citations,          (dedup)        (9 dimensions)   (series)
                                     series)
```

## CROSSCHECK states

| State | Condition |
|---|---|
| `NOT_ASSESSED` | no evidence linked, or no evidence attributable to an identified organization |
| `SINGLE_SOURCE` | fewer independent organizations than `min_independent_organizations` (default 2) |
| `MULTI_SOURCE_NOT_COMPARABLE` | ≥2 organizations, at least one required dimension `NOT_COMPARABLE` |
| `CROSSCHECK_PENDING` | ≥2 organizations, no dimension `NOT_COMPARABLE`, but at least one `PARTIAL`/`UNKNOWN`, or too few common conditions |
| `CROSSCHECKED_CONSISTENT` | all required dimensions comparable; all common conditions consistent |
| `CROSSCHECKED_MIXED` | all comparable; some conditions consistent, others differ in magnitude/direction |
| `CROSSCHECKED_CONFLICTING` | all comparable; opposite directions at ≥ `conflicting_point_share` of conditions, or stated qualitative conclusions differ |

A provisional outcome is always computed when ≥2 organizations have series. It
is reported as *provisional (not applied)* while the state is pending.

## Independence (deduplication)

Evidence items are grouped by contributing organization (resolved through
the spec's organization aliases). Several datasets, campaigns, model variants,
providers, network profiles or repeated runs from one organization count as
**one** organization. Evidence from derived/summary datasets and evidence
without an identified organization is never counted. The dedup decision is
reported per characteristic.

## Comparability dimensions

`definition`, `units`, `direction`, `scenario`, `measurement_layer`,
`baseline`, `network_conditions`, `statistical_basis`, `qualitative_conclusion`.

Automatic rule (over counted items): any item without a **verified** value
→ `UNKNOWN`; identical verified values → `COMPARABLE`; differing →
`NOT_COMPARABLE`. A rapporteur assessment in the spec (status plus a
mandatory rationale) overrides the rule and is reported as `assessment`.
`qualitative_conclusion` is evaluated per organization; differing conclusions
are a disagreement (→ `CONFLICTING`), not non-comparability.

Additional descriptive **facets** (model, sample size, task corpus, transmitted
representation, denominator, runs, …) do not change the state, but
differences or gaps across organizations become open comparability questions.

## No inference

* A claim is verified only if its quote appears verbatim in the cited cell.
  Whitespace, dashes and quotes are normalized before matching.
  Uncited or unverified claims count as `UNKNOWN` and raise a citation issue.
* Numbers are read from cited cells; formulas are not evaluated. A numeric
  constant (e.g. a denominator) must also occur inside its verified quote.
* Where the source reports derived values (e.g. "change vs baseline"), they
  are recomputed from the source counts and any mismatch is flagged.
* Missing facts are entered as `null` with a note. They are never filled in.

## Historical results

Historical agreed results (status STABLE with prior-agreement evidence) are
retained. Missing B.4.4 metadata is reported as one `QUALIFIED_GAP` per field
across all historical datasets, with no per-record actions. Missing metadata on
non-historical records is a `WARNING`.

## Configuration

`traffic_annotation/characteristics/rules.json` (override with `--rules`):
minimum organizations, required dimensions, effect of each dimension status
(`ok` / `pending` / `not_comparable`), outcome dead band, magnitude tolerance,
minimum common points, conflicting share, reported-value tolerance.

## Evidence spec (schema `traffic-annotation/evidence-spec@1`)

```json
{
  "schema": "traffic-annotation/evidence-spec@1",
  "organizations": [{"id": "ORG-A", "name": "Org A", "aliases": ["Organisation A"]}],
  "characteristics": [{"id": "CH-001", "name": "Loss tolerance"}],
  "evidence": [{
    "id": "E-A", "characteristic": "CH-001", "dataset": "DS-101", "organization": "Org A",
    "variant": "model m1", "campaign": "C1", "provider": "", "network_profile": "", "run_group": "",
    "series": {"sheet": "4.1 Loss A", "x_cells": "C7:F7", "baseline_cell": "B8", "value_cells": "C8:F8",
               "x_parse": "percent",
               "denominator": {"value": 100, "source": {"sheet": "4.1 Loss A", "cell": "A4", "quote": "100 questions per profile"}},
               "alt_denominator": {"cells": "C10:F10"},
               "reported_change_cells": "C9:F9", "alt_reported_change_cells": "C11:F11"},
    "dimensions": {"direction": {"value": "UL", "source": {"sheet": "4.1 Loss A", "cell": "A2", "quote": "uncorrelated UL packet loss"}},
                   "statistical_basis": {"value": null, "note": "not stated"}},
    "facets": {"model": {"value": "m1", "source": {"sheet": "4.1 Loss A", "cell": "A2", "quote": "model m1"}}}
  }],
  "assessments": {"CH-001": {"scenario": {"status": "PARTIAL", "rationale": "different task corpora"}}},
  "questions": {"CH-001": ["Free-text question for the rapporteur"]}
}
```

Specs built from real contributions are source-derived and are kept outside
this repository.

## Usage

```bash
python -m traffic_annotation.characteristics \
    --original ORIG.xlsx --annotated B4.xlsx --spec evidence_spec.json \
    --out /outside/repo/stage2 [--rules rules.json] [--sheets-dry-run] [--fail-on ERROR|WARNING|never]
```

Outputs are deterministic: byte-identical for identical inputs, with fixed
XLSX timestamps and sorted JSON.

* `characteristic_crosscheck_review.xlsx` has four tabs: **Characteristic Evaluation**,
  **Evidence Map**, **Dataset Sources**, **Validation Issues**
* `characteristic_crosscheck_report.md`
* `normalized/{organizations,datasets,characteristics,evidence,validation_issues,manifest}.json`
* `sheets_sync_plan.json` (with `--sheets-dry-run`)

Input SHA-256 hashes are compared before and after every run; the exit code is 3 if they changed.

## Google Sheets (dry run only)

`characteristics/gsheets.py` builds an ordered sync plan (create spreadsheet,
ensure tabs, clear, update ranges) from the same tables as the XLSX.
`SheetsSync(dry_run=True)` only summarizes the plan. A real run requires both
`allow_external_write=True` and an injected client. No Google library is
bundled and the module makes no network calls.

## Publication check (before every commit)

```bash
python -m traffic_annotation.publication build --workbook ORIG.xlsx --workbook B4.xlsx \
    --extra "<model or corpus names>" --out /outside/repo/denylist.txt
git add ...
python -m traffic_annotation.publication check --denylist /outside/repo/denylist.txt
```

`check` scans only the staged additions. It flags Office/PDF/ZIP files,
document numbers, denylisted names, and distinctive source numbers (integers
with five or more digits). It prints only the kind and location of a hit,
never the matched term.
