"""Bounded optional zero-budget research, never blocks original production."""
import json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1]
def run_hook(stage,arguments):
 config=R/'config/ucl_domestic_research.json'
 if not config.exists() or not json.loads(config.read_text(encoding='utf-8')).get('prospective_enabled'):return
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory=R/'artifacts/data/ucl_domestic_comparison/audits';directory.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy();env['OPENBLAS_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1'
 try:
  r=subprocess.run([sys.executable,'-X','utf8',str(R/'scripts/run_ucl_domestic_research.py'),stage,*map(str,arguments)],cwd=R,capture_output=True,text=True,encoding='utf-8',timeout=180,env=env)
  audit={'stage':stage,'status':'succeeded' if r.returncode==0 else 'failed','returncode':r.returncode,'stdout':r.stdout[-5000:],'stderr':r.stderr[-2000:],'production_blocked':False,'arguments':list(map(str,arguments))}
 except Exception as exc:audit={'stage':stage,'status':'failed','error_type':type(exc).__name__,'reason':str(exc),'production_blocked':False}
 audit['at']=datetime.now(timezone.utc).isoformat();path=directory/(stamp+'_'+stage+'.json');path.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ucl_research_hook':audit['status'],'audit':str(path)}))
