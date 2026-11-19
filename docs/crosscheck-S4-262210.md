# CROSSCHECK of the S4-262210 annotated workbook

Pipeline: `traffic-annotation` 0.1.0, run 2026-11-19.
Full machine-generated output (review XLSX, Markdown, JSON) is kept with the source files, outside this repository.

## 1. Inputs and inventory

The source directory held exactly three files. None was modified: SHA-256 hashes were verified before and after every run.

| Role | File | SHA-256 |
|---|---|---|
| Original results workbook (27 sheets) | `S4-262210 Collated_AI_Traffic_Results_note_0_6_3.xlsx` | `395f2bb3…53daab` |
| Annotated B.4 workbook (32 sheets) | `S4-262210-Collated_AI_Traffic_Results_B4.xlsx` | `08be556d…b2c103` |
| Contribution (Source: Qualcomm Incorporated, `[FS_6G_MED] Data Annotation`, TR 26.870 v0.6.3, AI 11.3.1, for agreement) | `S4-262210-Data-Annotation.docx` | `9ab06517…ea4ada` |

**Inputs not available.** These were referenced in the task but not found, either in the source directory or in a search of the wider drive:

* TR 26.870 itself (Annex B.4 text). The rules were therefore implemented from the contribution text and the workbook's own `Status Definitions` sheet. The workbook cites S4aP260156 as the B.4 source.
* A separate "handover requirements" document.
* `SA4_Traffic_Annotation_Pipeline_Starter.zip`. The pipeline was written from scratch.

## 2. Count comparison: contribution claims vs extracted

Each count was computed twice: once by the header-based parser and once as an independent raw count of non-empty rows. Both are compared with the number claimed in the contribution.

| Metric | Claimed | Parser | Raw rows | Result |
|---|---|---|---|---|
| Dataset Catalogue rows | 33 | 33 | 33 | PASS |
| Additional governance fields | 14 | 14 | – | PASS |
| STABLE records | 31 | 31 | – | PASS |
| SUBMITTED records | 2 | 2 | – | PASS |
| Derived / summary records | 4 | 4 | – | PASS |
| CROSS_CHECKED = NO | 33 | 33 | – | PASS |
| Characteristic Evidence rows | 10 | 10 | 10 | PASS |
| … provisional MULTI-SOURCE | 1 | 1 | – | PASS |
| … open assessments | 9 | 9 | – | PASS |
| Provenance History rows | 9 | 9 | 9 | PASS |
| Status Definitions rows | 8 | 8 | 8 | PASS |
| Dataset Status Register rows | – | 28 | 28 | PASS |

## 3. Result-sheet preservation

* All 27 original sheets are present in the annotated workbook. The 5 annotation sheets were added and nothing was removed.
* 25 result sheets are **value-identical**.
* `overview_2_local_server`: 38 cells differ only by float round-off (max relative difference 4.3e-16, i.e. save precision). **ACCEPT.**
* `0. Index`: 26 Status cells changed. 22 of them were `Agreed → STABLE`. The other four were `Agreed at SA4#137-e`, `Agreed at S4aP260158`, `Added at SA4#137-e` and `Renumbered at SA4#137-e`, each becoming `STABLE`. Four explanatory-note cells were appended below the original content (A62, A63, A68, A69). No other cell changed.

## 4. Source mapping (Dataset ID → sheet)

