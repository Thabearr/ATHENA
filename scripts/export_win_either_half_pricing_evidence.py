#!/usr/bin/env python3
"""Build deterministic Stage 5A Win Either Half pricing-evidence outputs."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain.markets import MarketId  # noqa: E402
from domain.model_status import (  # noqa: E402
    MODEL_STATUS_REGISTRY,
    PricingAuthority,
    SelectionAuthority,
)
from domain.win_either_half_pricing_evidence import (  # noqa: E402
    BOOKMAKER_FAIR_PROBABILITY_BANDS,
    CANONICAL_DECIMAL_PLACES,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    DEVIG_METHOD,
    EVALUATION_ROLE_SPLITS,
    MARKET_TARGETS,
    PERMITTED_MARKETS,
    PERMITTED_OUTCOMES,
    RESEARCH_QUOTE_FIELDS,
    EvidenceStatus,
    KnownFixture,
    PricingEvidenceError,
    ProviderSelectionMapping,
    QuoteValidationResult,
    SnapshotValidationResult,
    build_provider_mapping_registry,
    canonical_decimal,
    canonical_decimal_text,
    select_latest_eligible_snapshots,
    validate_complete_snapshot,
    validate_research_quote,
)
from scripts.export_win_either_half_feature_dataset import (  # noqa: E402
    canonical_json_sha256,
)
from scripts.freeze_evidence_baseline import (  # noqa: E402
    BaselineError,
    get_code_state,
    verify_revision_relationship,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-pricing-evidence-v1"
FROZEN_STAGE_4B_MANIFEST_LOGICAL_SHA256 = (
    "2c0edf9de4b7d23de508021e1ad5e022ee75d6500d6ae23aa5d3580eee401f99"
)
FROZEN_CALIBRATED_PREDICTIONS_IDENTITY = {
    "rows": 36318,
    "byte_size": 6705242,
    "sha256": "6e931ae156f7319bc9cba2647e746471422adafad8e431981bdb573ca64c44d4",
}
FROZEN_SELECTED_CALIBRATIONS = {
    "home_win_either_half_yes": "isotonic_calibration_v1",
    "away_win_either_half_yes": "identity_calibration_v1",
}
FROZEN_FIXTURE_MARKET_ROLE_COUNTS = {
    "CALIBRATION_FIT_OOF": 21270,
    "VALIDATION_SELECTION": 6952,
    "FINAL_TEST": 8096,
}
FROZEN_FIXTURE_MARKET_TOTAL = 36318
HOLDOUT_GOVERNANCE = {
    "final_test_season": "2025-26",
    "status": "ALREADY_CONSUMED_AUDIT_HOLDOUT",
    "prior_exposures": [
        "STAGE_4A_BENCHMARK_FINAL_TEST_EVALUATION",
        "STAGE_4B_CALIBRATION_FINAL_TEST_EVALUATION",
    ],
    "not_pristine_for_iterative_policy_tuning": True,
    "policy_inputs_frozen_without_final_test_outcomes_or_performance": [
        "availability_rules",
        "decision_timestamp",
        "devig_method",
        "freshness_window",
        "provider_mapping",
        "quote_source",
        "snapshot_selection",
    ],
    "production_approval_authorized_from_this_holdout_alone": False,
    "production_approval_requires": (
        "UNTOUCHED_FUTURE_SEASON_OR_PROSPECTIVE_HOLDOUT"
    ),
}
CALIBRATED_PREDICTION_COLUMNS = (
    "fixture_identity",
    "kickoff_utc",
    "league",
    "season",
    "split",
    "prediction_role",
    "target_name",
    "target_value",
    "base_model_identifier",
    "model_probability",
    "calibration_identifier",
    "calibrated_probability",
)
VALID_QUOTE_COLUMNS = (
    *RESEARCH_QUOTE_FIELDS,
    "decision_at",
    "evaluation_role",
    "validation_status",
    "validation_reasons_json",
)
REJECTED_QUOTE_COLUMNS = (
    "source_row_number",
    *RESEARCH_QUOTE_FIELDS,
    "validation_status",
    "validation_reasons_json",
)
SNAPSHOT_COLUMNS = (
    "fixture_identifier",
    "market_id",
    "line",
    "source",
    "quote_snapshot_id",
    "observed_at",
    "fixture_kickoff",
    "decision_at",
    "evaluation_role",
    "validation_status",
    "validation_reasons_json",
    "selected_latest_eligible",
    "yes_odds",
    "no_odds",
    "yes_raw_implied_probability",
    "no_raw_implied_probability",
    "overround",
    "devig_method",
    "yes_fair_probability",
    "no_fair_probability",
    "yes_bookmaker_fair_probability_band",
    "no_bookmaker_fair_probability_band",
)
FIXTURE_MARKET_COVERAGE_COLUMNS = (
    "fixture_identifier",
    "market_id",
    "fixture_kickoff",
    "evaluation_role",
    "raw_quote_row_count",
    "accepted_quote_row_count",
    "rejected_quote_row_count",
    "complete_eligible_snapshot_count",
    "selected_latest_snapshot_count",
    "availability_status",
    "availability_reason",
)
FORBIDDEN_OUTPUT_FIELDS = {
    "edge",
    "edge_pp",
    "expected_value",
    "kelly",
    "kelly_stake",
    "bet",
    "bet_decision",
}


class PricingExportError(RuntimeError):
    """A bounded Stage 5A input, output, or lifecycle failure."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: object, *, pretty: bool = False) -> bytes:
    options = {"allow_nan": False, "ensure_ascii": False, "sort_keys": True}
    if pretty:
        rendered = json.dumps(value, indent=2, **options) + "\n"
    else:
        rendered = json.dumps(value, separators=(",", ":"), **options)
    return rendered.encode("utf-8")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise PricingExportError(f"{label} could not be read: {path}") from error


