"""Read-only source-admission level report (SRC-01, P6).

    python -m scripts.source_successor_levels <path> [<path> ...] [--ref REF] [--json]

For each existing file it reports main's blob id and LF sha256, how many A2
inventory generations pin them, every other tracked file that contains either
identity (a frozen record), and a suggested level:

* L0  pinned only in A2 inventories: change freely.
* L1  also pinned in a frozen record, and every reader of that record is itself
      pinned only in A2: register an exact successor entry plus one additive
      admission in the reader.
* L2  the file is root-pinned: stop and report.
* L2? a reader of the record is pinned outside A2. It is L2 only if that reader
      must be edited (it checks the record against the file's bytes); a reader
      that merely mentions the record, or checks only the record's own hash, does
      not block. Read each named reader before deciding.

The level is a suggestion found by grep, not a proof: confirm L1 and L2? by
reading the named readers. The tool runs ``git show``, ``git rev-parse`` and
``git grep`` only, always against one pinned commit (main's tree, not your
work tree). It never writes, fetches or touches the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A2_INVENTORY = re.compile(
    r"^tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v\d+\.json$")
BATCH_FILE = re.compile(r"^scripts/source_successor_batch_\d{4}_[a-z0-9_]+\.py$")
A2_PATHSPEC = ":(exclude)tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v*.json"
ROOT_PINNED = (
    "scripts/audit_core_01d_ci_offline_transport_boundary.py",
    "tests/conftest.py",
    "tests/offline_transport.py",
    "tests/offline_linux.py",
    "tests/_offline_bootstrap/sitecustomize.py",
)


class LevelError(RuntimeError):
    pass


def _git(root: Path, *args: str, ok: tuple[int, ...] = (0,)) -> bytes:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if done.returncode not in ok:
        raise LevelError("git " + " ".join(args) + " failed: " + done.stderr.decode(errors="replace").strip())
    return done.stdout


def default_ref(root: Path) -> str:
    for candidate in ("origin/main", "main", "HEAD"):
        if subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", candidate],
                          capture_output=True, check=False).returncode == 0:
            return candidate
    raise LevelError("no origin/main, main or HEAD to read main's bytes from")


def identity_at(root: Path, ref: str, path: str) -> tuple[str, str]:
    """Main's git blob id and LF sha256 for ``path`` (read from git, not the work tree)."""
    blob = _git(root, "rev-parse", "--verify", f"{ref}:{path}").decode().strip()
    raw = _git(root, "show", f"{ref}:{path}").replace(b"\r\n", b"\n")
    return blob, hashlib.sha256(raw).hexdigest()


def resolve_commit(root: Path, ref: str) -> str:
    """The 40-hex commit for ``ref`` (git grep is only run against a pinned commit)."""
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise LevelError(f"{ref} does not resolve to a commit")
    return commit


def _grep_files(root: Path, commit: str, needles: tuple[str, ...], *, skip_a2: bool = False) -> list[str]:
    """Tracked files at ``commit`` that contain any needle (fixed strings)."""
    command = ["grep", "-l", "-F"]
    for needle in needles:
        command += ["-e", needle]
    command += [commit, "--", "."] + ([A2_PATHSPEC] if skip_a2 else [])
    prefix = commit + ":"
    return sorted(line[len(prefix):] if line.startswith(prefix) else line
                  for line in _git(root, *command, ok=(0, 1)).decode().splitlines() if line)


def _pinned_outside_a2(root: Path, commit: str, path: str) -> list[str]:
    try:
        blob, digest = identity_at(root, commit, path)
    except LevelError:
        return []  # new file: nothing can pin its main bytes yet
    return [name for name in _grep_files(root, commit, (blob, digest), skip_a2=True) if name != path]


def classify(root: Path, path: str, ref: str) -> dict:
    commit = resolve_commit(root, ref)
    blob, digest = identity_at(root, commit, path)
    holders = _grep_files(root, commit, (blob, digest))
    a2 = [name for name in holders if A2_INVENTORY.match(name)]
    records = [name for name in holders
               if not A2_INVENTORY.match(name) and not BATCH_FILE.match(name) and name != path]
    report = {"path": path, "ref": ref, "commit": commit, "blob": blob, "sha256": digest,
              "a2_generations": len(a2), "records": records, "readers": {}, "level": "L0", "reason": ""}
    if path in ROOT_PINNED:
        report.update(level="L2", reason="root-pinned file: out of reach for a registry entry")
        return report
    if not records:
        report["reason"] = "pinned only in A2 inventories"
        return report
    blockers: list[str] = []
    for record in records:
        readers = [name for name in _grep_files(root, commit, (record,), skip_a2=True)
                   if name.endswith(".py") and name not in (record, path)]
        report["readers"][record] = readers
        for reader in readers:
            pinned = _pinned_outside_a2(root, commit, reader)
            if pinned:
                blockers.append(f"{reader} (reads {record}) is pinned in {', '.join(pinned)}")
    if blockers:
        report.update(level="L2?", reason="review by hand: a reader of a frozen record is pinned outside A2 ("
                      + "; ".join(blockers) + ")")
    elif any(report["readers"].values()):
        report.update(level="L1", reason="pinned in a frozen record whose readers are pinned only in A2")
    else:
        report.update(level="L1", reason="pinned in a frozen record; no reader found by grep, verify by hand")
    return report


def render(report: dict) -> str:
    lines = [f"{report['path']}",
             f"  main ({report['ref']} = {report['commit'][:12]}): blob {report['blob']}  sha256 {report['sha256']}",
             f"  A2 inventory generations pinning it: {report['a2_generations']}"]
    for record in report["records"]:
        readers = report["readers"].get(record) or []
        lines.append(f"  record: {record}" + (f"  (read by: {', '.join(readers)})" if readers else ""))
    lines.append(f"  suggested level: {report['level']} - {report['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("paths", nargs="+", help="repository-relative paths of existing files")
    parser.add_argument("--ref", help="ref holding main's bytes (default: origin/main, main or HEAD)")
    parser.add_argument("--json", action="store_true", help="print one JSON document")
    args = parser.parse_args(argv)
    base = ROOT if root is None else Path(root)
    try:
        ref = args.ref or default_ref(base)
        reports = [classify(base, path, ref) for path in args.paths]
    except LevelError as exc:
        print("source_successor_levels: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        print("\n".join(render(report) for report in reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
