#!/usr/bin/env python3
"""Export deterministic Win Either Half post-match research labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.win_either_half_research import (  # noqa: E402
    DEFAULT_TEST_SEASONS,
    DEFAULT_TRAIN_SEASONS,
    DEFAULT_VALIDATION_SEASONS,
    ResearchLabelError,
    ResearchSplit,
    TemporalSplitConfig,
    WinEitherHalfLabelDataset,
    build_win_either_half_labels,
)
from scripts.audit_half_time_coverage import (  # noqa: E402
    load_observations_from_database,
)
from scripts.freeze_evidence_baseline import (  # noqa: E402
    BaselineError,
    build_evidence_baseline,
    compare_baselines,
    get_code_state,
    load_baseline,
    validate_ready_baseline,
    verify_revision_relationship,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-labels-v1"
LABEL_COLUMNS = (
    "fixture_identity",
    "home_team",
    "away_team",
    "kickoff_utc",
    "league",
    "season",
    "split",
    "source",
    "source_fixture_id",
    "score_provenance",
    "full_time_home_goals",
    "full_time_away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "second_half_home_goals",
    "second_half_away_goals",
    "first_half_outcome",
    "second_half_outcome",
    "home_win_first_half",
    "away_win_first_half",
    "home_win_second_half",
    "away_win_second_half",
    "home_win_either_half_yes",
    "away_win_either_half_yes",
    "both_teams_won_a_half",
)
EXCLUSION_COLUMNS = (
    "fixture_identity",
    "league",
    "season",
    "source",
    "validation_status",
    "provenance",
    "reason_codes",
    "explanation",
)
POST_MATCH_COLUMNS = (
    "full_time_home_goals",
    "full_time_away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "second_half_home_goals",
    "second_half_away_goals",
    "first_half_outcome",
    "second_half_outcome",
    "home_win_first_half",
    "away_win_first_half",
    "home_win_second_half",
    "away_win_second_half",
    "home_win_either_half_yes",
    "away_win_either_half_yes",
    "both_teams_won_a_half",
)


class ResearchExportError(RuntimeError):
    """A bounded user-facing export or verification failure."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _generated_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _label_row(label) -> dict:
    return {
        column: (
            getattr(getattr(label, column), "value", getattr(label, column))
            if getattr(label, column) is not None
            else ""
        )
        for column in LABEL_COLUMNS
    }


def _exclusion_row(exclusion) -> dict:
    return {
        "fixture_identity": exclusion.fixture_identity,
        "league": exclusion.league or "",
        "season": exclusion.season or "",
        "source": exclusion.source,
        "validation_status": exclusion.validation_status,
        "provenance": exclusion.provenance,
        "reason_codes": "|".join(
            reason.value for reason in exclusion.reason_codes
        ),
        "explanation": exclusion.explanation,
    }


