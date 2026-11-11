"""Bounded HTTP load check against a disposable LOCAL workspace; never a bank endpoint."""
import argparse
import getpass
import json
import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests


def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:5000');p.add_argument('--username',default='admin')
    p.add_argument('--requests',type=int,default=80);p.add_argument('--workers',type=int,default=4);p.add_argument('--output',default='reports/load-local.json')
    a=p.parse_args()
    if urlparse(a.url).hostname not in ('127.0.0.1','localhost'):raise SystemExit('This script only targets localhost')
    if not 1<=a.requests<=100 or not 1<=a.workers<=8:raise SystemExit('Use 1–100 requests and 1–8 workers; scoring rate limits remain enabled')
    password=os.getenv('GUARD_LOAD_PASSWORD') or getpass.getpass('Administrator password: ')
    s=requests.Session();token=s.get(a.url+'/api/csrf',timeout=10).json()['csrf_token']
    login=s.post(a.url+'/api/login',json={'username':a.username,'password':password},headers={'X-CSRF-Token':token},timeout=10)
    login.raise_for_status();token=login.json()['csrf_token'];cookies=s.cookies.get_dict();run=uuid.uuid4().hex[:10]
    def one(i):
        payload={'transaction_id':f'load-{run}-{i}','timestamp':datetime.now(timezone.utc).isoformat(),
            'payer_id':f'load-payer-{run}-{i}','payee_id':'load-payee','device_id':'load-device','amount':'250.00',
            'category':'grocery','channel':'qr','account_age_days':365,'failed_attempts_1h':0}
        start=time.perf_counter()
        try:
            r=requests.post(a.url+'/api/transactions',json=payload,cookies=cookies,headers={'X-CSRF-Token':token},timeout=30)
            return (time.perf_counter()-start)*1000,r.status_code
        except requests.RequestException:return (time.perf_counter()-start)*1000,0
    started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(one,range(a.requests)))
    elapsed=time.perf_counter()-started;lat=sorted(x[0] for x in results)
    report={'requests':a.requests,'workers':a.workers,'elapsed_seconds':round(elapsed,3),
        'throughput_rps':round(a.requests/elapsed,2),'median_ms':round(statistics.median(lat),2),
        'p95_ms':round(lat[min(len(lat)-1,int(.95*len(lat)))],2),'max_ms':round(max(lat),2),
        'status_counts':{str(status):sum(x[1]==status for x in results) for status in sorted({x[1] for x in results})},
        'errors':sum(x[1] not in (200,201) for x in results),
        'scope':'Local bounded HTTP smoke load; includes network, auth, rate limiting and DB commit. Not a capacity guarantee.'}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    raise SystemExit(1 if report['errors'] else 0)


if __name__=='__main__':main()
