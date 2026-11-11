from sqlalchemy import create_engine,inspect,text
from upi_guard.db import migrate


def test_fresh_schema_and_repeat_migration(tmp_path):
    url=f"sqlite:///{tmp_path/'migration.db'}"
    migrate(url);migrate(url)
    engine=create_engine(url)
    assert set(['users','transactions','cases','audit_events','rate_events','alembic_version']).issubset(inspect(engine).get_table_names())
    with engine.connect() as conn:assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0002'
    engine.dispose()


def test_existing_v2_transaction_backfill(tmp_path):
    import json
    from pathlib import Path
    from alembic.config import Config
    from alembic import command
    root=Path(__file__).resolve().parents[1]
    url=f"sqlite:///{tmp_path/'old.db'}"
    config=Config(str(root/'alembic.ini'));config.set_main_option('sqlalchemy.url',url)
    command.upgrade(config,'0001')
    engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,username,password_hash,role,active) VALUES (1,'old','unused','admin',1)"))
        conn.execute(text("INSERT INTO transactions (id,transaction_id,payload_hash,payer_id,event_time,payload,features,score,decision,reasons,model_version,model_status,latency_ms,actor_id,created_at) VALUES (1,'old-id','hash','payer','2025-01-01',:payload,'{}',0.1,'allow','[]','old-version','ready',1,1,'2025-01-01')"),{'payload':json.dumps({'payee_id':'recipient'})})
    migrate(url)
    with engine.connect() as conn:
        row=conn.execute(text('SELECT payee_id,context FROM transactions')).first()
        assert row[0]=='recipient' and json.loads(row[1])['legacy'] is True
    engine.dispose()
