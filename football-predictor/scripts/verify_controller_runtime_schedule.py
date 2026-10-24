"""Read-only check of the desktop scheduler's persisted nominal execution time."""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--automation-id', required=True)
    p.add_argument('--expected', required=True, help='Timezone-aware intended execution time')
    p.add_argument('--database', default=str(Path.home()/'.codex/sqlite/codex-dev.db'))
    p.add_argument('--output', required=True)
    a = p.parse_args()
    expected = datetime.fromisoformat(a.expected)
    if expected.tzinfo is None:
        raise ValueError('expected must include its timezone')
    with sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        row = c.execute('SELECT id,status,next_run_at,next_run_nominal_at,last_run_at,rrule,updated_at FROM automations WHERE id=?',(a.automation_id,)).fetchone()
    data = dict(row) if row else {}
    nominal = data.get('next_run_nominal_at')
    jittered = data.get('next_run_at')
    expected_ms = round(expected.timestamp()*1000)
    verified = bool(data.get('status') == 'ACTIVE' and nominal == expected_ms and jittered is not None and abs(jittered-nominal)<=5*60*1000)
    out = {'verified':verified,'verified_at':datetime.now(timezone.utc).isoformat(),'expected':expected.isoformat(),'runtime':data,'verification_source':'desktop sqlite read-only; nominal exact match and actual wake within five minutes; does not prove future dispatch'}
    target = Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False))
    return 0 if verified else 1


if __name__ == '__main__':
    raise SystemExit(main())
