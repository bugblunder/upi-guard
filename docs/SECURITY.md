# Security boundaries — revision 2.2

See [THREAT_MODEL.md](THREAT_MODEL.md) for actor capabilities, control-to-test mappings and residual risks. Revision 2.2 adds pre-deserialization metadata/path checks and exact-byte checksum loading, shared candidate validation for activation, revoked-session token recovery and stricter feedback contracts. These are integrity controls; model files and valid analyst labels still require trusted provenance.


Implemented: scrypt password hashes, no bundled login, session expiry, CSRF protection, backend role checks, active-user revocation, strict schema validation, SQL parameterization, escaped UI content, restrictive CSP, Secure cookies in production, bounded uploads, duplicate protection, optimistic case revisions, audit records and integrity checks for locally trusted models.

Rate limiting uses an in-memory demo backend or shared Redis. No per-request SQL rate-limit writes remain. Proxy headers are ignored unless the connecting peer and configured hop count are explicitly trusted. Production requires Redis; failures on limited endpoints return 503. Authentication still shares an IP limit for people behind the same NAT; deployment-specific abuse policy is necessary.

This is one organization's analyst workspace. There is no customer portal, multi-tenant isolation, bank/payment-provider authentication, SSO/MFA, encryption/key-management integration, tamper-evident external audit log or automated retention policy. Do not enter PINs, OTPs, real bank identifiers or sensitive production records. API callers can still submit fabricated amounts, parties or event times: ignoring the two deprecated hint fields does not make the entire feed authoritative.

Graph aggregates describe observed ledger relationships, not criminal status. SHAP is a model explanation, not a legal or causal explanation. Analyst outcomes are subjective until validated. Feedback remains vulnerable to mistakes, malicious administrators and selection bias; training never automatically activates a feedback candidate.

Model pickle/joblib files must be locally trusted. Checksums alone do not authenticate artifacts if an attacker can replace both metadata and model. Secrets and database files must not be committed. Backups and operational access controls are the operator's responsibility.

No independent security audit, production penetration test, regulatory certification, live banking integration or production deployment is claimed. See `reports/VALIDATION.md` for actual tests and `docs/OPERATIONS.md` for remaining runtime validation.
