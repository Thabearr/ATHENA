#!/usr/bin/env python3
"""Export deterministic leakage-safe Win Either Half pre-match features."""

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

from domain.win_either_half_features import (  # noqa: E402
    FEATURE_COLUMNS,
    FeatureBuildError,
    HistoricalLabelMatch,
    PreMatchFeatureDataset,
    build_pre_match_feature_dataset,
)
from domain.win_either_half_research import (  # noqa: E402
    ResearchLabelError,
    TemporalSplitConfig,
)
from scripts.export_win_either_half_research_dataset import (  # noqa: E402
    LABEL_COLUMNS,
    ResearchExportError,
    load_research_manifest,
    validate_market_safety,
    verify_stage_2_evidence,
)
from scripts.freeze_evidence_baseline import (  # noqa: E402
    BaselineError,
    get_code_state,
    load_baseline,
    verify_revision_relationship,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-features-v1"
_INTEGER_LABEL_FIELDS = (
    "full_time_home_goals",
    "full_time_away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "home_win_first_half",
    "away_win_first_half",
    "home_win_second_half",
    "away_win_second_half",
    "home_win_either_half_yes",
    "away_win_either_half_yes",
    "both_teams_won_a_half",
)
_BINARY_LABEL_FIELDS = (
    "home_win_first_half",
    "away_win_first_half",
    "home_win_second_half",
    "away_win_second_half",
    "home_win_either_half_yes",
    "away_win_either_half_yes",
    "both_teams_won_a_half",
)


class FeatureExportError(RuntimeError):
    """A bounded user-facing feature export or verification failure."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_sha256(value) -> str:
    """Return a platform-independent SHA-256 for a parsed JSON value."""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256(canonical)


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise FeatureExportError(f"{label} could not be read: {path}") from error


def _parse_int(row: dict, field_name: str) -> int:
    raw = row.get(field_name)
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise FeatureExportError(
            f"Label field {field_name} must be an integer"
        ) from error
    if str(value) != str(raw) or value < 0:
        raise FeatureExportError(
            f"Label field {field_name} must be a non-negative integer"
        )
    return value


def _parse_kickoff(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise FeatureExportError("Label kickoff_utc is required")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise FeatureExportError("Label kickoff_utc is invalid") from error
    if parsed.tzinfo is None:
        raise FeatureExportError("Label kickoff_utc must be timezone-aware")
    return parsed


def _expected_stage_2_identity(baseline: dict) -> dict:
    return {
        "baseline_name": baseline.get("baseline_name"),
        "cache_manifest_sha256": baseline.get(
            "football_data_uk_cache", {}
        ).get("manifest_sha256"),
        "evidence_git_head_sha": baseline.get("code", {}).get(
            "evidence_git_head_sha"
        ),
        "logical_evidence_sha256": baseline.get("database", {}).get(
            "logical_evidence_sha256"
        ),
        "schema_sha256": baseline.get("database", {}).get("schema_sha256"),
    }


def validate_label_manifest_contract(
    label_manifest: dict,
    *,
    baseline: dict,
    current_evidence: dict,
) -> TemporalSplitConfig:
    if label_manifest.get("dataset_name") != "win-either-half-labels-v1":
        raise FeatureExportError("Unexpected Stage 3 label dataset identity")
    if label_manifest.get("stage_2_baseline") != _expected_stage_2_identity(
        baseline
    ):
        raise FeatureExportError(
            "Stage 3 label manifest does not match the Stage 2 baseline"
        )
    if label_manifest.get("market_safety") != current_evidence.get(
        "market_safety"
    ):
        raise FeatureExportError("Stage 3 label manifest market safety drifted")
    validate_market_safety(label_manifest)
    splits = label_manifest.get("splits", {})
    try:
        config = TemporalSplitConfig(
            train_seasons=tuple(splits["train"]["seasons"]),
            validation_seasons=tuple(splits["validation"]["seasons"]),
            test_seasons=tuple(splits["test"]["seasons"]),
        )
    except (KeyError, TypeError, ResearchLabelError) as error:
        raise FeatureExportError(
            "Stage 3 label manifest temporal splits are invalid"
        ) from error
    labels_file = label_manifest.get("files", {}).get("labels", {})
    if labels_file.get("rows") != label_manifest.get("selection", {}).get(
        "eligible_labels"
    ):
        raise FeatureExportError(
            "Stage 3 label manifest row accounting is inconsistent"
        )
    return config


def load_verified_label_matches(
    labels_path: Path,
    label_manifest: dict,
    split_config: TemporalSplitConfig,
) -> tuple:
    content = _read_bytes(labels_path, "Labels CSV")
    expected = label_manifest.get("files", {}).get("labels", {})
    if len(content) != expected.get("byte_size"):
        raise FeatureExportError("Labels CSV byte size does not match manifest")
    if _sha256(content) != expected.get("sha256"):
        raise FeatureExportError("Labels CSV SHA-256 does not match manifest")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise FeatureExportError("Labels CSV is not valid UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != tuple(LABEL_COLUMNS):
        raise FeatureExportError("Labels CSV columns do not match the frozen contract")
    matches = []
    fixture_ids = set()
    split_counts = Counter()
    for row in reader:
        fixture_identity = str(row.get("fixture_identity") or "").strip()
        if not fixture_identity or fixture_identity in fixture_ids:
            raise FeatureExportError(
                "Labels CSV fixture identities must be present and unique"
            )
        fixture_ids.add(fixture_identity)
        values = {
            field_name: _parse_int(row, field_name)
            for field_name in _INTEGER_LABEL_FIELDS
        }
        for field_name in _BINARY_LABEL_FIELDS:
            if values[field_name] not in (0, 1):
                raise FeatureExportError(
                    f"Label field {field_name} must be 0 or 1"
                )
        season = str(row.get("season") or "").strip()
        split = str(row.get("split") or "").strip()
        if split_config.split_for(season).value != split:
            raise FeatureExportError(
                "Labels CSV season/split assignment differs from manifest"
            )
        split_counts[split] += 1
        matches.append(
            HistoricalLabelMatch(
                fixture_identity=fixture_identity,
                kickoff_utc=_parse_kickoff(row.get("kickoff_utc")),
                league=str(row.get("league") or "").strip(),
                season=season,
                split=split,
                home_team=str(row.get("home_team") or "").strip(),
                away_team=str(row.get("away_team") or "").strip(),
                full_time_home_goals=values["full_time_home_goals"],
                full_time_away_goals=values["full_time_away_goals"],
                half_time_home_goals=values["half_time_home_goals"],
                half_time_away_goals=values["half_time_away_goals"],
                home_win_first_half=values["home_win_first_half"],
                away_win_first_half=values["away_win_first_half"],
                home_win_second_half=values["home_win_second_half"],
                away_win_second_half=values["away_win_second_half"],
                home_win_either_half_yes=values[
                    "home_win_either_half_yes"
                ],
                away_win_either_half_yes=values[
                    "away_win_either_half_yes"
                ],
                both_teams_won_a_half=values["both_teams_won_a_half"],
            )
        )
    if len(matches) != expected.get("rows"):
        raise FeatureExportError("Labels CSV row count does not match manifest")
    for split_key, split_value in (
        ("TRAIN", "train"),
        ("VALIDATION", "validation"),
        ("TEST", "test"),
    ):
        expected_rows = label_manifest.get("splits", {}).get(
            split_value, {}
        ).get("rows")
        if split_counts[split_key] != expected_rows:
            raise FeatureExportError(
                f"Labels CSV {split_key} row count differs from manifest"
            )
    return tuple(matches), {
        "byte_size": len(content),
        "rows": len(matches),
        "sha256": _sha256(content),
    }


def _format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    return value


def render_feature_csv(dataset: PreMatchFeatureDataset) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=FEATURE_COLUMNS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in dataset.rows:
        writer.writerow(
            {key: _format_csv_value(row.get(key)) for key in FEATURE_COLUMNS}
        )
    return stream.getvalue().encode("utf-8")


def _generated_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def build_feature_manifest(
    dataset: PreMatchFeatureDataset,
    *,
    feature_bytes: bytes,
    feature_relative_name: str,
    baseline: dict,
    label_manifest: dict,
    label_manifest_logical_sha256: str,
    label_csv_identity: dict,
    generator_code_state: dict,
    generated_at_utc: Optional[str] = None,
) -> dict:
    split_counts = Counter(row["split"] for row in dataset.rows)
    return {
        "dataset_name": DATASET_NAME,
        "feature_schema": [column.to_dict() for column in dataset.schema],
        "files": {
            "features": {
                "byte_size": len(feature_bytes),
                "relative_name": str(feature_relative_name),
                "rows": len(dataset.rows),
                "sha256": _sha256(feature_bytes),
            }
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
        "market_safety": dict(label_manifest.get("market_safety", {})),
        "schema_version": SCHEMA_VERSION,
        "splits": {
            key: {
                "rows": split_counts[split_name],
                "seasons": list(
                    label_manifest.get("splits", {})
                    .get(key, {})
                    .get("seasons", ())
                ),
            }
            for key, split_name in (
                ("train", "TRAIN"),
                ("validation", "VALIDATION"),
                ("test", "TEST"),
            )
        },
        "stage_2_evidence": _expected_stage_2_identity(baseline),
        "stage_3_labels": {
            "dataset_name": label_manifest.get("dataset_name"),
            "generator_git_head_sha": label_manifest.get(
                "generator", {}
            ).get("generator_git_head_sha"),
            "label_manifest_logical_sha256": (
                label_manifest_logical_sha256
            ),
            "labels_csv": dict(label_csv_identity),
        },
        "temporal_safety": {
            "cutoff": "historical kickoff strictly less than target kickoff",
            "same_timestamp_policy": "excluded from each other's history",
            "split_history": {
                "TEST": ["TRAIN", "VALIDATION", "TEST"],
                "TRAIN": ["TRAIN"],
                "VALIDATION": ["TRAIN", "VALIDATION"],
            },
            "target_attachment": "after pre-match feature calculation",
        },
    }


def compare_feature_manifests(
    stored: dict,
    current: dict,
    *,
    allow_generator_revision_difference: bool = False,
) -> list:
    differences = []
    for key, label in (
        ("schema_version", "manifest schema version differs"),
        ("dataset_name", "dataset name differs"),
        ("stage_2_evidence", "Stage 2 evidence identity differs"),
        ("stage_3_labels", "Stage 3 label identity differs"),
        ("files", "feature CSV identity differs"),
        ("feature_schema", "feature schema differs"),
        ("splits", "temporal split counts differ"),
        ("temporal_safety", "temporal safety contract differs"),
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


def load_feature_manifest(path: Path) -> dict:
    content = _read_bytes(path, "Feature manifest")
    try:
        manifest = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeatureExportError("Feature manifest is not valid UTF-8 JSON") from error
    if not isinstance(manifest, dict) or manifest.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise FeatureExportError("Unsupported feature manifest contract")
    relative_name = manifest.get("files", {}).get("features", {}).get(
        "relative_name"
    )
    if (
        not isinstance(relative_name, str)
        or not relative_name
        or Path(relative_name).is_absolute()
        or Path(relative_name).name != relative_name
    ):
        raise FeatureExportError(
            "Feature manifest relative_name must be a plain file name"
        )
    return manifest


def _atomic_write(path: Path, content: bytes) -> None:
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


def write_feature_outputs(
    *,
    feature_path: Path,
    manifest_path: Path,
    feature_bytes: bytes,
    manifest: dict,
    force: bool = False,
) -> None:
    if Path(os.path.abspath(feature_path)) == Path(os.path.abspath(manifest_path)):
        raise FeatureExportError("Feature and manifest paths must be distinct")
    existing = [path for path in (feature_path, manifest_path) if path.exists()]
    if existing and not force:
        raise FeatureExportError(
            "Output already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    _atomic_write(feature_path, feature_bytes)
    _atomic_write(manifest_path, manifest_bytes)


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
        description="Export leakage-safe Win Either Half pre-match features."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--features-output", type=Path)
    parser.add_argument("--database", type=Path, default=Path("database/athena.db"))
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(
            "artifacts/evidence-baselines/half-time-ready-for-research.json"
        ),
    )
    parser.add_argument(
        "--label-manifest",
        type=Path,
        default=Path(
            "artifacts/research-manifests/win-either-half-labels-v1.json"
        ),
    )
    parser.add_argument(
        "--labels-input",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/labels-v1.csv"
        ),
    )
    parser.add_argument(
        "--cache-directory",
        type=Path,
        default=Path(".cache/football-data-uk"),
    )
    parser.add_argument("--expect-rows", type=_non_negative_integer)
    parser.add_argument("--force", action="store_true")
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
    if args.manifest_output is not None and args.features_output is None:
        parser.error("--features-output is required for generation")
    if args.check is not None and args.features_output is not None:
        parser.error("--features-output is valid only during generation")
    try:
        baseline = load_baseline(args.baseline)
        current_evidence = verify_stage_2_evidence(
            baseline,
            database_path=args.database,
            cache_directory=args.cache_directory,
            repository_root=repository_root,
        )
        label_manifest = load_research_manifest(args.label_manifest)
        split_config = validate_label_manifest_contract(
            label_manifest,
            baseline=baseline,
            current_evidence=current_evidence,
        )
        matches, label_csv_identity = load_verified_label_matches(
            args.labels_input,
            label_manifest,
            split_config,
        )
        generator_code = get_code_state(repository_root)
        if not generator_code.get("tracked_worktree_clean"):
            raise FeatureExportError("Tracked worktree is dirty")
        dataset = build_pre_match_feature_dataset(matches)
        if args.expect_rows is not None and len(dataset.rows) != args.expect_rows:
            raise FeatureExportError(
                "Feature row expectation mismatch: expected "
                f"{args.expect_rows}, found {len(dataset.rows)}"
            )
        feature_bytes = render_feature_csv(dataset)
        stored_manifest = (
            load_feature_manifest(args.check) if args.check is not None else None
        )
        feature_name = (
            stored_manifest.get("files", {})
            .get("features", {})
            .get("relative_name", "features-v1.csv")
            if stored_manifest is not None
            else args.features_output.name
        )
        current_manifest = build_feature_manifest(
            dataset,
            feature_bytes=feature_bytes,
            feature_relative_name=feature_name,
            baseline=baseline,
            label_manifest=label_manifest,
            label_manifest_logical_sha256=canonical_json_sha256(
                label_manifest
            ),
            label_csv_identity=label_csv_identity,
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
            differences = compare_feature_manifests(
                stored_manifest,
                current_manifest,
                allow_generator_revision_difference=(
                    revision["mode"] == "artifact_only_descendant"
                ),
            )
            if differences:
                print("Feature manifest verification failed:", file=sys.stderr)
                for difference in differences:
                    print(f"  - {difference}", file=sys.stderr)
                return 1
            print(f"Feature manifest verified: {args.check}")
            if revision["mode"] == "artifact_only_descendant":
                print("Revision verification: " + revision["message"])
            return 0
        write_feature_outputs(
            feature_path=args.features_output,
            manifest_path=args.manifest_output,
            feature_bytes=feature_bytes,
            manifest=current_manifest,
            force=args.force,
        )
        print(f"Feature dataset written: {args.features_output}")
        print(f"Feature manifest written: {args.manifest_output}")
        return 0
    except (
        BaselineError,
        FeatureBuildError,
        FeatureExportError,
        FileNotFoundError,
        OSError,
        ResearchExportError,
        ResearchLabelError,
        sqlite3.Error,
        UnicodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
