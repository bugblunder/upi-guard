# UPI Guard Research Extension

## Research objective

**Working title:** *Evaluating fraud-typology shift and delayed supervision in a synthetic UPI-like payment stream.*

Turn the application into an auditable experimental platform: a clear question, controlled comparisons, temporal evaluation, reproducible artifacts and honest uncertainty. The contribution currently is an experimental testbed and empirical stress study. It is not a new fraud algorithm, confirmed discovery about UPI, or an established publication novelty claim.

The earlier conversational summary supplied with this task referred to a different simulator and results that were absent from the uploaded ZIP. Those numbers are not imported into this study. The attached `research/results/` tables come from a fresh implementation and run.

## Questions and comparisons

| Question | Controlled comparison | Principal measurements |
|---|---|---|
| RQ1: Does the scheduled shift cause deterioration beyond normal temporal variation? | Fixed model in paired drift and stationary arms; compare adapted-minus-pre changes | Recall at 5% review capacity; average precision; paired difference in differences |
| RQ2: How does delayed supervision affect adaptation? | Four-week sliding training with 0-, 1- and 3-week label delays | Weekly recall, precision, average precision, transaction-value recall; paired strategy differences |
| RQ3: Does retaining old data help? | Expanding versus four-week training, both with one-week delay | Same outcomes under identical mature-label restrictions |
| RQ4: Do graph aggregates or novelty shortcuts carry the result? | Fixed full model versus removing all three graph aggregates or both novelty flags | Paired average-precision and recall differences; mule-family recall |
| RQ5: Are existing distribution alarms aligned with performance harm? | Fixed-model feature diagnostics, score PSI, fixed-threshold alert-rate change; stationary-arm alarm rates | Alarm frequency, retrospective harmful-week coverage, first alarm and first harmful week |

RQ5's harm-association rule is exploratory and was added after a smoke run. No result has been preregistered. Confidence intervals are descriptive across simulator seeds; these are multiple related comparisons without multiplicity correction.

## Simulator and causal ordering

`research/typology_sim.py` generates 24 zero-based weeks, default 240 three-transaction episodes per week (720 events/week, 17,280 events per arm per seed). The payer population is 120 synthetic users, plus eight receiving hubs per hub family. IDs satisfy the application's naming contract but do not enter model inputs.

Four latent episode templates are ordinary payments, merchant receipts and settlement, takeover-like payments, and mule-like receipts and forwarding. A baseline 4% of episodes are fraud scenarios, with transaction outcomes independently positive with probability 0.9. Fraud incidence is a configurable stress-test parameter, not an estimate for any payment network. Legitimate scenarios currently have zero latent fraud probability; this simplification is a major limitation. Symmetric 0.5% adjudication noise affects training targets only and is independently configurable.

At week 14 the mule share of fraud episodes increases from 15% to 75%. At week 18 the takeover anomalies in amount, device novelty and recipient novelty shrink by the configured strength (default 0.8). The stationary arm retains baseline probabilities throughout. It shares random draws, event counts, event times, latent outcome labels, observed labels and initial transactions with the drift arm. This isolates changes in feature/scenario relationships from prevalence differences. The fraud-family mix shift and anomaly reduction are interventions designed by the simulator author.

Within each episode, events occur 30 seconds apart. Merchant and mule episodes have two incoming payments followed by a forwarding payment. Other episodes contain three ordinary/takeover-like payments. Legitimate merchants also exhibit fan-in and fast forwarding; these patterns are risk signals rather than definitive labels. Distinct category distributions and limited hub populations can still create learnable template shortcuts.

The existing application's `feature_rows` and `build_features` functions compute all 18 features. They use strictly earlier transactions within 30 days and ignore all outcome/scenario fields. Earlier test transactions can enter the ledger for later test features; their labels cannot. This is chronological ledger replay. It does not simulate out-of-order ingestion, network latency or concurrency. An offline loader imports the app's pure feature and monitoring modules without importing Flask; it does not copy feature implementations.

## Frozen experimental protocol

| Stage | Zero-based weeks | Use |
|---|---|---|
| Warm-up | 0–4 | Establish more than 30 days of ledger history; no training labels used |
| Initial training | 5–8 | Fit common fixed model and fixed ablations |
| Monitor reference | 9–11 | Unlabeled feature/score reference and fixed 95th-percentile score threshold |
| Pre-shift evaluation | 12–13 | Baseline for paired temporal changes |
| Changed family mix | 14–17 | More mule-like episodes at matched overall prevalence |
| Adapted evaluation | 18–23 | Changed family mix plus reduced takeover anomalies |

Two learners are fixed in advance of the main run: logistic regression (`C=0.2`, no class balancing) and histogram gradient boosting (70 iterations, 10 leaves, minimum leaf size 25, L2=2, no early stopping). Numeric standardization and one-hot encoding fit exclusively on the allowed training rows. Hyperparameters are illustrative rather than tuned optima. Both models are reported; the test set does not select a winner.

The fixed model is trained on weeks 5–8. All its labels have matured by week 12 even under the longest three-week delay. Weekly strategies refit before each evaluated week. For event time `e`, scoring cutoff `w`, delay `d`, and window `L=4`, an event is eligible only if `e+d < w`, `e >= 5`, and `e >= w-d-L`. Cumulative training omits the final lower-window restriction. Both positive and negative labels arrive; unlabeled records are never treated as legitimate.

This is an idealized representative-outcome setting. Real investigator feedback is selected by past alerts. Delays are constant and identical across classes. Neither selective feedback nor class-dependent delays is solved here. Evaluation uses eventual simulator truth after the fact, whereas training uses only eligible noisy adjudications.

