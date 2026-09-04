"""CLI for one reviewed fresh-holdout activation tick."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_fresh_holdout_capture_qualification_adapter as live_capture_adapter
import domain.fotmob_fresh_holdout_ordinary_ft_settlement_schema_adapter as settlement_schema_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner


LIVE_CAPTURE_IDENTITY_ADAPTER_BLOB_SHA = "6fb36b3ced7f9879984128033473fee7721428f6"
SETTLEMENT_SCHEMA_ADAPTER_BLOB_SHA = "e5bc1f1581913fcebfb989eb6aeb3ab6485282ed"
ACTIVATION_RUNNER_BLOB_SHA = "901ab137d6601a3485eac30da7e6bad7eeefa397"


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


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _execute_collection_tick_with_reviewed_adapter(**kwargs):
    """Scope both reviewed compatibility adapters to exactly one CLI tick."""
    try:
        if (
            _git_blob_sha(Path(live_capture_adapter.__file__))
            != LIVE_CAPTURE_IDENTITY_ADAPTER_BLOB_SHA
        ):
            raise runner.FreshHoldoutActivationError(
                "reviewed live-capture identity adapter blob changed"
            )
        if (
            _git_blob_sha(Path(settlement_schema_adapter.__file__))
            != SETTLEMENT_SCHEMA_ADAPTER_BLOB_SHA
        ):
            raise runner.FreshHoldoutActivationError(
                "reviewed settlement schema adapter blob changed"
            )
        if _git_blob_sha(Path(runner.__file__)) != ACTIVATION_RUNNER_BLOB_SHA:
            raise runner.FreshHoldoutActivationError(
                "reviewed activation runner blob changed"
            )
        live_capture_adapter.verify_reviewed_dependencies()
        settlement_schema_adapter.verify_reviewed_dependencies()
    except OSError as exc:
        raise runner.FreshHoldoutActivationError(
            "could not verify reviewed fresh-holdout adapter installation"
        ) from exc

    original_qualifier = fresh.qualify_capture_fixtures
    if (
        getattr(original_qualifier, "__module__", None) != fresh.__name__
        or getattr(original_qualifier, "__name__", None) != "qualify_capture_fixtures"
    ):
        raise runner.FreshHoldoutActivationError(
            "fresh-holdout capture qualifier runtime identity changed"
        )

    original_score_pr89 = score_adapter.pr89
    if (
        getattr(original_score_pr89, "__name__", None)
        != "domain.fotmob_data_matches_eliminated_team_id_value_domain_extension"
        or getattr(
            original_score_pr89,
            "assess_fotmob_data_matches_eliminated_team_id_value_domain",
            None,
        )
        is None
    ):
        raise runner.FreshHoldoutActivationError(
            "ordinary-FT adapter PR89 runtime dependency changed"
        )
    settlement_proxy = (
        settlement_schema_adapter.build_pr89_settlement_compatibility_proxy()
    )
    try:
        # Runner._qualify and fresh settlement resolve this module global at call
        # time, so the reviewed adapter covers prediction and settlement identity.
        fresh.qualify_capture_fixtures = live_capture_adapter.qualify_capture_fixtures

        # The frozen ordinary-FT adapter keeps parsing score/reason semantics from
        # original network bytes. Only its internal PR89 structural assessment is
        # delegated through the reviewed compatibility projection.
        score_adapter.pr89 = settlement_proxy
        return runner.execute_collection_tick(**kwargs)
    finally:
        score_adapter.pr89 = original_score_pr89
        fresh.qualify_capture_fixtures = original_qualifier


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
        if bootstrap_path.is_symlink() or not bootstrap_path.is_file():
            raise runner.FreshHoldoutActivationError(
                "bootstrap projection must be a regular non-symlink file"
            )
        if bootstrap_path.stat().st_size != fresh.BOOTSTRAP_PROJECTION_SIZE:
            raise runner.FreshHoldoutActivationError(
                "bootstrap projection size changed"
            )
        bootstrap_raw = bootstrap_path.read_bytes()
        receipt = _execute_collection_tick_with_reviewed_adapter(
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
