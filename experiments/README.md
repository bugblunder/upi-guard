# ML security experiments

Start with [the threat model](../docs/THREAT_MODEL.md) and [results](../docs/ML_SECURITY_RESULTS.md).
The experiment is offline and synthetic; it does not connect to payment infrastructure or change the demo model.

```bash
python -m pip install -r research/requirements.txt
python -m experiments.poisoning --out experiments/results/local-reproduction --seed-start 100 --seeds 5 --episodes 240
python -m experiments.poisoning --out experiments/results/local-reproduction --verify
```

The published run is `results/poisoning/`. Its output files are:

| File | Purpose |
|---|---|
| `protocol.json` | Fixed configuration, seeds, temporal splits, package versions and source hashes |
| `corruption.csv` | Exact changed-label counts, prevalence and feature/label digests for each treatment |
| `weekly.csv` | All seed/arm/model/treatment/week measurements |
| `summary.csv` | Seed-aggregated descriptive intervals |
| `paired.csv` | Corrupted-minus-clean and targeted-minus-random paired estimates |
| `completion.json` | Expected row counts, run totals and output hashes |
| `poisoning_recall.png` | Plot regenerated from the verified tables |

`python -m experiments.report` regenerates the published study's figure and Markdown results.
For a fast functional run use one seed, `--episodes 40 --models lr` and a new directory; one seed cannot support cross-seed intervals.
Tests cover attack budgets, immutable inputs, paired arms, missing single-seed intervals, output tampering and overwrite rejection.

The largest targeted attack flips half of observed positive initial training labels to negative. Its random control flips
exactly the same number of arbitrary training labels. Neither can change features or eventual evaluation labels.
All scores use a fixed 5% offline weekly review budget. These choices do not model every permission or selection constraint
of a real analyst feedback system, and no defense is evaluated.
