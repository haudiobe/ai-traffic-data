"""Stage 2.1: trend vs magnitude agreement, authority of CROSSCHECKED results,
statistical-basis gate, metric basis (denominator) and reported-value diagnosis.

All organizations, numbers and texts are synthetic.
"""
import copy
import json

import openpyxl
import pytest

from traffic_annotation import workbook as wbm
from traffic_annotation.characteristics import outcome, review
from traffic_annotation.characteristics.evaluate import run
from traffic_annotation.characteristics.model import load_rules
from traffic_annotation.characteristics.spec import diagnose_reported, parse_spec

from stage2_fixtures import SHEETS, build_workbooks, item, spec, two_org_items
from test_stage2 import _cli, _ch, _eval, _sheets


def _relaxed(**over):
    rules = load_rules()
    rules["dimension_status_effect"].update({"PARTIAL": "ok", "UNKNOWN": "ok"})
    rules.update(over)
    return rules


# --------------------------------------------------------------------------- trend vs magnitude
def test_trend_agrees_despite_magnitude_difference_at_one_point(tmp_path):
    # Org A: 0, -3%, -10%, -20%; Org B: 0, -2.5%, -15%, -50%
    c = _ch(_eval(tmp_path, two_org_items(), sheets=_sheets(**{"4.2 Loss B": dict(values=[200, 195, 170, 100])})))
    o = c.outcome
    assert o.trend == "AGREE", o.trend_reason
    assert o.magnitude == "PARTIAL"
    assert [p.direction_agreement for p in o.points] == ["AGREE"] * 4
    assert [p.magnitude for p in o.points] == ["WITHIN", "WITHIN", "WITHIN", "OUTSIDE"]
    assert "outside at 30%" in o.magnitude_reason
    assert o.result == "MIXED" and c.state == "CROSSCHECKED_MIXED"
    assert c.authority == "PROVISIONAL"


def test_trend_agrees_while_magnitude_disagrees_everywhere(tmp_path):
    sheets = _sheets(**{"4.1 Loss A": dict(values=[90, 80, 70, 60]), "4.2 Loss B": dict(values=[140, 110, 80, 40])})
    o = _ch(_eval(tmp_path, two_org_items(), sheets=sheets)).outcome
    assert o.trend == "AGREE" and o.magnitude == "DISAGREE"
    assert set(o.series_trends.values()) == {"decreasing"}
    assert all(p.classification == "MIXED" for p in o.points)


def test_trend_opposite_and_partial():
    cfg = load_rules()["outcome"]
    opp = outcome.evaluate({"A": {"a": {0.1: -0.1, 0.2: -0.3}}, "B": {"b": {0.1: 0.1, 0.2: 0.3}}}, cfg)
    assert opp.trend == "OPPOSITE"
    part = outcome.evaluate({"A": {"a": {0.1: 0.0, 0.2: -0.2, 0.3: -0.3}},
                             "B": {"b": {0.1: -0.2, 0.2: 0.0, 0.3: -0.3}}}, cfg)
    assert part.trend == "PARTIAL" and part.series_trends["b"] == "non-monotonic"


def test_series_trend_ignores_steps_inside_dead_band():
    assert outcome.series_trend([0.0, 0.02, -0.1, -0.5], 0.05) == "decreasing"
    assert outcome.series_trend([0.0, 0.01, -0.01], 0.05) == "flat"
    assert outcome.series_trend([0.0, 0.2, 0.4], 0.05) == "increasing"
    assert outcome.series_trend([0.0, -0.2, 0.1], 0.05) == "non-monotonic"


def test_consistent_case_reports_trend_and_magnitude_agree(tmp_path):
    o = _ch(_eval(tmp_path, two_org_items())).outcome
    assert (o.result, o.trend, o.magnitude) == ("CONSISTENT", "AGREE", "AGREE")


# --------------------------------------------------------------------------- statistical evidence gate
def test_unknown_statistical_basis_is_pending_and_non_authoritative(tmp_path):
    c = _ch(_eval(tmp_path, two_org_items(drop=("statistical_basis",))))
    assert c.state == "CROSSCHECK_PENDING"
    assert c.outcome.result == "CONSISTENT"  # computed, not applied
    assert c.authority == "NOT_APPLICABLE" and "non-authoritative" in c.authority_reason


def test_relaxed_mapping_cannot_lift_unknown_statistical_basis(tmp_path):
    c = _ch(_eval(tmp_path, two_org_items(drop=("statistical_basis",)), rules=_relaxed()))
    assert c.state == "CROSSCHECK_PENDING" and "statistical_basis" in c.state_reason


