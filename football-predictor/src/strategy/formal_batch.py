"""Per-registered-batch paper budget and immutable ledger identities."""
import hashlib
import math
import re
from datetime import datetime, timedelta

TYPES = {'稳健': 'SAFE', '价值': 'VALUE'}


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def ticket_key(selections):
    return tuple(sorted(re.sub(r'\s+', '', s).casefold() for s in selections.split(' + ')))


def prepare_batch(*, sales_day, task, gate, strategy, plans, existing, policy, now):
    """Validate the whole batch before returning any rows to append."""
    if policy['scope'] != 'simulation_only' or policy['real_money_allowed']:
        raise ValueError('paper simulation only')
    if now < timestamp(policy['effective_from']):
        raise ValueError('policy not effective')
    if now.date().isoformat() != sales_day or now < timestamp(task['run_at']) - timedelta(minutes=35):
        raise ValueError('outside registered sales-day execution window')
    if task['sales_day'] != sales_day or task['purpose'] != '终版分析':
        raise ValueError('registered final batch required')
    if task['status'] in {'completed', 'skipped', 'cancelled', 'archived'}:
        raise ValueError('cannot backfill a terminal batch')
    if gate.get('phase') != 'READY_FOR_FINAL_ANALYSIS' or not gate.get('may_create_plan') or not strategy.get('ok'):
        raise ValueError('READY gate and successful strategy required')
    expected = set(task['match_numbers'])
    if not expected or set(gate['expected_match_numbers']) != expected:
        raise ValueError('gate must cover the exact registered batch')
    lock = min(timestamp(task['hard_lock']), timestamp(gate['deadlines']['decision_lock']))
    if now >= lock or now >= timestamp(task['sales_cutoff']):
        raise ValueError('batch hard lock passed')
    captured = timestamp(gate['freshness']['official_captured_at'])
    if captured < timestamp(policy['effective_from']) or captured > now or now-captured > timedelta(minutes=35):
        raise ValueError('fresh post-policy official snapshot required')
    cap = float(policy['budget_per_type'])
    if not 0 < cap <= 100 or policy['max_per_type_per_batch'] != 1:
        raise ValueError('invalid per-batch budget policy')
    formal = [p for p in plans if str(p.get('is_shadow', '')).lower() == 'false']
    if len(formal) != strategy['production_plan_rows']:
        raise ValueError('candidate count differs from strategy audit')
    selected = {}
    for plan in formal:
        kind = plan['plan_type']
        if kind not in TYPES or kind in selected:
            raise ValueError('at most one SAFE and one VALUE per batch')
        stake = float(plan['total_stake']); odds = float(plan['estimated_odds_min'])
        if not math.isfinite(stake) or not 0 < stake <= cap or not math.isfinite(odds) or odds <= 1:
            raise ValueError('invalid stake or odds')
        nums = re.findall(r'(?:^| \+ )(\d{3}) ', plan['selections'])
        if not nums or len(nums) != len(set(nums)) or not set(nums) <= expected:
            raise ValueError('selection outside batch or repeated match')
        selected[kind] = (plan, set(nums))
    if len(selected) == 2:
        safe, value = selected['稳健'], selected['价值']
        if ticket_key(safe[0]['selections']) == ticket_key(value[0]['selections']):
            raise ValueError('SAFE and VALUE cannot rename the same ticket')
        if len(safe[1] & value[1]) > policy['max_shared_matches']:
            raise ValueError('SAFE and VALUE share too many matches')
    digest = hashlib.sha256(task['key'].encode()).hexdigest()[:12]
    prefix = 'SPORTTERY_BATCH_' + sales_day.replace('-', '') + '_' + digest + '_'
    additions = []; cards = []
    for kind, suffix in TYPES.items():
        if kind not in selected:
            cards.append({'plan_type': kind, 'status': 'not_generated', 'budget': cap, 'stake': 0,
                          'unused_budget': cap, 'reason': 'no_qualified_distinct_candidate',
                          'candidate_rejections': strategy.get('production_rejections', [])})
            continue
        plan = selected[kind][0]
        row = {'date': sales_day, 'time_window': task['run_at'][11:16]+'-'+task['hard_lock'][11:16],
               'plan_id': prefix+suffix, 'plan_type': kind, 'selections': plan['selections'],
               'stake': plan['total_stake'], 'estimated_odds': plan['estimated_odds_min'],
               'actual_odds': '', 'result': '待赛', 'payout': '', 'net_profit': '', 'roi': '',
               'review_note': '仅模拟；policy='+policy['version']+'；batch_key='+task['key']+'；非保本、非已验证正EV'}
        prior = [r for r in existing if r['plan_id'] == row['plan_id']]
        if prior and (len(prior) != 1 or any(str(prior[0][k]) != str(row[k]) for k in ['date','plan_type','selections','stake','estimated_odds'])):
            raise ValueError('immutable batch ticket changed')
        if not prior:
            additions.append(row)
        cards.append({'plan_type': kind, 'status': 'already_recorded' if prior else 'recorded',
                      'budget': cap, 'stake': float(row['stake']), 'unused_budget': cap-float(row['stake']),
                      'plan_id': row['plan_id'], 'selections': row['selections'],
                      'odds': float(row['estimated_odds']),
                      'valuation_status': 'market_structure_observation_not_validated_advantage' if kind == '价值' else 'relative_stability_not_principal_protection'})
    return additions, {'policy': policy['version'], 'batch_key': task['key'], 'sales_day': sales_day,
                        'recorded_at': now.isoformat(), 'quota_scope': policy['quota_scope'],
                        'cards': cards, 'real_money_allowed': False}
