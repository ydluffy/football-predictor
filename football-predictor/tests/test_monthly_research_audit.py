import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('monthly_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_monthly_research.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_latest_review_hash_and_pending(tmp_path):
    snapshot = {'sales_day': '2026-10-01', 'batch_id': 'a', 'protocol_version': 'v2', 'frozen_at': '2026-10-01T10:00:00+08:00', 'experiments': [{'experiment_id': 'a'}, {'experiment_id': 'b'}]}
    path = tmp_path / 'snapshot.json'
    path.write_text(json.dumps(snapshot))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reviews = tmp_path / 'reviews'; reviews.mkdir()
    for name, stamp, ids, key in [('old', '2026-10-02T10:00:00+08:00', ['a','b'], digest), ('new', '2026-10-03T10:00:00+08:00', ['a'], digest), ('unrelated', '2026-10-04T10:00:00+08:00', ['a','b'], 'other')]:
        (reviews / (name+'.json')).write_text(json.dumps({'snapshot_sha256': key, 'reviewed_at': stamp, 'settled': [{'experiment_id': x} for x in ids]}))
    (tmp_path / 'auxiliary.json').write_text('[]')
    result = module.inventory(tmp_path, '2026-10')
    assert result['snapshot_count'] == 1
    assert result['pending_plans'] == 1
    assert module.inventory(tmp_path, '2026-09')['snapshot_count'] == 0
