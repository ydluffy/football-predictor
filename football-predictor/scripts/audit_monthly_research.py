"""Read-only monthly inventory of frozen research and its settlement evidence."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inventory(directory, month):
    reviews = {}
    errors = []
    for path in sorted((directory / 'reviews').glob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            key = value['snapshot_sha256']
            when = datetime.fromisoformat(value['reviewed_at'])
            if when.tzinfo is None:
                raise ValueError('review timestamp lacks timezone')
            if key not in reviews or when > reviews[key][0]:
                reviews[key] = (when, path, value)
        except (ValueError, KeyError) as exc:
            errors.append({'path': str(path), 'error': str(exc)})
    records = []
    for path in sorted(directory.glob('*.json')):
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            continue
        if not str(value.get('sales_day', '')).startswith(month + '-'):
            continue
        if 'experiments' not in value or 'frozen_at' not in value:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        review = reviews.get(digest)
        ids = {x['experiment_id'] for x in value['experiments']}
        settled = {x['experiment_id'] for x in review[2].get('settled', [])} if review else set()
        records.append({'snapshot': str(path), 'sha256': digest,
                        'sales_day': value['sales_day'], 'batch_id': value['batch_id'],
                        'protocol': value['protocol_version'], 'plans': len(ids),
                        'settled_plans': len(ids & settled), 'pending_plans': len(ids - settled),
                        'review': str(review[1]) if review else None,
                        'empty_snapshot': not bool(ids)})
    return {'snapshots': records, 'errors': errors,
            'snapshot_count': len(records),
            'pending_plans': sum(x['pending_plans'] for x in records),
            'note': 'Inventory only. Repeated versions are not independent events; no pooled ROI or automatic promotion.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--month', required=True)
    a = p.parse_args()
    if datetime.strptime(a.month, '%Y-%m').strftime('%Y-%m') != a.month:
        p.error('month must be YYYY-MM')
    result = {'month': a.month, 'simulation_only': True, 'production_promotion_allowed': False,
              'tracks': {name: inventory(ROOT / 'artifacts/data' / name, a.month)
                         for name in ('october_research', 'independent_comparison')}}
    out = ROOT / 'artifacts/research_schedule/monthly'
    out.mkdir(parents=True, exist_ok=True)
    target = out / (a.month + '_inventory.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(target), 'tracks': {k: {'snapshots': v['snapshot_count'], 'pending_plans': v['pending_plans'], 'errors': len(v['errors'])} for k,v in result['tracks'].items()}}))


if __name__ == '__main__':
    main()