For each evaluated week, select exactly `floor(0.05*n)` highest-scoring payments, breaking ties by chronological row order. This is an **offline weekly ranking capacity**, requiring the complete week's scores. It is not a causal real-time threshold policy. The reference score threshold is used separately for monitoring alert-rate changes. A production study must replace weekly hindsight ranking with a queueing or online-budget policy.

Average precision is scikit-learn's non-interpolated AP, not trapezoidal PR area. Also record ROC AUC, Brier score, amount-weighted recall, and per-family recalls. Amount-weighted recall is a transaction-value proxy: inflows and outflows can count the same funds more than once, so it is not unique financial loss prevented. Uncalibrated Brier scores compare raw outputs and do not establish production calibration.

## Monitoring protocol

The feature monitor uses the existing application's unmodified `reference_profile` and `drift_summary` rules: numerical PSI >0.2 or KS effect >0.15 with corrected p-value, and categorical JS/unseen-category rules. Score PSI uses reference quantile bins and a 0.2 threshold. An alert-rate alarm fires when the absolute proportion above the frozen reference score threshold moves by more than three percentage points.

These are illustrative distribution diagnostics, not newly tuned detectors. No Isolation Forest or alert-tail monitor is included in this version. Threshold calibration to an equal stationary false-alarm rate is future work.

`analyze_control.py` retrospectively calls a week harmful if fixed-model recall is below 80% of that seed's mean recall in weeks 12–13. It records alarm coverage on those weeks, including misses and background events in the control. The two-week reference can be noisy, so this rule is exploratory. First alarm minus first harmful week is descriptive and reported only when both exist. A single isolated low-recall week is not a proven sustained degradation event. The monitor never receives these outcomes as input.

## Replication and uncertainty

The default main study uses seeds 0–4, both models and both arms. Aggregate weekly results within each seed and phase before computing 95% Student t intervals across seeds. Paired strategy intervals use within-seed differences. Paired control intervals use `(adapted - pre)_drift - (adapted - pre)_control`. Weeks and transactions are not independent replications. The five-seed sample is small; wider seed and simulator sensitivity studies are necessary.

Absolute-metric t intervals are unconstrained and can extend outside [0,1]; do not interpret such endpoints as valid probability bounds. Raw endpoints are preserved rather than silently clipped. For differences, use the paired intervals. No uncertainty interval here measures uncertainty in real banking populations.

`protocol.json` records configuration, seeds, command, software versions, split definitions and SHA-256 hashes of experiment/feature sources present when the run starts. Each arm's generated rows have a SHA-256 digest in `diagnostics.json`. Result checkpoints are written after each arm; an interrupted directory is partial. Commands refuse to overwrite an existing result directory. The supplied report records completion and expected row counts. Figures regenerate from tables.

## Evidence needed for a paper

1. **Independent development and confirmation:** use present seeds as development; freeze simulator/protocol before evaluating a fresh seed set. A new seed tests simulation randomness, not external validity.
2. **Sensitivity:** vary fraud episode rate (0.01, 0.02, 0.04), adaptation strength (0, 0.4, 0.8), label noise (0, 0.005, 0.02), stream density and legitimate merchant proportion. Report null and reversed effects.
3. **Isolate the interventions:** add mix-only and adaptation-only arms. The present combined arm cannot isolate their individual causal contributions.
4. **Monitoring comparison:** calibrate thresholds on separate stationary development streams for equal false alarms; compare label-free baselines and a delayed-label performance monitor. An alert-tail or graph-motif monitor is a research candidate only after this baseline is stable.
5. **Generalization:** introduce unseen payer and hub cohorts, longer device persistence, multiple adversarial variants and fraud in ordinary-looking episodes. Current ablations expose reliance but do not remove every simulator shortcut.
6. **Independent data:** reproduce compatible questions on an independent licensed source. The existing ZIP's PaySim report is historical evidence from the application and was not rerun here. PaySim is synthetic mobile money, not UPI; do not invent missing device or channel fields. Real UPI claims require authorized, representative UPI outcomes.
7. **Operational realism:** simulate selective feedback, variable outcome delay, out-of-order transactions, daily review queues, and costs agreed with a domain owner. Do not infer customer impact from this simulator.

Suggested paper structure: problem and prior art; explicit hypotheses; simulator/data card; chronological protocol; controlled results and paired uncertainty; sensitivity and negative results; external validation; limitations and reproducibility appendix. The substantive contribution should be decided after these results, not by declaring a new hybrid algorithm.

## Related work and methodological sources

- Dal Pozzolo, Boracchi, Caelen, Alippi and Bontempi, *Credit Card Fraud Detection and Concept-Drift Adaptation with Delayed Supervised Information*, IJCNN 2015. Author-hosted paper: https://dalpozz.github.io/static/pdf/IJCNN2015_final.pdf . Delayed-label adaptation has established prior work; this extension does not claim to originate it.
- *Reproducible Machine Learning for Credit Card Fraud Detection — Practical Handbook*, validation strategies: https://fraud-detection-handbook.github.io/fraud-detection-handbook/Chapter_5_ModelValidationAndSelection/ValidationStrategies.html . Motivates chronological training/delay/test blocks and prequential evaluation.
- scikit-learn, common pitfalls: https://scikit-learn.org/stable/common_pitfalls.html . Motivates fitting preprocessing only on training data. The recorded experiment uses scikit-learn 1.8.0; online stable documentation may describe a later release.

Sources checked during this task on 2026-10-15. This is targeted methodological grounding, not an exhaustive novelty or systematic literature review.
