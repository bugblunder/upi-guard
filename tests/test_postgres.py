"""Optional integration gate: use only an isolated test database, e.g. CI service."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import select,func
from upi_guard import create_app
from upi_guard.db import migrate,Transaction
from upi_guard.__main__ import add_user
from upi_guard.scoring import score_transaction


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='No isolated PostgreSQL test service available')
def test_postgres_migration_and_concurrent_idempotency():
    url=os.environ['TEST_DATABASE_URL']
    if not url.split('?')[0].endswith('/guard_test'):pytest.fail('Use an isolated guard_test database')
    migrate(url)
    app=create_app({'DATABASE_URL':url,'SECRET_KEY':'integration-test-only-123456789012345',
                    'ARTIFACT_ROOT':str(Path(__file__).resolve().parents[1]/'artifacts')})
    username='pg-'+uuid.uuid4().hex[:12]
    add_user(app,username,'admin','Integration-test-password-2026')
    from upi_guard.db import User
    with app.extensions['db_factory']() as db:actor=db.scalar(select(User.id).where(User.username==username))
    payload=dict(transaction_id=username,timestamp='2025-01-01T12:00:00Z',payer_id=username,
        payee_id='pg-payee',device_id='pg-device',amount='100.00',category='food',channel='qr',account_age_days=10,failed_attempts_1h=0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(lambda _:score_transaction(app.extensions['db_factory'],app.extensions['model_store'],payload,actor),range(4)))
    assert sum(not r['replayed'] for r in result)==1
    with app.extensions['db_factory']() as db:assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.transaction_id==username))==1
    app.extensions['db_engine'].dispose()
