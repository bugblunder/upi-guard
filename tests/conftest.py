import os
from pathlib import Path
import pytest
from upi_guard import create_app
from upi_guard.db import init_db
from upi_guard.__main__ import add_user

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path):
    app=create_app({"TESTING":True,"SECRET_KEY":"test-secret-not-for-production-123456789",
        "DATABASE_URL":f"sqlite:///{tmp_path/'test.db'}","ARTIFACT_ROOT":str(ROOT/'artifacts'),
        "RATE_LIMIT_ENABLED":False,"TRUSTED_HOSTS":["localhost"]})
    init_db(app.extensions['db_engine'])
    add_user(app,'admin','admin','Test-admin-password-2026')
    add_user(app,'analyst','analyst','Test-analyst-password-2026')
    yield app
    app.extensions['db_engine'].dispose()


@pytest.fixture
def client(app):return app.test_client()


def login(client,name='admin'):
    token=client.get('/api/csrf').json['csrf_token']
    r=client.post('/api/login',json={'username':name,'password':f'Test-{name}-password-2026'},headers={'X-CSRF-Token':token})
    assert r.status_code==200,r.json
    return {'X-CSRF-Token':r.json['csrf_token']}


@pytest.fixture
def authenticated(client):return client,login(client)


@pytest.fixture
def payload():
    return dict(transaction_id='test-0001',timestamp='2025-01-01T12:00:00+00:00',payer_id='payer-test',
        payee_id='payee-test',device_id='device-test',amount='500.00',category='grocery',channel='qr',
        account_age_days=365,failed_attempts_1h=0)
