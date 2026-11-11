"""Build the evidence report from saved measurements, not hand-entered metrics."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
active=json.loads((root/'artifacts/active.json').read_text())['version']
r=json.loads((root/'artifacts'/active/'metrics.json').read_text())
old=json.loads((root/'reports/v2_original/metrics.json').read_text())
m=r['models'][r['selected_model']]['test'];o=old['models'][old['selected_model']]['test']
pay=json.loads((root/'reports/paysim-benchmark.json').read_text());load=json.loads((root/'reports/load-contention.json').read_text())
def pct(v):return f'{v*100:.2f}%'
def table(headers,rows):return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)
from sys import path
path.insert(0,str(root))
from upi_guard.evaluation import prevalence_table
projection=prevalence_table(o['recall'],o['false_positive_rate'])
text='''# Technical review response — version 2.1

The review is substantially correct. Version 2 was an engineering demonstration, not evidence of an industrial fraud detector. This revision fixes concrete integration defects and makes the negative experimental results visible. It does not turn synthetic success into real-world evidence.

## 1. Data realism, prevalence and workload

The original generator still defines the labels, and its scenario shortcuts remain a limitation. The project does not claim representative UPI prevalence. Adding features or changing a threshold cannot fix this. The old model's original metrics are preserved in `reports/v2_original/metrics.json`.

At fixed sensitivity and false-positive rate, precision is `prevalence * recall / (prevalence * recall + (1-prevalence) * FPR)`. Holding those rates constant is a hypothetical projection, not a UPI forecast. For the original model:

'''
text+=table(['Assumed prevalence','Projected precision','Alerts / 100,000'],[(pct(x['prevalence']),pct(x['precision']),round(x['alerts_per_100000'])) for x in projection])
text+='''
The revision exposes 0.5%, 1%, 2%, 5%, 10% and 20% validation review budgets. The default 2% is illustrative, not an agreed business capacity. A separate configured daily capacity shows queue backlog; every recommendation is retained. There is no silent alert dropping. Lower volume has a severe recall cost:

'''
text+=table(['Metric','Original v2 selected model','Revised selected model'],[(k,pct(o[k]),pct(m[k])) for k in ['precision','recall','false_positive_rate','alert_rate']])
text+=f'\nRevised model: `{r["selected_model"]}`; threshold `{m["threshold"]:.8f}`. The current inspected test has {m["fraud_count"]} fraud events among {m["n"]} rows. It catches {m["confusion_matrix"][1][1]} and misses {m["confusion_matrix"][1][0]}. This is not useful evidence of a deployable detector.\n'
text+='''
## 2. Selection uncertainty and threshold sensitivity

The original AP differences were too small to justify a strong winner claim. AP and F1 evaluate different things, so being best on validation AP never guaranteed best test F1. Selecting Random Forest after seeing its better test F1 would reuse the test set for selection.

The revision reports 300 paired payer-cluster bootstrap resamples of validation predictions and chooses the simplest candidate whose AP deficit interval includes zero. This is an explicitly documented simplicity heuristic, not proof of equivalence. It does not cover refitting uncertainty, temporal dependence between payers or multiple-comparison bias. The test result is calculated after that run's choice, but the old test period was already inspected during development. It is consequently labelled development evidence.

'''
text+=table(['Candidate','Validation AP','95% AP interval'],[(k,f'{v["ap"]:.4f}',f'{v["ap_interval"][0]:.4f}–{v["ap_interval"][1]:.4f}') for k,v in r['selection_uncertainty']['candidates'].items()])
text+='''
Three new simulator draws (seeds 101, 202, 303) were evaluated with the model, calibrator and threshold frozen. They are recorded in `reports/seed-validation.json`; they remain tests of the same generator. They do not establish robustness to new fraud mechanisms.

A threshold is necessarily a discontinuity. Raising it does not remove that property. The response now records the unrounded probability margin to the threshold, and no score automatically declines a payment. There is no claim that a near-threshold allow/review difference reflects a meaningful difference in ground truth.

## 3. Cold start remains unresolved

Cold-start novelty no longer treats every first recipient/device as suspicious. Fewer than five earlier payments invokes shadow-only recommendations, and results for cold histories and unseen payer identities are separately reported. This avoids pretending the cold-start score has been validated, but sacrifices detection. At the revised threshold the 374-event unseen-payer slice has **zero recall** (34 fraud events, none flagged). This is not a solved cold-start model. Representative onboarding data and an independently assessed fallback policy are still needed.

## 4. Explanations and action policy

The arbitrary `max(0.85, threshold + 0.25)` decline threshold is removed. Rule observations are retained only as context; they do not override the model to create unbudgeted recommendations. Model outages are explicitly routed to review and may overload the queue.

Per-case SHAP explains the original compatible model and frozen features. All contributions and the baseline are returned with units and a reconstruction check. Logistic Regression contributions reconstruct calibrated log odds; tree probability contributions are identified as preceding calibration. An unavailable historical model yields an unavailable explanation, not one from the current replacement. The UI separates model attribution from rule flags. SHAP is associational and background-dependent, not causal evidence.

## 5. Feedback integration

Export, merge and training now share a versioned frozen-feature CSV contract. `merge-feedback` combines reviewed cases with an explicit base snapshot; `train-snapshot` consumes it without inventing missing raw history. Duplicate IDs with conflicting immutable features are rejected. Source, feature version and label-availability time are retained. Late labels are excluded from historical fit/calibration/validation partitions until mature. Candidate training does not automatically activate a model.

This closes the file-format and point-in-time integration gap. It does not eliminate selective-review bias, label mistakes, or the need for representative later validation data. Unreviewed cases are never silently labelled legitimate. A feedback candidate must be reviewed and explicitly promoted.

## 6. Ingestion, limits and load

- Timestamps up to five minutes ahead are accepted, with skew recorded; larger future offsets return useful validation errors.
- Explicit trusted proxy networks and hop counts recover client addresses only from configured peers. Direct spoofed forwarding headers remain ignored.
- Late events are accepted, marked and scored from available earlier event-time history. Old decisions and feature snapshots stay frozen.
- Rate limits use a thread-safe bounded demo backend or an atomic Redis sliding-window backend. No SQL rate-limit writes remain. Production requires Redis. Lua concurrency was tested with fakeredis; a real Redis deployment remains untested here.
- Caller-supplied account age and failed-attempt fields are ignored by both features and rules. The payment feed itself still needs an authenticated provider integration; a browser request is not authoritative bank telemetry.

'''
text+=f'The local contention experiment ran {load["requests"]:,} requests with {load["workers"]} workers and 500 seeded payments. It produced {load["unexpected_responses"]} unexpected responses, {load["throughput_rps"]} requests/s, p95 {load["p95_ms"]} ms and p99 {load["p99_ms"]} ms. This exposes a latency problem; it does not prove industrial capacity. SQLite writer serialization and synchronous feature/anomaly work remain constraints. The run lasts only {load["elapsed_seconds"]:.1f} seconds; it is not a soak test.\n'
text+='''
## 7. Roadmap gaps

Implemented: local graph aggregates (recipient fan-in, payer incoming flow and pass-through ratio), shadow Isolation Forest with separate metrics, numeric PSI/KS and categorical JS/OOV diagnostics, and a public PaySim benchmark. Graph feature mechanics are covered by constructed-case tests. There is no validated mule-account classifier; the supplied generator does not provide that evidence. Isolation Forest is a shadow signal, not an automatically trusted fraud probability. Distribution drift is not measured performance drift. Reviewed-only outcomes cannot establish population recall.

PaySim is independently generated synthetic mobile-money data. Its native-schema experiment uses a label-independent 10% systematic sample, pre-transaction attributes only and chronological whole-step partitions. No UPI device/channel fields were invented. It is separate from the deployed UPI model. The validation partition contains only 30 fraud cases; the test contains 422, and prevalence changes materially across time. These limits matter when interpreting calibration and thresholds.

'''
text+=table(['PaySim model','Test precision','Test recall','Test FPR','Test alerts'],[(k,pct(v['test']['precision']),pct(v['test']['recall']),pct(v['test']['false_positive_rate']),pct(v['test']['alert_rate'])) for k,v in pay['models'].items()])
text+='''
Logistic Regression was the predeclared public-data baseline, and gradient boosting is a comparison. No test-based winner was deployed. Dataset, archive checksum, sampling and step boundaries are recorded in the JSON report. IEEE-CIS was not evaluated.

## What would justify the next stage

Authorized representative transaction data, delayed outcomes from more than the review queue, chronological arrival/reconciliation records, operational review capacity and a frozen later holdout are prerequisites for a meaningful detector. PostgreSQL/Redis multiworker load, prolonged failure/recovery tests and real browser verification remain engineering gates. Until then, describe this as a risk-investigation research prototype with reproducible experiments and explicit failure modes.
'''
(root/'docs/REVIEW_RESPONSE.md').write_text(text)
(root/'docs/PROJECT_REPORT.md').write_text('# Project report — version 2.1\n\nThe current technical report is [REVIEW_RESPONSE.md](REVIEW_RESPONSE.md). It contains the measured before/after comparison, uncertainty, workload trade-offs, unresolved cold-start results, public benchmark and remaining deployment gates.\n\nThe implementation comprises a Flask analyst UI and session API, shared point-in-time features, SQLAlchemy/Alembic persistence, offline scikit-learn pipelines, SHAP, a Redis rate-limit backend and investigation feedback snapshots. See DATA_CARD.md for provenance and the contract, API.md for interfaces, and OPERATIONS.md for deployment/model lifecycle.\n\nThe final-year contribution is the reproducible investigation workflow and honest experimental evaluation. No novel algorithm, real UPI effectiveness or industrial deployment is claimed.\n')
print('Wrote current review and project reports')