def test_partial_statistical_basis_cannot_produce_crosschecked(tmp_path):
    asm = {"CH-001": {"statistical_basis": {"status": "PARTIAL", "rationale": "runs stated by one source only"}}}
    for rules in (None, _relaxed()):
        c = _ch(_eval(tmp_path, two_org_items(), assessments=asm, rules=rules))
        assert c.state == "CROSSCHECK_PENDING", c.state_reason
        assert not c.state.startswith("CROSSCHECKED_")


def test_differing_statistical_basis_is_not_comparable(tmp_path):
    other = {"statistical_basis": {"value": "3 runs, median",
                                   "source": {"sheet": "4.2 Loss B", "cell": "A4", "quote": "3 runs"}}}
    c = _ch(_eval(tmp_path, two_org_items(override=other)))
    assert c.dims["statistical_basis"].status == "NOT_COMPARABLE"
    assert c.state == "MULTI_SOURCE_NOT_COMPARABLE"


def test_without_strict_gate_crosschecked_is_still_provisional(tmp_path):
    rules = _relaxed(strict_dimensions=[])
    c = _ch(_eval(tmp_path, two_org_items(drop=("statistical_basis",)), rules=rules))
    assert c.state == "CROSSCHECKED_CONSISTENT"
    assert c.authority == "PROVISIONAL" and "statistical_basis" in c.authority_reason


@pytest.mark.parametrize("status,expected", [("EXPERIMENTAL", "PROVISIONAL"), ("APPROVED", "AUTHORITATIVE")])
def test_authority_requires_approved_thresholds(tmp_path, status, expected):
    rules = load_rules()
    rules["threshold_status"] = status
    c = _ch(_eval(tmp_path, two_org_items(), rules=rules))
    assert c.state == "CROSSCHECKED_CONSISTENT" and c.authority == expected


def test_packaged_thresholds_are_experimental_and_validated(tmp_path):
    rules = load_rules()
    assert rules["threshold_status"] == "EXPERIMENTAL"
    assert "not normative" in rules["threshold_note"]
    assert rules["strict_dimensions"] == ["statistical_basis"]
    for bad in ({"threshold_status": "FINAL"}, {"strict_dimensions": ["colour"]}):
        r = copy.deepcopy(rules)
        r.update(bad)
        p = tmp_path / "r.json"
        p.write_text(json.dumps(r), encoding="utf-8")
        with pytest.raises(ValueError):
            load_rules(p)


# --------------------------------------------------------------------------- metric basis / denominators
B_ROWS = [
    ["Total questions (B)", 200, 200, 200, 200, 200],  # row 10
    ["Total received questions at server (C)", 200, 200, 190, 180, 160],  # row 11
    ["Change vs baseline (A/C)", "-", 0, -0.035, -0.074, -0.228],  # row 12
]


def _basis_items(basis_a="all_questions", basis_b="all_questions", quote_b="Total questions"):
    a, b = two_org_items()
    a["series"]["denominator"]["basis"] = basis_a
    b["series"]["denominator"] = {"cells": "C10:F10", "basis": basis_b,
                                  "source": {"sheet": "4.2 Loss B", "cell": "A10", "quote": quote_b}}
    b["series"]["alt_denominator"] = {"cells": "C11:F11", "basis": "received_at_server",
                                      "source": {"sheet": "4.2 Loss B", "cell": "A11",
                                                 "quote": "received questions at server"}}
    b["series"]["alt_reported_change_cells"] = "C12:F12"
    return [a, b]


def _basis_sheets():
    return _sheets(**{"4.2 Loss B": dict(base=120, values=[120, 110, 100, 74], extra_rows=B_ROWS)})


def test_all_questions_and_received_basis_are_distinguished(tmp_path):
    ev = _eval(tmp_path, _basis_items(), sheets=_basis_sheets())
    c = _ch(ev)
    assert c.basis_by_org == {"all_questions": ["Org A", "Org B"]}
    assert c.alt_basis_by_org == {"received_at_server": ["Org B"]}
    assert any("alternative basis 'received_at_server' reported by Org B only" in q for q in c.open_questions)
    rb = next(r for r in c.items if r.item.id == "E-B")
    # outcome uses the all-questions basis; the received basis is reported separately
    assert rb.rel_change[0.3] == pytest.approx(74 / 120 - 1)
    assert rb.alt_rel_change[0.3] == pytest.approx((74 / 160) / (120 / 200) - 1)
    pts = {p.x: p for p in c.outcome.points}
    assert pts[0.3].series_values["E-B"] == pytest.approx(74 / 120 - 1)


def test_differing_metric_basis_keeps_pending(tmp_path):
    c = _ch(_eval(tmp_path, _basis_items(basis_b="received_at_server"), sheets=_basis_sheets()))
    assert c.state == "CROSSCHECK_PENDING" and "metric basis differs" in c.state_reason


