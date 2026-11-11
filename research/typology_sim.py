"""Transparent transaction-level stress test, not a model of actual UPI traffic.

Weeks are zero-based. All arms share random draws; before week 14 they are
identical. The drift arm changes the fraud-family mix at week 14, then reduces
amount/device/recipient anomalies from week 18. Labels never drive features.
Legitimate merchants also receive and forward funds, confounding mule signals.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import numpy as np


@dataclass(frozen=True)
class SimConfig:
    weeks: int = 24
    episodes_per_week: int = 240
    fraud_episode_rate: float = .04
    drift_week: int = 14
    adaptation_week: int = 18
    adaptation_strength: float = .8
    label_flip_rate: float = .005
    seed: int = 0

    def __post_init__(self):
        if self.weeks < 20 or self.episodes_per_week < 10:
            raise ValueError('Need at least 20 weeks and 10 episodes/week')
        if not 12 <= self.drift_week < self.adaptation_week < self.weeks:
            raise ValueError('Need 12 <= drift < adaptation < weeks')
        if not 0 < self.fraud_episode_rate < .5:
            raise ValueError('fraud_episode_rate must be in (0, .5)')
        if not 0 <= self.adaptation_strength <= 1 or not 0 <= self.label_flip_rate < .5:
            raise ValueError('Invalid adaptation strength or label noise')


def generate(config=SimConfig(), control=False):
    rng = np.random.default_rng(config.seed)
    start = datetime(2025, 1, 6, tzinfo=timezone.utc)
    means = rng.lognormal(6.5, .65, 120)
    rows = []
    for week in range(config.weeks):
        for episode in range(config.episodes_per_week):
            # Draw a full event plan regardless of arm/scenario to preserve pairing.
            u = rng.random(21)
            noise = rng.random(3)
            users = rng.integers(0, 120, 3)
            hub_index = int(rng.integers(0, 8))
            familiar = rng.integers(0, 6, 3)
            amounts = np.clip(rng.lognormal(np.log(means[users]), .65), 1, 70000)
            fraud = u[0] < config.fraud_episode_rate
            changed = not control and week >= config.drift_week
            adapted = not control and week >= config.adaptation_week
            mule = fraud and u[1] < (.75 if changed else .15)
            merchant = not fraud and u[2] < .35
            strength = config.adaptation_strength if adapted else 0.
            # New recipient/device are noisy signals in BOTH legitimate and fraud traffic.
            anomaly = 1 - strength
            if fraud and not mule:
                amounts *= 1 + 3 * anomaly
            group = 'mule' if mule else 'takeover' if fraud else 'merchant' if merchant else 'legitimate'
            hub = f'mule-{hub_index:02}' if mule else f'merchant-{hub_index:02}'
            base = start + timedelta(weeks=week, seconds=(episode+.15)*604800/config.episodes_per_week)
            total_in = float(amounts[0]+amounts[1])
            for j in range(3):
                user = int(users[j])
                payer = f'user-{user:03}'
                novel_payee = u[3+j] < (.35 + .45*anomaly if fraud else .35)
                payee = f'new-{week}-{episode}-{j}' if novel_payee else f'contact-{user}-{familiar[j]}'
                new_device = u[6+j] < (.08 + .7*anomaly if fraud and not mule else .08)
                device = f'device-alt-{user}-{week}-{episode}' if new_device else f'device-{user}'
                amount = float(amounts[j])
                category = 'transfer' if u[9+j] < .65 else 'shopping'
                channel = 'collect' if u[12+j] < .15 else 'push' if u[12+j] < .75 else 'qr'
                if mule or merchant:
                    if j < 2:
                        payee = hub
                        category = 'transfer' if mule else 'shopping'
                    else:
                        payer, payee, device = hub, f'settlement-{hub_index%3}', f'device-{hub}'
                        amount = total_in * (.85 + .14*u[15])
                        category, channel = 'transfer', 'push'
                # Scenarios are latent planned causes. Outcomes sampled independently.
                positive = fraud and u[18+j] < .9
                target = int(positive)
                # Symmetric adjudication noise is a deliberate sensitivity parameter.
                flip_draw = float(noise[j])
                observed = target ^ int(flip_draw < config.label_flip_rate)
                rows.append(dict(transaction_id=f'res-{config.seed}-{week:02}-{episode:04}-{j}',
                    timestamp=(base+timedelta(seconds=30*j)).isoformat(),
                    payer_id=payer, payee_id=payee, device_id=device,
                    amount=f'{min(amount, 999999):.2f}', category=category, channel=channel,
                    fraud_label=target, observed_label=observed, scenario=group,
                    week=week, event_week=week+(episode+.15)/config.episodes_per_week+30*j/604800))
    return rows


def configuration(config):
    return asdict(config)
