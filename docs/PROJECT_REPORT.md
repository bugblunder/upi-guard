# UPI Guard: reliable fraud-risk ML under operational and adversarial constraints

## Research question

How do evolving behavior, delayed supervision, a limited investigation budget and corrupted labels affect
fraud-risk models, and which software boundaries make those effects reproducible and auditable?

The project uses synthetic payment-like streams because no authorized real UPI dataset is supplied. This choice
supports controlled interventions and repeatability while sharply limiting claims about real-world effectiveness.

## System design

A Flask application validates transactions through a shared Pydantic contract. Feature construction considers
only observed history strictly earlier than the event: velocity, amount deviation, novelty and local graph aggregates.
SQLAlchemy stores the original payload, frozen features, score, model version and decision atomically. Idempotent
IDs distinguish exact replay from changed payloads. Analysts investigate cases with ownership rules, optimistic
revision checks and audit events. Confirmed outcomes can be exported for explicit offline candidate training.

The application compares logistic regression, random forest and histogram gradient boosting with chronological
training, calibration, validation and test partitions. Selection and thresholding precede test evaluation. Its model
card reports poor recall at the chosen small review budget, including a cold-start failure. That tradeoff is part of
the result rather than hidden behind a favorable ROC-AUC.

## Experimental contributions

1. **Controlled drift:** paired stationary/drift streams share random draws. The study compares fixed models,
   delayed-label sliding/cumulative retraining and graph/novelty ablations. Weekly scores are summarized within
   seed before calculating uncertainty. A stationary control distinguishes intervention effects from normal variation.
2. **Label integrity:** the new study corrupts bounded initial training labels and compares targeted positive-to-negative
   flips with random flips of the same count. Features, test truth and model seeds stay fixed. Different seeds from the
   original study reduce direct reuse, although both experiments remain in the same authored synthetic world.
3. **System integrity:** regression tests exercise artifact validation before deserialization, role/session boundaries,
   feedback schema integrity, future-event exclusion, idempotency and safe failure to review.

The original drift study contains 1,680 weekly strategy rows across five seeds and two learners. The new security study
adds 140 model fits and 1,680 weekly treatment rows. These are separate experiments, not thousands of independent
statistical replicates. Five seeds are the unit of uncertainty in each.

## Findings and their interpretation

The original fixed HGB model's recall declines markedly after the scheduled simulator intervention, while retraining
recovers part of the lost recall. Label-delay effects differ across learners. Graph-feature benefits are limited and
uncertain; novelty shortcuts persist. Population-distribution monitors are weakly aligned with degradation.

In the new study, flipping half of positive training labels reduces drift-arm HGB recall from 31.1% to 20.7% at a 5%
weekly ranking budget. Its paired change is −10.4 percentage points, with a descriptive 95% interval of [−19.1, −1.8].
The targeted-versus-random contrast under drift crosses zero. The evidence supports label integrity as a risk in this
simulator; it does not establish a universal attack advantage or validate a mitigation.

Detailed methods, every treatment and limitations appear in [RESEARCH_RESULTS.md](RESEARCH_RESULTS.md) and
[ML_SECURITY_RESULTS.md](ML_SECURITY_RESULTS.md). [VALIDATION_V22.md](../reports/VALIDATION_V22.md) records
which engineering checks actually ran.

## Research value and next step

The strongest contribution is connecting statistical reliability to operational security: a high-ranking model can be
ineffective at the chosen review budget; trusted code can learn from untrustworthy labels; checksums can detect corruption
without establishing artifact authenticity. Each distinction is expressed in code, measurements or a documented boundary.

The highest-value next step is a frozen external temporal benchmark with explicit dataset permissions, followed by a
realistic selected-feedback poisoning experiment and an evaluated mitigation. More UI features or another classifier
would add less evidence. See [ROADMAP.md](ROADMAP.md).
