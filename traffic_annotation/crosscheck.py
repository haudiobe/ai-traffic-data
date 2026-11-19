"""CROSSCHECK engine: validates an annotated workbook against its original
results workbook, the Annex B.4 rules and the claims of the contribution.

The engine never changes a status. It records a decision per check:

* PASS    - rule satisfied
* ACCEPT  - deviation that is acceptable as-is (documented)
* REVIEW  - ambiguity or proposal that needs a human decision
* FAIL    - rule violated
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from openpyxl.utils import get_column_letter

from . import config, workbook as wbm
from .contribution import Contribution


@dataclass
class Finding:
    check_id: str
    scope: str
    subject: str
    rule: str
    observed: str
    expected: str
    decision: str  # PASS / ACCEPT / REVIEW / FAIL
    action: str = ""

    def as_dict(self):
        return asdict(self)


@dataclass
class DatasetRecord:
    dataset_id: str
    row: int
    parent_sheet_ref: str
    resolved_sheet: str | None
    resolve_method: str
    variant: str
    contributor: str
    status: str
    cross_checked: str
    derived: bool
    supplementary: bool
    tdocs: str
    prior_agreement: str
    missing_mandatory: list
    stated_missing: list
    register_status: str | None = None
    index_status: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Result:
    original_path: Path
    annotated_path: Path
    contribution_path: Path | None
    original_hash: str
    annotated_hash: str
    contribution_hash: str | None
    original_stats: dict
    annotated_stats: dict
    sheet_diffs: dict
    datasets: list
    evidence: list
    provenance: list
    index_rows: dict
    counts: list  # (metric, claimed, extracted_parser, extracted_raw, decision)
    findings: list
    contribution: Contribution | None
    version_info: dict

    def by_decision(self, decision):
        return [f for f in self.findings if f.decision == decision]


# ---------------------------------------------------------------------------
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _split_list(v) -> list[str]:
    if config.is_missing(v):
        return []
    return [p.strip() for p in re.split(r"[;,\n]", str(v)) if p.strip()]


def _parse_stated_missing(v) -> list[str]:
    s = _s(v)
    if ":" not in s:
        return []
    return [p.strip() for p in s.split(":", 1)[1].split(",") if p.strip()]


def _parse_index(ws, sheetnames):
    """Map sheet -> dict(status, row, content, reported_in) from the Index."""
    header_row = None
    for r in range(1, ws.max_row + 1):
        if _s(ws.cell(r, 1).value) == "Sheet":
            header_row = r
            break
    rows = {}
    if header_row is None:
        return rows, None
    headers = [_s(c.value) for c in ws[header_row]]
    col = {h: i + 1 for i, h in enumerate(headers) if h}
    for r in range(header_row + 1, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if name is None:
            continue
        sheet, method = wbm.resolve_sheet(_s(name), sheetnames)
        if sheet is None:
            continue
        rows[sheet] = {
            "row": r,
            "label": _s(name),
            "method": method,
            "status": _s(ws.cell(r, col.get("Status", 6)).value),
            "content": _s(ws.cell(r, col.get("Content", 2)).value),
            "reported_in": _s(ws.cell(r, col.get("Results reported in", 5)).value),
        }
    return rows, header_row


def _version_info(ws, path: Path) -> dict:
    label = None
    for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
        for v in row:
            m = re.search(r"Version\s+(\d+(?:\.\d+)+)", _s(v))
            if m:
                label = m.group(1)
                break
        if label:
            break
    m = re.search(r"(\d+)[._](\d+)[._](\d+)", path.name)
    fname = ".".join(m.groups()) if m else None
    return {"index_label": label, "filename": fname}


def _candidates(category: str, datasets: list) -> list:
    """Propose non-derived, non-supplementary datasets for a characteristic
    category using keyword hints. Proposals only - always reviewed."""
    cat = category.lower()
    pool = [d for d in datasets if not d.derived and not d.supplementary]
    hints = []
    for key, words in config.CHARACTERISTIC_CATEGORY_HINTS.items():
        if key in cat:
            if words is None:
                return pool
            hints.extend(words)
    if not hints:
        return []
    return [d for d in pool
            if any(h in (d.variant + " " + _s(d.raw.get("Application category"))).lower() for h in hints)]


# ---------------------------------------------------------------------------
def run(original: Path, annotated: Path, contribution: Contribution | None = None) -> Result:
    original, annotated = Path(original), Path(annotated)
    O = wbm.load(original)
    A = wbm.load(annotated)
    F: list[Finding] = []
    add = lambda *a, **k: F.append(Finding(*a, **k))  # noqa: E731

    o_stats = {ws.title: wbm.sheet_stats(ws) for ws in O.worksheets}
    a_stats = {ws.title: wbm.sheet_stats(ws) for ws in A.worksheets}

    # ---- C01 sheet set -----------------------------------------------------
    removed = [s for s in O.sheetnames if s not in A.sheetnames]
    added = [s for s in A.sheetnames if s not in O.sheetnames]
    missing_annot = [s for s in config.ANNOTATION_SHEETS if s not in A.sheetnames]
    unexpected = [s for s in added if s not in config.ANNOTATION_SHEETS]
    add("C01", "workbook", "sheet set", "Annotated workbook = original sheets + B.4 annotation sheets",
        f"removed={removed}; added={added}", f"removed=[]; added={list(config.ANNOTATION_SHEETS)}",
        "PASS" if not removed and not missing_annot and not unexpected else "FAIL",
        "" if not removed else "Restore removed result sheets")

    # ---- C02 measurement preservation -------------------------------------
    diffs = {}
    for name in O.sheetnames:
        if name not in A.sheetnames:
            continue
        d = wbm.diff_sheets(O[name], A[name])
        diffs[name] = d
        if name == config.INDEX_SHEET:
            continue
        if d.differing_cells:
            add("C02", "sheet", name, "Result values unchanged by annotation",
                f"{d.differing_cells} differing cells (e.g. {', '.join(d.samples)})", "0 differing cells",
                "FAIL", "Investigate value changes in result sheet")
        elif d.float_noise_cells:
            add("C02", "sheet", name, "Result values unchanged by annotation",
                f"{d.float_noise_cells} cells differ only by float round-off (max rel {d.max_rel_float_diff:.1e})",
                f"rel diff <= {config.FLOAT_REL_TOL}", "ACCEPT",
                "Save-precision noise; no action")
        else:
            add("C02", "sheet", name, "Result values unchanged by annotation", "identical", "identical", "PASS")

    # ---- Index -------------------------------------------------------------
    o_index, _ = _parse_index(O[config.INDEX_SHEET], O.sheetnames) if config.INDEX_SHEET in O.sheetnames else ({}, None)
    a_index, _ = _parse_index(A[config.INDEX_SHEET], A.sheetnames) if config.INDEX_SHEET in A.sheetnames else ({}, None)
    idx_diff = diffs.get(config.INDEX_SHEET)
    if idx_diff is not None:
        non_status, appended = [], []
        status_cells = set()
        mo, ma = wbm.cell_map(O[config.INDEX_SHEET]), wbm.cell_map(A[config.INDEX_SHEET])
        last_orig_row = max((r for r, _ in mo), default=0)
        status_col = 6
        for (r, c) in sorted(mo.keys() | ma.keys()):
            vo, va = mo.get((r, c)), ma.get((r, c))
            if vo == va:
                continue
            coord = f"{get_column_letter(c)}{r}"
            if vo is not None and c == status_col and mo.get((r, 1)) == ma.get((r, 1)):
                status_cells.add(coord)
            elif vo is None and r > last_orig_row:
                appended.append(coord)
            else:
                non_status.append(coord)
        add("C03", "sheet", config.INDEX_SHEET, "Index changes limited to the Status column",
            f"{len(status_cells)} status cells changed; {len(non_status)} other cells changed",
            "only Status column changed", "PASS" if not non_status else "REVIEW",
            "" if not non_status else f"Review non-status Index edits: {', '.join(non_status[:10])}")
        if appended:
            add("C03", "sheet", config.INDEX_SHEET, "Index additions appended below original content",
                f"{len(appended)} new cells ({', '.join(appended)})", "explanatory notes only", "ACCEPT",
                "Annotation notes appended; original content untouched")
        transitions = {}
        for sheet, o in o_index.items():
            a = a_index.get(sheet)
            if a:
                transitions.setdefault((o["status"], a["status"]), []).append(sheet)
        for (src, dst), sheets in sorted(transitions.items()):
            low = src.lower()
            if dst == "STABLE" and low.startswith(("agreed", "added")):
                dec, act = "PASS", ""
            elif dst == "STABLE" and low.startswith("renumbered"):
                dec, act = "ACCEPT", "Renumbering is not an agreement event; STABLE relies on underlying results being agreed earlier"
            else:
                dec, act = "REVIEW", "Confirm status transition"
            add("C03", "index-status", f"{src} -> {dst}", "Original Index status mapped to B.4 status",
                f"{len(sheets)} sheet(s): {'; '.join(sheets)}",
                "pre-existing agreed -> STABLE (B.4.3 NOTE 3)", dec, act)

    # ---- C18 version -------------------------------------------------------
    vinfo = {}
    for label, wb_, path_ in (("original", O, original), ("annotated", A, annotated)):
        if config.INDEX_SHEET not in wb_.sheetnames:
            continue
        v = _version_info(wb_[config.INDEX_SHEET], path_)
        vinfo[label] = v
        if v.get("index_label") and v.get("filename") and v["index_label"] != v["filename"]:
            add("C18", "workbook", path_.name, "Index version label matches file version",
                f"Index says {v['index_label']}, file name says {v['filename']}", "equal", "REVIEW",
                "Confirm workbook revision and update Index label")

    # ---- Catalogue ---------------------------------------------------------
    datasets: list[DatasetRecord] = []
    counts = []
    if config.CATALOGUE_SHEET in A.sheetnames:
        ws = A[config.CATALOGUE_SHEET]
        headers, recs = wbm.read_table(ws)
        hdr = [h for h in headers if h]
        n_m, n_r = len(config.MANDATORY_FIELDS), len(config.RECOMMENDED_FIELDS)
        ok_order = tuple(hdr[:n_m]) == config.MANDATORY_FIELDS and tuple(hdr[n_m:n_m + n_r]) == config.RECOMMENDED_FIELDS
        add("C04", "sheet", config.CATALOGUE_SHEET, "B.4.4 mandatory fields first, then recommended",
            f"{hdr[:n_m + n_r]}", f"{list(config.MANDATORY_FIELDS + config.RECOMMENDED_FIELDS)}",
            "PASS" if ok_order else "FAIL", "" if ok_order else "Reorder catalogue columns")
        n_additional = len(hdr) - n_m - n_r

        ids = [_s(r.get("Dataset ID")) for r in recs]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        add("C06", "sheet", config.CATALOGUE_SHEET, "Dataset IDs unique and non-empty",
            f"duplicates={dup}; empty={ids.count('')}", "no duplicates/empties",
            "PASS" if not dup and "" not in ids else "FAIL")
        schemes = {("DS-" if i.startswith("DS-") else "other") for i in ids}
        if len(schemes) > 1:
            others = [i for i in ids if not i.startswith("DS-")]
            add("C06", "sheet", config.CATALOGUE_SHEET, "Single Dataset ID scheme",
                f"mixed schemes; non 'DS-' IDs: {', '.join(others)}", "one scheme (e.g. DS-nnn)", "REVIEW",
                "Agree a single ID scheme before IDs are cited in Characteristic Evidence / TR")

        completeness_groups: dict = {}
        for r in recs:
            parent = _s(r.get(config.COL_PARENT))
            sheet, method = wbm.resolve_sheet(parent, A.sheetnames)
            variant = _s(r.get(config.COL_VARIANT))
            missing = [f for f in config.MANDATORY_FIELDS if config.is_missing(r.get(f))]
            ds = DatasetRecord(
                dataset_id=_s(r.get("Dataset ID")), row=r["_row"], parent_sheet_ref=parent,
                resolved_sheet=sheet, resolve_method=method, variant=variant,
                contributor=_s(r.get("Contributor")), status=_s(r.get(config.COL_STATUS)).upper(),
                cross_checked=_s(r.get(config.COL_XCHECK)),
                derived=_s(r.get(config.COL_DERIVED)).upper().startswith("YES"),
                supplementary="alternative" in variant.lower() or _s(r.get("Dataset ID")).upper().startswith("DS-SUP"),
                tdocs=_s(r.get(config.COL_TDOCS)), prior_agreement=_s(r.get(config.COL_PRIOR)),
                missing_mandatory=missing, stated_missing=_parse_stated_missing(r.get(config.COL_COMPLETENESS)),
                raw={k: v for k, v in r.items() if k != "_row"},
            )
            datasets.append(ds)

            # C07 parent sheet resolution
            if method in ("exact",):
                pass
            elif method == "normalized":
                add("C07", "dataset", ds.dataset_id, "Parent sheet reference resolves to a sheet",
                    f"'{parent}' matched '{sheet}' after whitespace/spelling normalization", "exact sheet name",
                    "ACCEPT", "Use exact sheet name in catalogue")
            elif method == "clause":
                add("C07", "dataset", ds.dataset_id, "Parent sheet reference resolves to a sheet",
                    f"'{parent}' matched '{sheet}' by clause number only", "exact sheet name", "REVIEW",
                    "Confirm mapping and use exact sheet name")
            else:
                add("C07", "dataset", ds.dataset_id, "Parent sheet reference resolves to a sheet",
                    f"'{parent}' does not resolve ({method})", "existing sheet", "REVIEW",
                    "Identify the source sheet(s) or mark record as umbrella/campaign-level")

            # C09 completeness recomputation (grouped by discrepancy below)
            stated = set(ds.stated_missing)
            computed = set(missing)
            if stated != computed:
                sig = (tuple(sorted(computed - stated)), tuple(sorted(stated - computed)))
                completeness_groups.setdefault(sig, []).append(ds.dataset_id)

            # C10 status rules
            if ds.status not in config.DATASET_STATUSES:
                add("C10", "dataset", ds.dataset_id, "Status is a B.4 dataset status",
                    ds.status or "(empty)", "/".join(config.DATASET_STATUSES), "FAIL")
            elif ds.status == "STABLE" and config.is_missing(ds.prior_agreement):
                add("C10", "dataset", ds.dataset_id, "STABLE requires agreement evidence (NOTE 3 or stabilization path)",
                    "no prior-agreement evidence", "evidence recorded", "FAIL", "Downgrade to SUBMITTED or add evidence")
            elif ds.status == "CANDIDATE" and missing:
                add("C10", "dataset", ds.dataset_id, "CANDIDATE requires complete mandatory metadata",
                    f"missing: {', '.join(missing)}", "none missing", "FAIL", "Keep SUBMITTED until complete")
            elif ds.status == "DEPRECATED" and config.is_missing(r.get(config.COL_RELATED)):
                add("C10", "dataset", ds.dataset_id, "DEPRECATED should reference superseding dataset",
                    "no related dataset", "reference", "REVIEW")
            elif ds.status == "STABLE" and ds.supplementary:
                add("C10", "dataset", ds.dataset_id, "Supplementary blocks do not inherit STABLE from parent sheet",
                    "STABLE", "SUBMITTED unless separately agreed", "REVIEW")

            # C11 cross-check
            if config.is_yes(ds.cross_checked):
                ok = re.search(r"S4\w*-\d{6}", ds.cross_checked) is not None
                add("C11", "dataset", ds.dataset_id, "CROSS_CHECKED=YES requires an identified verifying contribution",
                    ds.cross_checked, "YES + verifying contribution reference", "PASS" if ok else "FAIL",
                    "" if ok else "Set to NO unless verifying contribution is recorded")

        for (unlisted, overlisted), ids_ in completeness_groups.items():
            obs = []
            if unlisted:
                obs.append(f"missing/placeholder but not listed as missing: {', '.join(unlisted)}")
            if overlisted:
                obs.append(f"listed as missing but populated: {', '.join(overlisted)}")
            add("C09", "dataset-group", f"{len(ids_)} record(s)",
                "Stated B.4.4 completeness equals recomputed completeness",
                "; ".join(obs) + f" -- records: {', '.join(ids_)}", "identical field sets", "REVIEW",
                "Placeholder values such as 'Not identified in workbook' are not metadata; "
                "list the field as missing (or populate it from the source TDoc)")
        if not completeness_groups and datasets:
            add("C09", "workbook", config.CATALOGUE_SHEET, "Stated B.4.4 completeness equals recomputed completeness",
                "consistent for all records", "identical field sets", "PASS")

        # aggregate status decisions
        n_stable = sum(d.status == "STABLE" for d in datasets)
        n_sub = sum(d.status == "SUBMITTED" for d in datasets)
        n_derived = sum(d.derived for d in datasets)
        n_xno = sum(not config.is_yes(d.cross_checked) for d in datasets)
        add("C11", "workbook", config.CATALOGUE_SHEET, "No CROSS_CHECKED inferred from agreement or multi-provider data",
            f"CROSS_CHECKED=YES on {len(datasets) - n_xno} records", "0 unless verification evidence",
            "PASS" if n_xno == len(datasets) else "REVIEW")

        raw_rows = wbm.count_data_rows(ws)
        counts += [
            ("catalogue_rows", len(datasets), raw_rows),
            ("additional_fields", n_additional, None),
            ("stable_records", n_stable, None),
            ("submitted_records", n_sub, None),
            ("derived_records", n_derived, None),
            ("cross_checked_no_records", n_xno, None),
        ]

        # C08 coverage: every result sheet covered by >= 1 record
        covered = {d.resolved_sheet for d in datasets if d.resolved_sheet}
        for s in O.sheetnames:
            if s == config.INDEX_SHEET:
                continue
            if s not in covered:
                add("C08", "sheet", s, "Every result sheet is catalogued", "no catalogue record",
                    ">= 1 record", "FAIL", "Add catalogue record")
        multi = {}
        for d in datasets:
            if d.resolved_sheet:
                multi.setdefault(d.resolved_sheet, []).append(d.dataset_id)
        for s, ids_ in multi.items():
            if len(ids_) > 1:
                add("C08", "sheet", s, "Multi-dataset sheets split into logical records",
                    f"{len(ids_)} records: {', '.join(ids_)}", "split per provider/experiment", "PASS")

    # ---- Status register / Index consistency -------------------------------
    if config.REGISTER_SHEET in A.sheetnames:
        _, regs = wbm.read_table(A[config.REGISTER_SHEET])
        counts.append(("register_rows", len(regs), wbm.count_data_rows(A[config.REGISTER_SHEET])))
        for reg in regs:
            label = _s(reg.get("Dataset / sheet"))
            sheet, method = wbm.resolve_sheet(label, A.sheetnames)
            alt = "alternative" in label.lower()
            matched = [d for d in datasets if d.resolved_sheet == sheet and d.supplementary == alt] if sheet else []
            rstatus = _s(reg.get("Assigned status")).upper()
            if not matched:
                add("C12", "register", label, "Register row maps to catalogue record(s)",
                    f"no catalogue match (sheet resolution: {method})", ">= 1 record", "REVIEW",
                    "Add Dataset ID column to register")
                continue
            for d in matched:
                d.register_status = rstatus
                if d.status != rstatus:
                    add("C12", "dataset", d.dataset_id, "Catalogue status equals Status Register",
                        f"catalogue={d.status}; register={rstatus}", "equal", "FAIL", "Align status")
            if method != "exact" and not alt:
                add("C12", "register", label, "Register uses exact sheet names",
                    f"resolved to '{sheet}' via {method}", "exact", "ACCEPT")
        if datasets and len(regs) != len(datasets):
            add("C12", "workbook", config.REGISTER_SHEET, "Register granularity matches catalogue",
                f"register rows={len(regs)}; catalogue records={len(datasets)}; "
                f"records without register status: {[d.dataset_id for d in datasets if not d.register_status] or 'none'}",
                "one row per Dataset ID",
                "ACCEPT" if all(d.register_status for d in datasets) else "REVIEW",
                "Register is per sheet; consider adding a Dataset ID column so status is traceable per record")

    for d in datasets:
        if d.resolved_sheet and d.resolved_sheet in a_index and not d.supplementary:
            d.index_status = a_index[d.resolved_sheet]["status"].upper()
            if d.index_status != d.status:
                add("C13", "dataset", d.dataset_id, "Catalogue status equals annotated Index status",
                    f"catalogue={d.status}; index={d.index_status}", "equal", "FAIL", "Align status")

    # ---- Characteristic evidence ------------------------------------------
    evidence = []
    by_id = {d.dataset_id: d for d in datasets}
    if config.EVIDENCE_SHEET in A.sheetnames:
        _, evs = wbm.read_table(A[config.EVIDENCE_SHEET])
        counts.append(("evidence_rows", len(evs), wbm.count_data_rows(A[config.EVIDENCE_SHEET])))
        n_multi = n_open = 0
        for e in evs:
            cid = _s(e.get("Characteristic ID"))
            orgs = _split_list(e.get("Contributing organization(s)"))
            n_src = e.get("Number of independent sources") or 0
            n_ds = e.get("Number of datasets") or 0
            flag = _s(e.get("Evidence flag")).upper()
            ids_raw = _s(e.get("Dataset ID(s)"))
            id_tokens = _split_list(ids_raw)
            resolved = [t for t in id_tokens if t in by_id]
            proposed = []
            if id_tokens and not resolved:
                clauses = re.findall(r"\d+(?:\.\d+)+[a-z]?", ids_raw)
                for cl in clauses:
                    proposed += [d.dataset_id for d in datasets
                                 if d.resolved_sheet and wbm.clause_of(d.resolved_sheet) == cl.lower()]
            used = resolved or proposed
            used_ds = [by_id[i] for i in used if i in by_id]
            ds_orgs = sorted({d.contributor for d in used_ds if not config.is_missing(d.contributor)})
            derived_used = [d.dataset_id for d in used_ds if d.derived]
            exp_flag = config.expected_evidence_flag(len(orgs))
            n_multi += flag == "MULTI-SOURCE"
            n_open += _s(e.get("Assessment status")).upper() == "OPEN"

            # candidate mapping proposal for open characteristics
            cand = []
            if not used:
                cand = _candidates(_s(e.get("Application category")), datasets)
            cand_orgs = sorted({d.contributor for d in cand if not config.is_missing(d.contributor)})

            ev = {
                "characteristic_id": cid,
                "characteristic": _s(e.get("Characteristic / metric")),
                "orgs_listed": orgs,
                "n_sources_stated": n_src,
                "n_datasets_stated": n_ds,
                "flag_stated": flag,
                "flag_expected": exp_flag,
                "dataset_refs": ids_raw,
                "dataset_ids_resolved": resolved,
                "dataset_ids_proposed": proposed,
                "orgs_from_datasets": ds_orgs,
                "candidate_datasets": [d.dataset_id for d in cand],
                "candidate_orgs_identified": cand_orgs,
                "spread": _s(e.get("Observed spread / range")),
                "assessment_status": _s(e.get("Assessment status")),
            }
            evidence.append(ev)

            if int(n_src) != len(orgs):
                add("C14", "characteristic", cid, "Number of independent sources = distinct organizations listed",
                    f"stated {n_src}, listed {len(orgs)}", "equal", "FAIL")
            if flag != exp_flag:
                add("C14", "characteristic", cid, "Evidence flag follows independent-source count",
                    f"{flag} with {len(orgs)} org(s)", exp_flag, "FAIL")
            if id_tokens and not resolved:
                add("C14", "characteristic", cid, "Dataset ID(s) reference catalogue IDs",
                    f"'{ids_raw}' is not a Dataset ID list", "catalogue IDs",
                    "REVIEW", f"Proposed replacement: {', '.join(proposed) or 'none found'}")
            if used and int(n_ds) != len(used):
                add("C14", "characteristic", cid, "Number of datasets = referenced datasets",
                    f"stated {n_ds}, referenced {len(used)}", "equal", "FAIL")
            if used_ds and sorted(orgs) != ds_orgs:
                add("C14", "characteristic", cid, "Listed organizations = contributors of referenced datasets",
                    f"listed={orgs}; catalogue contributors={ds_orgs}", "equal", "REVIEW",
                    "Reconcile contributor names")
            elif used_ds:
                add("C14", "characteristic", cid, "Listed organizations = contributors of referenced datasets",
                    f"{orgs}", "equal", "PASS")
            if derived_used:
                add("C14", "characteristic", cid, "Derived/summary datasets not counted as evidence",
                    f"derived referenced: {derived_used}", "none", "FAIL")
            if flag in ("SINGLE-SOURCE", "MULTI-SOURCE") and config.is_missing(ev["spread"]):
                add("C14", "characteristic", cid, "Assessed characteristic records observed spread",
                    "spread empty", "spread / range", "REVIEW", "Compute metric-level spread across sources")
            if not used:
                n_c = len(cand_orgs)
                n_unid = sum(config.is_missing(d.contributor) for d in cand)
                add("C15", "characteristic", cid, "Candidate datasets proposed for open characteristic",
                    f"{len(cand)} keyword-matched candidate datasets ({n_unid} with unidentified contributor); "
                    f"identified contributors: {', '.join(cand_orgs) or 'none'}",
                    "metric-level mapping by rapporteur", "REVIEW",
                    (f"Upper bound only if the identified contributors' datasets actually report this metric: "
                     f"{config.expected_evidence_flag(n_c)}. " if n_c else "Cannot assess: ")
                    + "identify contributors of the remaining datasets first")
        counts += [("multi_source_characteristics", n_multi, None), ("open_characteristics", n_open, None)]

    # ---- Provenance --------------------------------------------------------
    provenance = []
    if config.PROVENANCE_SHEET in A.sheetnames:
        _, pvs = wbm.read_table(A[config.PROVENANCE_SHEET])
        counts.append(("provenance_rows", len(pvs), wbm.count_data_rows(A[config.PROVENANCE_SHEET])))
        for p in pvs:
            scope = _s(p.get("Dataset / scope"))
            sheet, method = wbm.resolve_sheet(scope, A.sheetnames)
            target = sheet or (scope if scope in by_id else None)
            kind = "sheet" if sheet else ("dataset" if target else ("global" if scope.lower().startswith("all") else "unresolved"))
            provenance.append({"event_id": _s(p.get("Event ID")), "scope": scope, "resolved": target or "", "kind": kind,
                               "confidence": _s(p.get("Confidence")), "date": _s(p.get("Date"))})
            if kind == "unresolved":
                add("C16", "provenance", _s(p.get("Event ID")), "Provenance scope resolves to sheet/dataset",
                    scope, "sheet or Dataset ID", "REVIEW")
            if _s(p.get("Confidence")).lower() == "medium" or config.is_missing(p.get("Date")):
                add("C16", "provenance", _s(p.get("Event ID")), "Provenance event fully evidenced",
                    f"confidence={_s(p.get('Confidence'))}; date={_s(p.get('Date')) or '(empty)'}",
                    "high confidence, dated", "REVIEW", _s(p.get("Follow-up")))
    if config.STATUS_DEFS_SHEET in A.sheetnames:
        _, sd = wbm.read_table(A[config.STATUS_DEFS_SHEET])
        counts.append(("status_definition_rows", len(sd), wbm.count_data_rows(A[config.STATUS_DEFS_SHEET])))

    # ---- C17 encoding damage ----------------------------------------------
    for name, st in a_stats.items():
        if st.replacement_chars:
            src = o_stats.get(name)
            inherited = src is not None and src.replacement_chars == st.replacement_chars
            add("C17", "sheet", name, "No encoding damage (U+FFFD) in text",
                f"{st.replacement_chars} replacement characters" + (" (also in original)" if inherited else ""),
                "0", "ACCEPT" if inherited else "REVIEW",
                "Restore original dash/bullet characters")

    # ---- Claimed vs extracted counts --------------------------------------
    claims = contribution.claims if contribution else {}
    count_rows = []
    for metric, parsed, raw in counts:
        claimed = claims.get(metric, (None, ""))[0]
        ok = (claimed is None or claimed == parsed) and (raw is None or raw == parsed)
        decision = "PASS" if ok else "FAIL"
        if claimed is None:
            decision = "PASS" if raw is None or raw == parsed else "FAIL"
        count_rows.append((metric, claimed, parsed, raw, decision))
        if not ok:
            add("C05", "count", metric, "Contribution claim / raw row count = parsed count",
                f"claimed={claimed}; parsed={parsed}; raw={raw}", "all equal", "FAIL")
    for key in claims:
        if key not in {c[0] for c in counts}:
            count_rows.append((key, claims[key][0], None, None, "REVIEW"))

    return Result(
        original_path=original, annotated_path=annotated,
        contribution_path=contribution.path if contribution else None,
        original_hash=wbm.sha256(original), annotated_hash=wbm.sha256(annotated),
        contribution_hash=wbm.sha256(contribution.path) if contribution else None,
        original_stats=o_stats, annotated_stats=a_stats, sheet_diffs=diffs,
        datasets=datasets, evidence=evidence, provenance=provenance, index_rows=a_index,
        counts=count_rows, findings=F, contribution=contribution, version_info=vinfo,
    )
