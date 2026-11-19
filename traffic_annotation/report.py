"""Review workbook, normalized annotation records and Markdown report."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import __version__, config
from .crosscheck import Result

_FILL = {
    "PASS": PatternFill("solid", fgColor="C6EFCE"),
    "ACCEPT": PatternFill("solid", fgColor="DDEBF7"),
    "REVIEW": PatternFill("solid", fgColor="FFEB9C"),
    "FAIL": PatternFill("solid", fgColor="FFC7CE"),
}
_HDR = PatternFill("solid", fgColor="1F3864")


def _sheet(wb, title, headers, rows, decision_col=None, widths=None):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _HDR
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(["" if v is None else (", ".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for v in r])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if decision_col is not None:
            cell = row[decision_col]
            if cell.value in _FILL:
                cell.fill = _FILL[cell.value]
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, min(max(len(h) + 2, 12), 40))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def decision_summary(res: Result) -> dict:
    out = {k: 0 for k in ("PASS", "ACCEPT", "REVIEW", "FAIL")}
    for f in res.findings:
        out[f.decision] += 1
    return out


def write_review_xlsx(res: Result, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    summ = decision_summary(res)
    lines = [
        ("Traffic annotation CROSSCHECK review", ""),
        ("Generated", _dt.datetime.now().isoformat(timespec="seconds")),
        ("Pipeline version", __version__),
        ("Original workbook", res.original_path.name),
        ("Annotated workbook", res.annotated_path.name),
        ("Contribution", res.contribution_path.name if res.contribution_path else "(none)"),
        ("Datasets catalogued", len(res.datasets)),
        ("Characteristics", len(res.evidence)),
        *[(f"Decisions: {k}", v) for k, v in summ.items()],
        ("", ""),
        ("Decision legend", ""),
        ("PASS", "Rule satisfied"),
        ("ACCEPT", "Deviation acceptable as-is, documented"),
        ("REVIEW", "Ambiguity or proposal requiring rapporteur/contributor decision"),
        ("FAIL", "Rule violated"),
        ("", ""),
        ("Note", "The pipeline never changes statuses or CROSS_CHECKED; it records decisions and proposals only. "
                 "Measurement values are compared but not copied."),
    ]
    for l in lines:
        ws.append(list(l))
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 90
    for k, fill in _FILL.items():
        for row in ws.iter_rows():
            if row[0].value == k or row[0].value == f"Decisions: {k}":
                row[0].fill = fill

    _sheet(wb, "Source Inventory", ["Role", "File", "SHA-256", "Sheets"], [
        ("Original results workbook", res.original_path.name, res.original_hash, len(res.original_stats)),
        ("Annotated B.4 workbook", res.annotated_path.name, res.annotated_hash, len(res.annotated_stats)),
        ("Contribution", res.contribution_path.name if res.contribution_path else "", res.contribution_hash or "", ""),
    ], widths={"SHA-256": 70, "File": 55})

    rows = []
    for name in dict.fromkeys(list(res.original_stats) + list(res.annotated_stats)):
        o, a = res.original_stats.get(name), res.annotated_stats.get(name)
        d = res.sheet_diffs.get(name)
        if o and a:
            verdict = "PASS" if d.identical and (o.nonempty_cells, o.numeric_cells) == (a.nonempty_cells, a.numeric_cells) else (
                "ACCEPT" if name == config.INDEX_SHEET and o.nonempty_cells == a.nonempty_cells else "REVIEW")
        else:
            verdict = "ACCEPT" if name in config.ANNOTATION_SHEETS else "FAIL"
        rows.append((name, bool(o), bool(a),
                     o.nonempty_cells if o else None, a.nonempty_cells if a else None,
                     o.numeric_cells if o else None, a.numeric_cells if a else None,
                     o.nonempty_rows if o else None, a.nonempty_rows if a else None,
                     o.merged_ranges if o else None, a.merged_ranges if a else None,
                     d.differing_cells if d else None, d.float_noise_cells if d else None,
                     f"{d.max_rel_float_diff:.1e}" if d and d.float_noise_cells else "", verdict))
    _sheet(wb, "Sheet Count Comparison",
           ["Sheet", "In original", "In annotated", "Non-empty (orig)", "Non-empty (annot)",
            "Numeric (orig)", "Numeric (annot)", "Rows (orig)", "Rows (annot)", "Merged (orig)", "Merged (annot)",
            "Differing cells", "Float-noise cells", "Max rel float diff", "Verdict"],
           rows, decision_col=14, widths={"Sheet": 34})

    _sheet(wb, "Claimed vs Extracted",
           ["Metric", "Claimed in contribution", "Extracted (parser)", "Raw row count", "Decision"],
           res.counts, decision_col=4, widths={"Metric": 32})

    _sheet(wb, "Dataset Mapping",
           ["Dataset ID", "Catalogue row", "Parent sheet (as written)", "Resolved sheet", "Resolution",
            "Variant", "Contributor", "Source TDoc(s)", "Prior agreement", "Status (catalogue)",
            "Status (register)", "Status (index)", "CROSS_CHECKED", "Derived", "Supplementary"],
           [(d.dataset_id, d.row, d.parent_sheet_ref, d.resolved_sheet, d.resolve_method, d.variant, d.contributor,
             d.tdocs, d.prior_agreement, d.status, d.register_status, d.index_status, d.cross_checked,
             "YES" if d.derived else "NO", "YES" if d.supplementary else "NO") for d in res.datasets],
           widths={"Parent sheet (as written)": 34, "Resolved sheet": 34, "Variant": 40})

    _sheet(wb, "B.4.4 Completeness",
           ["Dataset ID", "Missing (recomputed)", "Missing (stated)", "Mandatory complete", "Consistent"],
           [(d.dataset_id, d.missing_mandatory, d.stated_missing, "YES" if not d.missing_mandatory else "NO",
             "PASS" if set(d.missing_mandatory) == set(d.stated_missing) else "REVIEW") for d in res.datasets],
           decision_col=4, widths={"Missing (recomputed)": 60, "Missing (stated)": 60})

    _sheet(wb, "Characteristic Check",
           ["Characteristic ID", "Characteristic", "Orgs listed", "Sources stated", "Datasets stated",
            "Flag stated", "Flag expected", "Dataset refs (as written)", "Resolved IDs", "Proposed IDs",
            "Orgs from datasets", "Candidate datasets (proposal)", "Identified candidate orgs", "Assessment"],
           [(e["characteristic_id"], e["characteristic"], e["orgs_listed"], e["n_sources_stated"],
             e["n_datasets_stated"], e["flag_stated"], e["flag_expected"], e["dataset_refs"],
             e["dataset_ids_resolved"], e["dataset_ids_proposed"], e["orgs_from_datasets"],
             e["candidate_datasets"], e["candidate_orgs_identified"], e["assessment_status"])
            for e in res.evidence],
           widths={"Candidate datasets (proposal)": 50})

    hdr = ["Check", "Scope", "Subject", "Rule", "Observed", "Expected", "Decision", "Action"]
    w = {"Rule": 45, "Observed": 60, "Expected": 30, "Action": 45, "Subject": 28}
    _sheet(wb, "Crosscheck Decisions", hdr,
           [(f.check_id, f.scope, f.subject, f.rule, f.observed, f.expected, f.decision, f.action) for f in res.findings],
           decision_col=6, widths=w)
    _sheet(wb, "Open Ambiguities", hdr,
           [(f.check_id, f.scope, f.subject, f.rule, f.observed, f.expected, f.decision, f.action)
            for f in res.findings if f.decision in ("REVIEW", "FAIL")],
           decision_col=6, widths=w)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def normalized_records(res: Result) -> dict:
    """Normalized annotation metadata (no measurement values)."""
    return {
        "schema": "traffic-annotation/dataset-catalogue@1",
        "source": {"annotated_workbook": res.annotated_path.name, "sha256": res.annotated_hash},
        "datasets": [
            {
                "dataset_id": d.dataset_id,
                "sheet": d.resolved_sheet,
                "sheet_reference": d.parent_sheet_ref,
                "variant": d.variant,
                "contributor": None if config.is_missing(d.contributor) else d.contributor,
                "status": d.status,
                "cross_checked": config.is_yes(d.cross_checked),
                "derived": d.derived,
                "supplementary": d.supplementary,
                "source_tdocs": [t.strip() for t in d.tdocs.split(";")] if not config.is_missing(d.tdocs) else [],
                "b44_missing_mandatory": d.missing_mandatory,
                "b44_mandatory_complete": not d.missing_mandatory,
            }
            for d in res.datasets
        ],
        "characteristics": res.evidence,
    }


def write_json(res: Result, path: Path) -> Path:
    Path(path).write_text(json.dumps(normalized_records(res), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return Path(path)


def _md_table(headers, rows) -> str:
    esc = lambda v: ("" if v is None else (", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v))).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(esc(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def write_markdown(res: Result, path: Path) -> Path:
    s = decision_summary(res)
    c = res.contribution
    L = [
        "# Traffic annotation CROSSCHECK report",
        "",
        f"Generated {_dt.date.today().isoformat()} by traffic-annotation {__version__}.",
        "",
        "## Inputs",
        "",
        _md_table(["Role", "File", "SHA-256"], [
            ("Original results workbook", res.original_path.name, res.original_hash),
            ("Annotated B.4 workbook", res.annotated_path.name, res.annotated_hash),
            ("Contribution", res.contribution_path.name if res.contribution_path else "-", res.contribution_hash or "-"),
        ]),
        "",
    ]
    if c:
        L += [f"Contribution header: " + "; ".join(f"{k}: {v}" for k, v in c.header.items()), ""]
    L += [
        "## Decision summary",
        "",
        _md_table(["PASS", "ACCEPT", "REVIEW", "FAIL"], [(s["PASS"], s["ACCEPT"], s["REVIEW"], s["FAIL"])]),
        "",
        "## Count comparison: contribution claims vs extracted",
        "",
        _md_table(["Metric", "Claimed", "Extracted (parser)", "Raw row count", "Decision"], res.counts),
        "",
        "## Result-sheet preservation (original vs annotated)",
        "",
    ]
    rows = []
    for name, d in res.sheet_diffs.items():
        o, a = res.original_stats[name], res.annotated_stats[name]
        rows.append((name, o.nonempty_cells, a.nonempty_cells, o.numeric_cells, a.numeric_cells,
                     d.differing_cells, d.float_noise_cells))
    L += [_md_table(["Sheet", "Non-empty (orig)", "Non-empty (annot)", "Numeric (orig)", "Numeric (annot)",
                     "Differing", "Float-noise"], rows), ""]
    L += ["## Source mapping (Dataset ID -> sheet)", "",
          _md_table(["Dataset ID", "Parent sheet (as written)", "Resolved sheet", "Resolution", "Contributor",
                     "Status", "Register", "Index", "CROSS_CHECKED", "Derived", "Missing mandatory"],
                    [(d.dataset_id, d.parent_sheet_ref, d.resolved_sheet or "-", d.resolve_method, d.contributor,
                      d.status, d.register_status or "-", d.index_status or "-", d.cross_checked,
                      "YES" if d.derived else "NO", len(d.missing_mandatory)) for d in res.datasets]), ""]
    L += ["## Characteristic evidence check", "",
          _md_table(["ID", "Characteristic", "Orgs", "Flag stated", "Flag expected", "Resolved IDs",
                     "Proposed IDs", "Candidates (proposal)", "Identified candidate orgs"],
                    [(e["characteristic_id"], e["characteristic"], e["orgs_listed"], e["flag_stated"],
                      e["flag_expected"], e["dataset_ids_resolved"], e["dataset_ids_proposed"],
                      len(e["candidate_datasets"]), e["candidate_orgs_identified"]) for e in res.evidence]), ""]
    for title, decisions in (("Unresolved ambiguities and failures", ("FAIL", "REVIEW")),
                             ("Accepted deviations", ("ACCEPT",)),
                             ("Passed checks", ("PASS",))):
        fs = [f for f in res.findings if f.decision in decisions]
        L += [f"## {title} ({len(fs)})", "",
              _md_table(["Check", "Subject", "Rule", "Observed", "Decision", "Action"],
                        [(f.check_id, f.subject, f.rule, f.observed, f.decision, f.action) for f in fs]), ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")
    return Path(path)
