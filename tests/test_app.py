import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from upi_guard.db import Transaction,Case,AuditEvent,User
from upi_guard.features import build_features
from upi_guard.ml import ModelStore
from upi_guard.scoring import score_transaction
from conftest import login


def test_authentication_required(client):
    for path in ['/api/transactions','/api/cases','/api/model','/api/drift','/api/feedback.csv']:
        assert client.get(path).status_code==401
    assert client.get('/').status_code==302


def test_no_default_login_and_csrf(client):
    assert client.post('/api/login',json={'username':'admin','password':'admin'}).status_code==403
    token=client.get('/api/csrf').json['csrf_token']
    assert client.post('/api/login',json={'username':'admin','password':'admin'},headers={'X-CSRF-Token':token}).status_code==401


def test_login_rate_limit(app,client):
    app.config['RATE_LIMIT_ENABLED']=True
    token=client.get('/api/csrf').json['csrf_token']
    codes=[client.post('/api/login',json={'username':'nobody','password':'incorrect'},headers={'X-CSRF-Token':token}).status_code for _ in range(9)]
    assert codes[:8]==[401]*8 and codes[8]==429


def test_login_rotation_logout(authenticated):
    client,h=authenticated
    assert client.post('/api/logout').status_code==403
    assert client.post('/api/logout',headers=h).status_code==200
    assert client.get('/api/transactions').status_code==401


def test_disabled_user_loses_access(app,authenticated):
    client,h=authenticated
    with app.extensions['db_factory']() as db:
        user=db.scalar(select(User).where(User.username=='admin'));user.active=False;db.commit()
    assert client.get('/api/transactions').status_code==401


def test_headers_and_dashboard(authenticated):
    client,h=authenticated;r=client.get('/')
    assert r.status_code==200 and b'Investigation queue' in r.data
    assert "script-src 'self'" in r.headers['Content-Security-Policy']
    assert r.headers['X-Frame-Options']=='DENY'
    assert 'no-store' in r.headers['Cache-Control']


def test_score_invalid_and_missing(authenticated,payload):
    client,h=authenticated
    assert client.post('/api/transactions',json=payload).status_code==403
    assert client.post('/api/transactions',json={},headers=h).status_code==422
    assert client.post('/api/transactions',json={**payload,'amount':'-5'},headers=h).status_code==422


def test_score_idempotency_conflict_and_audit(app,authenticated,payload):
    client,h=authenticated
    first=client.post('/api/transactions',json=payload,headers=h)
    assert first.status_code==201 and first.json['model_status']=='ready'
    replay=client.post('/api/transactions',json={**payload,'amount':'500.0'},headers=h)
    assert replay.status_code==200 and replay.json['replayed'] is True
    assert replay.json['risk_score']==first.json['risk_score']
    assert client.post('/api/transactions',json={**payload,'amount':'501.00'},headers=h).status_code==409
    with app.extensions['db_factory']() as db:
        assert db.scalar(select(func.count()).select_from(Transaction))==1
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='transaction.scored'))==1


def test_parallel_duplicate_only_one_commit(app,payload):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:score_transaction(app.extensions['db_factory'],app.extensions['model_store'],payload,1),range(4)))
    assert sum(not r['replayed'] for r in results)==1
    with app.extensions['db_factory']() as db:assert db.scalar(select(func.count()).select_from(Transaction))==1


def test_online_offline_feature_parity_and_order(app,authenticated,payload):
    client,h=authenticated
    before={**payload,'transaction_id':'earlier','timestamp':'2025-01-01T11:58:00Z','amount':'100.00'}
    assert client.post('/api/transactions',json=before,headers=h).status_code==201
    assert client.post('/api/transactions',json=payload,headers=h).status_code==201
    with app.extensions['db_factory']() as db:
        saved=db.scalar(select(Transaction).where(Transaction.transaction_id==payload['transaction_id']))
        assert saved.features==build_features(payload,[before])
    stale={**before,'transaction_id':'stale-event'}
    late=client.post('/api/transactions',json=stale,headers=h)
    assert late.status_code==201 and late.json['context']['late_arrival']


def test_model_failure_requires_review(app,authenticated,payload,tmp_path):
    client,h=authenticated;app.extensions['model_store']=ModelStore(tmp_path/'missing')
    assert client.get('/health/ready').status_code==503
    r=client.post('/api/transactions',json=payload,headers=h)
    assert r.status_code==201 and r.json['decision']=='review' and r.json['risk_score'] is None
    assert any(x['code']=='MODEL_UNAVAILABLE' for x in r.json['reasons'])
    assert client.get('/api/cases').json['total']==1


def test_runtime_prediction_failure_requires_review(app,authenticated,payload,monkeypatch):
    def broken(_):raise RuntimeError('test outage')
    monkeypatch.setattr(app.extensions['model_store'],'score',broken)
    client,h=authenticated;r=client.post('/api/transactions',json=payload,headers=h)
    assert r.json['decision']=='review' and r.json['model_status']=='unavailable'


