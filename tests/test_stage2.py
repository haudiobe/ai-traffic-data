import copy
import json
import subprocess

import openpyxl
import pytest

from traffic_annotation import safety, workbook as wbm
from traffic_annotation.characteristics import comparability, gsheets, outcome, review
from traffic_annotation.characteristics.cli import main as cli
from traffic_annotation.characteristics.evaluate import run
from traffic_annotation.characteristics.model import STATES, load_rules
from traffic_annotation.characteristics.spec import parse_spec, parse_condition

from stage2_fixtures import SHEETS, build_workbooks, item, spec, two_org_items, write_spec


def _eval(tmp_path, items, sheets=None, rules=None, assessments=None, **kw):
    o, a = build_workbooks(tmp_path, sheets=sheets, **kw)
    return run(o, a, parse_spec(spec(items, assessments)), rules)


def _ch(ev, cid="CH-001"):
    return next(c for c in ev.characteristics if c.id == cid)


def _sheets(**changes):
    s = copy.deepcopy(SHEETS)
    for name, kw in changes.items():
        s[name].update(kw)
    return s


# --------------------------------------------------------------------------- states
def test_consistent(tmp_path):
    ev = _eval(tmp_path, two_org_items())
    c = _ch(ev)
    assert c.state == "CROSSCHECKED_CONSISTENT", c.state_reason
    assert c.outcome.result == "CONSISTENT" and len(c.outcome.common_points) == 4
    assert not [i for i in ev.issues if i.severity == "ERROR"]


def test_mixed_magnitude(tmp_path):
    ev = _eval(tmp_path, two_org_items(), sheets=_sheets(**{"4.2 Loss B": dict(values=[200, 195, 182, 120])}))
    c = _ch(ev)
    assert c.state == "CROSSCHECKED_MIXED"
    p30 = c.outcome.points[-1]
    assert p30.classification == "MIXED" and p30.gap_between_orgs == pytest.approx(0.2)


def test_conflicting_direction(tmp_path):
    ev = _eval(tmp_path, two_org_items(), sheets=_sheets(**{"4.2 Loss B": dict(values=[200, 215, 230, 250])}))
    c = _ch(ev)
    assert c.state == "CROSSCHECKED_CONFLICTING"
    # 10%: Org A -3% is inside the dead band -> MIXED; 20% and 30% are OPPOSITE (2/4 >= share 0.5)
    assert [p.classification for p in c.outcome.points] == ["CONSISTENT", "MIXED", "OPPOSITE", "OPPOSITE"]


def test_conflicting_qualitative_conclusion(tmp_path):
    sheets = _sheets(**{"4.2 Loss B": dict(conclusion="no effect of loss")})
    ev = _eval(tmp_path, two_org_items(conclusion="no effect of loss"), sheets=sheets)
    c = _ch(ev)
    assert c.dims["qualitative_conclusion"].disagreement
    assert c.state == "CROSSCHECKED_CONFLICTING"


def test_single_source_after_dedup_of_campaigns_and_providers(tmp_path):
    items = [item("E-A", "DS-101", "Org A", "4.1 Loss A", campaign="C1", provider="P1"),
             item("E-A2", "DS-103", "Organisation A", "4.3 Loss A2", campaign="C2", provider="P2")]
    c = _ch(_eval(tmp_path, items))
    assert c.state == "SINGLE_SOURCE" and c.independence.n == 1
    assert "2 datasets" in c.independence.collapsed[0] and "2 campaigns" in c.independence.collapsed[0]
    assert "2 providers" in c.independence.collapsed[0]


def test_repeated_runs_and_model_variants_count_once(tmp_path):
    items = [item("E-A1", "DS-101", "Org A", "4.1 Loss A", variant="m1", ),
             item("E-A2", "DS-101", "Org A", "4.1 Loss A", variant="m2"),
             item("E-B", "DS-102", "Org B", "4.2 Loss B")]
    items[1]["run_group"] = "run-2"
    c = _ch(_eval(tmp_path, items))
    assert c.independence.n == 2 and c.state == "CROSSCHECKED_CONSISTENT"


def test_not_assessed_without_evidence_and_with_unattributed_org(tmp_path):
    ev = _eval(tmp_path, [item("E-X", "DS-101", None, "4.1 Loss A")])
    assert _ch(ev).state == "NOT_ASSESSED"
    assert _ch(ev, "CH-002").state == "NOT_ASSESSED"
    assert any(i.category == "independence" and "not identified" in i.message for i in ev.issues)


def test_derived_dataset_not_counted(tmp_path):
    items = [item("E-A", "DS-101", "Org A", "4.1 Loss A"), item("E-D", "DS-109", "Org B", "4.9 Overview")]
    c = _ch(_eval(tmp_path, items))
    assert c.state == "SINGLE_SOURCE" and c.independence.excluded["E-D"] == "derived/summary dataset"


