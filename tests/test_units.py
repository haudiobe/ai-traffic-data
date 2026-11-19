from traffic_annotation import config, contribution, workbook as wbm


def test_is_missing_placeholders():
    for v in (None, "", "  ", "-", "—", "Not identified in workbook", "Not explicit in workbook",
              "Not recorded", "unknown", "TBD", "n/a"):
        assert config.is_missing(v), v
    for v in (0, 3, "Org A", "2026-01-01", "Notes on x"):
        assert not config.is_missing(v), v


def test_expected_evidence_flag():
    assert config.expected_evidence_flag(0) == "UNASSESSED"
    assert config.expected_evidence_flag(1) == "SINGLE-SOURCE"
    assert config.expected_evidence_flag(2) == "MULTI-SOURCE"
    assert config.expected_evidence_flag(5) == "MULTI-SOURCE"


def test_resolve_sheet_methods():
    names = ["2.1 Test Scenarios", "3.6 Chat Coding and  reasoning ", "3.15 Real-time Audio",
             "3_remote_test_overview", "2.4.1 A", "2.4.1b B"]
    assert wbm.resolve_sheet("2.1 Test Scenarios", names) == ("2.1 Test Scenarios", "exact")
    assert wbm.resolve_sheet("3.6 Chat Coding and reasoning", names)[1] == "normalized"
    assert wbm.resolve_sheet("3.15 Realtime Audio", names) == ("3.15 Real-time Audio", "normalized")
    assert wbm.resolve_sheet("2.4.1b something else", names) == ("2.4.1b B", "clause")
    assert wbm.resolve_sheet("3 remote", names) == ("3_remote_test_overview", "clause")
    assert wbm.resolve_sheet("Section 3 — remote", names) == (None, "unresolved")
    assert wbm.resolve_sheet(None, names) == (None, "unresolved")


def test_clause_of():
    assert wbm.clause_of("2.4.1c RT Video") == "2.4.1c"
    assert wbm.clause_of("3_remote_test_overview") == "3"
    assert wbm.clause_of("overview_2_local_server") is None


def test_contribution_claim_parsing_numbers_and_words():
    paras = [
        "Meeting\tS4-262999",
        "Source:\tX",
        "Added a 33-row Dataset Catalogue containing mandatory fields and 14 additional provenance, status, "
        "completeness, and governance fields.",
        "Assigned STABLE to 31 records and SUBMITTED to two records.",
        "Recorded CROSS_CHECKED = NO / not demonstrated for all 33 datasets.",
        "Identified four scenario-definition or overview records as derived/summary data.",
        "Added a ten-row Characteristic Evidence register following B.4.5, with one provisional "
        "MULTI-SOURCE assessment and nine open assessments.",
        "Added a nine-row Provenance History. Added an eight-row Status Definitions sheet.",
    ]
    header, claims = contribution.parse_text(paras)
    assert header["tdoc"] == "S4-262999" and header["source"] == "X"
    got = {k: v[0] for k, v in claims.items()}
    assert got == {
        "catalogue_rows": 33, "additional_fields": 14, "stable_records": 31, "submitted_records": 2,
        "cross_checked_no_records": 33, "derived_records": 4, "evidence_rows": 10,
        "multi_source_characteristics": 1, "open_characteristics": 9, "provenance_rows": 9,
        "status_definition_rows": 8,
    }
