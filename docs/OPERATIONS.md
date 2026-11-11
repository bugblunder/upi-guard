# Operations — revision 2.1

This application is a research sandbox. An `allow` response means no automatic review recommendation; it does not authorize a payment. Cold starts with fewer than five prior payments are shadow-only. Model failure still creates a manual-review case and can cause queue overload. There is no automatic decline threshold.

## Install and migrate

Use Python 3.12 and `requirements.lock`. For a new workspace run `python -m upi_guard init`; choose a strong password. Existing workspaces must run `python -m upi_guard migrate` before starting this version. Migration 0002 adds indexed recipient IDs and a frozen assessment-context field; old feature snapshots remain marked legacy and cannot be reused under feature version 2.1.0. Back up the database and artifacts together before migration. Test restore on a disposable database.

Use `docker compose up -d db redis`, build the app and run migrations/init through the app container before starting it. Docker, a real PostgreSQL server, and a real Redis server were not available for runtime verification in the build environment. CI definitions are supplied, not evidence of remote CI execution.

## Rate limiting and reverse proxies

Local development uses a bounded, thread-safe in-process sliding-window limiter. It is suitable only for one process; a restart clears it. Production requires `REDIS_URL`, with atomic Lua operations and Redis server time. No rate-limit write touches the transaction database. Redis outages return 503 for limited endpoints; readiness also reports failure. The Lua concurrency contract was tested with fakeredis and Lua, not a real Redis deployment. Redis must be on a private network, with suitable authentication/TLS if the deployment requires it. The supplied Compose Redis has a bounded memory limit and no eviction.

Forwarded headers are ignored by default. Set `TRUSTED_PROXY_CIDRS` to the exact proxy network(s) and `PROXY_HOPS` to the number of forwarding proxies. Only a directly connected peer in those CIDRs can trigger ProxyFix. The proxy must sanitize/append the correct forwarding headers, and direct external access to the app should be blocked. Do not trust every address or enable hops without knowing the topology. Documentation: https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/ . Shared NAT addresses can still share IP-based login limits.

Production also requires `SECRET_KEY`, `APP_ENV=production`, HTTPS and correct `TRUSTED_HOSTS`. Secure cookies are enabled in production. The Flask development server is for local demonstrations; Compose uses Gunicorn.

## Model lifecycle and feedback

`train` creates an immutable candidate; it does not activate it by default. Read `metrics.json`, budget curves, base-rate sensitivity, uncertainty and cold-start results. The old test set is already exposed; it cannot establish the benefit of revisions. A different simulator seed is not a different real-world population.

```bash
python -m upi_guard train --input data/synthetic_training.csv --artifacts candidates
# Export reviewed_feedback.csv through the authenticated admin UI.
python -m upi_guard merge-feedback --base artifacts/VERSION/training_snapshot.csv --feedback reviewed_feedback.csv --output data/merged.csv
python -m upi_guard train-snapshot --input data/merged.csv --artifacts candidates
# Only after inspecting the candidate, substitute its actual version:
python -m upi_guard activate VERSION --artifacts candidates
```

The app's `ARTIFACT_ROOT` must point at the directory you activate; restart **all** workers. To roll back, activate a previously reviewed compatible version and restart. Version 2.0 feature artifacts are incompatible with 2.1 code and require the previous application release as well.

Feedback uses the exact original feature snapshot. A duplicate ID with conflicting transaction content or features is rejected. Label-availability timestamps prevent late investigator outcomes from appearing prematurely in training/calibration/validation. Consequently, recently reviewed old events may be excluded until the historical split advances; the report gives counts of mature labels used. Provide enough newer, representative labelled data to create a valid later validation/test period. Feedback-only retraining is not a defensible population experiment. Review labels are biased and can also be wrong. Training a candidate is not automatic promotion.

Artifacts are locally trusted joblib files: hashes detect corruption but do not defend against an attacker replacing both artifact and manifest. Do not accept uploaded model files.

## Monitoring and capacity

`/api/capacity` reports pending cases, configured `REVIEW_CAPACITY_PER_DAY` (default 100), backlog days and a capacity warning. Cases are sorted by descending risk and retained even when capacity is exceeded; no alert is silently dropped to manufacture a budget result. The 2% validation target is not a hard live queue cap or a service-level promise. Required staffing scales with traffic; 2% of one million payments is still 20,000 reviews.

`/api/drift` uses the latest 500 assessments for the current model version. Numeric PSI and KS effect-size tests, plus categorical Jensen–Shannon divergence and unseen-category rates, detect more than mean shifts. Fewer than 30 rows is insufficient. Thresholds are illustrative, correlated events limit p-value interpretation, and covariate drift is not the same as performance deterioration. Reviewed-only outcomes cannot estimate population recall.

`/health/live` checks process availability; `/health/ready` checks schema, loaded artifact and configured Redis connectivity. A per-request model failure returns review/unavailable, but does not permanently trip a circuit breaker. JSON request logs omit payment bodies and credentials. Forward logs to an operational system for production; no managed alert service is installed.

## Measured performance limit

The 2,000-request local contention test includes recurring payer/recipient histories, duplicates, late events, invalid requests, authentication, in-memory rate limiting, anomaly scoring and commit time. It achieved about 49.6 requests/s, but p95 was 1.77 s and p99 3.70 s. SQLite serializes writers, and synchronous feature/anomaly work adds latency. This does not meet an assumed low-latency payment-serving target. PostgreSQL/Redis multiworker load, resource limits, longer runs, failure recovery and upstream timeouts remain unvalidated. See `reports/load-contention.json` for exact scope.
