"""Create or verify a deterministic Stage 5B3 capture-campaign plan."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from domain.win_either_half_capture_campaign import (  # noqa: E402
    ATTEMPT_WINDOW_SECONDS,
    DATASET_NAME,
    DEFAULT_PROTOCOL_PATH,
    DEFAULT_STAGE_5B2_PROTOCOL_PATH,
    EXPECTED_TASKS_PER_FIXTURE,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    MINIMUM_FIXTURES_FOR_INTERPRETATION,
    PERMITTED_ATTEMPT_RESULTS,
    PERMITTED_MARKETS,
    PERMITTED_QUOTE_OUTCOMES,
    SCHEMA_VERSION,
    CaptureCampaignError,
    CampaignPlan,
    assert_market_safety,
    assert_no_forbidden_fields,
    build_campaign_plan,
    load_fixtures,
    load_source_qualification,
    market_registry_snapshot,
    model_status_snapshot,
    parse_utc,
    serialize_utc,
    validate_campaign_protocol,
    validate_full_git_sha,
    validate_stage_5b2_protocol,
)
from scripts.freeze_evidence_baseline import get_code_state  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = (
    REPOSITORY_ROOT
    / ".cache"
    / "athena-research"
    / "win-either-half"
    / "capture-campaign"
)
OUTPUT_FILENAMES = {
    "tasks": "capture-campaign-tasks-v1.jsonl",
    "summary": "capture-campaign-summary-v1.json",
    "manifest": "capture-campaign-manifest-v1.json",
}


class CaptureCampaignExportError(ValueError):
    """Raised when deterministic campaign export fails closed."""


@dataclass(frozen=True)
class CampaignBundle:
    files: dict[str, bytes]
    summary: dict[str, Any]
    manifest: dict[str, Any]


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise CaptureCampaignExportError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        return path.read_bytes()
    except OSError as error:
        raise CaptureCampaignExportError(
            f"Could not read {label}: {path}"
        ) from error


def _read_json(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
    raw = _read_bytes(path, label)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureCampaignExportError(
            f"{label} must be valid UTF-8 JSON"
        ) from error
    if not isinstance(payload, Mapping):
        raise CaptureCampaignExportError(f"{label} must be a JSON object")
    return raw, payload


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: Any, *, pretty: bool) -> bytes:
    options: dict[str, Any] = {
        "ensure_ascii": False,
        "allow_nan": False,
        "sort_keys": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(value, **options) + "\n").encode("utf-8")


def _tasks_jsonl_bytes(plan: CampaignPlan) -> bytes:
    return b"".join(
        _canonical_json_bytes(task.to_mapping(), pretty=False)
        for task in plan.tasks
    )


def _input_identity(path: Path, raw: bytes, *, rows: int | None = None) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "relative_name": path.name,
        "byte_size": len(raw),
        "sha256": _sha256(raw),
    }
    if rows is not None:
        identity["rows"] = rows
    return identity


def _output_identity(name: str, content: bytes, rows: int) -> dict[str, Any]:
    return {
        "relative_name": OUTPUT_FILENAMES[name],
        "byte_size": len(content),
        "sha256": _sha256(content),
        "rows": rows,
    }


def build_bundle(
    *,
    source_qualification_path: Path,
    fixtures_path: Path,
    stage_5b2_protocol_path: Path,
    campaign_protocol_path: Path,
    anchor_at: str,
    code_state: Mapping[str, Any],
) -> CampaignBundle:
    """Build deterministic task, summary, and manifest bytes."""

    assert_market_safety()

    tracked_clean = code_state.get("tracked_worktree_clean")
    if tracked_clean is not True:
        raise CaptureCampaignExportError(
            "Tracked worktree must be clean before campaign generation"
        )
    git_sha = validate_full_git_sha(
        code_state.get("evidence_git_head_sha"),
        "evidence_git_head_sha",
    )

    source_raw, source_payload = _read_json(
        source_qualification_path,
        "Stage 5B1 source qualification",
    )
    fixtures_raw, fixtures_payload = _read_json(
        fixtures_path,
        "fixtures",
    )
    stage_5b2_raw, stage_5b2_payload = _read_json(
        stage_5b2_protocol_path,
        "Stage 5B2 protocol",
    )
    campaign_protocol_raw, campaign_protocol_payload = _read_json(
        campaign_protocol_path,
        "Stage 5B3 campaign protocol",
    )

    source_qualification = load_source_qualification(source_payload)
    fixtures = load_fixtures(fixtures_payload)
    validate_stage_5b2_protocol(stage_5b2_payload)
    validate_campaign_protocol(campaign_protocol_payload)
    anchor = parse_utc(anchor_at, "anchor_at")

    plan = build_campaign_plan(
        source_qualification=source_qualification,
        fixtures=fixtures,
        anchor_at=anchor,
        stage_5b2_protocol_sha256=_sha256(stage_5b2_raw),
        campaign_protocol_sha256=_sha256(campaign_protocol_raw),
    )

    tasks_bytes = _tasks_jsonl_bytes(plan)
    scheduled_values = [task.scheduled_at for task in plan.tasks]
    window_open_values = [task.capture_window_opens_at for task in plan.tasks]
    window_close_values = [task.capture_window_closes_at for task in plan.tasks]

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-capture-campaign-summary-v1",
        "campaign_id": plan.campaign_id,
        "provider_identifier": plan.provider_identifier,
        "prospective_replay_status": plan.source_status,
        "anchor_at": serialize_utc(plan.anchor_at),
        "fixture_count": len(plan.fixtures),
        "task_count": len(plan.tasks),
        "expected_tasks_per_fixture": EXPECTED_TASKS_PER_FIXTURE,
        "expected_task_count": (
            len(plan.fixtures) * EXPECTED_TASKS_PER_FIXTURE
        ),
        "candidate_offsets_seconds": list(
            FROZEN_CANDIDATE_OFFSETS_SECONDS
        ),
        "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
        "permitted_markets": [market.value for market in PERMITTED_MARKETS],
        "expected_attempt_results": list(PERMITTED_ATTEMPT_RESULTS),
        "expected_quote_outcomes": list(PERMITTED_QUOTE_OUTCOMES),
        "earliest_scheduled_at": serialize_utc(min(scheduled_values)),
        "latest_scheduled_at": serialize_utc(max(scheduled_values)),
        "earliest_window_opens_at": serialize_utc(min(window_open_values)),
        "latest_window_closes_at": serialize_utc(max(window_close_values)),
        "minimum_fixtures_for_interpretation": (
            MINIMUM_FIXTURES_FOR_INTERPRETATION
        ),
        "interpretation_eligible": plan.interpretation_eligible,
        "selected_offset_seconds": None,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "market_statuses": {
            "HOME_WIN_EITHER_HALF": "DISABLED",
            "AWAY_WIN_EITHER_HALF": "DISABLED",
        },
        "no_production_approval": (
            "Stage 5B3 creates a capture schedule only. It collects no odds, "
            "selects no offset, enables no market, and issues no bet."
        ),
    }
    assert_no_forbidden_fields(summary, "Campaign summary")
    summary_bytes = _canonical_json_bytes(summary, pretty=True)

    outputs = {
        "tasks": _output_identity("tasks", tasks_bytes, len(plan.tasks)),
        "summary": _output_identity("summary", summary_bytes, 1),
    }
    inputs = {
        "source_qualification": _input_identity(
            source_qualification_path,
            source_raw,
        ),
        "fixtures": _input_identity(
            fixtures_path,
            fixtures_raw,
            rows=len(plan.fixtures),
        ),
        "stage_5b2_protocol": _input_identity(
            stage_5b2_protocol_path,
            stage_5b2_raw,
        ),
        "campaign_protocol": _input_identity(
            campaign_protocol_path,
            campaign_protocol_raw,
        ),
    }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "win-either-half-capture-campaign-manifest-v1",
        "generator": "scripts/manage_win_either_half_capture_campaign.py",
        "generator_commit": git_sha,
        "tracked_worktree_clean": True,
        "campaign_id": plan.campaign_id,
        "provider_identifier": plan.provider_identifier,
        "prospective_replay_status": plan.source_status,
        "anchor_at": serialize_utc(plan.anchor_at),
        "candidate_offsets_seconds": list(
            FROZEN_CANDIDATE_OFFSETS_SECONDS
        ),
        "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
        "expected_tasks_per_fixture": EXPECTED_TASKS_PER_FIXTURE,
        "minimum_fixtures_for_interpretation": (
            MINIMUM_FIXTURES_FOR_INTERPRETATION
        ),
        "interpretation_eligible": plan.interpretation_eligible,
        "task_identity": {
            "algorithm": "SHA256_CANONICAL_JSON_PREFIX_24",
            "campaign_id_fields": [
                "provider_identifier",
                "prospective_replay_status",
                "anchor_at",
                "candidate_offsets_seconds",
                "attempt_window_seconds",
                "stage_5b2_protocol_sha256",
                "campaign_protocol_sha256",
                "sorted_fixtures",
            ],
            "task_id_fields": [
                "campaign_id",
                "fixture_identifier",
                "market_id",
                "offset_seconds_before_kickoff",
                "scheduled_at",
            ],
        },
        "deterministic_ordering": [
            "scheduled_at",
            "fixture_identifier",
            "market_id",
            "offset_seconds_before_kickoff",
            "task_id",
        ],
        "market_registry": market_registry_snapshot(),
        "model_status_registry": model_status_snapshot(),
        "selected_offset_seconds": None,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "network_requests": False,
        "odds_collection": False,
        "inputs": inputs,
        "outputs": outputs,
        "summary_accounting": {
            "fixture_count": summary["fixture_count"],
            "task_count": summary["task_count"],
            "expected_task_count": summary["expected_task_count"],
            "interpretation_eligible": summary["interpretation_eligible"],
        },
        "no_production_approval": (
            "Stage 5B3 is scheduling evidence only."
        ),
    }
    assert_no_forbidden_fields(manifest, "Campaign manifest")

    pre_hash_bytes = _canonical_json_bytes(manifest, pretty=True)
    manifest["logical_manifest_sha256"] = _sha256(pre_hash_bytes)
    manifest_bytes = _canonical_json_bytes(manifest, pretty=True)

    return CampaignBundle(
        files={
            "tasks": tasks_bytes,
            "summary": summary_bytes,
            "manifest": manifest_bytes,
        },
        summary=summary,
        manifest=manifest,
    )


def _output_paths_from_manifest_path(manifest_path: Path) -> dict[str, Path]:
    if manifest_path.name != OUTPUT_FILENAMES["manifest"]:
        raise CaptureCampaignExportError(
            "Manifest output filename must be "
            f"{OUTPUT_FILENAMES['manifest']}"
        )
    return {
        name: manifest_path.parent / filename
        for name, filename in OUTPUT_FILENAMES.items()
    }


def commit_bundle(
    *,
    output_paths: Mapping[str, Path],
    contents: Mapping[str, bytes],
    force: bool,
) -> None:
    """Write the complete campaign bundle transactionally with rollback."""

    if set(output_paths) != set(contents):
        raise CaptureCampaignExportError(
            "Output paths and content keys must match"
        )
    resolved = [path.resolve() for path in output_paths.values()]
    if len(set(resolved)) != len(resolved):
        raise CaptureCampaignExportError("Output paths must be distinct")
    parent_dirs = {path.parent for path in resolved}
    if len(parent_dirs) != 1:
        raise CaptureCampaignExportError(
            "All campaign outputs must share one directory"
        )
    output_dir = next(iter(parent_dirs))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing = [path for path in output_paths.values() if path.exists()]
        if existing:
            raise CaptureCampaignExportError(
                "Campaign output exists; use --force to replace the bundle"
            )

    stage_dir = Path(
        tempfile.mkdtemp(prefix=".stage5b3-stage-", dir=output_dir)
    )
    rollback_dir = Path(
        tempfile.mkdtemp(prefix=".stage5b3-rollback-", dir=output_dir)
    )
    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []

    try:
        for name in sorted(contents):
            staged = stage_dir / output_paths[name].name
            with staged.open("wb") as handle:
                handle.write(contents[name])
                handle.flush()
                os.fsync(handle.fileno())

        for name in sorted(output_paths):
            destination = output_paths[name]
            if destination.exists():
                backup = rollback_dir / destination.name
                os.replace(destination, backup)
                backups.append((backup, destination))

        for name in sorted(output_paths):
            destination = output_paths[name]
            staged = stage_dir / destination.name
            os.replace(staged, destination)
            installed.append(destination)

    except Exception as error:
        for destination in reversed(installed):
            try:
                if destination.exists():
                    destination.unlink()
            except OSError:
                pass
        for backup, destination in reversed(backups):
            try:
                if backup.exists():
                    os.replace(backup, destination)
            except OSError:
                pass
        raise CaptureCampaignExportError(
            "Campaign bundle transaction failed and was rolled back"
        ) from error
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        shutil.rmtree(rollback_dir, ignore_errors=True)


def check_bundle(
    *,
    output_paths: Mapping[str, Path],
    expected_contents: Mapping[str, bytes],
) -> None:
    for name in sorted(expected_contents):
        actual = _read_bytes(output_paths[name], f"stored {name} output")
        if actual != expected_contents[name]:
            raise CaptureCampaignExportError(
                f"Stored {name} output differs byte-for-byte"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or verify an offline Stage 5B3 Win Either Half "
            "prospective capture-campaign plan."
        )
    )
    parser.add_argument("--source-qualification", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument(
        "--stage-5b2-protocol",
        type=Path,
        default=DEFAULT_STAGE_5B2_PROTOCOL_PATH,
    )
    parser.add_argument(
        "--campaign-protocol",
        type=Path,
        default=DEFAULT_PROTOCOL_PATH,
    )
    parser.add_argument(
        "--anchor-at",
        required=True,
        help=(
            "Frozen UTC planning anchor. The first 24-hour capture window for "
            "every fixture must not have opened before this timestamp."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        try:
            code_state = get_code_state(REPOSITORY_ROOT)
        except Exception as error:
            raise CaptureCampaignExportError(
                "Git repository state could not be determined"
            ) from error

        bundle = build_bundle(
            source_qualification_path=args.source_qualification,
            fixtures_path=args.fixtures,
            stage_5b2_protocol_path=args.stage_5b2_protocol,
            campaign_protocol_path=args.campaign_protocol,
            anchor_at=args.anchor_at,
            code_state=code_state,
        )
        manifest_path = args.manifest_output or args.check
        if manifest_path is None:
            raise CaptureCampaignExportError("Campaign mode is missing")
        output_paths = _output_paths_from_manifest_path(manifest_path)

        if args.check is not None:
            if args.force:
                raise CaptureCampaignExportError(
                    "--force cannot be used with --check"
                )
            check_bundle(
                output_paths=output_paths,
                expected_contents=bundle.files,
            )
            print(
                "Stage 5B3 capture campaign verified: "
                f"campaign_id={bundle.summary['campaign_id']} "
                f"tasks={bundle.summary['task_count']}"
            )
            return 0

        commit_bundle(
            output_paths=output_paths,
            contents=bundle.files,
            force=args.force,
        )
        print(
            "Stage 5B3 capture campaign created: "
            f"campaign_id={bundle.summary['campaign_id']} "
            f"fixtures={bundle.summary['fixture_count']} "
            f"tasks={bundle.summary['task_count']}"
        )
        return 0
    except (CaptureCampaignError, CaptureCampaignExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
