"""Atomic scoring with payer serialization and request-id idempotency."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text, or_, func
from sqlalchemy.exc import IntegrityError
from .db import Transaction, Case, AuditEvent
from .schema import TransactionInput
from .features import build_features, FEATURE_VERSION


class Conflict(Exception):
    pass


def assessment(model, features):
    reasons=[]
    if features["count_5m"]>=3: reasons.append({"code":"VELOCITY_5M","text":"At least three earlier payments in five minutes"})
    if features["new_payee"] and features["history_count"]: reasons.append({"code":"NEW_PAYEE","text":"Recipient not seen in the previous 30 days"})
    if features["new_device"] and features["history_count"]: reasons.append({"code":"NEW_DEVICE","text":"Device not seen in the previous 30 days"})
    if features["amount_ratio"]>=5: reasons.append({"code":"UNUSUAL_AMOUNT","text":"Amount at least five times the 30-day median"})
    if features["history_count"]==0: reasons.append({"code":"LIMITED_HISTORY","text":"No earlier payer transactions in the previous 30 days"})
    if model.bundle is None:
        reasons.append({"code":"MODEL_UNAVAILABLE","text":"Model unavailable; manual review required"})
        return None,"review",reasons,"unavailable","unavailable"
    try:
        probability=model.score(features)
        if not 0<=probability<=1: raise ValueError("Invalid probability")
    except Exception:
        reasons.append({"code":"MODEL_UNAVAILABLE","text":"Scoring failed; manual review required"})
        return None,"review",reasons,model.bundle["version"],"unavailable"
    decision="allow"
    if features["history_count"]<5:
        reasons.append({"code":"COLD_START_SHADOW","text":"Fewer than five prior payments: score is experimental; no automated review recommendation"})
    elif probability>=model.bundle["threshold"]:
        decision="review"
        reasons.append({"code":"MODEL_THRESHOLD","text":"Model score exceeds the validation review-budget threshold"})
    if features["receiver_fanin_24h"]>=5:
        reasons.append({"code":"RECEIVER_FANIN","text":"Recipient received from at least five observed payers in 24 hours; contextual signal only"})
    if not reasons: reasons=[{"code":"NO_RULE_FLAGS","text":"No configured rule flags; this does not guarantee legitimacy"}]
    return probability,decision,reasons,model.bundle["version"],"ready"


def lock_payer(session,payer):
    if session.bind.dialect.name=="sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    elif session.bind.dialect.name=="postgresql":
        key=int.from_bytes(hashlib.sha256(payer.encode()).digest()[:8],"big",signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":key})


def serialize(tx, replay=False):
    return {"transaction_id":tx.transaction_id,"timestamp":tx.payload["timestamp"],
            "amount":tx.payload["amount"],"payer":mask(tx.payer_id),"payee":mask(tx.payload["payee_id"]),
            "risk_score":round(tx.score*100,1) if tx.score is not None else None,
            "decision":tx.decision,"reasons":tx.reasons,"model_version":tx.model_version,
            "model_status":tx.model_status,"latency_ms":round(tx.latency_ms,2),"replayed":replay,
            "simulation":True,"context":tx.context or {},
            "decision_meaning":"Review recommendation only; no payment is authorized or blocked"}


def mask(value):
    visible = 3 if len(value) > 6 else 1
    return value[:visible]+"•••"+value[-visible:]


def score_transaction(factory,model,raw,actor_id):
    started=time.perf_counter()
    received_at=datetime.now(timezone.utc)
    tx=TransactionInput.model_validate(raw)
    payload=tx.payload()
    # Decimal spellings such as 100, 100.0 and 100.00 have identical idempotency semantics.
    payload["amount"]=f"{tx.amount:.2f}"
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    with factory() as session:
        try:
            lock_payer(session,tx.payer_id)
            existing=session.scalar(select(Transaction).where(Transaction.transaction_id==tx.transaction_id))
            if existing:
                if existing.payload_hash!=digest: raise Conflict("Transaction ID already exists with different contents")
                return serialize(existing,True)
            latest=session.scalar(select(Transaction).where(Transaction.payer_id==tx.payer_id).order_by(Transaction.event_time.desc()).limit(1))
            late=False
            if latest:
                last=latest.event_time.replace(tzinfo=timezone.utc) if latest.event_time.tzinfo is None else latest.event_time
                late=tx.timestamp<last
            history=session.scalars(select(Transaction).where(or_(Transaction.payer_id==tx.payer_id,Transaction.payee_id.in_([tx.payer_id,tx.payee_id])),
                Transaction.event_time>=tx.timestamp-timedelta(days=30),Transaction.event_time<tx.timestamp)).all()
            features=build_features(payload,[r.payload for r in history])
            score,decision,reasons,version,status=assessment(model,features)
            context={"feature_version":FEATURE_VERSION,"received_at":received_at.isoformat(),
                     "late_arrival":late,"future_clock_skew_seconds":max(0,(tx.timestamp-received_at).total_seconds()),
                     "ignored_caller_fields":["account_age_days","failed_attempts_1h"],
                     "threshold":model.bundle["threshold"] if model.bundle else None,
                     "score_margin":score-model.bundle["threshold"] if score is not None and model.bundle else None,
                     "cold_start_shadow":features["history_count"]<5}
            if model.bundle and "anomaly" in model.bundle:
                try:
                    import pandas as pd
                    from .features import FEATURES
                    z=model.bundle["pipeline"].named_steps["preprocess"].transform(pd.DataFrame([features])[FEATURES])
                    anomaly=float(-model.bundle["anomaly"].score_samples(z)[0])
                    context["anomaly"]={"score":anomaly,"flag":anomaly>=model.bundle["anomaly_threshold"],"mode":"shadow"}
                except Exception:context["anomaly"]={"status":"unavailable","mode":"shadow"}
            item=Transaction(transaction_id=tx.transaction_id,payload_hash=digest,payer_id=tx.payer_id,
                event_time=tx.timestamp,payee_id=tx.payee_id,context=context,payload=payload,features=features,score=score,decision=decision,
                reasons=reasons,model_version=version,model_status=status,
                latency_ms=(time.perf_counter()-started)*1000,actor_id=actor_id)
            session.add(item);session.flush()
            if decision!="allow": session.add(Case(transaction_id=item.id))
            session.add(AuditEvent(actor_id=actor_id,action="transaction.scored",target=tx.transaction_id,
                                   details={"decision":decision,"model_version":version,"model_status":status}))
            session.commit()
            return serialize(item)
        except IntegrityError:
            session.rollback()
            # Covers races where the same ID arrives with two different payer IDs.
            existing=session.scalar(select(Transaction).where(Transaction.transaction_id==tx.transaction_id))
            if existing and existing.payload_hash==digest: return serialize(existing,True)
            raise Conflict("Transaction ID collision")
