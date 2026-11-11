"""Regenerate the ML security figure and report from verified result tables."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .poisoning import FRACTIONS, verify


def generate_report(folder, output):
    folder, output = Path(folder), Path(output)
    done = verify(folder)
    protocol = json.loads((folder / "protocol.json").read_text())
    if (protocol["seeds"] != list(range(100, 105)) or
        set(protocol["models"]) != {"hgb", "lr"} or protocol["budget"] != .05 or
        protocol["simulator"]["episodes_per_week"] != 240):
        raise ValueError("This narrative generator requires the published five-seed protocol; inspect other runs' CSV tables directly")
    summary = pd.read_csv(folder / "summary.csv")
    paired = pd.read_csv(folder / "paired.csv")
    accounting = pd.read_csv(folder / "corruption.csv")
    select = summary[(summary.phase == "adapted") & (summary.metric == "recall")]
    contrasts = paired[(paired.phase == "adapted") & (paired.metric == "recall")]
    def estimate(table, arm, model, regime):
        row = table[(table.arm == arm) & (table.model == model) & (table.regime == regime)].iloc[0]
        if pd.isna(row.ci95_low):
            return f"{100*row['mean']:.1f} [CI unavailable]"
        return f"{100*row['mean']:.1f} [{100*row.ci95_low:.1f}, {100*row.ci95_high:.1f}]"

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), sharey=True, layout="constrained")
    for ax, model, title in zip(axes, ["hgb", "lr"], ["Histogram gradient boosting", "Logistic regression"]):
        for kind, color, offset in [("targeted", "#b34448", -1), ("random", "#237d91", 1)]:
            points = contrasts[(contrasts.arm == "drift") & (contrasts.model == model)].set_index("regime")
            rows = points.loc[[f"{kind}_{fraction:g}" for fraction in FRACTIONS]]
            mean = rows["mean"].to_numpy()*100
            err = np.vstack([mean-rows.ci95_low.to_numpy()*100, rows.ci95_high.to_numpy()*100-mean])
            ax.errorbar(np.array(FRACTIONS)*100+offset, mean, yerr=err, marker="o", capsize=5,
                        color=color, label="Targeted positive → negative" if kind == "targeted" else "Matched random label flips")
        ax.axhline(0, color="#77808c", lw=1, ls="--")
        ax.set(title=title, xlabel="Attack budget (% of positive training labels)", xticks=[10,30,50])
        ax.grid(axis="y", alpha=.15)
    axes[0].set_ylabel("Change in recall vs clean training (percentage points)")
    axes[1].legend(frameon=False, loc="lower left", fontsize=9)
    fig.suptitle("Training-label corruption under synthetic drift\n5% weekly review budget · 5 paired seeds · descriptive 95% t intervals", fontsize=13)
    fig.savefig(folder / "poisoning_recall.png", dpi=180)
    plt.close(fig)
    lines = ["# ML security experiment: bounded training-label corruption", "",
        "This is a synthetic stress test of initial training-label integrity. It does not measure a live UPI attack or demonstrate a new defense.", "",
        "## Protocol", "",
        f"Completed {done['model_fits']} fits and {done['weekly_rows']} weekly evaluations across {done['unique_simulated_events']:,} unique simulated events, seeds 100–104, two learners and matched stationary/drift arms.",
        "Training uses weeks 5–8; evaluation uses weeks 12–23. Evaluation labels are latent simulator truth and are never corrupted. Models and the 5% weekly ranking budget are fixed before scoring. This experiment assumes zero additional label delay; delay is studied separately in the original suite.", "",
        "The attacker relabels 10%, 30% or 50% of observed positive training labels as legitimate. A matched random control flips exactly the same number of labels, sampled across all training rows. Both controls share the same features, temporal splits, model seeds and eventual evaluation labels. Equal counts do not equalize class prevalence, which is one mechanism being measured.", "",
        "## Recall in weeks 18–23", "",
        "Percent; brackets are descriptive 95% t intervals over seed-level weekly means. Intervals are not bounds on real-world performance.", "",
        "| Arm | Learner | Clean | Targeted, 50% | Random, matched count |", "|---|---|---:|---:|---:|"]
    for arm in ["control", "drift"]:
        for model in ["hgb", "lr"]:
            values = [estimate(select, arm, model, regime) for regime in ["clean", "targeted_0.5", "random_0.5"]]
            lines.append(f"| {arm} | {model.upper()} | " + " | ".join(values) + " |")
    lines += ["", "## Paired differences", "",
              "Recall difference in percentage points; negative means the first condition catches fewer positive events.", "",
              "| Arm | Learner | Targeted minus clean | Targeted minus random |", "|---|---|---:|---:|"]
    for arm in ["control", "drift"]:
        for model in ["hgb", "lr"]:
            lines.append(f"| {arm} | {model.upper()} | {estimate(contrasts, arm, model, 'targeted_0.5')} | {estimate(contrasts, arm, model, 'targeted_minus_random_0.5')} |")
    fraction = accounting[accounting.regime == "targeted_0.5"].fraction_all_labels
    lines += ["", f"The largest attack changes {100*fraction.min():.2f}%–{100*fraction.max():.2f}% of **all** initial training labels. The 50% figure refers to positive labels only.", "",
        "## Interpretation", "",
        "At the largest tested budget, targeted corruption lowers mean recall relative to clean training in both arms and learners; the displayed paired intervals exclude zero. In the drift arm, targeted-versus-random intervals cross zero for both learners. This run therefore does not establish that targeting is consistently more harmful than equally sized random corruption under drift. Intermediate budgets and AP/Brier results are available in the complete tables; no outcome was used to select a model or attack budget.", "",
        "This supports treating label provenance and adjudication as model-security concerns. It does not validate the application's workflow as a poisoning defense: corrupted but schema-valid labels remain possible, and privileged administrators are inside the trust boundary.", "",
        "## Limits", "",
        "Five authored-simulator seeds, exploratory comparisons without multiplicity correction, and no independent external dataset limit generalization. The attacker has direct access to selected initial training labels; this is not an experiment on only the cases reachable by one analyst. There is no optimized evasion, feature poisoning, backdoor, online attack, selective review simulation, or adaptive retraining defense. Ranking sees an entire week and is not a real-time capacity guarantee. Fixed-seed replication tests reproducibility; an external confirmation set is still needed.", "",
        "## Reproduce", "", "```bash",
        "python -m experiments.poisoning --out experiments/results/local-reproduction --seed-start 100 --seeds 5 --episodes 240",
        "python -m experiments.poisoning --out experiments/results/local-reproduction --verify",
        "python -m experiments.report --input experiments/results/poisoning --output docs/ML_SECURITY_RESULTS.md",
        "```", "",
        "The runner refuses to overwrite a directory. `protocol.json` records versions, source hashes and all treatments; `completion.json` records output hashes. These detect mismatches, not authenticity against a writer who can replace both files and manifests.", "",
        "![Paired recall effects of training-label corruption](../experiments/results/poisoning/poisoning_recall.png)", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("experiments/results/poisoning"))
    parser.add_argument("--output", type=Path, default=Path("docs/ML_SECURITY_RESULTS.md"))
    args = parser.parse_args()
    generate_report(args.input, args.output)
