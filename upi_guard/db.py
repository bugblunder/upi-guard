"""SQLAlchemy persistence, compatible with SQLite and PostgreSQL."""
from datetime import datetime, timezone
from sqlalchemy import (create_engine, event, Column, Integer, String, Text, Float,
                        DateTime, JSON, ForeignKey, Index, Boolean)
from sqlalchemy.orm import declarative_base, sessionmaker

Base=declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__="users"
    id=Column(Integer,primary_key=True)
    username=Column(String(64),unique=True,nullable=False)
    password_hash=Column(Text,nullable=False)
    role=Column(String(16),nullable=False,default="analyst")
    active=Column(Boolean,nullable=False,default=True)


class Transaction(Base):
    __tablename__="transactions"
    id=Column(Integer,primary_key=True)
    transaction_id=Column(String(64),unique=True,nullable=False)
    payload_hash=Column(String(64),nullable=False)
    payer_id=Column(String(64),nullable=False,index=True)
    payee_id=Column(String(64),nullable=False,index=True)
    context=Column(JSON,nullable=False,default=dict)
    event_time=Column(DateTime(timezone=True),nullable=False)
    payload=Column(JSON,nullable=False)
    features=Column(JSON,nullable=False)
    score=Column(Float,nullable=True)
    decision=Column(String(16),nullable=False)
    reasons=Column(JSON,nullable=False)
    model_version=Column(String(128),nullable=False)
    model_status=Column(String(20),nullable=False)
    latency_ms=Column(Float,nullable=False)
    actor_id=Column(Integer,ForeignKey("users.id"),nullable=False)
    created_at=Column(DateTime(timezone=True),default=utcnow,nullable=False)
    __table_args__=(Index("ix_payer_event_time","payer_id","event_time"),
                    Index("ix_payee_event_time","payee_id","event_time"),)


class Case(Base):
    __tablename__="cases"
    id=Column(Integer,primary_key=True)
    transaction_id=Column(Integer,ForeignKey("transactions.id"),unique=True,nullable=False)
    status=Column(String(20),default="open",nullable=False)
    outcome=Column(String(20),nullable=True)
    assigned_to=Column(Integer,ForeignKey("users.id"),nullable=True)
    notes=Column(Text,default="",nullable=False)
    revision=Column(Integer,default=1,nullable=False)
    updated_at=Column(DateTime(timezone=True),default=utcnow,nullable=False)


class AuditEvent(Base):
    __tablename__="audit_events"
    id=Column(Integer,primary_key=True)
    actor_id=Column(Integer,ForeignKey("users.id"),nullable=True)
    action=Column(String(64),nullable=False)
    target=Column(String(128),nullable=False)
    details=Column(JSON,nullable=False,default=dict)
    created_at=Column(DateTime(timezone=True),default=utcnow,nullable=False)


class RateEvent(Base):
    __tablename__="rate_events"
    id=Column(Integer,primary_key=True)
    bucket=Column(String(128),nullable=False,index=True)
    created_at=Column(DateTime(timezone=True),default=utcnow,nullable=False,index=True)


def connect(url):
    kwargs={"pool_pre_ping":True}
    if url.startswith("sqlite"):
        kwargs["connect_args"]={"check_same_thread":False,"timeout":30}
    engine=create_engine(url,**kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine,"connect")
        def configure(conn, record):
            cur=conn.cursor();cur.execute("PRAGMA foreign_keys=ON");cur.execute("PRAGMA journal_mode=WAL");cur.close()
    return engine,sessionmaker(bind=engine,expire_on_commit=False)


def init_db(engine):
    Base.metadata.create_all(engine)


def migrate(url):
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('sqlalchemy.url',url.replace('%','%%'))
    command.upgrade(config,'head')
