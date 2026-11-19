import openpyxl
import pytest

from traffic_annotation import contribution, crosscheck, report, safety
from traffic_annotation.cli import main

from conftest import SENTINEL, _cat_row, build_annotated, build_contribution, default_catalogue


def _run(workdir, **kw):
    tmp, orig = workdir
    ann = tmp / "ann.xlsx"
    build_annotated(orig, ann, **kw)
    doc = tmp / "c.docx"
    build_contribution(doc)
    return crosscheck.run(orig, ann, contribution.load(doc))


def _find(res, check, decision=None, subject=None):
    return [f for f in res.findings if f.check_id == check
            and (decision is None or f.decision == decision)
            and (subject is None or f.subject == subject)]


def test_clean_fixture_has_no_failures_and_counts_match(workdir):
    res = _run(workdir)
    assert res.by_decision("FAIL") == [], [f.as_dict() for f in res.by_decision("FAIL")]
    counts = {m: (claimed, parsed, raw, d) for m, claimed, parsed, raw, d in res.counts}
    assert counts["catalogue_rows"] == (5, 5, 5, "PASS")
    assert counts["stable_records"][:2] == (4, 4)
    assert counts["submitted_records"][:2] == (1, 1)
    assert counts["derived_records"][:2] == (1, 1)
    assert counts["additional_fields"][:2] == (14, 14)
    assert counts["evidence_rows"][:3] == (2, 2, 2)


def test_sheet_mapping_and_supplementary(workdir):
    res = _run(workdir)
    by = {d.dataset_id: d for d in res.datasets}
    assert by["DS-002"].resolved_sheet == "2.5 Chat  Streaming"
    assert by["DS-002"].resolve_method == "normalized"
    assert by["DS-SUP-001"].supplementary and by["DS-SUP-001"].register_status == "SUBMITTED"
    assert by["DS-003"].index_status == "STABLE"
    assert _find(res, "C08", "PASS", "3.2 Chat - Provider X")  # split into 2 records


def test_measurement_change_is_detected(workdir):
    def mutate(wb):
        wb["2.5 Chat  Streaming"]["B2"] = SENTINEL + 1
    res = _run(workdir, mutate=mutate)
    f = _find(res, "C02", "FAIL", "2.5 Chat  Streaming")
    assert f and "B2" in f[0].observed and str(SENTINEL) not in f[0].observed


def test_float_noise_is_accepted(workdir):
    def mutate(wb):
        wb["2.5 Chat  Streaming"]["B2"] = SENTINEL * (1 + 1e-16)
    res = _run(workdir, mutate=mutate)
    assert not _find(res, "C02", "FAIL")


def test_index_appended_notes_accepted_but_edits_reviewed(workdir):
    def mutate(wb):
        ws = wb["0. Index"]
        ws.cell(ws.max_row + 2, 1).value = "Status assignment note"
    res = _run(workdir, mutate=mutate)
    assert _find(res, "C03", "PASS", "0. Index") and _find(res, "C03", "ACCEPT", "0. Index")

    res = _run(workdir, mutate=lambda wb: wb["0. Index"].cell(4, 2, "edited content"))
    f = _find(res, "C03", "REVIEW", "0. Index")
    assert f and "B4" in f[0].action


def test_removed_sheet_fails(workdir):
    res = _run(workdir, mutate=lambda wb: wb.remove(wb["2.1 Scenarios"]))
    assert _find(res, "C01", "FAIL")


def test_cross_checked_yes_requires_verifying_contribution(workdir):
    cat = default_catalogue()
    cat[1] = _cat_row("DS-002", "Org A", "2.5 Chat Streaming", "Chat streaming", xcheck="YES")
    res = _run(workdir, catalogue=cat)
    assert _find(res, "C11", "FAIL", "DS-002")
    cat[1] = _cat_row("DS-002", "Org A", "2.5 Chat Streaming", "Chat streaming", xcheck="YES (S4-261234)")
    res = _run(workdir, catalogue=cat)
    assert _find(res, "C11", "PASS", "DS-002")


def test_candidate_requires_complete_mandatory_metadata(workdir):
    cat = default_catalogue()
    cat[2] = _cat_row("DS-003", "Org B", "3.2 Chat - Provider X", "Chat", status="CANDIDATE",
                      **{"Model name": "Not identified in workbook"})
    res = _run(workdir, catalogue=cat)
    assert _find(res, "C10", "FAIL", "DS-003")


