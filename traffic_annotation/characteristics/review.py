"""Deterministic outputs: four-tab review XLSX, normalized JSON, Markdown."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .. import config as s1config
from .model import DIMENSIONS
from .evaluate import Evaluation

TABS = ("Characteristic Evaluation", "Evidence Map", "Dataset Sources", "Validation Issues")
_FIXED_TIME = _dt.datetime(2000, 1, 1)

_STATE_FILL = {
    "NOT_ASSESSED": "EDEDED", "SINGLE_SOURCE": "DDEBF7", "MULTI_SOURCE_NOT_COMPARABLE": "F8CBAD",
    "CROSSCHECK_PENDING": "FFEB9C", "CROSSCHECKED_CONSISTENT": "C6EFCE", "CROSSCHECKED_MIXED": "FFD966",
    "CROSSCHECKED_CONFLICTING": "FFC7CE",
    "COMPARABLE": "C6EFCE", "PARTIAL": "FFEB9C", "UNKNOWN": "EDEDED", "NOT_COMPARABLE": "FFC7CE",
    "ERROR": "FFC7CE", "WARNING": "FFEB9C", "QUALIFIED_GAP": "DDEBF7", "INFO": "EDEDED",
}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return "; ".join(str(_fmt(x)) for x in v)
    return v


def _pct(x):
    return f"{x * 100:g}%"


def tables(ev: Evaluation) -> dict:
    """tab -> (headers, rows). Shared by XLSX and Google Sheets sync plan."""
    reg = ev.registry
    # --- Characteristic Evaluation
    h1 = (["Characteristic ID", "Characteristic", "CROSSCHECK state", "State basis", "Independent organizations",
           "Organizations", "Evidence items (counted / linked)", "Datasets"]
          + [f"Dim: {d}" for d in DIMENSIONS]
          + ["Provisional outcome (not applied)", "Common conditions", "Max spread at common conditions",
             "Recorded flag / assessment (unchanged)", "Open comparability questions"])
    r1 = []
    for c in ev.characteristics:
        ind = c.independence
        counted = sum(len(v) for v in ind.groups.values()) if ind else 0
        out = c.outcome
        r1.append([
            c.id, c.name, c.state, c.state_reason, ind.n if ind else 0,
            [reg.name(o) for o in ind.counted] if ind else [],
            f"{counted} / {len(c.items)}", sorted({r.item.dataset for r in c.items}),
            *[c.dims[d].status if c.dims else "UNKNOWN" for d in DIMENSIONS],
            (f"{out.result}: {out.reason}" if out else ""),
            [_pct(x) if isinstance(x, float) else x for x in out.common_points] if out else [],
            max((p.spread_all for p in out.points), default=None) if out else None,
            f"{c.recorded_flag or '-'} / {c.recorded_assessment or '-'}",
            "\n".join(c.open_questions),
        ])
    # --- Evidence Map: one row per evidence item x common condition (or one row if no series)
    h2 = ["Characteristic ID", "Evidence ID", "Dataset", "Organization", "Counted", "Exclusion / dedup note",
          "Variant", "Campaign", "Condition", "Baseline value", "Value", "Relative change vs baseline",
          "Reported change (source)", "Relative change, alt. denominator", "Point classification",
          "Point spread (all series)", "Gap between organizations", "Cited cells"]
    r2 = []
    for c in ev.characteristics:
        ind = c.independence
        counted_ids = {i for ids in ind.groups.values() for i in ids} if ind else set()
        pts = {p.x: p for p in (c.outcome.points if c.outcome else [])}
        for r in c.items:
            it = r.item
            note = ind.excluded.get(it.id, "") if ind else ""
            org = reg.resolve(it.organization)
            if note == "" and org and ind and len(ind.groups.get(org, [])) > 1:
                note = f"same organization as {', '.join(i for i in ind.groups[org] if i != it.id)}; counted once"
            base = [c.id, it.id, it.dataset, reg.name(org) if org else (it.organization or "not identified"),
                    "YES" if it.id in counted_ids else "NO", note, it.variant, it.campaign]
            if not r.x:
                r2.append(base + [""] * 9 + ["; ".join(sorted(set(r.cited_cells)))])
                continue
            for x, v in zip(r.x, r.values):
                p = pts.get(x)
                r2.append(base + [
                    _pct(x) if isinstance(x, float) else x, r.baseline, v, r.rel_change.get(x),
                    r.reported_change.get(x), r.alt_rel_change.get(x),
                    p.classification if p else "not common",
                    p.spread_all if p else None, p.gap_between_orgs if p else None,
                    "; ".join(sorted(set(r.cited_cells))),
                ])
    # --- Dataset Sources
    used = {}
    for c in ev.characteristics:
        for r in c.items:
            used.setdefault(r.item.dataset, []).append(r.item.id)
    h3 = ["Dataset ID", "Sheet", "Organization (resolved)", "Contributor as recorded", "Status (unchanged)",
          "Historical agreed", "Derived / summary", "Supplementary", "Source TDoc(s)", "Mandatory fields missing",
          "Used by evidence", "Workbook SHA-256"]
    r3 = []
    for d in ev.stage1.datasets:
        org = reg.resolve(d.contributor)
        hist = d.status == "STABLE" and not s1config.is_missing(d.prior_agreement)
        r3.append([d.dataset_id, d.resolved_sheet or d.parent_sheet_ref, reg.name(org) if org else "",
                   d.contributor, d.status, "YES" if hist else "NO", "YES" if d.derived else "NO",
                   "YES" if d.supplementary else "NO", d.tdocs, len(d.missing_mandatory),
                   sorted(used.get(d.dataset_id, [])), ev.source_hashes["annotated"]])
    # --- Validation Issues
    h4 = ["Severity", "Category", "Subject", "Message", "Action"]
    r4 = [[i.severity, i.category, i.subject, i.message, i.action] for i in ev.issues]
    return {TABS[0]: (h1, r1), TABS[1]: (h2, r2), TABS[2]: (h3, r3), TABS[3]: (h4, r4)}


def _normalize_zip(path: Path) -> None:
    """Rewrite the XLSX zip with fixed timestamps so output is byte-deterministic."""
    data = Path(path).read_bytes()
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            payload = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl stamps the save time into dcterms:modified/created
                payload = re.sub(rb"(<dcterms:(?:modified|created)[^>]*>)[^<]*(</dcterms:)",
                                 rb"\g<1>2000-01-01T00:00:00Z\g<2>", payload)
            dst.writestr(zi, payload)
    Path(path).write_bytes(buf.getvalue())


def write_xlsx(ev: Evaluation, path: Path) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "traffic-annotation"
    wb.properties.created = wb.properties.modified = _FIXED_TIME
    for tab, (headers, rows) in tables(ev).items():
        ws = wb.create_sheet(tab)
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for row in rows:
            ws.append([_fmt(v) for v in row])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if isinstance(cell.value, str) and cell.value in _STATE_FILL:
                    cell.fill = PatternFill("solid", fgColor=_STATE_FILL[cell.value])
        for i, h in enumerate(headers, 1):
            w = 60 if h in ("Open comparability questions", "Message", "State basis", "Cited cells") else \
                min(max(len(h) + 2, 12), 30)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = ws.dimensions
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    _normalize_zip(path)
    return path


# ---------------------------------------------------------------------------
def normalized(ev: Evaluation) -> dict:
    reg = ev.registry
    orgs = [{"id": o.id, "name": o.name, "aliases": sorted(o.aliases)} for o in sorted(reg.orgs.values(), key=lambda o: o.id)]
    datasets = []
    for d in ev.stage1.datasets:
        org = reg.resolve(d.contributor)
        datasets.append({
            "id": d.dataset_id, "sheet": d.resolved_sheet, "organization": org, "status": d.status,
            "historical": d.status == "STABLE" and not s1config.is_missing(d.prior_agreement),
            "derived": d.derived, "supplementary": d.supplementary,
            "missing_mandatory": sorted(d.missing_mandatory),
        })
    chars, rels = [], []
    for c in ev.characteristics:
        ind = c.independence
        chars.append({
            "id": c.id, "name": c.name, "state": c.state, "state_basis": c.state_reason,
            "independent_organizations": ind.counted if ind else [],
            "dimensions": {d: {"status": c.dims[d].status, "method": c.dims[d].method} for d in DIMENSIONS} if c.dims else {},
            "provisional_outcome": c.outcome.result if c.outcome else None,
            "dedup": ind.collapsed if ind else [],
            "open_questions": c.open_questions,
        })
        counted_ids = {i for ids in ind.groups.values() for i in ids} if ind else set()
        for r in c.items:
            rels.append({
                "evidence": r.item.id, "characteristic": c.id, "dataset": r.item.dataset,
                "organization": reg.resolve(r.item.organization), "counted": r.item.id in counted_ids,
                "excluded_reason": ind.excluded.get(r.item.id) if ind else None,
                "variant": r.item.variant, "campaign": r.item.campaign,
                "relative_change": {f"{x:g}": round(v, 6) for x, v in sorted(r.rel_change.items())},
                "cited_cells": sorted(set(r.cited_cells)),
            })
    return {"organizations": orgs, "datasets": datasets, "characteristics": chars, "evidence": rels}


def write_json(ev: Evaluation, out_dir: Path) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = normalized(ev)
    paths = []
    for key in ("organizations", "datasets", "characteristics", "evidence"):
        p = out_dir / f"{key}.json"
        p.write_text(json.dumps({"schema": f"traffic-annotation/{key}@1", key: data[key]},
                                indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(p)
    p = out_dir / "validation_issues.json"
    p.write_text(json.dumps([i.__dict__ for i in ev.issues], indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    paths.append(p)
    p = out_dir / "manifest.json"
    p.write_text(json.dumps({"inputs_sha256": ev.source_hashes, "rules": ev.rules},
                            indent=1, sort_keys=True) + "\n", encoding="utf-8")
    paths.append(p)
    return paths


def write_markdown(ev: Evaluation, path: Path) -> Path:
    from collections import Counter

    cnt = Counter(c.state for c in ev.characteristics)
    sev = Counter(i.severity for i in ev.issues)
    L = ["# Characteristic-level CROSSCHECK evaluation", "",
         f"Inputs (SHA-256): original `{ev.source_hashes['original']}`, annotated `{ev.source_hashes['annotated']}`", "",
         "## States", "", "| State | Count |", "|---|---|"]
    from .model import STATES
    L += [f"| {s} | {cnt.get(s, 0)} |" for s in STATES]
    L += ["", "## Characteristics", "",
          "| ID | Characteristic | State | Basis | Provisional outcome |", "|---|---|---|---|---|"]
    for c in ev.characteristics:
        L.append(f"| {c.id} | {c.name} | {c.state} | {c.state_reason} | "
                 f"{(c.outcome.result + ': ' + c.outcome.reason) if c.outcome else '-'} |")
    for c in ev.characteristics:
        if not c.items:
            continue
        L += ["", f"## {c.id} detail", "", "| Dimension | Status | Method | Rationale |", "|---|---|---|---|"]
        for d in DIMENSIONS:
            r = c.dims[d]
            L.append(f"| {d} | {r.status} | {r.method} | {r.rationale.replace('|', '/')} |")
        if c.outcome and c.outcome.points:
            orgs = sorted(c.outcome.points[0].org_ranges)
            L += ["", "| Condition | " + " | ".join(ev.registry.name(o) + " range" for o in orgs)
                  + " | Spread (all series) | Gap between orgs | Classification |",
                  "|---" * (len(orgs) + 4) + "|"]
            for p in c.outcome.points:
                rngs = " | ".join(f"{p.org_ranges[o][0]:+.3f} … {p.org_ranges[o][1]:+.3f}" for o in orgs)
                L.append(f"| {_pct(p.x) if isinstance(p.x, float) else p.x} | {rngs} | {p.spread_all:.3f} | "
                         f"{p.gap_between_orgs:.3f} | {p.classification} |")
        if c.independence and c.independence.collapsed:
            L += ["", "Deduplication: " + "; ".join(c.independence.collapsed)]
        if c.open_questions:
            L += ["", "Open comparability questions:", ""] + [f"- {q}" for q in c.open_questions]
    L += ["", "## Validation issues", "", " · ".join(f"{k}: {sev.get(k, 0)}" for k in
                                                     ("ERROR", "WARNING", "QUALIFIED_GAP", "INFO")), "",
          "| Severity | Category | Subject | Message |", "|---|---|---|---|"]
    L += [f"| {i.severity} | {i.category} | {i.subject} | {i.message.replace('|', '/')} |" for i in ev.issues]
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")
    return Path(path)
