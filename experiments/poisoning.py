"""Matched label-corruption stress test; no application model is changed.

The attacker can flip a bounded subset of initial training labels, but cannot
change features, evaluation labels, the review budget, or the test partition.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from research.shared import features as ft
from research.study import fit_model, interval, metric
from research.typology_sim import SimConfig, configuration, generate

ROOT = Path(__file__).resolve().parents[1]
FRACTIONS = (0.1, 0.3, 0.5)
REGIMES = ("clean",) + tuple(f"{kind}_{fraction:g}" for fraction in FRACTIONS
                            for kind in ("targeted", "random"))


def corrupt_labels(labels, fraction, kind, seed):
    """Random control flips exactly as many labels as the targeted attack.

    Fractions refer to observed POSITIVE training labels, not all training rows.
    Selection is uniform within the permitted set, independent of test outcomes.
    """
    original = np.asarray(labels)
    if original.ndim != 1 or not np.isin(original, [0, 1]).all():
        raise ValueError("Expected a one-dimensional binary label vector")
    if not np.isfinite(fraction) or not 0 <= fraction < 1:
        raise ValueError("fraction must be in [0,1)")
    if kind not in ("targeted", "random"):
        raise ValueError("Unknown corruption strategy")
    positive = np.flatnonzero(original == 1)
    count = int(len(positive) * fraction)
    candidates = positive if kind == "targeted" else np.arange(len(original))
    # A fixed permutation gives nested subsets across increasing budgets.
    selected = np.random.default_rng(seed).permutation(candidates)[:count]
    result = original.astype(int, copy=True)
    result[selected] = 1 - result[selected]
    return result, selected


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(frame):
    metrics = ["recall", "average_precision", "precision", "brier"]
    seed_means = frame.groupby(["seed", "arm", "model", "regime", "phase"])[metrics].mean().reset_index()
    estimates, paired = [], []
    for keys, group in seed_means.groupby(["arm", "model", "regime", "phase"]):
        for name in metrics:
            values = group[name].dropna()
            if len(values):
                estimates.append(dict(zip(["arm", "model", "regime", "phase"], keys),
                                      metric=name, **interval(values)))
    for keys, group in seed_means.groupby(["arm", "model", "phase"]):
        for name in metrics:
            pivot = group.pivot(index="seed", columns="regime", values=name)
            for regime in REGIMES[1:]:
                delta = (pivot[regime] - pivot["clean"]).dropna()
                if len(delta):
                    paired.append(dict(zip(["arm", "model", "phase"], keys),
                                       regime=regime, metric=name, **interval(delta)))
            for fraction in FRACTIONS:
                delta = (pivot[f"targeted_{fraction:g}"] - pivot[f"random_{fraction:g}"]).dropna()
                if len(delta):
                    paired.append(dict(zip(["arm", "model", "phase"], keys),
                                       regime=f"targeted_minus_random_{fraction:g}",
                                       metric=name, **interval(delta)))
    return pd.DataFrame(estimates), pd.DataFrame(paired)


def run(out, seeds, episodes=240, models=("hgb", "lr"), budget=.05):
    if not seeds or len(set(seeds)) != len(seeds) or any(s < 0 for s in seeds):
        raise ValueError("Use unique non-negative seeds")
    if not 0 < budget <= 1 or not models or not set(models) <= {"hgb", "lr"}:
        raise ValueError("Invalid review budget or learners")
    config = SimConfig(episodes_per_week=episodes)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT / "research/study.py", ROOT / "research/shared.py",
               ROOT / "research/typology_sim.py", ROOT / "upi_guard/features.py",
               ROOT / "upi_guard/monitoring.py"]
    protocol = dict(schema_version=1, simulator=configuration(config), seeds=seeds,
                    models=list(models), arms=["control", "drift"], budget=budget,
                    regimes=list(REGIMES), positive_label_fractions=list(FRACTIONS),
                    train_weeks=[5, 6, 7, 8], evaluation_weeks=list(range(12, 24)),
                    label_delay_weeks=0, python=platform.python_version(),
                    numpy=np.__version__, pandas=pd.__version__, sklearn=sklearn.__version__,
                    source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
                    uncertainty="Descriptive 95% t intervals across paired seed means; exploratory, no multiplicity correction.",
                    threat="Initial training-label corruption only; immutable features and latent test truth. No adversarial input optimization.")
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    records, corruption = [], []
    with threadpool_limits(limits=1):
        for seed in seeds:
            for arm in protocol["arms"]:
                print(f"poisoning seed={seed} arm={arm}", flush=True)
                rows = generate(SimConfig(episodes_per_week=episodes, seed=seed), control=arm == "control")
                x = pd.DataFrame(ft.feature_rows(rows))[ft.FEATURES]
                weeks = np.array([r["week"] for r in rows])
                truth = np.array([r["fraud_label"] for r in rows])
                observed = np.array([r["observed_label"] for r in rows])
                amounts = np.array([float(r["amount"]) for r in rows])
                groups = np.array([r["scenario"] for r in rows])
                train = (weeks >= 5) & (weeks < 9)
                labels = {"clean": (observed[train].copy(), np.array([], dtype=int))}
                for fraction in FRACTIONS:
                    for kind in ("targeted", "random"):
                        labels[f"{kind}_{fraction:g}"] = corrupt_labels(observed[train], fraction, kind, seed + 1_000_000)
                for regime, (y, changed) in labels.items():
                    corruption.append(dict(seed=seed, arm=arm, regime=regime,
                        training_rows=len(y), original_positive=int(observed[train].sum()),
                        corrupted_positive=int(y.sum()), changed_labels=len(changed),
                        fraction_all_labels=len(changed)/len(y),
                        label_sha256=hashlib.sha256(y.astype("int8").tobytes()).hexdigest(),
                        feature_sha256=hashlib.sha256(x[train].to_json(orient="records").encode()).hexdigest()))
                    for model in models:
                        fitted = fit_model(x[train], y, model, seed)
                        for week in protocol["evaluation_weeks"]:
                            test = weeks == week
                            scores = fitted.predict_proba(x[test])[:, 1]
                            records.append(dict(seed=seed, arm=arm, model=model, regime=regime,
                                week=week, phase="pre" if week < 14 else "mix" if week < 18 else "adapted",
                                **metric(truth[test], scores, amounts[test], budget, groups[test])))
                # Partial outputs are never represented as a completed run.
                pd.DataFrame(records).to_csv(out / "weekly.csv", index=False)
                pd.DataFrame(corruption).to_csv(out / "corruption.csv", index=False)
    summary, paired = summarize(pd.DataFrame(records))
    summary.to_csv(out / "summary.csv", index=False)
    paired.to_csv(out / "paired.csv", index=False)
    completion = dict(status="complete", weekly_rows=len(records), corruption_rows=len(corruption),
                      unique_simulated_events=len(seeds)*2*config.weeks*episodes*3,
                      model_fits=len(seeds)*2*len(REGIMES)*len(models),
                      output_sha256={name: sha(out / name) for name in
                                     ["protocol.json", "weekly.csv", "corruption.csv", "summary.csv", "paired.csv"]})
    (out / "completion.json").write_text(json.dumps(completion, indent=2) + "\n")
    verify(out)
    return completion


def verify(out):
    """Checks remain active under python -O. Hashes detect edits, not authorship."""
    out = Path(out)
    p = json.loads((out / "protocol.json").read_text())
    done = json.loads((out / "completion.json").read_text())
    if done.get("status") != "complete":
        raise ValueError("Run is incomplete")
    for name, digest in done["output_sha256"].items():
        if Path(name).name != name or sha(out / name) != digest:
            raise ValueError(f"Output checksum mismatch: {name}")
    for name, digest in p["source_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError(f"Source checksum mismatch: {name}")
    w = pd.read_csv(out / "weekly.csv")
    expected = {(s, a, m, r, week) for s in p["seeds"] for a in p["arms"]
                for m in p["models"] for r in p["regimes"] for week in p["evaluation_weeks"]}
    actual = list(w[["seed", "arm", "model", "regime", "week"]].itertuples(index=False, name=None))
    if len(actual) != len(expected) or set(actual) != expected or len(w) != done["weekly_rows"]:
        raise ValueError("Missing or duplicate experiment rows")
    if not (w.alert_count == (w.n * p["budget"]).astype(int)).all():
        raise ValueError("Review capacity mismatch")
    same_truth = w.groupby(["seed", "arm", "week"]).fraud_count.nunique()
    if not (same_truth == 1).all():
        raise ValueError("Evaluation labels differ across treatments")
    c = pd.read_csv(out / "corruption.csv")
    if len(c) != len(p["seeds"]) * 2 * len(p["regimes"]) or c.duplicated(["seed", "arm", "regime"]).any():
        raise ValueError("Incomplete corruption accounting")
    if not (c.groupby("seed").feature_sha256.nunique() == 1).all():
        raise ValueError("Training features changed between treatments")
    if not (c.groupby(["seed", "regime"]).label_sha256.nunique() == 1).all():
        raise ValueError("Paired arms have different training labels")
    for fraction in FRACTIONS:
        t = c[c.regime == f"targeted_{fraction:g}"].set_index(["seed", "arm"])
        r = c[c.regime == f"random_{fraction:g}"].set_index(["seed", "arm"])
        if not t.changed_labels.equals(r.changed_labels):
            raise ValueError("Corruption budgets are unmatched")
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("experiments/results/poisoning"))
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--episodes", type=int, default=240)
    parser.add_argument("--models", nargs="+", choices=["hgb", "lr"], default=["hgb", "lr"])
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = verify(args.out) if args.verify else run(args.out, list(range(args.seed_start, args.seed_start+args.seeds)), args.episodes, args.models)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