def test_stable_without_agreement_evidence_fails(workdir):
    cat = default_catalogue()
    cat[1] = _cat_row("DS-002", "Org A", "2.5 Chat Streaming", "Chat", prior="Not recorded")
    res = _run(workdir, catalogue=cat)
    assert _find(res, "C10", "FAIL", "DS-002")


def test_placeholder_not_listed_as_missing_is_grouped(workdir):
    cat = default_catalogue()
    for i, ds in ((1, "DS-002"), (2, "DS-003")):
        cat[i] = _cat_row(ds, "Not identified in workbook", "2.5 Chat Streaming", "Chat", stated=[])
    res = _run(workdir, catalogue=cat)
    f = _find(res, "C09", "REVIEW")
    assert len(f) == 1 and "Contributor" in f[0].observed and "DS-002" in f[0].observed and "DS-003" in f[0].observed


def test_evidence_flag_and_source_count_mismatch(workdir):
    ev = [["CH-001", "Latency", "Chat", "UL", "Org A", 2, 1, "DS-002", "x", "MULTI-SOURCE", "PROVISIONAL",
           "", "", ""]]
    res = _run(workdir, evidence=ev)
    rules = {f.rule for f in _find(res, "C14", "FAIL", "CH-001")}
    assert "Evidence flag follows independent-source count" in rules
    assert "Number of independent sources = distinct organizations listed" in rules


def test_derived_dataset_cannot_count_as_evidence(workdir):
    ev = [["CH-001", "Latency", "Chat", "UL", "Org A", 1, 1, "DS-001", "x", "SINGLE-SOURCE", "PROVISIONAL",
           "", "", ""]]
    res = _run(workdir, evidence=ev)
    assert any("Derived" in f.rule for f in _find(res, "C14", "FAIL", "CH-001"))


def test_sheet_reference_in_evidence_gets_proposed_ids(workdir):
    ev = [["CH-001", "Latency", "Chat", "UL", "Org B", 1, 2, "rows for 3.2", "x", "SINGLE-SOURCE",
           "PROVISIONAL", "", "", ""]]
    res = _run(workdir, evidence=ev)
    f = _find(res, "C14", "REVIEW", "CH-001")
    assert any("DS-003, DS-004" in x.action for x in f)


def test_status_mismatch_between_catalogue_and_register(workdir):
    def mutate(wb):
        wb["Dataset Status Register"]["E3"] = "SUBMITTED"
    res = _run(workdir, mutate=mutate)
    assert _find(res, "C12", "FAIL", "DS-002")


def test_claim_mismatch_fails(workdir):
    tmp, orig = workdir
    ann = tmp / "ann.xlsx"
    build_annotated(orig, ann)
    doc = tmp / "c.docx"
    build_contribution(doc, catalogue_rows=6)
    res = crosscheck.run(orig, ann, contribution.load(doc))
    assert _find(res, "C05", "FAIL", "catalogue_rows")


def test_outputs_written_without_measurement_values(workdir):
    tmp, _ = workdir
    res = _run(workdir)
    x = report.write_review_xlsx(res, tmp / "out" / "r.xlsx")
    m = report.write_markdown(res, tmp / "out" / "r.md")
    j = report.write_json(res, tmp / "out" / "r.json")
    wb = openpyxl.load_workbook(x)
    assert {"Summary", "Sheet Count Comparison", "Claimed vs Extracted", "Dataset Mapping",
            "B.4.4 Completeness", "Characteristic Check", "Crosscheck Decisions",
            "Open Ambiguities"} <= set(wb.sheetnames)
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            assert SENTINEL not in row
    assert str(SENTINEL) not in m.read_text(encoding="utf-8")
    assert str(SENTINEL) not in j.read_text(encoding="utf-8")


def test_cli_end_to_end(workdir, capsys):
    tmp, orig = workdir
    ann = tmp / "ann.xlsx"
    build_annotated(orig, ann)
    doc = tmp / "c.docx"
    build_contribution(doc)
    rc = main(["--original", str(orig), "--annotated", str(ann), "--contribution", str(doc),
               "--out", str(tmp / "out")])
    assert rc == 0
    assert (tmp / "out" / "crosscheck_review.xlsx").is_file()
    assert "FAIL=0" in capsys.readouterr().out


def test_cli_refuses_output_inside_repo(workdir):
    tmp, orig = workdir
    with pytest.raises(ValueError):
        main(["--original", str(orig), "--annotated", str(orig), "--out", str(safety.REPO_ROOT / "out")])


def test_no_source_documents_are_tracked():
    assert safety.forbidden_tracked() == []
