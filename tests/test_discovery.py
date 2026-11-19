"""Regression coverage for Stage 3 discovery; synthetic cells only."""
from openpyxl import Workbook
from traffic_annotation.discovery import discover, write_outputs

def test_labels_and_coordinates_are_candidates_not_crosschecks(tmp_path):
    path=tmp_path/"s.xlsx"
    w=Workbook()
    s=w.active;s.title="2.5 synthetic"
    s.append(["Profile","A","B"])
    s.append(["Uplink bytes",100,110])
    s.append(["Mean latency (s)",1.2,2.3])
    s.append(["No matching label",1234,5678])
    w.save(path)
    result=discover(path)
    assert result["characteristics"]["CH-001"]["candidate_rows"]==1
    assert result["characteristics"]["CH-005"]["candidate_rows"]==1
    assert result["characteristics"]["CH-007"]["candidate_rows"]==0
    assert all(c["review_status"]=="CANDIDATE_UNVERIFIED" for c in result["candidates"])
    assert all(c["numeric_cells"] for c in result["candidates"])
    assert all(c["verified_evidence"]==0 for c in result["characteristics"].values())
    write_outputs(result,tmp_path/"generated")
    assert (tmp_path/"generated"/"candidate_measurements.json").exists()

def test_column_header_and_source_hash(tmp_path):
    path=tmp_path/"s.xlsx";w=Workbook();s=w.active;s.title="3.2 synthetic"
    s.append(["Scenario","Turns","UL per turn (B)"])
    s.append(["A",20,100])
    s.append(["B",30,200])
    w.save(path)
    from traffic_annotation.discovery import sha256
    old=sha256(path)
    result=discover(path)
    assert old==sha256(path)==result["source_sha256"]
    assert result["characteristics"]["CH-010"]["candidate_rows"]==1
    assert result["characteristics"]["CH-002"]["candidate_rows"]==1
    assert result["characteristics"]["CH-010"]["verified_evidence"]==0
