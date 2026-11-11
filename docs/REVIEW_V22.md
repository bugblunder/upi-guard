# Revision 2.2 review and changes

## Overall assessment

The uploaded project was already materially stronger than a classifier-only demo: it had chronological evaluation,
calibration, an authenticated workflow and a five-seed controlled drift study. Its main weaknesses for a research portfolio
were fragmented presentation, incomplete ML-security framing, several integrity-boundary defects and stale dependency/security evidence.

The most valuable improvement is making its contribution and evidence auditable. More classifiers or unsupported accuracy
claims would not resolve the real weaknesses: authored data, operational recall failures and a lack of representative external validation.

## Concrete findings addressed

| Finding in the uploaded code | Change | Verification |
|---|---|---|
| Metadata version/feature validation partly occurred after joblib loading | Preflight metadata and path containment; deserialize the exact verified bytes | Reject-before-load, traversal, symlink and file-replacement regression tests |
| Activation used a narrower check than model loading | Activation now uses the same complete candidate loader before replacing the active pointer | Corrupt candidate cannot change the pointer |
| Revoking a user while fetching `/api/csrf` could clear the token then produce a 500 | Create a fresh anonymous token after revocation | Token fetch succeeds while protected endpoints still deny access |
| Short displayed identifiers could expose every character | Always hide part of the identifier | Parameterized masking tests |
| Feedback loader accepted duplicate CSV headers, bool-valued numeric features and mismatched categorical context | Reject malformed rows, duplicate headers, booleans and category/channel conflicts | Malformed snapshot regression tests |
| Direct training lacked the feedback loader's label-availability validation | Validate timezone awareness and non-preceding label time consistently | Training rejects naive or pre-event label timestamps |
| Pillow 12.3.0 had advisory findings | Pin Pillow 13.0.0 and rerun the advisory audit | Before/after reports retained; no known runtime-pin findings after the update at validation time |
| Python metadata said 2.0.0 and lacked an installable setup | Version 2.2.0, editable installation, console entry point and explicit source-checkout contract | Clean installation and CLI checks |
| Security was documented mainly as web controls | Add a threat model plus a paired label-corruption experiment | Five-seed completed run, raw tables, checksums, paired estimates and tests |
| Research story was buried in revision history | Rewrite entry-point README; add model card, report, portfolio guide and prioritized roadmap | Documentation/relative-link review and claim-to-result checks |

## Evidence preservation

The bundled application model is retained. The original research Python sources, shared feature/monitoring code and
original study outputs are preserved so their recorded source hashes remain checkable. New experiments live under
`experiments/` and do not activate a model. Historical validation reports describe earlier environments and should not
be read as current checks; use [VALIDATION_V22.md](../reports/VALIDATION_V22.md).

The release manifest is regenerated for the new repository. Hashes show file consistency, not origin or freedom from vulnerabilities.

## What still needs research

- The original model's low policy recall and unseen-payer failure are not fixed by this revision.
- The poisoning study measures vulnerability, not a working defense. Its privileged label access is simplified.
- A five-seed simulator result is not evidence of real UPI effectiveness or a universally superior learner.
- PostgreSQL/Docker and remote GitHub workflows need execution on their intended infrastructure.
- License/attribution must reflect the actual provenance and contributors; this revision does not invent those rights.
