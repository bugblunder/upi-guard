# Research roadmap

The current revision is a defensible portfolio prototype. These are proposed extensions, not completed results.

| Priority | Question and experiment | Acceptance evidence |
|---|---|---|
| 1. External temporal benchmark | Does the evaluation pipeline survive a different data-generating process? Use a dataset whose terms permit the intended use, retain its true schema and avoid presenting it as UPI data. | Dataset card with provenance/checksum; frozen train/validation/test periods; simple and capacity-matched baselines; confirmation results recorded once after protocol freeze |
| 2. Reachable feedback poisoning | What can an analyst corrupt when they see only reviewed cases? Simulate case selection, label delay and a limited malicious-analyst budget. | Explicit attack surface; matched corruption budgets; bias-aware controls; sensitivity to review policy and prevalence |
| 3. Evaluate a defense | Do independent adjudication, label-source weighting or disagreement quarantine improve robustness? Compare each against clean and attacked baselines. | Paired security and utility metrics; reviewer cost; clean-data penalty; held-out attack settings; uncertainty and failure cases |
| 4. Stronger artifact provenance | Can deployment authenticate a training pipeline's output? Compare restricted serialization or sandboxed inference and separately managed signatures. | Threat model for signing keys, key rotation and rollback; malicious-artifact tests; compatibility and inference parity checks |
| 5. More credible deployment evidence | Can the workflow preserve integrity under PostgreSQL/Redis failure and contention? | Actual service-backed CI run, concurrency/chaos cases, measured tail latency, safe startup and recovery evidence |
| 6. Confirmation and reporting | Do conclusions persist after freezing hypotheses and seeds? | Protocol committed before execution; more independent seeds and external periods; paired intervals; predefined primary endpoints and treatment of multiple comparisons |

## Suggested four-week sequence

- **Week 1:** understand and reproduce the supplied work; publish a clean repository and demonstration; freeze one extension protocol.
- **Week 2:** build the external benchmark adapter and leakage/availability checks, retaining the dataset's own feature meaning.
- **Week 3:** implement one realistic feedback attack and one mitigation; measure utility and investigator workload.
- **Week 4:** run confirmation experiments, write a concise technical report and revise resume claims to match the evidence.

This is an execution plan, not a promised research outcome. Do not optimize on the external test split or select only successful seeds.