def test_not_comparable_direction(tmp_path):
    sheets = _sheets(**{"4.2 Loss B": dict(direction="DL")})
    c = _ch(_eval(tmp_path, two_org_items(direction="DL"), sheets=sheets))
    assert c.dims["direction"].status == "NOT_COMPARABLE"
    assert c.state == "MULTI_SOURCE_NOT_COMPARABLE"


def test_pending_when_dimension_unknown(tmp_path):
    c = _ch(_eval(tmp_path, two_org_items(drop=("statistical_basis",))))
    assert c.dims["statistical_basis"].status == "UNKNOWN"
    assert c.state == "CROSSCHECK_PENDING"
    assert c.outcome.result == "CONSISTENT"  # provisional, not applied
    assert any(q.startswith("[statistical_basis]") for q in c.open_questions)


def test_partial_assessment_pending_and_configurable(tmp_path):
    asm = {"CH-001": {"scenario": {"status": "PARTIAL", "rationale": "different task corpora"}}}
    c = _ch(_eval(tmp_path, two_org_items(), assessments=asm))
    assert c.state == "CROSSCHECK_PENDING" and c.dims["scenario"].method == "assessment"
    rules = load_rules()
    rules["dimension_status_effect"]["PARTIAL"] = "ok"
    c = _ch(_eval(tmp_path, two_org_items(), assessments=asm, rules=rules))
    assert c.state == "CROSSCHECKED_CONSISTENT"


def test_insufficient_overlap_is_pending(tmp_path):
    sheets = _sheets(**{"4.2 Loss B": dict(labels=["lossy 5%", "lossy 15%", "lossy 25%", "lossy 40%"])})
    c = _ch(_eval(tmp_path, two_org_items(), sheets=sheets))
    assert c.outcome.result == "INSUFFICIENT" and c.state == "CROSSCHECK_PENDING"


def test_min_organizations_configurable(tmp_path):
    rules = load_rules()
    rules["min_independent_organizations"] = 3
    c = _ch(_eval(tmp_path, two_org_items(), rules=rules))
    assert c.state == "SINGLE_SOURCE"


# --------------------------------------------------------------------------- no inference
def test_unverified_quote_is_error_and_unknown(tmp_path):
    bad = {"statistical_basis": {"value": "10 runs", "source": {"sheet": "4.2 Loss B", "cell": "A4", "quote": "10 runs"}}}
    ev = _eval(tmp_path, two_org_items(override=bad))
    c = _ch(ev)
    assert c.dims["statistical_basis"].status == "UNKNOWN" and c.state == "CROSSCHECK_PENDING"
    assert any(i.severity == "ERROR" and "quote not found" in i.message for i in ev.issues)


def test_uncited_claim_is_unknown(tmp_path):
    c = _ch(_eval(tmp_path, two_org_items(override={"units": {"value": "fraction"}})))
    assert c.dims["units"].status == "UNKNOWN"


def test_denominator_constant_must_occur_in_quote(tmp_path):
    items = two_org_items()
    items[1]["series"]["denominator"] = {"value": 999, "source": {"sheet": "4.2 Loss B", "cell": "A4",
                                                                  "quote": "questions per profile"}}
    ev = _eval(tmp_path, items)
    assert any("does not occur in the cited quote" in i.message for i in ev.issues)


def test_reported_change_mismatch_flags_definition(tmp_path):
    sheets = _sheets(**{"4.2 Loss B": dict(reported=[0.0, -0.5, -0.09, -0.2])})
    ev = _eval(tmp_path, two_org_items(), sheets=sheets)
    assert any(i.category == "definition" and i.severity == "WARNING" and i.subject == "E-B" for i in ev.issues)
    assert any(i.category == "definition" and i.severity == "INFO" and i.subject == "E-A" for i in ev.issues)


def test_non_numeric_series_is_error(tmp_path):
    items = two_org_items()
    items[0]["series"]["value_cells"] = "A1:D1"
    ev = _eval(tmp_path, items)
    assert any(i.severity == "ERROR" and i.category == "series" for i in ev.issues)
    assert _ch(ev).state == "SINGLE_SOURCE"


# --------------------------------------------------------------------------- historical gaps
def test_historical_gaps_are_aggregated_qualified_gaps(tmp_path):
    ev = _eval(tmp_path, two_org_items())
    gaps = [i for i in ev.issues if i.severity == "QUALIFIED_GAP"]
    subjects = [g.subject for g in gaps]
    assert len(subjects) == len(set(subjects))  # one per field, never per record
    assert all("results retained" in g.message for g in gaps)
    assert not any(i.severity == "ERROR" and i.category.endswith("metadata") for i in ev.issues)
    assert not any(i.severity == "WARNING" and i.category == "metadata" for i in ev.issues)