def csv_upload(client,h,rows):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return client.post('/api/import',data={'file':(io.BytesIO(out.getvalue().encode()),'input.csv')},headers=h)


def test_csv_prevalidation_no_partial_write(authenticated,payload):
    client,h=authenticated;r=csv_upload(client,h,[payload,{**payload,'transaction_id':'bad-row','amount':'-1'}])
    assert r.status_code==422 and r.json['errors'][0]['row']==3
    assert client.get('/api/transactions').json['total']==0


def test_csv_valid_and_conflicting_rows(authenticated,payload):
    client,h=authenticated;r=csv_upload(client,h,[payload,{**payload,'amount':'600.00'}])
    assert r.status_code==200 and r.json['conflicts']==1
    assert client.get('/api/transactions').json['total']==1


def test_csv_rejects_legacy_schema_and_oversize(app,authenticated,payload):
    client,h=authenticated
    assert csv_upload(client,h,[{'Id':'1','fraud_risk':'0'}]).status_code==422
    app.config['MAX_CONTENT_LENGTH']=200
    assert client.post('/api/import',data={'file':(io.BytesIO(b'a'*500),'big.csv')},headers=h).status_code==413


def test_analyst_cannot_import_or_export(client,payload):
    h=login(client,'analyst')
    assert csv_upload(client,h,[payload]).status_code==403
    assert client.get('/api/feedback.csv').status_code==403
    assert client.get('/api/audit').status_code==403


def test_case_resolution_concurrency_history_feedback(authenticated,payload):
    client,h=authenticated
    client.post('/api/transactions',json={**payload,'failed_attempts_1h':5},headers=h)
    assert client.post('/api/transactions/'+payload['transaction_id']+'/review',headers=h).status_code==200
    case=client.get('/api/cases').json['items'][0]
    body={'revision':case['revision'],'status':'resolved','outcome':'fraud','assigned_to':1,'notes':'Confirmed synthetic incident'}
    r=client.patch(f"/api/cases/{case['id']}",json=body,headers=h)
    assert r.status_code==200 and r.json['revision']==2
    assert client.patch(f"/api/cases/{case['id']}",json=body,headers=h).status_code==409
    history=client.get(f"/api/cases/{case['id']}/history").json['items']
    assert len(history)==2 and history[-1]['details']['after']['outcome']=='fraud'
    feedback=client.get('/api/feedback.csv')
    assert feedback.status_code==200 and b'fraud_label' in feedback.data and b'test-0001' in feedback.data


def test_analyst_assignment_boundaries(client,payload):
    h=login(client)
    client.post('/api/transactions',json={**payload,'failed_attempts_1h':5},headers=h)
    assert client.post('/api/transactions/'+payload['transaction_id']+'/review',headers=h).status_code==200
    case=client.get('/api/cases').json['items'][0]
    h=login(client,'analyst')
    body={'revision':1,'status':'investigating','assigned_to':1,'notes':'test'}
    assert client.patch(f"/api/cases/{case['id']}",json=body,headers=h).status_code==403
    body['assigned_to']=2
    assert client.patch(f"/api/cases/{case['id']}",json=body,headers=h).status_code==200


def test_resolution_requires_label(authenticated,payload):
    client,h=authenticated;client.post('/api/transactions',json={**payload,'failed_attempts_1h':5},headers=h)
    assert client.post('/api/transactions/'+payload['transaction_id']+'/review',headers=h).status_code==200
    case=client.get('/api/cases').json['items'][0]
    assert client.patch(f"/api/cases/{case['id']}",json={'revision':1,'status':'resolved','assigned_to':1},headers=h).status_code==422


def test_query_input_does_not_change_sql(authenticated):
    client,h=authenticated
    assert client.get('/api/transactions',query_string={'q':"' OR 1=1 --"}).status_code==200
    assert client.get('/api/transactions?page=nope').status_code==422
    assert client.get('/api/cases?status=invalid').status_code==422


@pytest.mark.parametrize('endpoint', ['/api/transactions', '/api/cases'])
def test_pagination_rejects_out_of_range_offsets(authenticated, endpoint):
    client, _ = authenticated
    for page in ('0', '-1', '1000001', '9999999999999999999999999999'):
        assert client.get(endpoint, query_string={'page': page}).status_code == 422


def test_monitor_small_sample(authenticated):
    client,h=authenticated
    assert client.get('/api/drift').json['status']=='insufficient_data'
    report=client.get('/api/model').json['report']
    assert report['data_kind']=='synthetic only'
    splits=report['splits']
    assert splits['train']['last']<splits['calibration']['first']<splits['validation']['first']<splits['test']['first']