def _file_identity(
    content: bytes, relative_name: Optional[str] = None, rows: Optional[int] = None
) -> dict:
    result = {"byte_size": len(content), "sha256": _sha256(content)}
    if relative_name is not None:
        result["relative_name"] = relative_name
    if rows is not None:
        result["rows"] = rows
    return result


def _verify_file_identity(content: bytes, expected: Mapping, label: str) -> None:
    if len(content) != expected.get("byte_size"):
        raise PricingExportError(f"{label} byte size differs from frozen identity")
    if _sha256(content) != expected.get("sha256"):
        raise PricingExportError(f"{label} SHA-256 differs from frozen identity")


def load_stage_4b_manifest(path: Path) -> dict:
    content = _read_bytes(path, "Stage 4B manifest")
    try:
        value = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PricingExportError("Stage 4B manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PricingExportError("Stage 4B manifest must be a JSON object")
    return value


def verify_stage_4b_manifest_contract(manifest: Mapping) -> dict:
    if canonical_json_sha256(manifest) != FROZEN_STAGE_4B_MANIFEST_LOGICAL_SHA256:
        raise PricingExportError("Stage 4B manifest logical identity drifted")
    if manifest.get("schema_version") != 1 or manifest.get("dataset_name") != (
        "win-either-half-calibration-v1"
    ):
        raise PricingExportError("Unexpected Stage 4B manifest contract")
    if manifest.get("selected_calibrations") != FROZEN_SELECTED_CALIBRATIONS:
        raise PricingExportError("Stage 4B selected calibrations drifted")
    identity = manifest.get("files", {}).get("calibrated_predictions", {})
    if {
        key: identity.get(key) for key in ("rows", "byte_size", "sha256")
    } != FROZEN_CALIBRATED_PREDICTIONS_IDENTITY:
        raise PricingExportError("Stage 4B calibrated-prediction identity drifted")
    if manifest.get("numerical_reproducibility", {}).get(
        "canonical_decimal_places"
    ) != CANONICAL_DECIMAL_PLACES:
        raise PricingExportError("Stage 4B canonical precision drifted")
    expected_scopes = {
        "CALIBRATION_FIT_OOF": "CALIBRATION_FIT_SAMPLE",
        "VALIDATION_SELECTION": "SELECTION_SAMPLE",
        "FINAL_TEST": "INDEPENDENT_FINAL_TEST",
    }
    if manifest.get("subgroup_policy", {}).get(
        "evaluation_role_scopes"
    ) != expected_scopes:
        raise PricingExportError("Stage 4B evaluation-role contract drifted")
    expected_safety = {
        "home_win_either_half": "DISABLED",
        "away_win_either_half": "DISABLED",
    }
    if manifest.get("market_safety") != expected_safety:
        raise PricingExportError("Stage 4B market safety drifted")
    for market in PERMITTED_MARKETS:
        definition = MODEL_STATUS_REGISTRY[market]
        if (
            definition.pricing_authority is not PricingAuthority.NOT_AUTHORIZED
            or definition.selection_authority
            is not SelectionAuthority.NOT_AUTHORIZED
        ):
            raise PricingExportError(
                "Win Either Half pricing/selection authority is not disabled"
            )
    return {
        "dataset_name": manifest["dataset_name"],
        "generator_git_head_sha": manifest["generator"]["generator_git_head_sha"],
        "manifest_logical_sha256": canonical_json_sha256(manifest),
        "calibrated_predictions": dict(FROZEN_CALIBRATED_PREDICTIONS_IDENTITY),
        "selected_calibrations": dict(FROZEN_SELECTED_CALIBRATIONS),
        "stage_2_evidence": dict(manifest["stage_2_evidence"]),
        "stage_3_labels": dict(manifest["stage_3_labels"]),
        "stage_3_features": dict(manifest["stage_3_features"]),
        "stage_4_benchmarks": dict(manifest["stage_4_benchmarks"]),
    }


def _parse_aware_timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PricingExportError(f"{label} is missing")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise PricingExportError(f"{label} is not an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PricingExportError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def load_verified_calibrated_predictions(
    path: Path,
    manifest: Mapping,
    *,
    expected_identity: Optional[Mapping] = None,
    require_frozen_identity: bool = True,
) -> tuple[dict[tuple[str, MarketId], KnownFixture], dict]:
    """Verify exact bytes and expose frozen fixture/kickoff/evaluation roles."""
    content = _read_bytes(path, "Stage 4B calibrated predictions")
    manifest_identity = manifest.get("files", {}).get("calibrated_predictions", {})
    if require_frozen_identity:
        expected = FROZEN_CALIBRATED_PREDICTIONS_IDENTITY
        if {
            key: manifest_identity.get(key) for key in expected
        } != FROZEN_CALIBRATED_PREDICTIONS_IDENTITY:
            raise PricingExportError("Stage 4B prediction identity contract drifted")
    else:
        expected = expected_identity or manifest_identity
    _verify_file_identity(content, expected, "Stage 4B calibrated predictions")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PricingExportError(
            "Stage 4B calibrated predictions are not valid UTF-8"
        ) from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != CALIBRATED_PREDICTION_COLUMNS:
        raise PricingExportError("Stage 4B calibrated-prediction columns drifted")
    target_markets = {target: market for market, target in MARKET_TARGETS.items()}
    catalog: dict[tuple[str, MarketId], KnownFixture] = {}
    seen = set()
    role_counts = Counter()
    rows = 0
    for raw in reader:
        rows += 1
        fixture_identifier = str(raw.get("fixture_identity") or "").strip()
        target = raw.get("target_name")
        market = target_markets.get(target)
        role = raw.get("prediction_role")
        split = raw.get("split")
        if not fixture_identifier or market is None:
            raise PricingExportError("Stage 4B fixture or target identity drifted")
        if role not in EVALUATION_ROLE_SPLITS or split != EVALUATION_ROLE_SPLITS[role]:
            raise PricingExportError("Stage 4B prediction evaluation role drifted")
        key = (fixture_identifier, market)
        if key in seen:
            raise PricingExportError("Duplicate Stage 4B fixture/target prediction")
        seen.add(key)
        kickoff = _parse_aware_timestamp(raw.get("kickoff_utc"), "Fixture kickoff")
        catalog[key] = KnownFixture(fixture_identifier, market, kickoff, role)
        role_counts[role] += 1
    if rows != expected.get("rows"):
        raise PricingExportError("Stage 4B calibrated-prediction row count drifted")
    if require_frozen_identity and rows != 36318:
        raise PricingExportError("Stage 4B calibrated-prediction rows drifted")
    if set(role_counts) != set(EVALUATION_ROLE_SPLITS):
        raise PricingExportError("Stage 4B evaluation roles are incomplete")
    if require_frozen_identity and dict(role_counts) != (
        FROZEN_FIXTURE_MARKET_ROLE_COUNTS
    ):
        raise PricingExportError("Stage 4B fixture-market role counts drifted")
    if require_frozen_identity and len(catalog) != FROZEN_FIXTURE_MARKET_TOTAL:
        raise PricingExportError("Stage 4B fixture-market universe drifted")
    return catalog, {
        **_file_identity(content, rows=rows),
        "evaluation_role_rows": dict(sorted(role_counts.items())),
    }


def _load_json(path: Path, label: str) -> tuple[Any, bytes]:
    content = _read_bytes(path, label)
    try:
        return json.loads(content.decode("utf-8", errors="strict")), content
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PricingExportError(f"{label} is not valid UTF-8 JSON") from error


def _frozen_fixture_kickoffs(
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
) -> dict[str, datetime]:
    kickoffs = {}
    for fixture in fixture_catalog.values():
        existing = kickoffs.setdefault(fixture.fixture_identifier, fixture.kickoff)
        if existing != fixture.kickoff:
            raise PricingExportError("Frozen fixture kickoff differs across markets")
    return kickoffs


def load_provider_mappings(
    path: Path,
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
) -> tuple[dict, dict]:
    value, content = _load_json(path, "Provider mapping file")
    if not isinstance(value, list):
        raise PricingExportError("Provider mapping file must contain a JSON list")
    try:
        mappings_list = []
        for row in value:
            if not isinstance(row, Mapping):
                raise PricingExportError("Provider mapping row must be an object")
            mappings_list.append(ProviderSelectionMapping.from_mapping(row))
        mappings = tuple(mappings_list)
        for mapping in mappings:
            if (mapping.fixture_identifier, mapping.market_id) not in fixture_catalog:
                raise PricingEvidenceError(
                    "Provider mapping fixture-market is outside the frozen universe"
                )
        registry = build_provider_mapping_registry(mappings)
    except (PricingEvidenceError, TypeError) as error:
        raise PricingExportError(str(error)) from error
    return registry, _file_identity(content, rows=len(mappings))


def load_decisions(
    path: Path,
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
) -> tuple[dict[str, datetime], dict]:
    value, content = _load_json(path, "Decision timestamp file")
    if not isinstance(value, list):
        raise PricingExportError("Decision timestamp file must contain a JSON list")
    decisions = {}
    frozen_kickoffs = _frozen_fixture_kickoffs(fixture_catalog)
    for row in value:
        if not isinstance(row, Mapping):
            raise PricingExportError("Decision timestamp row must be an object")
        fixture = str(row.get("fixture_identifier") or "").strip()
        if not fixture or fixture in decisions:
            raise PricingExportError("Decision fixture identities must be unique")
        if fixture not in frozen_kickoffs:
            raise PricingExportError(
                "Decision fixture is outside the frozen fixture universe"
            )
        decision_at = _parse_aware_timestamp(
            row.get("decision_at"), "Decision timestamp"
        )
        if decision_at >= frozen_kickoffs[fixture]:
            raise PricingExportError(
                "Decision timestamp must be strictly before frozen fixture kickoff"
            )
        decisions[fixture] = decision_at
    return decisions, _file_identity(content, rows=len(value))


def load_quote_rows(path: Path) -> tuple[list[dict], dict]:
    content = _read_bytes(path, "Raw research quote file")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PricingExportError("Raw research quote file is not valid UTF-8") from error
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise PricingExportError(
                f"Raw research quote JSONL is malformed at line {line_number}"
            ) from error
        if not isinstance(value, dict):
            raise PricingExportError(
                f"Raw research quote line {line_number} is not an object"
            )
        value = dict(value)
        value["_source_row_number"] = line_number
        rows.append(value)
    return rows, _file_identity(content, rows=len(rows))


def evaluate_pricing_evidence(
    quote_rows: Sequence[Mapping[str, Any]],
    *,
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
    provider_mappings: Mapping,
    decisions: Mapping[str, Any],
    max_quote_age_seconds: int = DEFAULT_MAX_QUOTE_AGE_SECONDS,
) -> dict:
    quote_results: list[QuoteValidationResult] = []
    for index, raw in enumerate(quote_rows, 1):
        fixture_identifier = str(raw.get("fixture_identifier") or "").strip()
        quote_results.append(
            validate_research_quote(
                raw,
                fixture_catalog=fixture_catalog,
                provider_mappings=provider_mappings,
                decision_at=decisions.get(fixture_identifier),
                max_quote_age_seconds=max_quote_age_seconds,
                source_row_number=int(raw.get("_source_row_number") or index),
            )
        )

    grouped = {}
    for result in quote_results:
        if result.status is not EvidenceStatus.ACCEPTED or result.record is None:
            continue
        record = result.record
        key = (
            record.fixture_identifier,
            record.market_id,
            record.source,
            record.quote_snapshot_id,
        )
        grouped.setdefault(key, []).append(record)
    snapshot_results = [
        validate_complete_snapshot(records)
        for _, records in sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0],
                item[0][1].value,
                item[0][2],
                item[0][3],
            ),
        )
    ]
    snapshot_results = list(select_latest_eligible_snapshots(snapshot_results))
    fixture_market_coverage = build_fixture_market_coverage(
        fixture_catalog=fixture_catalog,
        quote_rows=quote_rows,
        quote_results=quote_results,
        snapshot_results=snapshot_results,
    )
    quote_counts = Counter(result.status.value for result in quote_results)
    snapshot_counts = Counter(result.status.value for result in snapshot_results)
    overall = summarize_fixture_market_coverage(fixture_market_coverage)
    role_counts = {
        role: summarize_fixture_market_coverage(
            [row for row in fixture_market_coverage if row["evaluation_role"] == role]
        )
        for role in EVALUATION_ROLE_SPLITS
    }
    return {
        "quote_results": tuple(quote_results),
        "snapshot_results": tuple(snapshot_results),
        "fixture_market_coverage": tuple(fixture_market_coverage),
        "coverage": {
            "scope": "ALL_ROLES_DESCRIPTIVE",
            **overall,
            "quote_counts": {
                status.value: quote_counts[status.value] for status in EvidenceStatus
            },
            "snapshot_counts": {
                status.value: snapshot_counts[status.value] for status in EvidenceStatus
            },
            "by_evaluation_role": role_counts,
        },
    }


