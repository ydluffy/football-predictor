"""Bounded account probes; never persist credentials or raw account payloads."""
import json,os,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip(chr(34)).strip(chr(39)))
def get(url,headers):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,{}
 except Exception as e:return None,{'transport_error_type':type(e).__name__}
checks={}
k=os.getenv('API_FOOTBALL_KEY','')
code,v=get('https://v3.football.api-sports.io/status',{'x-apisports-key':k}) if k else (None,{})
resp=v.get('response',{}) or {};checks['api_football']={'configured':bool(k),'http_status':code,'api_errors_present':bool(v.get('errors')),'subscription':{x:resp.get('subscription',{}).get(x) for x in ['plan','active']},'requests':{x:resp.get('requests',{}).get(x) for x in ['current','limit_day']},'transport_error_type':v.get('transport_error_type')}
k=os.getenv('SERPAPI_API_KEY','')
code,v=get('https://serpapi.com/account.json',{'Authorization':'Bearer '+k}) if k else (None,{})
# This endpoint requires api_key query authentication; retain no URL or account identity.
if k and code in [401,403]:
 from urllib.parse import urlencode
 code,v=get('https://serpapi.com/account.json?'+urlencode({'api_key':k}),{})
checks['serpapi']={'configured':bool(k),'http_status':code,**{x:v.get(x) for x in ['plan_name','searches_per_month','total_searches_left','this_month_usage']},'transport_error_type':v.get('transport_error_type')}
k=os.getenv('SPORTMONKS_API_TOKEN','')
code,v=get('https://api.sportmonks.com/v3/football/leagues',{'Authorization':k}) if k else (None,{})
checks['sportmonks']={'configured':bool(k),'http_status':code,'leagues':[{'id':x.get('id'),'name':x.get('name')} for x in v.get('data',[])],'transport_error_type':v.get('transport_error_type')}
audit={'checked_at':datetime.now(timezone.utc).isoformat(),'credentials_persisted':False,'checks':checks,'scope':'account and league access only; not proof of lineup/xG endpoint permissions'}
p=ROOT/'artifacts/data/free_provider_access_20261012.json';p.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=True))