def test_unverified_basis_is_unspecified(tmp_path):
    ev = _eval(tmp_path, _basis_items(quote_b="questions answered by the server"), sheets=_basis_sheets())
    c = _ch(ev)
    assert c.basis_by_org == {"all_questions": ["Org A"]}
    assert any("treated as unspecified" in i.message for i in ev.issues)
    assert any(q.startswith("[metric_basis] denominator basis not stated") for q in c.open_questions)


# --------------------------------------------------------------------------- reported-value diagnosis
def test_diagnose_rounding_convention():
    # exact: (74/160)/(120/200)-1 = -0.2292; with accuracies rounded to 3 decimals: -0.2283
    d = diagnose_reported(120, 200, 74, 160, -0.228)
    assert d["decimals"] == 3 and d["exact"] == pytest.approx(-0.229167, abs=1e-6)
    assert d["matches"] == ["accuracies rounded to 3 decimals before division"]
    assert diagnose_reported(120, 200, 74, 160, -0.229)["matches"][0] == "accuracies rounded to 4 decimals before division"
    assert diagnose_reported(120, 200, 74, 160, -0.5)["matches"] == []


def test_reported_mismatch_is_diagnosed_without_changing_values(tmp_path):
    o, a = build_workbooks(tmp_path, sheets=_basis_sheets())
    before = (wbm.sha256(o), wbm.sha256(a))
    ev = run(o, a, parse_spec(spec(_basis_items())))
    assert (wbm.sha256(o), wbm.sha256(a)) == before
    w = [i for i in ev.issues if i.category == "definition" and i.subject == "E-B" and i.severity == "WARNING"]
    assert len(w) == 1 and "x=0.3" in w[0].message
    assert "Reproduced only by: accuracies rounded to 3 decimals before division" in w[0].action
    assert "Measured values unchanged" in w[0].action
    rb = next(r for r in _ch(ev).items if r.item.id == "E-B")
    assert rb.values == [120, 110, 100, 74]  # source counts untouched
    assert rb.alt_reported_change[0.3] == -0.228  # source value reported as-is
    assert rb.reported_diagnosis["reported change (alt. denominator)"][0.3]["matches"]


# --------------------------------------------------------------------------- outputs
def test_review_outputs_label_non_authoritative_and_experimental(tmp_path):
    ev = _eval(tmp_path, two_org_items(drop=("statistical_basis",)))
    h, rows = review.tables(ev)["Characteristic Evaluation"]
    row = dict(zip(h, next(r for r in rows if r[0] == "CH-001")))
    out_col = next(k for k in h if k.startswith("Provisional outcome"))
    assert row[out_col].startswith("NON-AUTHORITATIVE")
    assert row["Trend agreement (from data)"] == "AGREE"
    assert row["Thresholds"].startswith("EXPERIMENTAL thresholds")
    md = review.write_markdown(ev, tmp_path / "r.md").read_text(encoding="utf-8")
    assert "not normative" in md and "NON-AUTHORITATIVE" in md and "Trend agreement (from data)" in md


def test_cli_still_deterministic_with_diagnosis(tmp_path, capsys):
    from stage2_fixtures import write_spec
    build_workbooks(tmp_path, sheets=_basis_sheets())
    write_spec(tmp_path, spec(_basis_items()))
    assert _cli(tmp_path, tmp_path / "o1", [], build=False) == 0
    assert _cli(tmp_path, tmp_path / "o2", [], build=False) == 0
    out = capsys.readouterr().out
    assert "authority:" in out and "thresholds EXPERIMENTAL" in out
    for f in (tmp_path / "o1").rglob("*"):
        if f.is_file():
            assert f.read_bytes() == (tmp_path / "o2" / f.relative_to(tmp_path / "o1")).read_bytes(), f
    ev = json.loads((tmp_path / "o1" / "normalized" / "evidence.json").read_text(encoding="utf-8"))
    eb = next(e for e in ev["evidence"] if e["evidence"] == "E-B")
    assert eb["metric_basis"] == "all_questions" and eb["alternative_basis"] == "received_at_server"
    assert eb["reported_value_diagnosis"]
    wb = openpyxl.load_workbook(tmp_path / "o1" / "characteristic_crosscheck_review.xlsx")
    assert tuple(wb.sheetnames) == review.TABS


# --------------------------------------------------------------------------- history scan
def test_publication_history_finds_removed_content(tmp_path):
    import subprocess
    from traffic_annotation import publication

    def git(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                       cwd=repo, check=True, capture_output=True)

    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main")
    (repo / "report.md").write_text("by org secret, value 7654321\n")
    (repo / "ok.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    git("rm", "-q", "report.md")
    git("commit", "-q", "-m", "remove report")
    found = publication.history(repo, ["Org Secret"], {"7654321"})
    assert [f.path for f in found] == ["report.md"]
    assert found[0].refs == []  # no longer in any current tree, still in history
    assert found[0].kinds == {"denylisted-term": 1, "source-number": 1}
    assert len(found[0].commits) == 1
