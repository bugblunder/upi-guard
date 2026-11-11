# Setup and reproducibility

Use Python 3.12 and run commands from the extracted repository root. Keep the checkout:
artifacts and Alembic migrations are repository resources. The supported installation is editable/source based.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m upi_guard init
.\.venv\Scripts\python.exe -m upi_guard demo --count 300
.\.venv\Scripts\python.exe -m upi_guard serve
```

## macOS / Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m upi_guard init
python -m upi_guard demo --count 300
python -m upi_guard serve
```

Open http://127.0.0.1:5000 and sign in as `admin` with the password chosen during `init` (12–128 characters).
The generated local session secret and SQLite database live in ignored `instance/`.
Subsequent starts only need `python -m upi_guard serve`. Do not rerun `init` for an existing username.

The short demo may produce no automatic review cases. Use **Transactions → Open case** to investigate any event.
Repeating a demo seed replays existing decisions; a new `--seed` produces different event identifiers.
Never enter real bank details, PINs or OTPs.

## Useful commands

```bash
python -m upi_guard add-user analyst --role analyst
python -m upi_guard check
python -m upi_guard simulate --count 12000 --seed 43 --output data/seed43.csv
python -m upi_guard train --input data/seed43.csv --artifacts candidates --seed 43
python -m upi_guard activate VERSION --artifacts candidates
```

`activate` validates a candidate before changing the pointer. For that example, set `ARTIFACT_ROOT` to the absolute
`candidates` directory when serving, then restart every worker. Training does not activate by default.
Do not upload or load third-party joblib/pickle files. Checksums cannot authenticate an attacker-controlled model and manifest.
The deployment scikit-learn version must match training; upgrade it by retraining and reviewing a new candidate.

## Tests and optional UI checks

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m unittest discover -s research/tests -v
python -m ruff check upi_guard research experiments tests scripts
python -m bandit -r upi_guard -ll
python -m pip_audit -r requirements.lock --no-deps --disable-pip
npm ci --ignore-scripts
python scripts/ui_smoke.py
```

The PostgreSQL test skips without an isolated `TEST_DATABASE_URL` ending in `/guard_test`.
CI supplies that service. The UI test uses jsdom and a real local HTTP API; it does not verify browser layout or CSP execution.

## Docker development environment

```bash
python scripts/configure.py
docker compose up -d db redis
docker compose build app
docker compose run --rm app python -m upi_guard init
docker compose run --rm app python -m upi_guard demo --count 300
docker compose up -d app
```

`configure.py` creates random secrets in `.env` and refuses to overwrite it. The UI binds to loopback.
See [OPERATIONS.md](OPERATIONS.md) for HTTPS, Redis, trusted proxies, migrations and backups.
Docker configuration is supplied; its presence alone does not mean a deployment was tested.

## Troubleshooting

| Symptom | Check |
|---|---|
| Model unavailable | Run `python -m upi_guard check`; use the exact runtime pins and verify `artifacts/active.json`. Do not bypass integrity checks. |
| Login fails after account revocation | Reload to obtain a new CSRF token; a revoked account still requires administrator reactivation. |
| User already exists | Start `serve`; use `add-user` for a different account. |
| Empty review queue | Small demos are often cold-start/shadow cases. Open a case manually. |
| Experiment output exists | Select a new output directory; completed evidence is never overwritten. |
| Release hash mismatch after editing | Expected for modified source. Review/test changes, then intentionally regenerate the release manifest. |
