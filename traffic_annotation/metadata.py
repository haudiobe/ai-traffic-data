"""Read-only B.4 metadata audit; never infer missing facts or change statuses.

python -m traffic_annotation.metadata --workbook /private/B4.xlsx --out /private/report
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook

MANDATORY = ('Contributor', 'Creation date', 'Scenario ID', 'Scenario version',
             'Network profile ID(s)', 'Application category', 'Traffic direction',
             'Model provider', 'Model name', 'Execution date', 'Number of runs')
# Dataset ID is also mandatory under B.4.4, checked separately as a primary key.
MISSING = re.compile(r'^\\s*(?:-|–|—|n/?a|none|unknown|tbd|tbc|\\?|not\\s+(?:identified|explicit|recorded|available|known|demonstrated|provided|stated)\\b.*)?\\s*$', re.I)

def missing(value):
    return value is None or (isinstance(value, str) and bool(MISSING.fullmatch(value)))

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def normalize_sheet(value):
    return re.sub(r'[^a-z0-9]+', '', str(value).casefold())

def audit(path):
    path = Path(path)
    initial = sha256(path)
    wb = load_workbook(path, read_only=True, data_only=False)
    if 'Dataset Catalogue' not in wb.sheetnames:
        raise ValueError('Dataset Catalogue not found')
    iterator = wb['Dataset Catalogue'].iter_rows(values_only=True)
    header = [str(x).strip() if x is not None else '' for x in next(iterator)]
    idx = {name: n for n, name in enumerate(header)}
    if 'Dataset ID' not in idx:
        raise ValueError('Dataset ID column not found')
    rows = []
    field_counts, historic, new, statuses = Counter(), Counter(), Counter(), Counter()
    ids = set()
    sheet_titles = set(wb.sheetnames)
    normalized_titles = {normalize_sheet(s) for s in sheet_titles}
    for excel_row, values in enumerate(iterator, 2):
        if not any(v is not None for v in values):
            continue
        def get(name):
            pos = idx.get(name)
            return values[pos] if pos is not None and pos < len(values) else None
        ds_id = str(get('Dataset ID') or '').strip()
        status = str(get('Assigned status') or '').strip().upper()
        prior = get('Prior agreement evidence')
        historical = status == 'STABLE' and not missing(prior)
        statuses[status or 'UNKNOWN'] += 1
        issues = []
        if not ds_id or ds_id in ids:
            issues.append('MISSING_OR_DUPLICATE_DATASET_ID')
        if ds_id:
            ids.add(ds_id)
        for col in MANDATORY:
            if col not in idx or missing(get(col)):
                issues.append(col)
                field_counts[col] += 1
                (historic if historical else new)[col] += 1
        sheet = str(get('Parent sheet') or '').strip()
        if not sheet or (sheet not in sheet_titles and normalize_sheet(sheet) not in normalized_titles):
            issues.append('UNRESOLVED_PARENT_SHEET')
        rows.append({
            'dataset_id': ds_id, 'excel_row': excel_row,
            'assigned_status_unchanged': status,
            'prior_agreement_evidence_present': not missing(prior),
            'historical_agreed': historical, 'parent_sheet': sheet,
            'missing_fields': [f for f in issues if f in MANDATORY],
            'structural_issues': [f for f in issues if f not in MANDATORY],
            'review_class': 'HISTORICAL_QUALIFIED_GAP' if historical else 'NEW_OR_UNCONFIRMED_METADATA_GAP'
        })
    wb.close()
    if initial != sha256(path):
        raise RuntimeError('Source changed during metadata audit')
    summary = [{'field': field, 'missing_total': field_counts[field],
                'historical_qualified_gap': historic[field],
                'new_or_unconfirmed_gap': new[field]} for field in MANDATORY]
    return {
        'schema': 'traffic-annotation/metadata-audit@1',
        'source_sha256': initial, 'dataset_count': len(rows),
        'status_counts': dict(sorted(statuses.items())),
        'metadata_field_summary': summary, 'datasets': rows,
        'interpretation': 'Historical STABLE metadata gaps do not downgrade status or create per-dataset actions; new submissions require prospective completion.'
    }

def write(result, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'metadata_audit.json').write_text(
        json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, rows, fields in [
        ('missing_metadata_by_field.csv', result['metadata_field_summary'],
         ['field', 'missing_total', 'historical_qualified_gap', 'new_or_unconfirmed_gap']),
        ('dataset_metadata_review.csv', result['datasets'],
         ['dataset_id', 'excel_row', 'assigned_status_unchanged', 'historical_agreed',
          'parent_sheet', 'missing_fields', 'structural_issues'])
    ]:
        with (out / name).open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for record in rows:
                writer.writerow({key: '; '.join(map(str, record[key]))
                                 if isinstance(record.get(key), list) else record.get(key, '')
                                 for key in fields})
    return out

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    from . import safety
    safety.assert_outside_repo(args.workbook, args.out)
    result = audit(args.workbook)
    write(result, args.out)
    print('datasets:', result['dataset_count'], 'status:', result['status_counts'])
    print('metadata field gaps:', {r['field']: r['missing_total'] for r in result['metadata_field_summary']})
    print('source SHA-256 unchanged:', result['source_sha256'])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
