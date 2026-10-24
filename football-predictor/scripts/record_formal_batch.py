"""Freeze SAFE/VALUE paper tickets by canonical registry key, never by daily quota."""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from strategy.formal_batch import prepare_batch


def main():
    p = argparse.ArgumentParser()
    for name in ['sales-day', 'batch-key', 'plans-csv', 'strategy-audit', 'gate-json']:
        p.add_argument('--'+name, required=True)
    p.add_argument('--registry')
    p.add_argument('--ledger', default='data/manual/betting_plan_ledger.csv')
    p.add_argument('--policy', default='config/formal_simulation_policy.json')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--correct-empty-scope', action='store_true', help='Preserve an empty receipt whose strategy omitted registered matches; allow one pre-lock correction')
    p.add_argument('--prior-strategy-audit')
    a = p.parse_args()
    def path(s):
        x = Path(s); return x if x.is_absolute() else ROOT/x
    def read(s): return json.loads(path(s).read_text(encoding='utf-8-sig'))
    inputs = {k: hashlib.sha256(path(getattr(a,k)).read_bytes()).hexdigest()
              for k in ['plans_csv','strategy_audit','gate_json','policy']}
    digest = hashlib.sha256(a.batch_key.encode()).hexdigest()[:12]
    output = ROOT/f'artifacts/data/formal_batches/{a.sales_day}_{digest}.json'
    original_output = output
    if a.correct_empty_scope:
        output = original_output.with_stem(original_output.stem+'_scope_correction')
    ledger = path(a.ledger)
    lock = ledger.with_suffix('.formal_batch.lock')
    with lock.open('x', encoding='utf-8') as f: f.write(str(os.getpid()))
    try:
        correction = None
        if a.correct_empty_scope:
            if not a.prior_strategy_audit: raise ValueError('original strategy evidence required')
            prior_receipt = json.loads(original_output.read_text(encoding='utf-8'))
            prior_strategy = read(a.prior_strategy_audit)
            if hashlib.sha256(path(a.prior_strategy_audit).read_bytes()).hexdigest() != prior_receipt['input_sha256']['strategy_audit']:
                raise ValueError('prior strategy evidence hash mismatch')
            if any(c['status'] != 'not_generated' or c['stake'] != 0 for c in prior_receipt['cards']):
                raise ValueError('only an empty original receipt may be corrected')
            if not prior_strategy['match_rows'] < prior_strategy['input_rows']:
                raise ValueError('original scope must demonstrably be incomplete')
            correction = {'reason':'original_formal_scope_incomplete','supersedes':str(original_output.relative_to(ROOT)),
                          'prior_strategy_sha256':prior_receipt['input_sha256']['strategy_audit']}
        if output.exists():
            old = json.loads(output.read_text(encoding='utf-8'))
            if old['input_sha256'] != inputs: raise ValueError('immutable batch inputs changed')
            with ledger.open(encoding='utf-8-sig', newline='') as f: recorded = list(csv.DictReader(f))
            for card in old['cards']:
                if card['status'] == 'not_generated': continue
                matches = [r for r in recorded if r['plan_id'] == card['plan_id']]
                if len(matches) != 1 or matches[0]['selections'] != card['selections'] or float(matches[0]['stake']) != card['stake'] or float(matches[0]['estimated_odds']) != card['odds'] or matches[0]['plan_type'] != card['plan_type'] or matches[0]['date'] != a.sales_day:
                    raise ValueError('receipt no longer matches ledger')
            print(json.dumps({'idempotent':True,'output':str(output)},ensure_ascii=True)); return
        registry = read(a.registry or f'artifacts/data/sporttery_task_registry_{a.sales_day}.json')
        tasks = [t for t in registry['tasks'] if t['key'] == a.batch_key]
        if len(tasks) != 1: raise ValueError('unique canonical batch required')
        if correction:
            current_strategy = read(a.strategy_audit)
            if current_strategy['input_rows'] != len(tasks[0]['match_numbers']) or current_strategy['match_rows'] != len(tasks[0]['match_numbers']):
                raise ValueError('correction must evaluate the complete registered batch')
        with path(a.plans_csv).open(encoding='utf-8-sig',newline='') as f: plans=list(csv.DictReader(f))
        with ledger.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f); fields=reader.fieldnames; existing=list(reader)
        additions, receipt = prepare_batch(sales_day=a.sales_day, task=tasks[0], gate=read(a.gate_json),
            strategy=read(a.strategy_audit), plans=plans, existing=existing, policy=read(a.policy),
            now=datetime.now(timezone(timedelta(hours=8))))
        receipt.update(input_sha256=inputs,rows_added=len(additions),dry_run=a.dry_run)
        if correction: receipt['correction'] = correction
        if a.dry_run:
            print(json.dumps(receipt,ensure_ascii=True)); return
        if additions:
            with ledger.open('a',encoding='utf-8',newline='') as f:
                csv.DictWriter(f,fieldnames=fields).writerows(additions); f.flush(); os.fsync(f.fileno())
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x',encoding='utf-8') as f: json.dump(receipt,f,ensure_ascii=False,indent=2)
        print(json.dumps({'output':str(output),'rows_added':len(additions),'cards':receipt['cards']},ensure_ascii=True))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
