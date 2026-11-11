import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from werkzeug.exceptions import ServiceUnavailable
from upi_guard.schema import TransactionInput
from upi_guard.features import build_features, feature_rows, FEATURE_VERSION
from upi_guard.evaluation import capacity_threshold, prevalence_table
from upi_guard.limiting import Limiter, TrustedProxy
from upi_guard.monitoring import reference_profile, drift_summary
from upi_guard.db import Transaction, RateEvent
from upi_guard.scoring import assessment
from upi_guard.explanations import explain
from upi_guard.feedback import FIELDS, load_snapshot, merge_feedback, train_snapshot
from upi_guard.simulator import generate_transactions
from conftest import login


def test_clock_skew_tolerance(payload):
    now=datetime.now(timezone.utc)
    for seconds in (3,299):
        assert TransactionInput.model_validate({**payload,'timestamp':(now+timedelta(seconds=seconds)).isoformat()})
    with pytest.raises(ValidationError):
        TransactionInput.model_validate({**payload,'timestamp':(now+timedelta(seconds=301)).isoformat()})


def test_caller_hints_do_not_change_features_or_score(app,payload):
    f=build_features(payload,[])
    other=build_features({**payload,'account_age_days':0,'failed_attempts_1h':1000},[])
    assert f==other
    assert app.extensions['model_store'].score(f)==app.extensions['model_store'].score(other)
    assert 'failed_attempts_1h' not in f and 'account_age_days' not in f


def test_graph_features_and_future_exclusion(payload):
    # Two distinct senders paid the recipient; a third funded the payer.
    rows=[{**payload,'transaction_id':'old-1','payer_id':'source-a','timestamp':'2025-01-01T11:30:00Z'},
          {**payload,'transaction_id':'old-2','payer_id':'source-b','timestamp':'2025-01-01T11:40:00Z'},
          {**payload,'transaction_id':'old-3','payer_id':'source-c','payee_id':payload['payer_id'],'amount':'1000.00','timestamp':'2025-01-01T11:50:00Z'}]
    f=build_features(payload,rows)
    assert f['receiver_fanin_24h']==2 and f['payer_incoming_count_1h']==1 and f['pass_through_ratio_1h']==.5
    assert f==feature_rows(rows+[payload])[-1]
    assert build_features(payload,rows+[{**rows[0],'payer_id':'future-payer','timestamp':'2025-01-01T12:01:00Z'}])==f


def test_late_event_does_not_rewrite_previous_snapshot(app,authenticated,payload):
    client,h=authenticated
    client.post('/api/transactions',json=payload,headers=h)
    late={**payload,'transaction_id':'late-123','timestamp':'2025-01-01T11:00:00Z'}
    r=client.post('/api/transactions',json=late,headers=h)
    assert r.status_code==201 and r.json['context']['late_arrival']
    with app.extensions['db_factory']() as db:
        first=db.scalar(select(Transaction).where(Transaction.transaction_id==payload['transaction_id']))
        older=db.scalar(select(Transaction).where(Transaction.transaction_id=='late-123'))
        assert first.features['history_count']==0 and older.features['history_count']==0


def test_no_automatic_decline_even_at_max_score(app,payload,monkeypatch):
    store=app.extensions['model_store'];monkeypatch.setattr(store,'score',lambda _:1.)
    f=build_features(payload,[])
    assert assessment(store,f)[1]=='allow' # explicitly shadow, never payment authorization
    assert assessment(store,{**f,'history_count':5})[1]=='review'


def test_shap_reconstructs_calibrated_probability(app,authenticated,payload):
    client,h=authenticated;client.post('/api/transactions',json=payload,headers=h)
    r=client.get('/api/transactions/'+payload['transaction_id']+'/explanation')
    assert r.status_code==200,r.json
    assert r.json['method']=='SHAP' and r.json['reconstruction_error']<1e-6
    assert abs(r.json['calibrated_probability']-app.extensions['model_store'].score(build_features(payload,[])))<1e-6


def test_budget_ties_and_prevalence_arithmetic():
    p=np.array([.1,.8,.8,.9]);t=capacity_threshold(p,.5)
    assert np.sum(p>=t)<=2
    row=prevalence_table(.9662447257,.1086453999,[.01])[0]
    assert row['precision']==pytest.approx(.0824306,abs=1e-5)


