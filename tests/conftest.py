"""Synthetic fixtures. No real measurement data or contribution text."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from traffic_annotation import config

SENTINEL = 123.456789  # measurement value that must never appear in outputs

CAT_HEADERS = list(config.MANDATORY_FIELDS) + list(config.RECOMMENDED_FIELDS) + [
    config.COL_PARENT, config.COL_VARIANT, config.COL_TDOCS, "First evidenced addition / revision",
    config.COL_PRIOR, "TR reporting location", config.COL_STATUS, config.COL_STATUS_BASIS, config.COL_XCHECK,
    config.COL_COMPLETENESS, config.COL_DERIVED, config.COL_RELATED, "Open action", "Notes",
]


def _cat_row(ds_id, contributor, parent, variant, status="STABLE", xcheck="NO / not demonstrated",
             derived="NO", prior="Agreed", provider="Provider X", name="model-x", stated=None, **extra):
    vals = {
        "Dataset ID": ds_id, "Contributor": contributor, "Creation date": "2026-01-01", "Scenario ID": "2.5",
        "Scenario version": "1", "Network profile ID(s)": "NP-1", "Application category": variant,
        "Traffic direction": "UL+DL", "Model provider": provider, "Model name": name,
        "Execution date": "2026-01-02", "Number of runs": 3,
        config.COL_PARENT: parent, config.COL_VARIANT: variant, config.COL_TDOCS: "TD-0001",
        config.COL_PRIOR: prior, config.COL_STATUS: status, config.COL_STATUS_BASIS: "basis",
        config.COL_XCHECK: xcheck, config.COL_DERIVED: derived,
    }
    vals.update(extra)
    missing = [f for f in config.MANDATORY_FIELDS if config.is_missing(vals.get(f))]
    if stated is None:
        stated = missing
    vals[config.COL_COMPLETENESS] = ("INCOMPLETE: " + ", ".join(stated)) if stated else "COMPLETE"
    return [vals.get(h) for h in CAT_HEADERS]


def build_original(path: Path):
    wb = openpyxl.Workbook()
    ix = wb.active
    ix.title = config.INDEX_SHEET
    ix.append(["Synthetic results workbook"])
    ix.append(["Version 1.2.3 test"])
    ix.append(["Sheet", "Content", "Scenario", "Execution", "Results reported in", "Status"])
    ix.append(["2.1 Scenarios", "defs", "all", "Local", "Annex X", "Agreed"])
    ix.append(["2.5 Chat Streaming", "chat", "Chat", "Local", "Annex X", "Agreed"])
    ix.append(["3.2 Chat - Provider X", "chat", "Chat", "Remote", "Annex X", "Added at MTG-1"])
    s = wb.create_sheet("2.1 Scenarios")
    s.append(["Scenario", "Profile"])
    s.append(["chat", "NP-1"])
    s = wb.create_sheet("2.5 Chat  Streaming")  # double space on purpose
    s.append(["Metric", "Value"])
    s.append(["UL bytes", SENTINEL])
    s.append(["DL bytes", 2048.5])
    s = wb.create_sheet("3.2 Chat - Provider X")
    s.append(["Metric", "Provider X", "Provider Y"])
    s.append(["RTT", 10.0, 12.0])
    wb.save(path)


def build_annotated(orig: Path, path: Path, catalogue=None, evidence=None, mutate=None):
    wb = openpyxl.load_workbook(orig)
    ix = wb[config.INDEX_SHEET]
    for r in range(4, ix.max_row + 1):
        ix.cell(r, 6).value = "STABLE"
    cat = wb.create_sheet(config.CATALOGUE_SHEET)
    cat.append(CAT_HEADERS)
    for row in catalogue if catalogue is not None else default_catalogue():
        cat.append(row)
    ev = wb.create_sheet(config.EVIDENCE_SHEET)
    ev.append(["Characteristic ID", "Characteristic / metric", "Application category", "Traffic direction",
               "Contributing organization(s)", "Number of independent sources", "Number of datasets",
               "Dataset ID(s)", "Observed spread / range", "Evidence flag", "Assessment status",
               "Basis / method", "Open action", "Notes"])
    for row in evidence if evidence is not None else default_evidence():
        ev.append(row)
    pv = wb.create_sheet(config.PROVENANCE_SHEET)
    pv.append(["Event ID", "Dataset / scope", "Event type", "Meeting / revision", "Date", "Source / evidence",
               "Change recorded", "Status consequence", "Confidence", "Follow-up"])
    pv.append(["EV-001", "2.5 Chat Streaming", "Addition", "MTG-1", "2026-01-03", "TD-0001", "added",
               "STABLE", "High", ""])
    sd = wb.create_sheet(config.STATUS_DEFS_SHEET)
    sd.append(["Item", "Definition / decision rule", "Application", "Required evidence / next transition"])
    sd.append(["STABLE", "def", "app", "ev"])
    rg = wb.create_sheet(config.REGISTER_SHEET)
    rg.append(["Dataset / sheet", "Scenario / content", "Execution", "Prior agreement evidence",
               "Assigned status", "CROSS_CHECKED"])
    rg.append(["2.1 Scenarios", "defs", "Local", "Agreed", "STABLE", "NO"])
    rg.append(["2.5 Chat Streaming", "chat", "Local", "Agreed", "STABLE", "NO"])
    rg.append(["3.2 Chat - Provider X", "chat", "Remote", "Agreed", "STABLE", "NO"])
    rg.append(["2.5 alternative test site", "alt", "Local", "none", "SUBMITTED", "NO"])
    if mutate:
        mutate(wb)
    wb.save(path)


def default_catalogue():
    return [
        _cat_row("DS-001", "Org A", "2.1 Scenarios", "Scenario definitions", derived="YES"),
        _cat_row("DS-002", "Org A", "2.5 Chat Streaming", "Chat streaming"),
        _cat_row("DS-003", "Org B", "3.2 Chat - Provider X", "Chat - Provider X"),
        _cat_row("DS-004", "Org B", "3.2 Chat - Provider X", "Chat - Provider Y", provider="Provider Y"),
        _cat_row("DS-SUP-001", "Org C", "2.5 Chat  Streaming", "Alternative test site", status="SUBMITTED",
                 prior="none found"),
    ]


def default_evidence():
    return [
        ["CH-001", "Latency", "Chat", "UL+DL", "Org A; Org B", 2, 2, "DS-002; DS-003", "10-12 ms",
         "MULTI-SOURCE", "PROVISIONAL", "", "", ""],
        ["CH-002", "Token cadence", "Chat / LLM", "DL", "", 0, 0, "", "", "UNASSESSED", "OPEN", "", "", ""],
    ]


def build_contribution(path: Path, catalogue_rows=5, stable=4, submitted=1, derived=1):
    import docx

    d = docx.Document()
    d.add_paragraph("Synthetic meeting\tTD-0099")
    d.add_paragraph("Source:\tTest Org")
    d.add_paragraph("Title:\tSynthetic annotation")
    d.add_paragraph(f"Added a {catalogue_rows}-row Dataset Catalogue containing the fields and "
                    f"14 additional provenance and governance fields.")
    d.add_paragraph(f"Assigned STABLE to {stable} records and SUBMITTED to {submitted} record.")
    d.add_paragraph(f"Identified {derived} overview record as derived/summary data.")
    d.add_paragraph("Added a two-row Characteristic Evidence register, with one provisional MULTI-SOURCE "
                    "assessment and one open assessments.")
    d.add_paragraph("Added a one-row Provenance History. Added a one-row Status Definitions sheet.")
    d.save(path)


@pytest.fixture
def workdir(tmp_path):
    orig = tmp_path / "orig.xlsx"
    build_original(orig)
    return tmp_path, orig