def _raw_fixture_market_key(value: Mapping[str, Any]) -> Optional[tuple[str, MarketId]]:
    fixture_identifier = str(value.get("fixture_identifier") or "").strip()
    try:
        market_id = MarketId(value.get("market_id"))
    except (TypeError, ValueError):
        return None
    if not fixture_identifier or market_id not in PERMITTED_MARKETS:
        return None
    return fixture_identifier, market_id


def build_fixture_market_coverage(
    *,
    fixture_catalog: Mapping[tuple[str, MarketId], KnownFixture],
    quote_rows: Sequence[Mapping[str, Any]],
    quote_results: Sequence[QuoteValidationResult],
    snapshot_results: Sequence[SnapshotValidationResult],
) -> list[dict]:
    """Build one deterministic availability row per frozen fixture-market."""
    raw_counts = Counter(
        key for row in quote_rows if (key := _raw_fixture_market_key(row)) is not None
    )
    accepted_counts = Counter(
        (result.record.fixture_identifier, result.record.market_id)
        for result in quote_results
        if result.status is EvidenceStatus.ACCEPTED and result.record is not None
    )
    rejected_counts = Counter()
    for result in quote_results:
        if result.status is EvidenceStatus.ACCEPTED:
            continue
        key = _raw_fixture_market_key(result.audit_dict())
        if key is not None:
            rejected_counts[key] += 1
    complete_counts = Counter(
        (result.snapshot.fixture_identifier, result.snapshot.market_id)
        for result in snapshot_results
        if result.status is EvidenceStatus.ACCEPTED and result.snapshot is not None
    )
    selected_counts = Counter(
        (result.snapshot.fixture_identifier, result.snapshot.market_id)
        for result in snapshot_results
        if result.selected and result.snapshot is not None
    )
    rows = []
    for key, fixture in sorted(
        fixture_catalog.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        raw_count = raw_counts[key]
        accepted_count = accepted_counts[key]
        selected_count = selected_counts[key]
        if raw_count == 0:
            availability_status = "UNAVAILABLE"
            availability_reason = "NO_QUOTE_RECORDS"
        elif accepted_count == 0:
            availability_status = "UNAVAILABLE"
            availability_reason = "NO_ACCEPTED_QUOTES"
        elif selected_count == 0:
            availability_status = "UNAVAILABLE"
            availability_reason = "NO_ELIGIBLE_COMPLETE_SNAPSHOT"
        else:
            availability_status = "AVAILABLE"
            availability_reason = ""
        rows.append(
            {
                "fixture_identifier": fixture.fixture_identifier,
                "market_id": fixture.market_id.value,
                "fixture_kickoff": fixture.kickoff.astimezone(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
                "evaluation_role": fixture.evaluation_role,
                "raw_quote_row_count": raw_count,
                "accepted_quote_row_count": accepted_count,
                "rejected_quote_row_count": rejected_counts[key],
                "complete_eligible_snapshot_count": complete_counts[key],
                "selected_latest_snapshot_count": selected_count,
                "availability_status": availability_status,
                "availability_reason": availability_reason,
            }
        )
    return rows


def summarize_fixture_market_coverage(rows: Sequence[Mapping]) -> dict:
    total = len(rows)
    available = sum(row["availability_status"] == "AVAILABLE" for row in rows)
    unavailable = total - available
    if available + unavailable != total:
        raise PricingExportError("Fixture-market availability accounting differs")
    return {
        "total_frozen_fixture_markets": total,
        "available_fixture_markets": available,
        "unavailable_fixture_markets": unavailable,
        "availability_rate": canonical_decimal(available / total) if total else 0.0,
        "selected_snapshot_count": sum(
            int(row["selected_latest_snapshot_count"]) for row in rows
        ),
        "reason_counts": dict(
            sorted(
                Counter(
                    row["availability_reason"]
                    for row in rows
                    if row["availability_reason"]
                ).items()
            )
        ),
    }


def _render_csv(fieldnames: Sequence[str], rows: Sequence[Mapping]) -> bytes:
    if FORBIDDEN_OUTPUT_FIELDS.intersection(fieldnames):
        raise PricingExportError("Stage 5A output contains a forbidden decision field")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fieldnames, extrasaction="raise", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def render_valid_quotes(results: Sequence[QuoteValidationResult]) -> tuple[bytes, int]:
    rows = []
    for result in results:
        if result.status is not EvidenceStatus.ACCEPTED or result.record is None:
            continue
        record = result.record.to_dict()
        record["decimal_odds"] = canonical_decimal_text(record["decimal_odds"])
        record["validation_status"] = result.status.value
        record["validation_reasons_json"] = "[]"
        rows.append(record)
    rows.sort(
        key=lambda row: (
            row["fixture_identifier"],
            row["market_id"],
            row["source"],
            row["observed_at"],
            row["quote_snapshot_id"],
            row["outcome_id"],
        )
    )
    return _render_csv(VALID_QUOTE_COLUMNS, rows), len(rows)


def render_rejected_quotes(
    results: Sequence[QuoteValidationResult],
) -> tuple[bytes, int]:
    rows = []
    for result in results:
        if result.status is EvidenceStatus.ACCEPTED:
            continue
        audit = result.audit_dict()
        rows.append(
            {
                "source_row_number": result.source_row_number,
                **{field: audit.get(field) for field in RESEARCH_QUOTE_FIELDS},
                "validation_status": result.status.value,
                "validation_reasons_json": _canonical_json_bytes(
                    [reason.value for reason in result.reasons]
                ).decode("utf-8"),
            }
        )
    rows.sort(key=lambda row: (row["source_row_number"] or 0, row["validation_reasons_json"]))
    return _render_csv(REJECTED_QUOTE_COLUMNS, rows), len(rows)


def render_snapshots(
    results: Sequence[SnapshotValidationResult],
) -> tuple[bytes, int]:
    rows = []
    for result in results:
        snapshot = result.snapshot
        representative = snapshot or (result.records[0] if result.records else None)
        row = {
            "fixture_identifier": getattr(representative, "fixture_identifier", ""),
            "market_id": getattr(getattr(representative, "market_id", None), "value", ""),
            "line": "",
            "source": getattr(representative, "source", ""),
            "quote_snapshot_id": getattr(representative, "quote_snapshot_id", ""),
            "observed_at": "",
            "fixture_kickoff": "",
            "decision_at": "",
            "evaluation_role": getattr(representative, "evaluation_role", ""),
            "validation_status": result.status.value,
            "validation_reasons_json": _canonical_json_bytes(
                [reason.value for reason in result.reasons]
            ).decode("utf-8"),
            "selected_latest_eligible": "1" if result.selected else "0",
            "yes_odds": "",
            "no_odds": "",
            "yes_raw_implied_probability": "",
            "no_raw_implied_probability": "",
            "overround": "",
            "devig_method": "",
            "yes_fair_probability": "",
            "no_fair_probability": "",
            "yes_bookmaker_fair_probability_band": "",
            "no_bookmaker_fair_probability_band": "",
        }
        if representative is not None:
            for name in ("observed_at", "fixture_kickoff", "decision_at"):
                value = getattr(representative, name)
                row[name] = value.astimezone(timezone.utc).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
        if snapshot is not None:
            priced = snapshot.to_dict()
            for name in (
                "yes_odds",
                "no_odds",
                "yes_raw_implied_probability",
                "no_raw_implied_probability",
                "overround",
                "yes_fair_probability",
                "no_fair_probability",
            ):
                row[name] = canonical_decimal_text(priced[name])
            row["devig_method"] = priced["devig_method"]
            row["yes_bookmaker_fair_probability_band"] = priced[
                "yes_fair_probability_band"
            ]
            row["no_bookmaker_fair_probability_band"] = priced[
                "no_fair_probability_band"
            ]
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["fixture_identifier"],
            row["market_id"],
            row["source"],
            row["observed_at"],
            row["quote_snapshot_id"],
        )
    )
    return _render_csv(SNAPSHOT_COLUMNS, rows), len(rows)


