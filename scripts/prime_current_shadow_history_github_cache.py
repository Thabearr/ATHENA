"""Prime the Current Shadow immutable GitHub history transport cache.

This command is transport-only.  It deliberately does not construct a current
football handoff, claim a complete history proof, price anything, select anything,
or place a wager.  The normal Current Shadow builder remains the authority and
will re-request/re-record/replay every exact GitHub read when it runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from domain import current_fotmob_latest_durable_fresh_history as latest_history
from scripts import current_shadow_history_github_persistent_cache as cache


SCHEMA_VERSION = 1
STATUS = "CURRENT_SHADOW_HISTORY_TRANSPORT_CACHE_PRIMED_NO_EVIDENCE_AUTHORITY"


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _cache_inventory(root: Path) -> tuple[int, int, str]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    if root.is_dir() and not root.is_symlink():
        for metadata_path in sorted(root.glob("*.json")):
            if metadata_path.is_symlink() or not metadata_path.is_file():
                continue
            try:
                raw = metadata_path.read_bytes()
                metadata = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if type(metadata) is not dict or _canonical(metadata) != raw:
                continue
            endpoint = metadata.get("endpoint")
            digest = metadata.get("payload_sha256")
            size = metadata.get("payload_size_bytes")
            if type(endpoint) is not str or type(digest) is not str or type(size) is not int:
                continue
            payload_path = metadata_path.with_suffix(".payload")
            if payload_path.is_symlink() or not payload_path.is_file():
                continue
            payload = payload_path.read_bytes()
            if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
                continue
            total_bytes += size
            entries.append(
                {
                    "endpoint": endpoint,
                    "payload_sha256": digest,
                    "payload_size_bytes": size,
                }
            )
    inventory_sha = hashlib.sha256(_canonical(entries)).hexdigest()
    return len(entries), total_bytes, inventory_sha


def prime(*, output_dir: Path) -> dict[str, Any]:
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required to prime Current Shadow history transport")

    root = cache._cache_root()
    hooks = cache.install(latest_history)
    try:
        repository = latest_history.REPOSITORY

        def get_runs_page(page: int, per_page: int):
            return latest_history.lineage_audit._gh_json(
                f"/repos/{repository}/actions/workflows/"
                "fotmob-utc-native-xg-fresh-holdout.yml/runs"
                f"?per_page={per_page}&page={page}"
            )

        universe = latest_history.recovery_projection._prefetch_workflow_run_universe(
            get_runs_page
        )
    finally:
        cache.restore(latest_history, hooks)

    output_dir.mkdir(parents=True, exist_ok=True)
    cache_out = output_dir / "history-cache"
    if cache_out.exists():
        shutil.rmtree(cache_out)
    if root.is_dir():
        shutil.copytree(root, cache_out)
    else:
        cache_out.mkdir()

    entry_count, payload_bytes, inventory_sha = _cache_inventory(cache_out)
    runs = getattr(universe, "runs", ())
    run_count = len(runs) if type(runs) is tuple else 0
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "exact_commit_sha": os.environ.get("GITHUB_SHA"),
        "captured_run_universe_count": run_count,
        "cached_immutable_binary_entry_count": entry_count,
        "cached_immutable_binary_payload_bytes": payload_bytes,
        "cache_inventory_sha256": inventory_sha,
        "evidence_authority": False,
        "model_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "execution_authority": False,
        "bet_authority": False,
        "wager_placed": False,
    }
    (output_dir / "current-shadow-history-cache-prime-receipt.json").write_bytes(
        _canonical(receipt)
    )
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/current-shadow-history-cache-prime"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    print(json.dumps(prime(output_dir=args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