def test_recorded_flags_are_reported_not_changed(tmp_path):
    o, a = build_workbooks(tmp_path)
    h = wbm.sha256(a)
    ev = run(o, a, parse_spec(spec(two_org_items(drop=("statistical_basis",)))))
    assert wbm.sha256(a) == h
    assert any(i.category == "state" and "recorded values not changed" in i.message for i in ev.issues)
    assert _ch(ev).recorded_flag == "MULTI-SOURCE"


# --------------------------------------------------------------------------- outputs
def _cli(tmp_path, out, extra=(), build=True):
    if build:
        build_workbooks(tmp_path)
        write_spec(tmp_path, spec(two_org_items()))
    o, a, s = tmp_path / "orig.xlsx", tmp_path / "ann.xlsx", tmp_path / "spec.json"
    return cli(["--original", str(o), "--annotated", str(a), "--spec", str(s), "--out", str(out), *extra])


def test_cli_outputs_four_tabs_and_are_deterministic(tmp_path, capsys):
    assert _cli(tmp_path, tmp_path / "o1", ["--sheets-dry-run"]) == 0
    assert _cli(tmp_path, tmp_path / "o2", ["--sheets-dry-run"], build=False) == 0
    out = capsys.readouterr().out
    assert "inputs unchanged (SHA-256 verified)" in out and "[dry-run] create spreadsheet" in out
    wb = openpyxl.load_workbook(tmp_path / "o1" / "characteristic_crosscheck_review.xlsx")
    assert tuple(wb.sheetnames) == review.TABS
    files = sorted(p.relative_to(tmp_path / "o1") for p in (tmp_path / "o1").rglob("*") if p.is_file())
    assert len(files) == 9
    for f in files:
        assert (tmp_path / "o1" / f).read_bytes() == (tmp_path / "o2" / f).read_bytes(), f


def test_xlsx_has_no_wall_clock_timestamps(tmp_path):
    import zipfile
    _cli(tmp_path, tmp_path / "o")
    z = zipfile.ZipFile(tmp_path / "o" / "characteristic_crosscheck_review.xlsx")
    core = z.read("docProps/core.xml").decode()
    assert core.count("2000-01-01T00:00:00Z") == 2
    assert {i.date_time for i in z.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_normalized_json_is_compact_and_linked(tmp_path):
    _cli(tmp_path, tmp_path / "o")
    n = tmp_path / "o" / "normalized"
    ev = json.loads((n / "evidence.json").read_text(encoding="utf-8"))["evidence"]
    ch = json.loads((n / "characteristics.json").read_text(encoding="utf-8"))["characteristics"]
    ds = json.loads((n / "datasets.json").read_text(encoding="utf-8"))["datasets"]
    assert {e["dataset"] for e in ev} <= {d["id"] for d in ds}
    assert {e["characteristic"] for e in ev} <= {c["id"] for c in ch}
    assert next(c for c in ch if c["id"] == "CH-001")["state"] == "CROSSCHECKED_CONSISTENT"
    assert set(next(c for c in ch if c["id"] == "CH-001")["independent_organizations"]) == {"ORG-A", "ORG-B"}


def test_cli_refuses_paths_inside_repo(tmp_path):
    o, a = build_workbooks(tmp_path)
    s = write_spec(tmp_path, spec(two_org_items()))
    with pytest.raises(ValueError):
        cli(["--original", str(o), "--annotated", str(a), "--spec", str(s), "--out", str(safety.REPO_ROOT / "out")])


def test_cli_fail_on_error(tmp_path):
    o, a = build_workbooks(tmp_path)
    items = two_org_items()
    items[0]["series"]["value_cells"] = "A1:D1"
    s = write_spec(tmp_path, spec(items))
    assert cli(["--original", str(o), "--annotated", str(a), "--spec", str(s), "--out", str(tmp_path / "o")]) == 2


# --------------------------------------------------------------------------- units / config
def test_parse_condition():
    assert parse_condition("lossy 10%", "percent") == 0.1
    assert parse_condition("lossy 2.5 %", "percent") == 0.025
    assert parse_condition("no_emul", "percent") is None


def test_outcome_dead_band_and_tolerance():
    cfg = load_rules()["outcome"]
    res = outcome.evaluate({"A": {"a": {0.1: -0.04, 0.2: -0.2}}, "B": {"b": {0.1: 0.03, 0.2: -0.25}}}, cfg)
    assert res.result == "CONSISTENT"
    res = outcome.evaluate({"A": {"a": {0.1: -0.04}}, "B": {"b": {0.1: 0.03}}}, cfg)
    assert res.result == "INSUFFICIENT"


def test_states_vocabulary():
    assert STATES == ("NOT_ASSESSED", "SINGLE_SOURCE", "MULTI_SOURCE_NOT_COMPARABLE", "CROSSCHECK_PENDING",
                      "CROSSCHECKED_CONSISTENT", "CROSSCHECKED_MIXED", "CROSSCHECKED_CONFLICTING")


def test_rules_validation(tmp_path):
    p = tmp_path / "r.json"
    r = load_rules()
    r["required_dimensions"].append("colour")
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError):
        load_rules(p)