| Dataset ID | Sheet (resolved) | Resolution | Contributor | Status | Derived | Mandatory fields missing |
|---|---|---|---|---|---|---|
| DS-001 | 2.1 Test Scenarios | exact | – | STABLE | YES | 8 |
| DS-002 | 2.4.1 RT Video Understanding | exact | – | STABLE | NO | 7 |
| DS-003 | 2.4.1b RT Video Loss Sweep | exact | Huawei/HiSilicon | STABLE | NO | 6 |
| DS-004 | 2.4.1c RT Video Loss Sweep-2 | exact | NTT DOCOMO | STABLE | NO | 6 |
| DS-005 | 2.4.2 NRT Video Understndg | exact | – | STABLE | NO | 8 |
| DS-SUP-001 | 2.4.2 NRT Video Understndg (alternative site) | exact | – | SUBMITTED | NO | 6 |
| DS-006 | 2.5.1 Chat Tokens | exact | – | STABLE | NO | 8 |
| DS-007 | 2.5.2 Chat Streaming | exact | – | STABLE | NO | 8 |
| DS-008 | 2.5.3 Chat Non-Streaming | exact | – | STABLE | NO | 8 |
| DS-SUP-002 | 2.5.3 Chat Non-Streaming (alternative site) | exact | – | SUBMITTED | NO | 6 |
| DS-009 | 2.6 Reasoning | exact | – | STABLE | NO | 8 |
| DS-010 | 2.7.2 Multimodal Non-Streaming | exact | – | STABLE | NO | 8 |
| DS-011 | 2.8 A2A Collaboration | exact | – (S4-261446) | STABLE | NO | 6 |
| DS-012 | 2.9 Multimodal analysis live AI | exact | – | STABLE | NO | 7 |
| DS-013 | overview_2_local_server | exact | – | STABLE | YES | 9 |
| DS-014 | *"Section 3 — remote hosted AI services"*: **no sheet** | unresolved | – | STABLE | NO | 10 |
| DS-015 | 3_remote_test_overview | exact | – | STABLE | YES | 9 |
| 3.2-A / 3.2-B | 3.2 Chat Basic (Provider C / Provider A) | exact | – | STABLE | NO | 5 |
| 3.3-A / B / C | 3.3 Chat Streaming (Providers A / B / C) | exact | – | STABLE | NO | 5 |
| DS-016 | 3.6 Chat Coding and␣␣reasoning␣ | whitespace-normalized | – | STABLE | NO | 9 |
| DS-017 | 3.8 Multimodal - Provider B | exact | – | STABLE | NO | 8 |
| DS-018 | 3.9 Image Generation - Provider | exact | – | STABLE | NO | 8 |
| 3.10-A / 3.10-B | 3.10 Web Search - Provider A (Provider A / Provider C) | exact | – | STABLE | NO | 5 |
| DS-019 | 3.12 MCP␣␣- Provider A | whitespace-normalized | – | STABLE | NO | 9 |
| DS-020 | 3.14 Computer Control - Provide | exact | – | STABLE | NO | 8 |
| DS-021 | 3.15 Real-time Audio | spelling-normalized | – | STABLE | NO | 9 |
| DS-022 | 3.17 Real-time Text interactive | spelling-normalized | – | STABLE | NO | 9 |
| DS-023 | 3.22 Per-Scenario Summary remot | exact | – | STABLE | YES | 8 |
| DS-024 | 3.23 Personal Assistant Agent | exact | – (S4-261446) | STABLE | NO | 6 |

Every result sheet is covered by at least one record. In the catalogue, the Status Register and the annotated Index, status agrees for every record that appears in all three.

## 5. Crosscheck decisions

Summary: **40 PASS · 11 ACCEPT · 22 REVIEW · 0 FAIL**.

| Topic | Decision | Basis |
|---|---|---|
| Result values unchanged | PASS / ACCEPT | §3 |
| 31 STABLE assignments under B.4.3 NOTE 3 | PASS, except DS-014 and DS-004 (REVIEW, see A3/A4) | Each record has prior-agreement evidence in the original Index |
| 2.9 `Renumbered → STABLE` | ACCEPT | Renumbering is not an agreement event; STABLE relies on the underlying results having been agreed earlier |
| 2 SUBMITTED supplementary records | PASS | Not inherited from the parent sheet; no separate agreement evidence |
| CROSS_CHECKED = NO for all 33 | **Confirmed** | No verifying second-contributor contribution is recorded; not inferred from STABLE or MULTI-SOURCE |
| CH-007 MULTI-SOURCE | Flag **consistent** (2 organizations = DS-003/DS-004 contributors); stays PROVISIONAL | Dataset reference and spread are open (A6) |
| CH-001…CH-006, CH-008…CH-010 | Remain UNASSESSED | Contributors are unidentified for 25 of 27 non-derived records, so independent-source counts cannot be established (A7) |
| Catalogue column order / ID uniqueness | PASS | |

