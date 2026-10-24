import json
import subprocess
import sys
from pathlib import Path

from strategy.october_research import build_experiments

ROOT=Path(__file__).resolve().parents[1]

def test_focused_protocol_retires_variants_without_losing_observation():
    plans,skips=build_experiments([{'match_number':'001'}],{'research_focus':'independent_comparison_only'})
    assert plans==[] and skips==[{'match_number':'001','reason':'broad_variants_retired_use_independent_comparison'}]

def test_live_entry_uses_configured_model_and_exact_sbv_identity(tmp_path):
    scan=tmp_path/'scan.json';output=tmp_path/'predictions.csv'
    # A deterministic model fixture keeps the CLI test independent of ignored research artifacts.
    model=tmp_path/'model.json'
    model.write_text(json.dumps({'N1':{
        'teams':['Heerenveen','Excelsior'], 'coefficients':[0.2,0.1,0.0,0.0,0.0,0.0],
        'trained_through':'2026-08-02T00:00:00', 'penalty':1.0, 'half_life':365.0,
        'temperature':1.0,
    }}),encoding='utf-8')
    scan.write_text(json.dumps({'fixtures':[{'match_id':'diagnostic|004','home_team':'海伦芬','away_team':'SBV精英','kickoff':'2030-01-01T00:00:00+08:00','competition_id':'NED_EREDIVISIE'}]},ensure_ascii=False),encoding='utf-8')
    command=[sys.executable,str(ROOT/'scripts/predict_independent_goals.py'),'--scan-json',str(scan),'--output',str(output),'--model-json',str(model)]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0, result.stderr
    import pandas as pd
    row=pd.read_csv(output).iloc[0]
    assert row.status=='research_only'
    assert row.model_id==json.loads((ROOT/'config/independent_goals_research.json').read_text(encoding='utf-8'))['model_id']
    assert pd.Timestamp(row.train_through)>pd.Timestamp('2026-08-01')
    assert abs(sum(row['margin_probability_'+str(i)] for i in range(-4,5))-1)<1e-9
    assert row.primary_direction in ['home','draw','away']
    before=output.read_bytes()
    repeat=subprocess.run(command,cwd=ROOT,capture_output=True)
    assert repeat.returncode!=0 and output.read_bytes()==before
