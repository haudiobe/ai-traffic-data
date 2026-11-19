from openpyxl import Workbook
from traffic_annotation.metadata import audit, write, sha256

def test_missing_metadata_qualified_and_prospective(tmp_path):
    p = tmp_path / 'input.xlsx'
    w = Workbook()
    c = w.active
    c.title = 'Dataset Catalogue'
    c.append(['Dataset ID', 'Assigned status', 'Prior agreement evidence', 'Parent sheet', 'Contributor', 'Application category'])
    c.append(['DS-001', 'STABLE', 'Agreed', '2.1 source', 'Not identified in workbook', 'Chat'])
    c.append(['DS-002', 'SUBMITTED', None, '2.1 source', None, 'Chat'])
    w.create_sheet('2.1 source')
    w.save(p)
    before = sha256(p)
    result = audit(p)
    assert sha256(p) == before
    assert result['dataset_count'] == 2
    assert result['status_counts'] == {'STABLE': 1, 'SUBMITTED': 1}
    assert result['datasets'][0]['review_class'] == 'HISTORICAL_QUALIFIED_GAP'
    assert result['datasets'][1]['review_class'] == 'NEW_OR_UNCONFIRMED_METADATA_GAP'
    assert result['metadata_field_summary'][0]['missing_total'] == 2
    write(result, tmp_path / 'output')
    assert (tmp_path / 'output' / 'missing_metadata_by_field.csv').exists()

def test_unresolved_sheet_and_duplicate_id(tmp_path):
    p = tmp_path / 'input.xlsx'
    w = Workbook()
    w.active.title = 'Dataset Catalogue'
    w.active.append(['Dataset ID','Assigned status','Parent sheet'])
    w.active.append(['D','SUBMITTED','ghost'])
    w.active.append(['D','STABLE','ghost'])
    w.save(p)
    result = audit(p)
    assert 'UNRESOLVED_PARENT_SHEET' in result['datasets'][0]['structural_issues']
    assert 'MISSING_OR_DUPLICATE_DATASET_ID' in result['datasets'][1]['structural_issues']
