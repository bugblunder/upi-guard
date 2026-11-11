# Model card: bundled application model

## Identity and intended use

| Field | Value |
|---|---|
| Artifact | `v21-9fd597289003-logistic_regression` |
| Algorithm | Scaled numeric features + one-hot categories; class-weighted logistic regression; separate sigmoid calibration |
| Feature contract | 2.1.0; 16 numeric and 2 categorical features |
| Intended use | Synthetic investigation demos and evaluation of review-capacity tradeoffs |
| Excluded use | Real payment authorization, creditworthiness, identity verification or accusations of fraud |
| Revision 2.2 behavior | Existing model bytes retained; stronger loading/activation checks; new experiments do not replace the model |

## Data and evaluation

The included 12,000-row CSV was generated, not collected from a bank. Labels and scenario templates come from
an authored simulator. The chronological partitions contain 7,200 training, 1,200 calibration, 1,200 validation
and 2,400 test events. See [DATA_CARD.md](DATA_CARD.md). Model selection uses validation data; the supplied
holdout has already been inspected and is now development evidence, not an untouched confirmation set.

| Test quantity | Value | Interpretation |
|---|---:|---|
| Average precision | 0.6328 | Ranking across this synthetic distribution |
| ROC-AUC | 0.9513 | Does not establish useful recall under a small review budget |
| Policy recall | 11.81% | 28 of 237 positive events recommended for review |
| Policy precision | 65.12% | 28 positive events among 43 recommendations |
| Alert rate | 1.79% | 43 of 2,400 test events |
| False-positive rate | 0.693% | 15 of 2,163 negative events |
| Unseen-payer recall | 0% | Failure on this operational slice; not solved by good aggregate ranking |

The policy is chosen for an illustrative 2% validation alert budget. Cold-start transactions with fewer than five prior
payments are scored in shadow mode and do not trigger model recommendations. `allow` means no review recommendation;
it never authorizes a payment. Model failure instead routes a transaction to manual review.

## Known limitations

- Novel recipient/device indicators and repeated scenario templates provide synthetic shortcuts.
- Payer incoming count and pass-through features are all zero in the original training CSV; the separate research generator activates them.
- Calibration is distribution-specific; neither calibrated real-world probabilities nor demographic fairness is established.
- Review labels are selected and fallible; unreviewed transactions are not labelled legitimate.
- Graph aggregates are behavioral context, not proof that an account is a mule.
- SHAP describes model contributions; it is not causal evidence or a guarantee that a decision is right.

## Lifecycle and provenance

`metrics.json` records splits, data/feature/model digests, calibration, selection uncertainty and comparison models.
`training_snapshot.csv` retains frozen features and label availability. Reproduce into a separate artifact root,
review the candidate and explicitly activate it. Restrict write access to artifact files; hashes do not authenticate
an attacker-controlled manifest. Retest and retrain when changing the model environment.

The separate drift and poisoning studies have their own protocols and scores. Their metrics must not be presented as
this bundled model's performance.
