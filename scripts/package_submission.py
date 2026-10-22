"""Package the committed source tree and its complete reachable Git history."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if git("status", "--porcelain").strip():
        parser.error("Commit all changes before packaging.")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("Write the archive outside the repository.")
    commit = git("rev-parse", "HEAD").decode().strip()
    branch = git("branch", "--show-current").decode().strip()
    source = zipfile.ZipFile(io.BytesIO(git("archive", "--format=zip", "HEAD")))
    files = {"source/" + name: source.read(name) for name in source.namelist() if not name.endswith("/")}
    forbidden = [name for name in files if name.endswith("/.env") or "/data/raw/" in name or "/.venv/" in name]
    if forbidden:
        parser.error("Refusing to package local secrets or raw client data.")
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory) / "decision-brief.bundle"
        git("bundle", "create", str(bundle), "HEAD", "--branches", "--tags")
        subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=ROOT, check=True, capture_output=True)
        files[bundle.name] = bundle.read_bytes()
    files["VERSION.json"] = (json.dumps({"repository": "https://github.com/BoytsovM/decision-brief",
        "commit": commit, "branch": branch, "tags": git("tag", "--points-at", "HEAD").decode().split(),
        "commit_time": git("show", "-s", "--format=%cI", "HEAD").decode().strip()}, ensure_ascii=False, indent=2)+"\n").encode()
    files["START_HERE.txt"] = ("Decision Brief submission\n\nRead source/SUBMISSION.md and source/README.md.\n"
        "Run: cd source && docker compose up --build --wait\n"
        "Restore history: git clone -b " + branch + " decision-brief.bundle decision-brief\n"
        "This archive does not publish changes to GitHub.\nCommit: " + commit + "\n").encode()
    files["SHA256SUMS.txt"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                                          for name, data in sorted(files.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    print(json.dumps({"archive": str(output), "commit": commit, "files": len(files),
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
