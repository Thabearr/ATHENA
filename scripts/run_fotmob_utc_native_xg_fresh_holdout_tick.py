"""CLI for one reviewed fresh-holdout activation tick."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import domain.fotmob_fresh_holdout_capture_qualification_adapter as capture_qualification
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner


def _parse_utc(text: str) -> dt.datetime:
    if not text.endswith("Z") or text != text.strip():
        raise argparse.ArgumentTypeError("scheduled-for must be exact UTC Z text")
    try:
        value = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("scheduled-for is malformed") from exc
    return value.astimezone(dt.timezone.utc)


def _canonical(value: dict) -> bytes:
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


def _reviewed_qualify(evidence: runner.CaptureEvidence):
    return capture_qualification.qualify_capture_fixtures(
        evidence.raw_json,
        evidence.manifest,
    )


def _install_reviewed_capture_qualifier() -> None:
    """Bridge only the scheduled CLI onto the reviewed PR89 structural chain."""
    current = runner._qualify
    if current is _reviewed_qualify:
        return
    if (
        getattr(current, "__module__", None) != runner.__name__
        or getattr(current, "__name__", None) != "_qualify"
    ):
        raise runner.FreshHoldoutActivationError(
            "fresh-holdout qualifier hook changed before reviewed adapter installation"
        )
    capture_qualification.verify_reviewed_dependencies()
    runner._qualify = _reviewed_qualify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one exact reviewed FotMob fresh-holdout collection tick."
    )
    parser.add_argument("--scheduled-for", type=_parse_utc, required=True)
    parser.add_argument("--bootstrap-projection", type=Path, required=True)
    parser.add_argument("--durable-release-tag", required=True)
    parser.add_argument("--durable-asset-name", required=True)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(
            ".cache/athena-research/fotmob-utc-native-xg-fresh-holdout"
        ),
    )
    parser.add_argument(
        "--receipt-output",
        type=Path,
        default=Path("fresh-holdout-tick-receipt.json"),
    )
    parser.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize the reviewed live requests required by this exact control tick.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    bootstrap_path = args.bootstrap_projection
    try:
        _install_reviewed_capture_qualifier()
        if bootstrap_path.is_symlink() or not bootstrap_path.is_file():
            raise runner.FreshHoldoutActivationError(
                "bootstrap projection must be a regular non-symlink file"
            )
        if bootstrap_path.stat().st_size != fresh.BOOTSTRAP_PROJECTION_SIZE:
            raise runner.FreshHoldoutActivationError(
                "bootstrap projection size changed"
            )
        bootstrap_raw = bootstrap_path.read_bytes()
        receipt = runner.execute_collection_tick(
            scheduled_for=args.scheduled_for,
            bootstrap_projection_raw=bootstrap_raw,
            durable_release_tag=args.durable_release_tag,
            durable_asset_name=args.durable_asset_name,
            execute_live_network=args.execute_live_network,
            state_root=args.state_root,
        )
        raw = _canonical(receipt)
        args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_output.write_bytes(raw)
        print(raw.decode("utf-8").rstrip())
        return 0
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "runner_id": runner.RUNNER_ID,
            "scheduled_for_utc": args.scheduled_for.isoformat().replace("+00:00", "Z"),
            "disposition": "TICK_NOT_COMMITTED_REVIEW_FAILURE_EVIDENCE",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "network_replay_authorized": False,
            "backfill_or_retrofill_authorized": False,
            "safety": {key: False for key in runner.SAFETY_KEYS},
        }
        try:
            args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
            args.receipt_output.write_bytes(_canonical(failure))
        except OSError:
            pass
        print(
            f"fresh holdout tick failed: {type(exc).__name__}: {str(exc)[:500]}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