def _csv_bytes(columns: tuple, rows: Iterable[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=columns,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def render_dataset_csv(
    dataset: WinEitherHalfLabelDataset,
) -> tuple:
    labels = _csv_bytes(
        LABEL_COLUMNS,
        (_label_row(label) for label in dataset.labels),
    )
    exclusions = _csv_bytes(
        EXCLUSION_COLUMNS,
        (_exclusion_row(item) for item in dataset.exclusions),
    )
    return labels, exclusions


def verify_stage_2_evidence(
    baseline: dict,
    *,
    database_path: Path,
    cache_directory: Path,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict:
    """Verify every non-code Stage 2 evidence field through its contract."""
    current = build_evidence_baseline(
        database_path=database_path,
        cache_directory=cache_directory,
        baseline_name=baseline.get("baseline_name", ""),
        code_state=dict(baseline.get("code", {})),
        repository_root=repository_root,
    )
    differences = compare_baselines(
        baseline,
        current,
        allow_revision_difference=True,
    )
    if differences:
        raise ResearchExportError(
            "Stage 2 evidence verification failed: "
            + "; ".join(differences)
        )
    return current


def _label_counts(dataset: WinEitherHalfLabelDataset) -> dict:
    home_yes = sum(item.home_win_either_half_yes for item in dataset.labels)
    away_yes = sum(item.away_win_either_half_yes for item in dataset.labels)
    both = sum(item.both_teams_won_a_half for item in dataset.labels)
    total = len(dataset.labels)
    return {
        "away_no": total - away_yes,
        "away_yes": away_yes,
        "both_teams_won_a_half": both,
        "home_no": total - home_yes,
        "home_yes": home_yes,
    }


def _bucket(labels) -> dict:
    values = tuple(labels)
    return {
        "away_yes": sum(item.away_win_either_half_yes for item in values),
        "both_teams_won_a_half": sum(
            item.both_teams_won_a_half for item in values
        ),
        "home_yes": sum(item.home_win_either_half_yes for item in values),
        "rows": len(values),
    }


def _grouped_breakdown(labels, field_name: str) -> dict:
    groups = {}
    for label in labels:
        value = getattr(label, field_name)
        key = getattr(value, "value", value)
        groups.setdefault(str(key), []).append(label)
    return {key: _bucket(groups[key]) for key in sorted(groups)}


def build_research_manifest(
    dataset: WinEitherHalfLabelDataset,
    *,
    labels_bytes: bytes,
    exclusions_bytes: bytes,
    labels_relative_name: str,
    exclusions_relative_name: str,
    stage_2_baseline: dict,
    current_evidence: dict,
    generator_code_state: dict,
    generated_at_utc: Optional[str] = None,
) -> dict:
    split_breakdown = _grouped_breakdown(dataset.labels, "split")
    split_config = dataset.split_config
    splits = {}
    for split, seasons in (
        (ResearchSplit.TRAIN, split_config.train_seasons),
        (ResearchSplit.VALIDATION, split_config.validation_seasons),
        (ResearchSplit.TEST, split_config.test_seasons),
    ):
        bucket = split_breakdown.get(split.value, _bucket(()))
        splits[split.value.lower()] = {
            **bucket,
            "seasons": list(seasons),
        }

    exclusion_counts = Counter(
        reason.value
        for exclusion in dataset.exclusions
        for reason in exclusion.reason_codes
    )
    stage_code = stage_2_baseline.get("code", {})
    stage_database = stage_2_baseline.get("database", {})
    stage_cache = stage_2_baseline.get("football_data_uk_cache", {})
    return {
        "breakdowns": {
            "by_league": _grouped_breakdown(dataset.labels, "league"),
            "by_season": _grouped_breakdown(dataset.labels, "season"),
            "by_split": split_breakdown,
        },
        "column_roles": {
            "post_match_only_never_features": list(POST_MATCH_COLUMNS),
            "purpose": "LABEL_DATASET_NOT_FEATURE_MATRIX",
        },
        "dataset_name": DATASET_NAME,
        "exclusion_reasons": {
            key: exclusion_counts[key] for key in sorted(exclusion_counts)
        },
        "files": {
            "exclusions": {
                "byte_size": len(exclusions_bytes),
                "relative_name": str(exclusions_relative_name),
                "rows": len(dataset.exclusions),
                "sha256": _sha256(exclusions_bytes),
            },
            "labels": {
                "byte_size": len(labels_bytes),
                "relative_name": str(labels_relative_name),
                "rows": len(dataset.labels),
                "sha256": _sha256(labels_bytes),
            },
        },
        "generated_at_utc": generated_at_utc or _generated_at_utc(),
        "generator": {
            "generator_git_head_sha": generator_code_state.get(
                "evidence_git_head_sha"
            ),
            "tracked_worktree_clean": generator_code_state.get(
                "tracked_worktree_clean"
            ),
        },
        "labels": _label_counts(dataset),
        "market_safety": dict(current_evidence.get("market_safety", {})),
        "schema_version": SCHEMA_VERSION,
        "selection": {
            "eligible_labels": len(dataset.labels),
            "excluded_fixtures": len(dataset.exclusions),
            "selected_fixtures": dataset.selected_fixtures,
        },
        "splits": splits,
        "stage_2_baseline": {
            "baseline_name": stage_2_baseline.get("baseline_name"),
            "cache_manifest_sha256": stage_cache.get("manifest_sha256"),
            "evidence_git_head_sha": stage_code.get(
                "evidence_git_head_sha"
            ),
            "logical_evidence_sha256": stage_database.get(
                "logical_evidence_sha256"
            ),
            "schema_sha256": stage_database.get("schema_sha256"),
        },
    }


def compare_research_manifests(
    stored: dict,
    current: dict,
    *,
    allow_generator_revision_difference: bool = False,
) -> list:
    differences = []
    for key, label in (
        ("schema_version", "manifest schema version differs"),
        ("dataset_name", "dataset name differs"),
        ("stage_2_baseline", "Stage 2 baseline identity differs"),
        ("selection", "selection counts differ"),
        ("splits", "temporal split counts or configuration differ"),
        ("labels", "label counts differ"),
        ("breakdowns", "dataset breakdowns differ"),
        ("exclusion_reasons", "exclusion reason counts differ"),
        ("files", "label or exclusion file identity differs"),
        ("column_roles", "post-match column classification differs"),
        ("market_safety", "market safety state differs"),
    ):
        if stored.get(key) != current.get(key):
            differences.append(label)
    stored_generator = stored.get("generator", {})
    current_generator = current.get("generator", {})
    if (
        not allow_generator_revision_difference
        and stored_generator.get("generator_git_head_sha")
        != current_generator.get("generator_git_head_sha")
    ):
        differences.append("generator Git revision differs")
    if stored_generator.get("tracked_worktree_clean") != current_generator.get(
        "tracked_worktree_clean"
    ):
        differences.append("tracked worktree cleanliness differs")
    return differences


def validate_expectations(
    dataset: WinEitherHalfLabelDataset,
    *,
    selected: Optional[int],
    eligible: Optional[int],
    exclusions: Optional[int],
) -> None:
    failures = []
    for label, expected, actual in (
        ("selected fixtures", selected, dataset.selected_fixtures),
        ("eligible labels", eligible, len(dataset.labels)),
        ("exclusions", exclusions, len(dataset.exclusions)),
    ):
        if expected is not None and expected != actual:
            failures.append(f"{label}: expected {expected}, found {actual}")
    if failures:
        raise ResearchExportError(
            "Research dataset expectation mismatch: " + "; ".join(failures)
        )


def validate_market_safety(manifest: dict) -> None:
    market_safety = manifest.get("market_safety", {})
    failures = [
        key
        for key in ("home_win_either_half", "away_win_either_half")
        if market_safety.get(key) != "DISABLED"
    ]
    if failures:
        raise ResearchExportError(
            "Win Either Half market safety gate failed: "
            + ", ".join(failures)
            + " must remain DISABLED"
        )


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_research_outputs(
    *,
    labels_path: Path,
    exclusions_path: Path,
    manifest_path: Path,
    labels_bytes: bytes,
    exclusions_bytes: bytes,
    manifest: dict,
    force: bool = False,
) -> None:
    paths = (labels_path, exclusions_path, manifest_path)
    normalized = {str(Path(os.path.abspath(path))) for path in paths}
    if len(normalized) != len(paths):
        raise ResearchExportError("Output paths must be distinct")
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise ResearchExportError(
            "Output already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(labels_path, labels_bytes)
    _atomic_write_bytes(exclusions_path, exclusions_bytes)
    _atomic_write_bytes(manifest_path, manifest_bytes)


def load_research_manifest(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ResearchExportError(
            f"Research manifest could not be read: {path}"
        ) from error
    if not isinstance(manifest, dict):
        raise ResearchExportError("Research manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ResearchExportError(
            "Unsupported research manifest schema_version: "
            f"{manifest.get('schema_version')!r}"
        )
    for key in ("labels", "exclusions"):
        relative_name = (
            manifest.get("files", {}).get(key, {}).get("relative_name")
        )
        if (
            not isinstance(relative_name, str)
            or not relative_name
            or Path(relative_name).is_absolute()
            or Path(relative_name).name != relative_name
        ):
            raise ResearchExportError(
                f"Manifest {key} relative_name must be a plain file name"
            )
    return manifest


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export deterministic post-match Win Either Half research labels."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--database", type=Path, default=Path("database/athena.db"))
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(
            "artifacts/evidence-baselines/half-time-ready-for-research.json"
        ),
    )
    parser.add_argument(
        "--cache-directory",
        type=Path,
        default=Path(".cache/football-data-uk"),
    )
    parser.add_argument("--labels-output", type=Path)
    parser.add_argument("--exclusions-output", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--require-baseline-evidence",
        action="store_true",
        help=(
            "Require the complete non-code evidence state to match Stage 2 "
            "(verification is always fail-closed)."
        ),
    )
    parser.add_argument(
        "--train-seasons",
        nargs="+",
        default=list(DEFAULT_TRAIN_SEASONS),
    )
    parser.add_argument(
        "--validation-seasons",
        nargs="+",
        default=list(DEFAULT_VALIDATION_SEASONS),
    )
    parser.add_argument(
        "--test-seasons",
        nargs="+",
        default=list(DEFAULT_TEST_SEASONS),
    )
    parser.add_argument("--expect-selected-fixtures", type=_non_negative_integer)
    parser.add_argument("--expect-eligible-labels", type=_non_negative_integer)
    parser.add_argument("--expect-exclusions", type=_non_negative_integer)
    return parser


def main(
    argv: Optional[Iterable[str]] = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check is not None and args.force:
        parser.error("--force is valid only with --manifest-output")
    if args.manifest_output is not None:
        if args.labels_output is None or args.exclusions_output is None:
            parser.error(
                "--labels-output and --exclusions-output are required for generation"
            )
    elif args.labels_output is not None or args.exclusions_output is not None:
        parser.error("row-level output paths are valid only during generation")

    try:
        split_config = TemporalSplitConfig(
            train_seasons=tuple(args.train_seasons),
            validation_seasons=tuple(args.validation_seasons),
            test_seasons=tuple(args.test_seasons),
        )
        baseline = load_baseline(args.baseline)
        if args.require_baseline_evidence:
            validate_ready_baseline(baseline)
        current_evidence = verify_stage_2_evidence(
            baseline,
            database_path=args.database,
            cache_directory=args.cache_directory,
            repository_root=repository_root,
        )
        generator_code = get_code_state(repository_root)
        if not generator_code.get("tracked_worktree_clean"):
            raise ResearchExportError("Tracked worktree is dirty")
        observations = load_observations_from_database(str(args.database))
        dataset = build_win_either_half_labels(
            observations,
            split_config=split_config,
        )
        validate_expectations(
            dataset,
            selected=args.expect_selected_fixtures,
            eligible=args.expect_eligible_labels,
            exclusions=args.expect_exclusions,
        )
        labels_bytes, exclusions_bytes = render_dataset_csv(dataset)
        stored_manifest = (
            load_research_manifest(args.check)
            if args.check is not None
            else None
        )
        labels_name = (
            stored_manifest.get("files", {})
            .get("labels", {})
            .get("relative_name", "labels-v1.csv")
            if stored_manifest is not None
            else args.labels_output.name
        )
        exclusions_name = (
            stored_manifest.get("files", {})
            .get("exclusions", {})
            .get("relative_name", "exclusions-v1.csv")
            if stored_manifest is not None
            else args.exclusions_output.name
        )
        current_manifest = build_research_manifest(
            dataset,
            labels_bytes=labels_bytes,
            exclusions_bytes=exclusions_bytes,
            labels_relative_name=labels_name,
            exclusions_relative_name=exclusions_name,
            stage_2_baseline=baseline,
            current_evidence=current_evidence,
            generator_code_state=generator_code,
        )
        validate_market_safety(current_manifest)

        if stored_manifest is not None:
            stored_generator = stored_manifest.get("generator", {})
            revision = verify_revision_relationship(
                {
                    "evidence_git_head_sha": stored_generator.get(
                        "generator_git_head_sha"
                    ),
                    "tracked_worktree_clean": stored_generator.get(
                        "tracked_worktree_clean"
                    ),
                },
                generator_code,
                check_path=args.check,
                repository_root=repository_root,
            )
            differences = compare_research_manifests(
                stored_manifest,
                current_manifest,
                allow_generator_revision_difference=(
                    revision["mode"] == "artifact_only_descendant"
                ),
            )
            if differences:
                print("Research manifest verification failed:", file=sys.stderr)
                for difference in differences:
                    print(f"  - {difference}", file=sys.stderr)
                return 1
            print(f"Research manifest verified: {args.check}")
            if revision["mode"] == "artifact_only_descendant":
                print("Revision verification: " + revision["message"])
            return 0

        write_research_outputs(
            labels_path=args.labels_output,
            exclusions_path=args.exclusions_output,
            manifest_path=args.manifest_output,
            labels_bytes=labels_bytes,
            exclusions_bytes=exclusions_bytes,
            manifest=current_manifest,
            force=args.force,
        )
        print(f"Research labels written: {args.labels_output}")
        print(f"Research exclusions written: {args.exclusions_output}")
        print(f"Research manifest written: {args.manifest_output}")
        return 0
    except (
        BaselineError,
        ResearchExportError,
        ResearchLabelError,
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        UnicodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