def test_redis_limiter_atomic_across_clients():
    import fakeredis
    server=fakeredis.FakeServer()
    a=Limiter();b=Limiter()
    a.redis=fakeredis.FakeRedis(server=server);b.redis=fakeredis.FakeRedis(server=server)
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed=list(pool.map(lambda i:(a if i%2 else b).allowed('same',10,60),range(40)))
    assert sum(allowed)==10
    assert a.allowed('different',1,60)


def test_redis_failure_returns_unavailable():
    class Broken:
        def eval(self,*args):raise ConnectionError()
    limiter=Limiter();limiter.redis=Broken()
    with pytest.raises(ServiceUnavailable):limiter.allowed('key',1,60)


def test_limiter_does_not_write_sql(app):
    app.config['RATE_LIMIT_ENABLED']=True
    from upi_guard import rate_allowed
    with app.app_context():
        assert all(rate_allowed('test',5) for _ in range(5))
        assert not rate_allowed('test',5)
    with app.extensions['db_factory']() as db:
        assert db.scalar(select(func.count()).select_from(RateEvent))==0


def test_proxy_headers_only_trusted_from_configured_peer():
    seen=[]
    def terminal(env,start):seen.append(env['REMOTE_ADDR']);return []
    proxy=TrustedProxy(terminal,['10.0.0.0/24'],1)
    proxy({'REMOTE_ADDR':'10.0.0.5','HTTP_X_FORWARDED_FOR':'198.51.100.9'},None)
    proxy({'REMOTE_ADDR':'203.0.113.5','HTTP_X_FORWARDED_FOR':'198.51.100.9'},None)
    assert seen==['198.51.100.9','203.0.113.5']


def test_equal_mean_variance_shift_and_category_change():
    reference={'x':{'kind':'numeric','mean':0.,'std':1.,'edges':[None,-1.,0.,1.,None],
                    'counts':[0,100,0,100],'sample':[-1.,1.]*100},
               'category':{'kind':'categorical','counts':{'grocery':200}}}
    rows=[{'x':-10. if i%2 else 10.,'category':'unseen'} for i in range(200)]
    d=drift_summary(rows,reference)
    assert all(x['flag'] for x in d['features'])
    assert d['features'][0]['standardized_mean_shift']==0
    assert d['features'][1]['unseen_rate']==1


def test_feedback_export_merges_frozen_features(authenticated,payload,tmp_path):
    client,h=authenticated;client.post('/api/transactions',json=payload,headers=h)
    c=client.post('/api/transactions/'+payload['transaction_id']+'/review',headers=h).json
    r=client.patch('/api/cases/'+str(c['id']),json={'revision':1,'status':'resolved','outcome':'fraud','assigned_to':1},headers=h)
    assert r.status_code==200
    feedback=tmp_path/'feedback.csv';feedback.write_bytes(client.get('/api/feedback.csv').data)
    loaded=load_snapshot(feedback);assert loaded[payload['transaction_id']]['label']==1
    features=loaded[payload['transaction_id']]['features']
    assert features==build_features(payload,[])
    out=tmp_path/'merged.csv';report=merge_feedback(feedback,feedback,out)
    assert report['rows']==1 and load_snapshot(out)[payload['transaction_id']]['features']==features
    broken=feedback.read_text().replace(FEATURE_VERSION,'wrong-version');feedback.write_text(broken)
    with pytest.raises(ValueError,match='version'):load_snapshot(feedback)


def test_snapshot_training_consumes_export_contract_without_activation(tmp_path):
    rows=generate_transactions(2000,77);features=feature_rows(rows)
    file=tmp_path/'snapshot.csv'
    with file.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for row,feature in zip(rows,features):
            tx={k:v for k,v in row.items() if k not in ('scenario','fraud_label')}
            writer.writerow(dict(transaction_json=json.dumps(tx),features_json=json.dumps(feature),
                feature_version=FEATURE_VERSION,fraud_label=row['fraud_label'],label_available_at=row['timestamp'],source='synthetic_test'))
    report=train_snapshot(file,tmp_path/'candidate')
    assert report['feature_version']==FEATURE_VERSION
    assert not (tmp_path/'candidate'/'active.json').exists()
    assert (tmp_path/'candidate'/report['version']/'training_snapshot.csv').exists()


def test_drift_report_is_json_serializable_with_current_reference(app):
    rows=feature_rows(generate_transactions(60,5))
    report=drift_summary(rows,app.extensions['model_store'].report['reference_features'])
    json.dumps(report,allow_nan=False)
