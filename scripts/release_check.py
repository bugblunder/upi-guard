"""Check release-file hashes and Git path hygiene without importing the model.

This detects accidental changes. It is not a secret scanner or a signed release.
Run --write only when intentionally preparing a new reviewed release.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"
EXCLUDED = {"MANIFEST.sha256", "reports/junit.xml", "reports/baseline-junit.xml"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths():
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    return sorted(set(output.decode().split("\0")) - {""})


def hygiene(files):
    for name in files:
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or
            any(p in {".venv", "venv", "node_modules", "instance", "__pycache__"} for p in path.parts) or
            any(p.startswith("pytest-of-") for p in path.parts) or
            (path.name.startswith(".env") and path.name != ".env.example") or
            path.suffix in {".db", ".key", ".pem", ".p12"} or
            "feedback" in path.name.lower() and path.suffix == ".csv"):
            raise ValueError(f"Private/runtime file must not be published: {name}")
        if (ROOT / path).is_symlink():
            raise ValueError(f"Symlink is not allowed in the source release: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        files = paths()
        hygiene(files)
        MANIFEST.write_text("".join(f"{digest(ROOT / name)}  {name}\n" for name in files
                                    if name not in EXCLUDED), encoding="utf-8")
    else:
        entries = [line.split("  ", 1) for line in MANIFEST.read_text().splitlines()]
        names = [name for _, name in entries]
        hygiene(names)
        if len(names) != len(set(names)):
            raise ValueError("Duplicate release manifest entry")
        for expected, name in entries:
            if digest(ROOT / name) != expected:
                raise ValueError(f"Release hash mismatch: {name}")
        if (ROOT / ".git").exists():
            hygiene(paths())
        print(f"Verified {len(entries)} release files. Hashes establish consistency, not authenticity.")


if __name__ == "__main__":
    main()
