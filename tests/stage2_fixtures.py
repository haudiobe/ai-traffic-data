"""Synthetic Stage 2 fixtures: loss-sweep sheets, catalogue and evidence specs.

All organizations, numbers and texts are invented.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import openpyxl

from traffic_annotation import config
from conftest import CAT_HEADERS, _cat_row

LABELS = ["lossy 5%", "lossy 10%", "lossy 20%", "lossy 30%"]


def loss_sheet(wb, name, base, values, direction="UL", conclusion="degradation increases with loss",
               labels=LABELS, reported=None, n=100, extra_rows=()):
    ws = wb.create_sheet(name)
    ws["A1"] = f"{name} Synthetic loss sweep"
    ws["A2"] = f"Loss model: uncorrelated {direction} packet loss, no added delay"
    ws["A3"] = "Definition: change = (count - baseline) / baseline, reported as fraction"
    ws["A4"] = f"Sample: {n} questions per profile, 3 runs, mean reported"
    ws["A5"] = f"Conclusion: {conclusion}"
    ws.append([])
    ws.append(["Metric", "no_emul", *labels])  # row 7
    ws.append(["Correct", base, *values])  # row 8
    ws.append(["Reported change", "-", *(reported or [round((v - base) / base, 3) for v in values])])  # row 9
    for row in extra_rows:  # rows 10+
        ws.append(list(row))
    return ws


SHEETS = {
    "4.1 Loss A": dict(base=100, values=[100, 97, 90, 80]),
    "4.2 Loss B": dict(base=200, values=[200, 195, 182, 160]),
    "4.3 Loss A2": dict(base=50, values=[50, 49, 45, 40]),
    "4.9 Overview": dict(base=1, values=[1, 1, 1, 1]),
}


def build_workbooks(tmp: Path, sheets=None, catalogue=None, evidence_rows=None):
    sheets = sheets or copy.deepcopy(SHEETS)
    orig = openpyxl.Workbook()
    ix = orig.active
    ix.title = config.INDEX_SHEET
    ix.append(["Synthetic index"])
    for name, kw in sheets.items():
        loss_sheet(orig, name, **kw)
    op = tmp / "orig.xlsx"
    orig.save(op)

    ann = openpyxl.load_workbook(op)
    cat = ann.create_sheet(config.CATALOGUE_SHEET)
    cat.append(CAT_HEADERS)
    rows = catalogue or [
        _cat_row("DS-101", "Org A", "4.1 Loss A", "Loss sweep A"),
        _cat_row("DS-102", "Org B", "4.2 Loss B", "Loss sweep B"),
        _cat_row("DS-103", "Org A", "4.3 Loss A2", "Loss sweep A, second campaign", provider="Provider Y"),
        _cat_row("DS-109", "Not identified in workbook", "4.9 Overview", "Overview", derived="YES",
                 stated=["Contributor"]),
        _cat_row("DS-110", "Org C", "4.9 Overview", "Supplementary result, alternative site",
                 status="SUBMITTED", prior="none"),
    ]
    for r in rows:
        cat.append(r)
    ev = ann.create_sheet(config.EVIDENCE_SHEET)
    ev.append(["Characteristic ID", "Characteristic / metric", "Application category", "Traffic direction",
               "Contributing organization(s)", "Number of independent sources", "Number of datasets",
               "Dataset ID(s)", "Observed spread / range", "Evidence flag", "Assessment status",
               "Basis / method", "Open action", "Notes"])
    for r in evidence_rows or [
        ["CH-001", "Loss tolerance", "Synthetic", "UL", "Org A; Org B", 2, 2, "DS-101; DS-102", "",
         "MULTI-SOURCE", "PROVISIONAL", "", "", ""],
        ["CH-002", "Other metric", "Synthetic", "DL", "", 0, 0, "", "", "UNASSESSED", "OPEN", "", "", ""],
    ]:
        ev.append(r)
    for title, hdr in ((config.PROVENANCE_SHEET, ["Event ID", "Dataset / scope", "Date", "Confidence"]),
                       (config.STATUS_DEFS_SHEET, ["Item", "Definition / decision rule"]),
                       (config.REGISTER_SHEET, ["Dataset / sheet", "Assigned status"])):
        ann.create_sheet(title).append(hdr)
    ap = tmp / "ann.xlsx"
    ann.save(ap)
    return op, ap


def _q(sheet, cell, quote):
    return {"sheet": sheet, "cell": cell, "quote": quote}


def item(eid, dataset, org, sheet, direction="UL", conclusion="degradation increases with loss",
         variant="", campaign="", provider="", n=100, char="CH-001", drop=(), override=None):
    dims = {
        "definition": {"value": "relative change vs baseline", "source": _q(sheet, "A3", "change = (count - baseline) / baseline")},
        "units": {"value": "fraction", "source": _q(sheet, "A3", "reported as fraction")},
        "direction": {"value": direction, "source": _q(sheet, "A2", f"uncorrelated {direction} packet loss")},
        "scenario": {"value": "synthetic loss sweep", "source": _q(sheet, "A1", "Synthetic loss sweep")},
        "measurement_layer": {"value": "task metric under packet loss", "source": _q(sheet, "A3", "Definition")},
        "baseline": {"value": "no_emul", "source": _q(sheet, "B7", "no_emul")},
        "network_conditions": {"value": "uncorrelated loss, no added delay", "source": _q(sheet, "A2", "no added delay")},
        "statistical_basis": {"value": "3 runs, mean", "source": _q(sheet, "A4", "3 runs, mean reported")},
        "qualitative_conclusion": {"value": conclusion, "source": _q(sheet, "A5", conclusion)},
    }
    for d in drop:
        dims[d] = {"value": None, "note": "not stated"}
    for d, v in (override or {}).items():
        dims[d] = v
    return {
        "id": eid, "characteristic": char, "dataset": dataset, "organization": org, "variant": variant,
        "campaign": campaign, "provider": provider,
        "series": {"sheet": sheet, "x_cells": "C7:F7", "baseline_cell": "B8", "value_cells": "C8:F8",
                   "denominator": {"value": n, "source": _q(sheet, "A4", f"{n} questions per profile")},
                   "reported_change_cells": "C9:F9"},
        "dimensions": dims,
        "facets": {"sample_size": {"value": f"{n} questions", "source": _q(sheet, "A4", f"{n} questions")}},
    }


def spec(items, assessments=None, questions=None):
    return {
        "schema": "traffic-annotation/evidence-spec@1",
        "organizations": [{"id": "ORG-A", "name": "Org A", "aliases": ["Organisation A"]},
                          {"id": "ORG-B", "name": "Org B"}, {"id": "ORG-C", "name": "Org C"}],
        "characteristics": [{"id": "CH-001", "name": "Loss tolerance"}],
        "evidence": items,
        "assessments": assessments or {},
        "questions": questions or {},
    }


def two_org_items(**kw_b):
    return [item("E-A", "DS-101", "Org A", "4.1 Loss A"),
            item("E-B", "DS-102", "Org B", "4.2 Loss B", **kw_b)]


def write_spec(tmp: Path, data: dict) -> Path:
    p = tmp / "spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p
