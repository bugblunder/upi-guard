# API — revision 2.1

Every API route except login and CSRF retrieval requires a session. Mutations require the `X-CSRF-Token` header. Use `GET /api/csrf`, then `POST /api/login` with username/password and that token; save the cookie and the rotated token returned by login. `scripts/demo_api.py` is a runnable client.

## Score

`POST /api/transactions`

```json
{
  "transaction_id": "payment-001",
  "timestamp": "2025-06-01T12:00:00+05:30",
  "payer_id": "customer-001",
  "payee_id": "merchant-001",
  "device_id": "device-001",
  "amount": "499.00",
  "category": "shopping",
  "channel": "qr"
}
```

Optional deprecated `account_age_days` and `failed_attempts_1h` are accepted and stored but ignored for scoring. Defaults are zero. Labels, unknown fields, negative amounts, excessive precision, invalid identifiers or timestamps more than five minutes ahead are rejected with 422 and field-specific errors. Age here is not a customer's personal age.

Returns 201 for a new assessment, 200 for an exact normalized replay and 409 for a reused ID with different request contents. Late events return 201 and `context.late_arrival=true`. No old assessment is recalculated. Equivalent Decimal spellings and timezone offsets normalize identically. All payload fields, including deprecated hints, remain part of duplicate-content checking.

`risk_score` is 0–100, or null on scoring failure. `decision` is `allow` or `review` for new assessments. Historical `decline` rows from v2 may remain visible. Every decision is simulated; `allow` is not a real payment authorization. Cold-start scores (fewer than five earlier payments) generate no automated recommendation. The response records score margin to threshold, event/receipt times, skew, feature version, ignored hints, model version and the shadow anomaly signal. Rule reasons are observations, not SHAP contributions.

## Investigation and explanation

| Route | Purpose |
|---|---|
| GET `/api/transactions` | Paginated search; optional `q`, `decision`, `page` |
| POST `/api/transactions/{id}/review` | Open or return an analyst-requested case, including unflagged events |
| GET `/api/transactions/{id}/explanation` | SHAP from that transaction's original compatible model artifact and frozen features |
| GET `/api/cases` | Risk-prioritized queue; filter by `status` and `page` |
| PATCH `/api/cases/{id}` | Revision-checked assignment, notes, status and confirmed outcome |
| GET `/api/cases/{id}/history` | Creation/update audit trail |
| GET `/api/capacity` | Pending count, planned daily capacity, backlog warning |
| GET `/api/model` | Measured model comparison, uncertainty and budget/prevalence tables |
| GET `/api/drift` | Current-model numeric/categorical distribution diagnostics |
| GET `/api/users` | Active analyst identities for assignment |
| GET `/api/overview` | Persisted counts and service timing |

The transaction and case lists accept page numbers from 1 through 1,000,000. Invalid or larger numbers return 422 rather than overflowing the database offset.

SHAP returns all feature contributions, base value, units, reconstruction error and calibrated score. Logistic model attributions sum in calibrated log-odds units; tree probability contributions are explicitly identified when calibration is a separate transformation. These are explanations of a model, not proof that a transaction is fraudulent. Missing/incompatible original artifacts return 409; attribution failures return 503. No newer model is silently substituted.

A case update includes `revision`, `status` (`open`, `investigating`, `resolved`), `outcome`, `assigned_to`, and `notes`. Resolution requires `fraud` or `legitimate`. Non-admin analysts must claim their own case and cannot edit another analyst's assignment. Stale revisions return 409. Manually opened cases have creation audit events whose details differ from update events.

## Admin operations

`POST /api/import` accepts a UTF-8 CSV in multipart field `file`, maximum 2 MB and 1,000 rows. Required headers match required transaction fields; the two deprecated hints are optional. Duplicate, unknown and label columns are rejected. Schema validation finishes before scoring any row; valid rows are then replayed chronologically. ID conflicts are reported per row, so a semantically conflicting file may be partially processed.

`GET /api/feedback.csv` exports confirmed outcomes under the frozen-feature training contract: `transaction_json,features_json,feature_version,fraud_label,label_available_at,source`. This is consumed by `merge-feedback` and `train-snapshot`, not by the raw-transaction `train` command. Legacy incompatible snapshots are skipped and counted in a response header. `GET /api/sample.csv` supplies a transaction example; `GET /api/audit` returns recent global audit actions.

Default limits: login 20/IP and 8/username per five minutes, scoring 120/user/minute, imports 5/user/five minutes, explanations 30/user/minute. Correct proxy configuration matters. Redis-backed production limits are shared across workers. Service outages return 503, exceeded limits 429. Local in-memory limits are process-local.
