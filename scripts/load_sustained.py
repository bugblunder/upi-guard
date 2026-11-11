"""Disposable local HTTP contention experiment, not a production capacity claim."""
import argparse
import json
import logging
import secrets
import statistics
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from werkzeug.serving import make_server
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from upi_guard import create_app
from upi_guard.db import init_db
from upi_guard.__main__ import add_user
from upi_guard.scoring import score_transaction


def main():
    p=argparse.ArgumentParser();p.add_argument('--requests',type=int,default=2000);p.add_argument('--workers',type=int,default=16)
    p.add_argument('--output',default='reports/load-contention.json');a=p.parse_args()
    if not 100<=a.requests<=10000 or not 1<=a.workers<=32:raise ValueError('Bounded local test only')
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='guard-load-') as tmp:
        app=create_app({'DATABASE_URL':f'sqlite:///{tmp}/load.db','SECRET_KEY':secrets.token_hex(32),
            'ARTIFACT_ROOT':str(root/'artifacts'),'SCORE_RATE_LIMIT':20000})
        app.logger.setLevel(logging.ERROR);logging.getLogger('werkzeug').setLevel(logging.ERROR)
        init_db(app.extensions['db_engine']);pw=secrets.token_urlsafe(24);add_user(app,'load-admin','admin',pw)
        base=datetime.now(timezone.utc)-timedelta(hours=2)
        def payload(i):
            return dict(transaction_id=f'load-{i:06d}',timestamp=(base+timedelta(seconds=i)).isoformat(),
                payer_id=f'payer-{i%50:03d}',payee_id=f'payee-{i%20:03d}',device_id=f'device-{i%50:03d}',
                amount=f'{100+(i%300)}.00',category='transfer',channel='push')
        for i in range(500):score_transaction(app.extensions['db_factory'],app.extensions['model_store'],payload(i),1)
        server=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}';s=requests.Session()
        csrf=s.get(url+'/api/csrf',timeout=10).json()['csrf_token']
        login=s.post(url+'/api/login',json={'username':'load-admin','password':pw},headers={'X-CSRF-Token':csrf},timeout=10)
        login.raise_for_status();headers={'X-CSRF-Token':login.json()['csrf_token']};cookies=s.cookies.get_dict()
        def one(i):
            # 10% exact replays of seeded rows, 5% invalid inputs, 10% late arrivals.
            row=payload(i+500);expected=201;kind='new'
            if i%20<2:row=payload(i%500);expected=200;kind='duplicate'
            elif i%20==2:row['amount']='-1';expected=422;kind='invalid'
            elif i%20<5:row['timestamp']=(base-timedelta(minutes=10)+timedelta(seconds=i)).isoformat();kind='late'
            start=time.perf_counter()
            try:r=requests.post(url+'/api/transactions',json=row,headers=headers,cookies=cookies,timeout=60);status=r.status_code
            except requests.RequestException:status=0
            return {'ms':1000*(time.perf_counter()-start),'status':status,'expected':expected,'kind':kind}
        start=time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(one,range(a.requests)))
        finally:server.shutdown();thread.join();app.extensions['db_engine'].dispose()
        elapsed=time.perf_counter()-start;lat=sorted(r['ms'] for r in results)
        def quantile(q):return round(lat[min(len(lat)-1,int(q*len(lat)))],2)
        report={'requests':a.requests,'workers':a.workers,'seeded_transactions':500,'elapsed_seconds':round(elapsed,3),
            'throughput_rps':round(a.requests/elapsed,2),'p50_ms':quantile(.5),'p95_ms':quantile(.95),'p99_ms':quantile(.99),'max_ms':round(max(lat),2),
            'status_counts':dict(Counter(str(r['status']) for r in results)),
            'unexpected_responses':sum(r['status']!=r['expected'] for r in results),
            'workload':dict(Counter(r['kind'] for r in results)),
            'configuration':'One threaded Werkzeug process, SQLite WAL, 50 recurring payers, 20 shared recipients; in-memory limiter enabled at 20000/min for this experiment only.',
            'scope':'Includes HTTP, auth, limiter, growing payer/receiver histories, anomaly scoring, commits and contention. No PostgreSQL/Redis/multiworker/network-capacity claim.'}
        Path(a.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        if report['unexpected_responses']:raise SystemExit(1)


if __name__=='__main__':main()
