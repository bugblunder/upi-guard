"""Shared point-in-time features. Only observed payments enter these features."""
from collections import defaultdict
from datetime import datetime, timedelta
from math import log1p, sin, cos, pi
import numpy as np

NUMERIC = ["log_amount", "count_5m", "count_1h", "log_sum_1h", "amount_ratio",
           "new_payee", "new_device", "distinct_payees_1h", "history_count",
           "observed_history_days", "cold_start", "hour_sin", "hour_cos",
           "receiver_fanin_24h", "payer_incoming_count_1h", "pass_through_ratio_1h"]
CATEGORICAL = ["category", "channel"]
FEATURES = NUMERIC + CATEGORICAL
FEATURE_VERSION = "2.1.0"


def parse_time(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_features(tx, history):
    now = parse_time(tx["timestamp"])
    available = [p for p in history if now-timedelta(days=30) <= parse_time(p["timestamp"]) < now]
    past = [p for p in available if p["payer_id"] == tx["payer_id"]]
    hour = [p for p in past if parse_time(p["timestamp"]) >= now-timedelta(hours=1)]
    five = [p for p in hour if parse_time(p["timestamp"]) >= now-timedelta(minutes=5)]
    incoming = [p for p in available if p["payee_id"] == tx["payer_id"]
                and parse_time(p["timestamp"]) >= now-timedelta(hours=1)]
    receiver = [p for p in available if p["payee_id"] == tx["payee_id"]
                and parse_time(p["timestamp"]) >= now-timedelta(days=1)]
    amount = float(tx["amount"])
    median = float(np.median([float(p["amount"]) for p in past])) if past else amount
    incoming_sum = sum(float(p["amount"]) for p in incoming)
    local_hour = (now.hour + now.minute/60 + 5.5) % 24
    return dict(log_amount=log1p(amount), count_5m=len(five), count_1h=len(hour),
                log_sum_1h=log1p(sum(float(p["amount"]) for p in hour)),
                amount_ratio=min(amount/max(median, 1), 100),
                new_payee=int(bool(past) and not any(p["payee_id"] == tx["payee_id"] for p in past)),
                new_device=int(bool(past) and not any(p["device_id"] == tx["device_id"] for p in past)),
                distinct_payees_1h=len({p["payee_id"] for p in hour}), history_count=len(past),
                observed_history_days=(now-min(parse_time(p["timestamp"]) for p in past)).total_seconds()/86400 if past else 0.,
                cold_start=int(not past), hour_sin=sin(2*pi*local_hour/24), hour_cos=cos(2*pi*local_hour/24),
                receiver_fanin_24h=len({p["payer_id"] for p in receiver}),
                payer_incoming_count_1h=len(incoming),
                pass_through_ratio_1h=min(amount/incoming_sum, 100) if incoming_sum else 0.,
                category=tx["category"], channel=tx["channel"])


def feature_rows(transactions):
    """Process in arrival order; filter history by event time for each row.

    Training normally passes chronological rows. An arrival replay must pass
    ingestion order. Late arrivals never rewrite previous feature snapshots.
    """
    outgoing, incoming, rows = defaultdict(list), defaultdict(list), []
    for tx in transactions:
        relevant = {p["transaction_id"]: p for p in
                    outgoing[tx["payer_id"]]+incoming[tx["payer_id"]]+incoming[tx["payee_id"]]}
        rows.append(build_features(tx, relevant.values()))
        outgoing[tx["payer_id"]].append(tx)
        incoming[tx["payee_id"]].append(tx)
    return rows
