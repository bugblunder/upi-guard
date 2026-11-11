# Validation — revision 2.1

**Current review: 67 tests passed, 1 PostgreSQL integration test skipped; all 8 UI DOM/API checks passed.** The added tests cover oversized and invalid pagination on both list endpoints. A disposable SQLite workspace also completed `init`, `demo --count 30`, and `check` with a ready database and model. Dependency consistency passed with `uv pip check`. Docker, a real PostgreSQL server, a real Redis server, and a full browser remained unavailable for this review.

The archived `junit-v21.xml` and `tests-v21.log` show the earlier 65-test build. They have not been replaced with the current review's test log.

All measurements below were executed locally. The result files give precise scope and configuration; supplied deployment configuration is not evidence of deployment.

| Check | Evidence | Scope |
|---|---|---|
| Python regression suite | `junit-v21.xml`, `tests-v21.log` | Authentication, contracts, features, duplicate concurrency, late events, skew, migrations, feedback training, SHAP additivity, drift serialization and limiter concurrency |
| UI integration | `ui-dom-check.json` | Eight passing DOM/API checks, including manual case creation and SHAP; canvas/dialog primitives stubbed |
| Native PaySim benchmark | `paysim-benchmark.json` | Full archive read, 636,262-row systematic sample, chronological step boundaries, two separate native-schema models |
| Frozen model on fresh simulator draws | `seed-validation.json` | Seeds 101, 202, 303; same generator, no new scenario families |
| HTTP contention | `load-contention.json` | 2,000 requests / 16 workers, 500 existing records, growing shared histories, 0 unexpected responses |
| Active training | `artifacts/<active-version>/metrics.json` | Three supervised candidates, paired validation uncertainty, budget curves, prevalence sensitivity, cold-start/unseen slices and shadow Isolation Forest |
| Dependency consistency | `pip check` | Passed in tested isolated Python 3.12 environment; production dependency closure pinned |

The old model's metrics remain in `v2_original/metrics.json`; other original reports in that folder are historical. They are not evidence for the revised code.

The local load result is approximately 49.6 requests/s with p95 1.77 s and p99 3.70 s, using one threaded Werkzeug process and SQLite. This is poor tail latency for a hypothetical payment-serving target, not an industrial throughput claim. The test is a short contention run, not a soak test. The score endpoint includes synchronous anomaly computation. Rate limiting was enabled with an explicitly raised local test quota to permit the run; standard quota enforcement is tested separately.

Redis's atomic Lua path was exercised using a shared fakeredis server with Lua under concurrent clients. It was not tested against a real Redis daemon or a distributed deployment. In-memory limiting remains single-process only. The optional PostgreSQL integration test is skipped when `TEST_DATABASE_URL` is absent.

Not executed here: real PostgreSQL/Redis deployment, Docker container startup, remote GitHub CI, independent security review, a real browser rendering/CSP/mobile check, Windows installation, a sustained production-like load/soak/failover test, IEEE-CIS benchmark or real UPI validation. Chromium could not run in this environment; DOM checks do not replace browser testing.

Model validity remains weak: the inspected synthetic holdout was used during development, and the default capacity policy detects only 28 of 237 fraud examples. Unseen-payer recall is zero. PaySim is also synthetic and validates a separate model/schema. The new graph features and anomaly signal are implemented, not proven useful for real mule/fraud detection.
