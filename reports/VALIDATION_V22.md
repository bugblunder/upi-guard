# Validation — revision 2.2

Executed on 2026-11-10. These are local results, not a claim that a remote GitHub workflow or production deployment ran.

## Environment and results

Python 3.12.14 on Linux. Final application tests and retraining used a newly created isolated virtual environment
without inherited system packages. Runtime dependencies were installed from `requirements.lock`; `pip check` passed.
Node 24.22.1 was used for the jsdom checks. CI is configured for Python 3.12 and Node 22.

| Check | Observed result | Evidence / scope |
|---|---|---|
| Uploaded application baseline | 67 passed, 1 skipped | Run before edits; PostgreSQL service absent |
| Revised pytest suite | **100 passed, 1 skipped** | `junit-v22.xml`; 33 additional cases |
| Original research unit tests | **10 passed** | `python -m unittest discover -s research/tests -v` |
| Original result/source verification | Passed | 1,680 weekly rows, 240 monitor rows; preserved source hashes |
| New ML-security study | Completed | 5 seeds, 140 fits, 172,800 unique events; 1,680 weekly rows, 70 corruption-accounting rows |
| New result verification under `python -O` | Passed | Explicit checks remain active when assertions are disabled |
| Full application retraining | Selected model, test metrics, policy metrics and feature digest exactly match | `retraining-v22.json`; new artifact remains an unactivated candidate |
| Editable install and console entry point | Passed | `pip install --no-deps -e .`; `upi-guard --help` |
| Source distribution build | Passed | `python -m build --sdist`; standalone wheel deployment is not supported |
| UI/API integration | 8 checks, 0 errors | `ui-dom-check.json`; live HTTP API + jsdom, no visual-browser claim |
| Ruff correctness rules | Passed | E9/F63/F7/F82 only; not a complete style audit |
| Bandit | 0 findings in the application scan | `bandit-v22.json`; scanner coverage is limited |
| Python dependency audit | 0 known findings in 44 runtime pins after update | `dependency-audit-v22.json`; advisory database at execution time |
| Original dependency audit | 39 advisory records for Pillow 12.3.0 | `dependency-audit-before-v22.json`; records may refer to overlapping issues |
| npm dependency audit | 0 known findings | `npm-audit-v22.json`; developer-only jsdom dependency tree |
| Published security figure | Generated and visually inspected | Clear axes, units, legend and paired uncertainty; no real-world extrapolation |

Pillow was updated to 13.0.0 following the [upstream security release](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).
The application has no arbitrary-image upload endpoint; dependency findings do not establish a demonstrated exploit in this application.

## Reproduction commands

```bash
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest -q --junitxml=reports/junit.xml
python -m unittest discover -s research/tests -v
python -m research.verify_results research/results
python -O -m experiments.poisoning --verify
python -m ruff check upi_guard research experiments tests scripts
python -m bandit -r upi_guard -ll
python -m pip_audit -r requirements.lock --no-deps --disable-pip
npm ci --ignore-scripts
npm audit
python scripts/ui_smoke.py
python scripts/release_check.py
```

To reproduce the application-model check, train into a new output directory. Metadata normalization may change the
version identifier; compare feature digests, selected model and metrics instead of assuming identical serialized bytes.

## Not executed or not established

- PostgreSQL integration: one test skipped because no isolated service was available.
- Docker/Compose execution and deployment: Docker was unavailable; supplied configuration was not run here.
- Remote GitHub Actions, branch protections, publishing and private vulnerability reporting: configured/instructed, not activated.
- Independent penetration testing, real-browser rendering/CSP execution, production load and live banking integration: not performed.
- The original five-seed drift study and historic PaySim benchmark were not rerun end to end in this revision; original research tests and stored source/result consistency checks passed.
- Windows runtime execution was not tested; PowerShell setup instructions and Git line-ending rules are supplied.
- No real UPI validation, novel algorithm or measured poisoning defense is established.

The archive's consistency manifest and Git path checks detect accidental changes and disallowed runtime filenames.
They are not a comprehensive secret scan, an authenticity signature or a security certification.
