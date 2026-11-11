# Changelog

## 2.2.0 — 2026-11-10

- Add a five-seed, two-learner training-label corruption study with paired random controls, raw results and provenance checks.
- Harden model preflight and activation, revoked-session recovery, display masking and feedback validation.
- Update vulnerable Pillow pin; add dependency and static-security CI checks.
- Add editable installation, CLI metadata, release checks, model/threat cards and portfolio documentation.
- Retain original research/model evidence; see reports/VALIDATION_V22.md for this revision’s checks.

# Changes

## Research extension — 2026-10-15

- Add an offline transaction simulator with paired stationary/drift arms and legitimate merchant graph confounds.
- Evaluate seven fixed/retraining/ablation strategies, mature-label delays, two learners and five seeds.
- Include per-week metrics, paired uncertainty, monitor association tables, six figures, source/data digests and a completeness verifier.
- Add ten validity tests, research CI step, methodological sources, reproduction instructions and candid limitations.
- Preserve the application feature/scoring code, original datasets and deployed model artifacts.

## Review follow-up

- Bound transaction and case pagination to avoid database offset overflow and return a client error for invalid page numbers.
- Ignore generated local training outputs and exported feedback when preparing a GitHub repository.

## 2.1 — response to technical review

- Remove automatic decline and arbitrary decline threshold; use validation review budgets, paired payer-bootstrap comparison and explicit cold-start shadow mode.
- Add prevalence sensitivity and capacity curves, model-selection uncertainty, preserved original metrics, frozen-model new-seed runs and an independent PaySim native-schema benchmark.
- Ignore caller-provided account age/failed-attempt hints. Add observed-history, recipient fan-in, incoming-flow aggregates and a shadow Isolation Forest.
- Add per-case SHAP with reconstruction checks and original-version lookup; keep rule observations separate.
- Export frozen-feature feedback; merge into a representative base, preserve source and label availability, train candidates without automatic activation.
- Accept five-minute clock skew and late arrivals, preserving original assessments and arrival context.
- Replace SQL rate-limit writes with bounded memory/atomic Redis backends. Add explicit proxy CIDR/hop trust and Redis readiness checks.
- Add PSI/KS, categorical JS/OOV, risk-prioritized queue, manual investigation opening and backlog/capacity display.
- Add migration 0002, regression tests, UI workflow checks and a 2,000-request contention test.

These changes do not solve cold-start detection, establish real-world calibration, remove review-label bias, validate mule detection or demonstrate production capacity. The measured default policy has low recall. See docs/REVIEW_RESPONSE.md.
