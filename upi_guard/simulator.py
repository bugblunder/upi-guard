"""Seeded synthetic events. Scenario labels are NOT real-world fraud outcomes."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np


def generate_transactions(n=12000, seed=42, start=None):
    rng = np.random.default_rng(seed)
    start = start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    categories = ["transfer", "grocery", "shopping", "bills", "travel", "food", "other"]
    means = rng.lognormal(6, .8, 180)
    account_ages = rng.integers(2, 2500, 180)
    rows, burst_user, remaining = [], None, 0
    for i in range(n):
        # Last 20% also includes genuinely unseen payer IDs.
        user = int(rng.integers(0, 150 if i < int(n*.8) else 180))
        now = start + timedelta(seconds=i*300)
        scenario = "normal"
        if remaining:
            user, scenario = burst_user, "burst"
            remaining -= 1
            now = parse_iso(rows[-1]["timestamp"]) + timedelta(seconds=40)
        elif rng.random() < .014:
            burst_user, remaining, scenario = user, int(rng.integers(3, 7)), "burst"
        elif rng.random() < .028:
            scenario = "takeover"
        elif rng.random() < .025:
            scenario = "social_engineering"
        elif rng.random() < .06:
            scenario = "legitimate_unusual"
        amount = float(rng.lognormal(np.log(means[user]), .65))
        payee = f"payee-{user}-{int(rng.integers(0, 6))}"
        device = f"device-{user}"
        failed = int(rng.choice([0, 1, 2], p=[.95, .04, .01]))
        fraud_probability = .003
        if scenario == "burst":
            amount *= rng.uniform(1, 5)
            payee = f"payee-burst-{int(rng.integers(0, 80))}"
            fraud_probability = .65
        elif scenario == "takeover":
            amount *= rng.uniform(3, 14)
            device = f"device-new-{user}-{i}"
            payee = f"payee-new-{i}"
            failed = int(rng.integers(0, 9))
            fraud_probability = .85
        elif scenario == "social_engineering":
            payee = f"payee-new-{i}"
            amount *= rng.uniform(1, 6)
            fraud_probability = .65
        elif scenario == "legitimate_unusual":
            amount *= rng.uniform(4, 12)
            device = f"device-new-{user}-{i}" if rng.random() < .35 else device
            payee = f"payee-new-{i}" if rng.random() < .3 else payee
            fraud_probability = .008
        rows.append(dict(transaction_id=f"sim-{seed}-{i:07d}", timestamp=now.isoformat(),
                         payer_id=f"payer-{user:03d}", payee_id=payee, device_id=device,
                         amount=f"{min(amount, 999999):.2f}", category=str(rng.choice(categories)),
                         channel=str(rng.choice(["push", "qr", "collect"], p=[.55, .35, .1])),
                         account_age_days=int(account_ages[user] + (now-start).days),
                         failed_attempts_1h=failed,
                         fraud_label=int(rng.random() < fraud_probability), scenario=scenario))
    return sorted(rows, key=lambda r: (r["timestamp"], r["transaction_id"]))


def parse_iso(value):
    return datetime.fromisoformat(value)


def write_csv(rows, path, labelled=True):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    if not labelled:
        fields = [f for f in fields if f not in ("fraud_label", "scenario")]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
