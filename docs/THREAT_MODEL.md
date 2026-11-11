# Threat model: application and ML lifecycle

## Scope and trust boundaries

The protected assets are account sessions, transaction/feature integrity, analyst labels, model artifacts,
review decisions and evidence provenance. The application is a single-organization analyst sandbox.
An authenticated API caller is not automatically an authoritative payment feed.

| Actor | Capabilities assumed | Boundary |
|---|---|---|
| Unauthenticated visitor | Send requests, spoof untrusted forwarded headers, attempt login | Session, CSRF and rate-limit checks |
| Analyst | Submit valid synthetic transactions, inspect cases, claim/edit own cases | Role and assignment checks; no bulk import/export or model activation |
| Administrator | Manage local users, import/export data, operate training/activation | Privileged and trusted; malicious administrators are not contained |
| Label-corruption actor in the experiment | Flip a bounded portion of initial training labels | Cannot alter features, test truth, review budget or model selection |
| Artifact writer | Replace files on the trusted model volume | Outside checksum authenticity guarantees; filesystem access is security critical |

## Threats, controls and verification

| Threat | Implemented control / evidence | Remaining exposure |
|---|---|---|
| Session theft, fixation and CSRF | scrypt; login token rotation; HttpOnly/SameSite; CSRF validation; revocation checked per request; `test_app.py`, `test_security_boundaries.py` | No SSO/MFA or centralized session revocation store; HTTPS is a deployment responsibility |
| Privilege or case ownership abuse | Server-side admin checks; analyst assignment restrictions; optimistic revisions; `test_app.py` | Users share one organization's case visibility; no tenant isolation |
| Forged transactions and replay | Strict schema, unique IDs, content hashes, atomic writes and payer serialization | A valid payload may still be false; no bank-origin cryptographic attestation |
| Leakage from future events or labels | Strict past-event feature boundary, frozen snapshots, mature-label masks, research invariance tests | Arrival order and concurrency affect available history; not a globally serialized graph snapshot |
| Feedback corruption | Matching transaction/category context, feature-version checks, finite numeric features, no automatic activation; new malformed-input tests | A schema-valid wrong outcome is accepted. Human review and retention do not prove label truth |
| Targeted training-label poisoning | Explicit measured attack/control experiment in `experiments/poisoning.py` | No effective poisoning defense is claimed or evaluated |
| Malicious or inconsistent artifacts | Path containment, metadata/version/feature checks and exact-byte SHA-256 verification before joblib loading; activation shares the loading path | joblib can execute code. An attacker who changes model and manifest bypasses integrity-only protection |
| Service exhaustion | Bounded CSV/request sizes, endpoint limits, Redis backend, safe model failure to manual review | Feature queries and explanation work remain costly; no production capacity claim |
| Dependency compromise | Runtime pins, Pillow update, dependency audit CI and Dependabot | Pins are not signed provenance; upstream advisory coverage and future changes remain limitations |
| Audit tampering / data exposure | Audit rows, restricted exports, masked display identifiers, no-store headers, secret exclusions | Audit rows are mutable by database administrators; display masking is not anonymization or encryption |

## Security contribution and limits

The defensible contribution is making assumptions testable: an invalid artifact must not reach deserialization,
a revoked session must lose access, a wrong feedback schema must fail, and an experiment must preserve its attacker budget.
The label-corruption study demonstrates that malicious-but-valid labels are a separate risk from malformed inputs.

No penetration test, formal verification, compliance certification, automated poisoning detector, adversarial robustness
certificate, model-extraction defense or membership-inference evaluation has been completed.

## References

- [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html): trusted artifact sources and environment compatibility.
- [OWASP Machine Learning Security Top Ten](https://owasp.org/www-project-machine-learning-security-top-10/): taxonomy used to frame input, label and supply-chain risks; this project does not claim coverage of the entire list.
- [Pillow 13.0.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html): upstream security fixes motivating the dependency update.

These references frame the design. Local test results, not the references, are the evidence for implemented behavior.
