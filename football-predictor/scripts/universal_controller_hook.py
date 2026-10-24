"""Best-effort research hook; failures never invalidate original production."""
import json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1]


def run_hook(stage,arguments):
    cfg=json.loads((R/'config/universal_goals_research.json').read_text(encoding='utf-8'))
    if not cfg.get('prospective_shadow_enabled'):return
    command=[sys.executable,str(R/'scripts/run_universal_comparison.py'),stage,*map(str,arguments)]
    try:
        completed=subprocess.run(command,cwd=R,capture_output=True,text=True,encoding='utf-8',timeout=180)
    except subprocess.TimeoutExpired:
        completed=subprocess.CompletedProcess(command,124,'','universal research timeout after 180 seconds; original production not blocked')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=R/'artifacts/data/universal_comparison/audits';directory.mkdir(parents=True,exist_ok=True)
    audit={'at':datetime.now(timezone.utc).isoformat(),'stage':stage,'status':'succeeded' if completed.returncode==0 else 'failed','returncode':completed.returncode,'arguments':list(map(str,arguments)),'stdout':completed.stdout[-6000:],'stderr':completed.stderr[-6000:],'production_blocked':False}
    with (directory/f'{stamp}_{stage}.json').open('x',encoding='utf-8') as stream:json.dump(audit,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'universal_research_hook':audit['status'],'audit':str(directory/f'{stamp}_{stage}.json')}))
