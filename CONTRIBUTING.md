# Contributing

Use Python 3.12, `requirements-dev.txt` and an editable source installation; see [setup](docs/QUICKSTART.md).
Keep changes scoped and explain the resulting behavior. Run the relevant application/research tests before opening a PR.

For experiments, freeze the question, dataset provenance, temporal splits, attacker budget and primary metrics before
examining the evaluation outcomes. Report all treatments and seeds; compute uncertainty across independent units.
Do not overwrite completed result folders or silently replace historical evidence. Model candidates need explicit review and activation.

For security changes, update [THREAT_MODEL.md](docs/THREAT_MODEL.md) and add a regression test that exercises the trust boundary.
Never add real payment data, PINs, OTPs, account credentials, local databases or exported analyst feedback.

Review dependency updates against the persisted model environment. Changing scikit-learn requires retraining and model review,
not simply relaxing the version check. The release manifest must be intentionally regenerated after reviewed source changes.

Use [SECURITY.md](SECURITY.md) for sensitive reports. License and contributor attribution must be established by the repository owner.
