# Original project to version 2

This release is a separate upgrade. The original uploaded ZIP is preserved. It is not bundled again because its datasets/assets/reports have unresolved provenance and its saved TensorFlow artifacts do not match the documented results.

## Confirmed original findings

The archive has 163 files, one Python application, seven templates, three CSVs, two HDF5 models, notebooks and project documents. The primary dataset contains 2,666 rows: 1,578 fraud-labelled and 1,088 legitimate-labelled events, all dated 2022. Every `upi_number` is unique. The two primary CSV copies differ in 27 identifier cells. The upload CSV contains 925 rows and a different identifier representation. There is no complete reproducible source-to-training-data pipeline.

The model described as a CNN uses Dense(64), Dense(128), and Dense(1) layers. The notebook compares its training-set accuracy with other models' test-set accuracy. The application refits preprocessing on all rows rather than using the training scaler. Model saving is conditional on the file not already existing. A NumPy replay of the stored deployed weights on the notebook-defined 400-row diagnostic subset yielded 82.25% with the reconstructed training scaler and 82.75% with the application's scaler. These diagnostics cannot establish an unseen test score for the saved artifact because its exact training lineage is unknown.

The JavaScript login checks admin/admin without backend access control. The Train/Test button only waits and redirects. Charts use fixed numbers. Age calculation fails in the reviewed pandas environment. One included CSV fails upload because its index header does not match `Id`. The upload form targets localhost explicitly. The reports describe algorithms and database/payment features absent from the code; one contains invalid Java-like code presented as Python. These issues must not be carried into a new submission.

## Resolution map

| Original issue | Version 2 treatment |
|---|---|
| Incorrect CNN description | Accurately named tabular baselines; v2 selected gradient boosting, v2.1 selects Logistic Regression |
| Training accuracy presented as comparative result | Chronological final test and consistent metrics across models |
| Scaler mismatch | Same persisted pipeline at evaluation and serving |
| Stale model saving | Immutable versioned artifacts and explicit activation |
| Client-side login only | Backend authentication, roles and CSRF |
| Simulated training button | Actual offline CLI training; UI displays measured results |
| Hardcoded dashboard | Database-backed counts and model reports |
| Invalid age calculation | DOB removed from the contract; calendar-age utility covered by tests |
| Incompatible CSVs | One explicit JSON/CSV schema; legacy inputs rejected with explanations |
| No persistent workflow | Transactions, cases, feedback and audit history |
| Unclear data origin | Included generator/data card; no real-transaction claims |
| Outdated/unrelated UI assets | New self-contained HTML/CSS/JS dashboard |
| Unsupported report claims | Rewritten project report, limitations and measured validation |

Version 2 does not attempt to claim that the original card-style dataset was real UPI data. It does not translate arbitrary state codes or identifiers into supposed genuine Indian payment records.