def render_fixture_market_coverage(rows: Sequence[Mapping]) -> tuple[bytes, int]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (row["fixture_identifier"], row["market_id"]),
    )
    for row in ordered:
        if set(row) != set(FIXTURE_MARKET_COVERAGE_COLUMNS):
            raise PricingExportError("Fixture-market coverage columns differ")
    return _render_csv(FIXTURE_MARKET_COVERAGE_COLUMNS, ordered), len(ordered)


def render_coverage(coverage: Mapping) -> bytes:
    return _canonical_json_bytes(coverage, pretty=True)


def build_pricing_manifest(
    *,
    stage_4b_manifest: Mapping,
    prediction_identity: Mapping,
    quote_identity: Mapping,
    mapping_identity: Mapping,
    decision_identity: Mapping,
    valid_quote_bytes: bytes,
    valid_quote_rows: int,
    rejected_quote_bytes: bytes,
    rejected_quote_rows: int,
    snapshot_bytes: bytes,
    snapshot_rows: int,
    fixture_market_coverage_bytes: bytes,
    fixture_market_coverage_rows: int,
    coverage_bytes: bytes,
    coverage: Mapping,
    generator_code_state: Mapping,
    max_quote_age_seconds: int,
    generated_at_utc: Optional[str] = None,
) -> dict:
    ancestry = verify_stage_4b_manifest_contract(stage_4b_manifest)
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "generator": {
            "generator_git_head_sha": generator_code_state.get(
                "evidence_git_head_sha"
            ),
            "tracked_worktree_clean": generator_code_state.get(
                "tracked_worktree_clean"
            ),
        },
        "stage_4b_calibration": ancestry,
        "inputs": {
            "calibrated_predictions": dict(prediction_identity),
            "raw_quotes": dict(quote_identity),
            "provider_mappings": dict(mapping_identity),
            "decision_timestamps": dict(decision_identity),
        },
        "quote_contract": {
            "schema_version": SCHEMA_VERSION,
            "fields": list(RESEARCH_QUOTE_FIELDS),
            "permitted_markets": [market.value for market in PERMITTED_MARKETS],
            "permitted_outcomes": [outcome.value for outcome in PERMITTED_OUTCOMES],
            "line": None,
            "provider_mapping": "exact_event_market_selection",
        },
        "as_of_policy": {
            "default_max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
            "configured_max_quote_age_seconds": max_quote_age_seconds,
            "latest_snapshot_tie_break": "lexically_greatest_quote_snapshot_id",
            "observed_at_not_after_decision": True,
            "decision_strictly_before_kickoff": True,
        },
        "pricing_calculation": {
            "canonical_decimal_places": CANONICAL_DECIMAL_PLACES,
            "devig_method": DEVIG_METHOD,
            "required_outcomes": ["YES", "NO"],
        },
        "bookmaker_fair_probability_bands": [
            value[0] for value in BOOKMAKER_FAIR_PROBABILITY_BANDS
        ],
        "evaluation_roles": dict(EVALUATION_ROLE_SPLITS),
        "holdout_governance": dict(HOLDOUT_GOVERNANCE),
        "coverage": dict(coverage),
        "files": {
            "valid_quotes": _file_identity(
                valid_quote_bytes, "pricing-valid-quotes-v1.csv", valid_quote_rows
            ),
            "rejected_quotes": _file_identity(
                rejected_quote_bytes,
                "pricing-rejected-quotes-v1.csv",
                rejected_quote_rows,
            ),
            "snapshots": _file_identity(
                snapshot_bytes, "pricing-snapshots-v1.csv", snapshot_rows
            ),
            "fixture_market_coverage": _file_identity(
                fixture_market_coverage_bytes,
                "pricing-fixture-market-coverage-v1.csv",
                fixture_market_coverage_rows,
            ),
            "coverage": _file_identity(
                coverage_bytes, "pricing-coverage-v1.json"
            ),
        },
        "market_safety": {
            "home_win_either_half": "DISABLED",
            "away_win_either_half": "DISABLED",
            "production_activation_authorized": False,
        },
        "prohibited_calculations": [
            "BET_DECISION",
            "BOOKMAKER_VALUE_CLAIM",
            "EDGE",
            "EXPECTED_VALUE",
            "KELLY_STAKE",
            "THRESHOLD_APPROVAL",
        ],
    }