def test_spec_validation():
    with pytest.raises(ValueError):
        parse_spec({"schema": "wrong"})
    bad = spec([item("E", "DS-101", "Org A", "4.1 Loss A")])
    bad["evidence"][0]["dimensions"]["colour"] = "red"
    with pytest.raises(ValueError):
        parse_spec(bad)
    bad = spec([], assessments={"CH-001": {"scenario": {"status": "PARTIAL", "rationale": ""}}})
    with pytest.raises(ValueError):
        parse_spec(bad)


def test_org_level_qualitative_conclusion():
    from traffic_annotation.characteristics.model import Claim, EvidenceItem
    a1 = EvidenceItem("a1", "C", "D", "A", dimensions={"qualitative_conclusion": Claim("x", verified=True)})
    a2 = EvidenceItem("a2", "C", "D", "A", dimensions={"qualitative_conclusion": Claim(None)})
    b = EvidenceItem("b", "C", "D", "B", dimensions={"qualitative_conclusion": Claim("x", verified=True)})
    r = comparability.assess("C", [a1, a2, b], {}, {"a1": "A", "a2": "A", "b": "B"})
    assert r["qualitative_conclusion"].status == "COMPARABLE"


# --------------------------------------------------------------------------- Google Sheets (dry-run)
class FakeClient:
    def __init__(self):
        self.calls = []

    def create_spreadsheet(self, title):
        self.calls.append(("create", title))
        return "sid"

    def ensure_tab(self, sid, tab):
        self.calls.append(("tab", tab))

    def clear(self, sid, rng):
        self.calls.append(("clear", rng))

    def update(self, sid, rng, values):
        self.calls.append(("update", rng, len(values)))


def test_sheets_plan_dry_run_and_write_guard(tmp_path):
    ev = _eval(tmp_path, two_org_items())
    plan = gsheets.build_plan(review.tables(ev), "T")
    assert [o["op"] for o in plan["operations"]][:2] == ["create_spreadsheet", "ensure_tab"]
    assert sum(o["op"] == "update" for o in plan["operations"]) == 4
    lines = gsheets.SheetsSync().run(plan)
    assert lines[0] == "create spreadsheet 'T'"
    with pytest.raises(gsheets.ExternalWriteDisabled):
        gsheets.SheetsSync(dry_run=False).run(plan)
    with pytest.raises(gsheets.ExternalWriteDisabled):
        gsheets.SheetsSync(client=FakeClient(), dry_run=False).run(plan)
    fc = FakeClient()
    gsheets.SheetsSync(client=fc, dry_run=False, allow_external_write=True).run(plan)
    assert fc.calls[0] == ("create", "T") and sum(c[0] == "update" for c in fc.calls) == 4


def test_gsheets_module_has_no_network_dependencies():
    import traffic_annotation.characteristics.gsheets as g
    src = open(g.__file__, encoding="utf-8").read()
    for banned in ("import requests", "googleapiclient", "import socket", "urllib.request", "http.client"):
        assert banned not in src


# --------------------------------------------------------------------------- publication check
def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


DOCNO = "S4" + "-269999"  # built at runtime so this file passes the publication check


def test_publication_check_detects_leaks(tmp_path):
    from traffic_annotation import publication
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "ok.py").write_text("x = 1\n")
    _git(repo, "add", "ok.py")
    assert publication.check(repo, ["Org Secret"], {"7654321"}) == []
    (repo / "leak.md").write_text(f"by org secret\nvalue 7654321\nsee {DOCNO}\n")
    (repo / "data.xlsx").write_bytes(b"x")
    _git(repo, "add", "-f", "leak.md", "data.xlsx")
    kinds = sorted(h.kind for h in publication.check(repo, ["Org Secret"], {"7654321"}))
    assert kinds == ["denylisted-term", "document-number", "forbidden-file-type", "source-number"]


def test_build_denylist_from_workbook(tmp_path):
    from traffic_annotation import publication
    o, a = build_workbooks(tmp_path)
    wb = openpyxl.load_workbook(a)
    wb["4.1 Loss A"]["H8"] = 123456
    wb["4.1 Loss A"]["A10"] = f"Source: {DOCNO} something"
    wb.save(a)
    d = publication.build_denylist([a], extra=["ModelX"])
    assert "Org A" in d and "Org B" in d and "ModelX" in d and DOCNO in d and "#123456" in d
