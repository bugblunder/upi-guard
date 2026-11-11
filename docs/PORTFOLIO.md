# Portfolio and master's-application guide

## Suggested project title

**UPI Guard — Reliable Fraud-Risk ML under Drift and Label Corruption**

Suggested repository description:

> Reproducible synthetic fraud-risk research with temporal evaluation, label-poisoning experiments and an auditable analyst workflow.

Suggested GitHub topics: `machine-learning`, `ml-security`, `fraud-detection`, `concept-drift`, `data-poisoning`,
`reproducible-research`, `scikit-learn`, `flask`.

## Resume bullets

Use only statements you can explain and reproduce, and accurately describe your contribution if earlier work was collaborative.
Choose two or three bullets; do not paste every metric into a resume.

- Built an auditable fraud-risk research prototype with point-in-time transaction features, chronological model evaluation, calibrated scoring and an authenticated analyst investigation workflow.
- Evaluated temporal drift and delayed-label retraining across five paired simulation seeds and two learners, with graph/novelty ablations and uncertainty estimated at the seed level.
- Designed and ran a training-label corruption study with **140 model fits over 172,800 synthetic events**, comparing targeted poisoning against matched random corruption under stationary and drifting conditions.
- Hardened model loading, activation, session revocation and feedback validation, with automated regression tests and dependency-security checks.

Optional result-focused replacement for the third bullet:

- Measured a **10.4 percentage-point recall reduction** under the largest tested label-corruption budget for HGB in a synthetic drift setting; reported paired uncertainty and an inconclusive targeted-versus-random comparison.

Always retain the word **synthetic** for dataset and result claims. Do not call the project a bank deployment,
a novel fraud-detection algorithm, an effective anti-poisoning defense or a published paper.

## Research statement paragraph

My interest in machine learning security developed through investigating how fraud-risk models fail when their operating conditions change. In UPI Guard, I studied temporal drift, delayed supervision and corrupted training labels using controlled synthetic streams. I coupled these experiments with an auditable investigation workflow so that feature timing, label provenance and model activation were explicit engineering boundaries. One important lesson was that strong ranking metrics can coexist with weak recall under a realistic review constraint, and that validating the format of feedback does not establish its truth. I would like to extend this work to representative temporal datasets and experimentally evaluated defenses against selective feedback corruption.

Adapt this paragraph to your actual role and experience. It is a project narrative, not a claim of admission competitiveness or publication novelty.

## Five-minute demonstration

| Time | Show | Explain |
|---|---|---|
| 0:00–0:45 | README question and scope | Why capacity, drift and label integrity matter; all data is synthetic |
| 0:45–1:45 | Transaction → case → history | Frozen features, idempotency, ownership and auditable adjudication |
| 1:45–2:45 | Model card and original drift results | Why ROC-AUC is insufficient; why a stationary control is needed |
| 2:45–4:00 | Poisoning figure and paired table | Attacker budget, random control, 5 seeds, uncertainty and negative/inconclusive findings |
| 4:00–5:00 | Threat model and regression tests | What is enforced, what remains trusted, and the next external-validation experiment |

## Questions you should be able to answer

1. What is the difference between covariate shift, a change in fraud prevalence and a change in the fraud-label relationship? Which changes does your generator actually impose?
2. Why split chronologically, calibrate on a separate partition and freeze selection before the test set?
3. Why is average precision useful under imbalance, and why must recall be measured at a review budget?
4. Why are weeks within a seed dependent, and why are 1,680 weekly rows not 1,680 independent replications?
5. What can the poisoning actor change? Why compare with equal-count random corruption? What does that control fail to equalize?
6. What distinguishes input validation from protection against a plausible but wrong analyst label?
7. Why can a valid checksum coexist with malicious pickle code? What would signed provenance change?
8. How can graph features confound legitimate merchants with suspicious transfer patterns?
9. What would you change before using representative external data or deploying to multiple organizations?
10. Which result weakened your original hypothesis, and how did you report it?

## Before using this in applications

Run the project yourself, reproduce one experiment, explain the threat model without reading notes and keep a record
of your design decisions. Record a short synthetic-data demonstration and publish a stable repository release.
A stronger follow-up is one well-controlled external experiment with an evaluated defense, rather than extra UI features.
See [ROADMAP.md](ROADMAP.md) for a concrete sequence.