def compare_pricing_manifests(
    stored: Mapping,
    current: Mapping,
    *,
    allow_generator_revision_difference: bool = False,
) -> list[str]:
    differences = []
    for key, label in (
        ("schema_version", "manifest schema version differs"),
        ("dataset_name", "dataset name differs"),
        ("stage_4b_calibration", "Stage 4B ancestry differs"),
        ("inputs", "pricing input identities differ"),
        ("quote_contract", "research quote contract differs"),
        ("as_of_policy", "as-of pricing policy differs"),
        ("pricing_calculation", "pricing calculation contract differs"),
        ("bookmaker_fair_probability_bands", "bookmaker fair bands differ"),
        ("evaluation_roles", "evaluation-role contract differs"),
        ("holdout_governance", "holdout-governance contract differs"),
        ("coverage", "pricing coverage differs"),
        ("files", "pricing output identities differ"),
        ("market_safety", "market safety differs"),
        ("prohibited_calculations", "prohibited-calculation contract differs"),
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


def write_pricing_outputs(
    *,
    valid_quotes_path: Path,
    rejected_quotes_path: Path,
    snapshots_path: Path,
    fixture_market_coverage_path: Path,
    coverage_path: Path,
    manifest_path: Path,
    valid_quote_bytes: bytes,
    rejected_quote_bytes: bytes,
    snapshot_bytes: bytes,
    fixture_market_coverage_bytes: bytes,
    coverage_bytes: bytes,
    manifest: Mapping,
    force: bool = False,
) -> None:
    paths = (
        valid_quotes_path,
        rejected_quotes_path,
        snapshots_path,
        fixture_market_coverage_path,
        coverage_path,
        manifest_path,
    )
    if len({Path(os.path.abspath(path)) for path in paths}) != len(paths):
        raise PricingExportError("Stage 5A output paths must be distinct")
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise PricingExportError(
            "Output already exists; use --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    _atomic_write(valid_quotes_path, valid_quote_bytes)
    _atomic_write(rejected_quotes_path, rejected_quote_bytes)
    _atomic_write(snapshots_path, snapshot_bytes)
    _atomic_write(fixture_market_coverage_path, fixture_market_coverage_bytes)
    _atomic_write(coverage_path, coverage_bytes)
    _atomic_write(manifest_path, _canonical_json_bytes(manifest, pretty=True))


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate deterministic Win Either Half historical pricing evidence; "
            "no network requests, edge, staking, or betting decisions are performed."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest-output", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--provider-mappings", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument(
        "--calibration-manifest",
        type=Path,
        default=Path(
            "artifacts/research-manifests/win-either-half-calibration-v1.json"
        ),
    )
    parser.add_argument(
        "--calibrated-predictions",
        type=Path,
        default=Path(
            ".cache/athena-research/win-either-half/calibrated-predictions-v1.csv"
        ),
    )
    output_root = Path(".cache/athena-research/win-either-half")
    parser.add_argument(
        "--valid-quotes-output",
        type=Path,
        default=output_root / "pricing-valid-quotes-v1.csv",
    )
    parser.add_argument(
        "--rejected-quotes-output",
        type=Path,
        default=output_root / "pricing-rejected-quotes-v1.csv",
    )
    parser.add_argument(
        "--snapshots-output",
        type=Path,
        default=output_root / "pricing-snapshots-v1.csv",
    )
    parser.add_argument(
        "--fixture-market-coverage-output",
        type=Path,
        default=output_root / "pricing-fixture-market-coverage-v1.csv",
    )
    parser.add_argument(
        "--coverage-output",
        type=Path,
        default=output_root / "pricing-coverage-v1.json",
    )
    parser.add_argument(
        "--max-quote-age-seconds",
        type=_positive_integer,
        default=DEFAULT_MAX_QUOTE_AGE_SECONDS,
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        stage_4b_manifest = load_stage_4b_manifest(args.calibration_manifest)
        verify_stage_4b_manifest_contract(stage_4b_manifest)
        fixture_catalog, prediction_identity = load_verified_calibrated_predictions(
            args.calibrated_predictions, stage_4b_manifest
        )
        mappings, mapping_identity = load_provider_mappings(
            args.provider_mappings, fixture_catalog
        )
        decisions, decision_identity = load_decisions(args.decisions, fixture_catalog)
        quote_rows, quote_identity = load_quote_rows(args.quotes)
        code_state = get_code_state(REPOSITORY_ROOT)
        if not code_state.get("tracked_worktree_clean"):
            raise PricingExportError("Tracked worktree is dirty")
        evaluation = evaluate_pricing_evidence(
            quote_rows,
            fixture_catalog=fixture_catalog,
            provider_mappings=mappings,
            decisions=decisions,
            max_quote_age_seconds=args.max_quote_age_seconds,
        )
        valid_bytes, valid_rows = render_valid_quotes(evaluation["quote_results"])
        rejected_bytes, rejected_rows = render_rejected_quotes(
            evaluation["quote_results"]
        )
        snapshot_bytes, snapshot_rows = render_snapshots(
            evaluation["snapshot_results"]
        )
        fixture_market_coverage_bytes, fixture_market_coverage_rows = (
            render_fixture_market_coverage(evaluation["fixture_market_coverage"])
        )
        coverage_bytes = render_coverage(evaluation["coverage"])
        manifest = build_pricing_manifest(
            stage_4b_manifest=stage_4b_manifest,
            prediction_identity=prediction_identity,
            quote_identity=quote_identity,
            mapping_identity=mapping_identity,
            decision_identity=decision_identity,
            valid_quote_bytes=valid_bytes,
            valid_quote_rows=valid_rows,
            rejected_quote_bytes=rejected_bytes,
            rejected_quote_rows=rejected_rows,
            snapshot_bytes=snapshot_bytes,
            snapshot_rows=snapshot_rows,
            fixture_market_coverage_bytes=fixture_market_coverage_bytes,
            fixture_market_coverage_rows=fixture_market_coverage_rows,
            coverage_bytes=coverage_bytes,
            coverage=evaluation["coverage"],
            generator_code_state=code_state,
            max_quote_age_seconds=args.max_quote_age_seconds,
        )
        if args.check is not None:
            stored = load_stage_4b_manifest(args.check)
            differences = compare_pricing_manifests(
                stored, manifest, allow_generator_revision_difference=True
            )
            if differences:
                raise PricingExportError("; ".join(differences))
            relationship = verify_revision_relationship(
                {
                    "evidence_git_head_sha": stored.get("generator", {}).get(
                        "generator_git_head_sha"
                    )
                },
                {
                    "evidence_git_head_sha": code_state.get("evidence_git_head_sha"),
                    "tracked_worktree_clean": code_state.get(
                        "tracked_worktree_clean"
                    ),
                },
                check_path=args.check,
                repository_root=REPOSITORY_ROOT,
            )
            print(
                "Stage 5A pricing evidence verified: "
                + relationship["message"]
            )
            return 0
        write_pricing_outputs(
            valid_quotes_path=args.valid_quotes_output,
            rejected_quotes_path=args.rejected_quotes_output,
            snapshots_path=args.snapshots_output,
            fixture_market_coverage_path=args.fixture_market_coverage_output,
            coverage_path=args.coverage_output,
            manifest_path=args.manifest_output,
            valid_quote_bytes=valid_bytes,
            rejected_quote_bytes=rejected_bytes,
            snapshot_bytes=snapshot_bytes,
            fixture_market_coverage_bytes=fixture_market_coverage_bytes,
            coverage_bytes=coverage_bytes,
            manifest=manifest,
            force=args.force,
        )
        print(
            "Stage 5A pricing evidence generated: "
            f"accepted_quotes={evaluation['coverage']['quote_counts']['ACCEPTED']}, "
            f"rejected_quotes={evaluation['coverage']['quote_counts']['REJECTED']}, "
            f"accepted_snapshots={evaluation['coverage']['snapshot_counts']['ACCEPTED']}, "
            f"unavailable_snapshots={evaluation['coverage']['snapshot_counts']['UNAVAILABLE']}"
        )
        return 0
    except (BaselineError, PricingEvidenceError, PricingExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