## 6. Unresolved ambiguities (for rapporteur / contributors)

| # | Item | Observation | Proposed resolution |
|---|---|---|---|
| A1 | Workbook version | The original workbook's Index says **Version 0.6.1**, but its file name says 0.6.3 | Confirm the revision and update the Index label |
| A2 | B.4.4 completeness of `Contributor` | 31 records hold the placeholder "Not identified/explicit in workbook", yet the completeness column does not list Contributor as missing. This contradicts the workbook's own rule that "missing values are explicit, not inferred" | Add Contributor to the missing list for these 31 records, or populate it from the source TDocs |
| A3 | DS-014 | The parent "Section 3 — remote hosted AI services" is a section heading, not a sheet. The record has no Status Register or Index entry and is not marked derived, so it risks double counting with the 3.x records | Mark it as an umbrella/derived record, or remove it |
| A4 | DS-004 (2.4.1c) status | Catalogue: unconditional STABLE ("Agreed at S4aP260158"). Provenance EV-003 (Medium): "STABLE if agreed before B.4". The Index row lacks scenario, execution and reporting location | Confirm that S4aP260158 agreement predates B.4 agreement |
| A5 | Dataset ID scheme | Mixed: `DS-nnn` alongside `3.2-A`, `3.3-B`, `3.10-B`, … | Agree one scheme before IDs are cited in the TR / evidence register |
| A6 | CH-007 Dataset IDs and spread | Dataset reference is written "DS rows for 2.4.1b and 2.4.1c"; observed spread is empty | Replace with **DS-003; DS-004** and compute the metric-level spread |
| A7 | Open characteristics | Keyword-matched candidates: CH-001…004: 27, CH-005/006: 10, CH-008: 6, CH-009: 5, CH-010: 19. In each case the only identified contributors are those of DS-003/DS-004 | Identify contributors per dataset first; MULTI-SOURCE is an upper bound only |
| A8 | Sub-clause numbering inside sheets | 3.2-B is "3.1 … Provider A", 3.3-B/C are "3.4"/"3.5", and 3.10-B is "3.11 Web Search – Provider C" inside the sheet named "… Provider A" | Record the sub-clause as the Scenario ID, or rename the sheets |
| A9 | Sheet-name spelling | The catalogue and register use "Realtime" and single spaces; the actual sheet names are "Real-time" or contain double or trailing spaces (3.6, 3.12, 3.15, 3.17) | Use exact sheet names (ACCEPT for now) |
| A10 | 3.15 DL traffic models (EV-007) | Added in rev 0.6.3 via S4-261780 and treated as part of the parent dataset | Decide whether these are a separately identifiable dataset (as DS-SUP-001/002 were) |
| A11 | Undated provenance | EV-001, 003, 006, 007, 008, 009 have no date or Medium confidence | Fill in from meeting reports |
| A12 | Status Register granularity | 28 rows per sheet vs 33 catalogue records; only DS-014 has no register status | Add a Dataset ID column to the register |

## 7. Method notes

* Placeholders ("Not identified in workbook", "Not recorded", "Unknown", "–", …) count as missing, never as metadata.
* Sheet references are resolved in this order: exact, then whitespace/dash/"real-time" normalization, then unique clause number, otherwise unresolved.
* Evidence flag: 0 independent organizations = UNASSESSED, 1 = SINGLE-SOURCE, ≥2 = MULTI-SOURCE. Providers and repeated runs are not organizations. Derived datasets are never counted.
* Measurement values are compared but never copied into any output.
