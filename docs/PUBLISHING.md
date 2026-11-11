# Publish a reviewable GitHub repository

The delivery archive contains source, synthetic sample data, the demo model and reproducible evidence. It excludes
local accounts, secrets, databases, dependency folders and transient outputs. No remote repository has been created or pushed.

## First commit

Extract the archive, enter `upi-guard`, and run:

```bash
git init -b main
git add .
git status --short
python scripts/release_check.py
git diff --cached --check
git commit -m "Add UPI Guard ML security research prototype"
```

Configure your own Git author name and email if Git requests them. Create an empty repository on GitHub, then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/upi-guard.git
git push -u origin main
```

Replace `YOUR_USERNAME`. The commands publish source; they do not deploy the application.

## Repository settings

- Use the description and topics in [PORTFOLIO.md](PORTFOLIO.md).
- Enable private vulnerability reporting and dependency alerts.
- Run the included CI workflow and inspect the service-backed PostgreSQL, UI, dependency and Docker checks.
- Protect `main` using passing CI as a merge requirement once the remote checks have run successfully.
- After reviewing the first release, create a `v2.2.0` tag and a release that links the protocol, model card and actual validation report.

## Ownership, attribution and license

The uploaded archive contained no project license or verified contributor inventory. No copyright ownership,
sole-authorship claim or open-source grant has been invented in this revision. Before choosing a license or making
public authorship claims, confirm the origin of inherited code, data and figures and credit actual contributors.
Add your chosen `LICENSE` when you have established those rights. Repository visibility alone does not select a license.

No real UPI data is required for the supplied demo. Do not commit external datasets or real feedback exports merely
because a `.gitignore` rule is absent. Review staged contents each time.

## Future releases

Run the checks, keep old experiment evidence immutable and use a new directory for new runs. Once changes are reviewed,
regenerate the consistency manifest and stage it with the changes:

```bash
python scripts/release_check.py --write
python scripts/release_check.py
git add MANIFEST.sha256
```

The manifest is not a signature. Dependency findings can change with advisory databases; a past clean audit is not a permanent guarantee.
