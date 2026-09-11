"""Immutable, non-decision evidence capture for the future P3.0 replay gate.

This module deliberately knows nothing about provider acquisition, Current Shadow
orchestration, share-code transport, or football selection.  A prospective
capture caller supplies explicit, already-observed legacy and canonical facts;
this module validates, joins, canonicalizes, and writes those facts without
attempting to fill gaps or compare the two decisions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P3_0_COMPARISON_EVIDENCE_V1"

JOIN_STATES = frozenset(
    {
        "EXACT_SAME_FIXTURE_PROVEN",
        "LEGACY_ONLY",
        "CANONICAL_ONLY",
        "IDENTITY_AMBIGUOUS",
        "KICKOFF_MISMATCH",
        "COMPETITION_MISMATCH",
        "AS_OF_NOT_PROVEN",
        "EVIDENCE_INCOMPLETE",
    }
)
COMPLETENESS_STATES = frozenset(
    {"P3_0_CAPTURE_COMPLETE", "P3_0_CAPTURE_PARTIAL", "P3_0_CAPTURE_UNUSABLE"}
)

FIXTURE_IDENTITY_KEYS = frozenset(
    {
        "fixture_identity",
        "fixture_identity_policy",
        "home_team",
        "away_team",
        "home_source_id",
        "away_source_id",
        "competition_identity",
        "competition_name",
        "kickoff",
        "fixture_source",
        "fixture_source_event_id",
        "fixture_source_observed_at",
        "fixture_source_artifact_sha256",
        "fixture_source_manifest_sha256",
    }
)
TIMING_KEYS = frozenset(
    {
        "legacy_evidence_observed_at",
        "legacy_evaluation_time",
        "probability_evaluation_time",
        "provider_quote_observed_at",
        "canonical_price_all_evaluation_time",
        "canonical_router_evaluation_time",
        "kickoff_time",
        "common_as_of_time",
        "common_as_of_proven",
    }
)
CANONICAL_AUTHORITY_KEYS = frozenset(
    {
        "canonical_core_policy_id",
        "canonical_core_contract_sha256",
        "authority_manifest_sha256",
        "registry_canonical_sha256",
        "authority_profile",
        "resolved_components",
    }
)
REQUIRED_CANONICAL_RESPONSIBILITIES = frozenset(
    {
        "provider_market_semantics",
        "price_all_and_de_vig",
        "market_router",
        "portfolio_optimizer",
        "delivery_share_code_transport",
    }
)

# These are names of values that must never enter a durable comparison artifact.
# The safety booleans in an explicit receipt are allowed; account/session material
# is not.  We deliberately reject rather than silently redact so lineage stays
# truthful and the caller must make an explicit safe projection.
_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "bearer",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
    "wallet",
    "account_balance",
    "stake_amount",
    "wager_amount",
    "share_code",
    "share_url",
)


def _contract_payload() -> dict[str, Any]:
    """Stable schema identity, separate from a particular prospective run."""
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "fixture_identity_keys": sorted(FIXTURE_IDENTITY_KEYS),
        "timing_keys": sorted(TIMING_KEYS),
        "canonical_authority_keys": sorted(CANONICAL_AUTHORITY_KEYS),
        "required_canonical_responsibilities": sorted(REQUIRED_CANONICAL_RESPONSIBILITIES),
        "join_states": sorted(JOIN_STATES),
        "completeness_states": sorted(COMPLETENESS_STATES),
        "sensitive_key_fragments": sorted(_SENSITIVE_KEY_FRAGMENTS),
    }


class P30ComparisonEvidenceError(ValueError):
    """Raised when a capture cannot be represented safely and exactly."""


class LegacyEvidenceObserver:
    """Explicit, memory-only observer for the supported AnalysisPipeline seam.

    It is deliberately not installed by this module. A bounded future capture
    invocation must create one and pass it to ``run_pipeline_snapshot``. The
    observer returns no decision and retains only explicit safe projections.
    """

    def __init__(self) -> None:
        self._observations: list[dict[str, Any]] = []

    def __call__(
        self,
        fixture_context: Mapping[str, Any],
        legacy_analysis_before_runtime_gate: Mapping[str, Any],
        authorized_analysis: Mapping[str, Any],
        exported_row: Mapping[str, Any],
    ) -> None:
        self._observations.append(
            {
                "legacy_input": _plain_mapping(fixture_context, "legacy_fixture_context"),
                "legacy_output": {
                    "legacy_analysis_before_runtime_gate": _plain_mapping(
                        legacy_analysis_before_runtime_gate,
                        "legacy_analysis_before_runtime_gate",
                    ),
                    "authorized_analysis": _plain_mapping(authorized_analysis, "legacy_authorized_analysis"),
                    "exported_row": _plain_mapping(exported_row, "legacy_exported_row"),
                },
            }
        )

    def observations(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(load_json_bytes(canonical_json_bytes(value)) for value in self._observations)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise P30ComparisonEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(raw: bytes) -> Any:
    """Load UTF-8 JSON fail-closed on duplicate keys and non-finite values."""
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                P30ComparisonEvidenceError(f"non-finite JSON constant: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P30ComparisonEvidenceError("invalid UTF-8 canonical JSON") from exc
    _validate_json_value(value, "$")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the single canonical serialization accepted by policy v1."""
    _validate_json_value(value, "$")
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise P30ComparisonEvidenceError("value is not canonically serializable") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def calculate_contract_sha256() -> str:
    return canonical_sha256(_contract_payload())


EXPECTED_CONTRACT_SHA256 = "33367636297cee01a3386923a7e5a2c1be414272c83af560eb819adf8cf3de7a"


def validate_contract() -> str:
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise P30ComparisonEvidenceError("P3.0 comparison evidence contract drifted")
    return actual


def _validate_json_value(value: Any, location: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise P30ComparisonEvidenceError(f"non-finite number at {location}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{location}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise P30ComparisonEvidenceError(f"non-string JSON key at {location}")
            _reject_sensitive_key(key, f"{location}.{key}")
            _validate_json_value(item, f"{location}.{key}")
        return
    raise P30ComparisonEvidenceError(f"non-JSON value at {location}: {type(value).__name__}")


def _reject_sensitive_key(key: str, location: str) -> None:
    normalized = key.casefold().replace("-", "_")
    if any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS):
        raise P30ComparisonEvidenceError(f"sensitive evidence key is forbidden at {location}")


def _plain_mapping(value: Mapping[str, Any] | None, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise P30ComparisonEvidenceError(f"{label} must be a plain JSON object or null")
    _validate_json_value(value, label)
    # Canonical JSON round-trip prohibits arbitrary Mapping implementations and
    # ensures callers cannot mutate the stored capture through shared references.
    return load_json_bytes(canonical_json_bytes(value))


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unexpected = sorted(set(value) - expected)
        raise P30ComparisonEvidenceError(
            f"{label} keys drifted; missing={missing}, unexpected={unexpected}"
        )


def normalize_fixture_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an explicit identity projection without guessing any field."""
    item = _plain_mapping(value, "fixture_identity")
    assert item is not None
    _exact_keys(item, FIXTURE_IDENTITY_KEYS, "fixture_identity")
    for key in (
        "fixture_identity",
        "fixture_identity_policy",
        "home_team",
        "away_team",
        "competition_identity",
        "competition_name",
        "kickoff",
        "fixture_source",
        "fixture_source_event_id",
        "fixture_source_observed_at",
        "fixture_source_artifact_sha256",
        "fixture_source_manifest_sha256",
    ):
        if item[key] is not None and type(item[key]) is not str:
            raise P30ComparisonEvidenceError(f"fixture_identity.{key} must be string or null")
    for key in ("home_source_id", "away_source_id"):
        if item[key] is not None and type(item[key]) not in (str, int):
            raise P30ComparisonEvidenceError(f"fixture_identity.{key} must be string, integer, or null")
    return item


def normalize_timing(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "timing")
    assert item is not None
    _exact_keys(item, TIMING_KEYS, "timing")
    for key, item_value in item.items():
        if key == "common_as_of_proven":
            if type(item_value) is not bool:
                raise P30ComparisonEvidenceError("timing.common_as_of_proven must be bool")
        elif item_value is not None and type(item_value) is not str:
            raise P30ComparisonEvidenceError(f"timing.{key} must be string or null")
    if item["common_as_of_proven"] and item["common_as_of_time"] is None:
        raise P30ComparisonEvidenceError("proved common as-of requires common_as_of_time")
    return item


def normalize_canonical_authority(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "canonical_authority")
    assert item is not None
    _exact_keys(item, CANONICAL_AUTHORITY_KEYS, "canonical_authority")
    if item["authority_profile"] != "SHADOW":
        raise P30ComparisonEvidenceError("P3.0-E1 canonical evidence must remain SHADOW-only")
    if type(item["resolved_components"]) is not list or not item["resolved_components"]:
        raise P30ComparisonEvidenceError("canonical_authority.resolved_components must be non-empty list")
    for key in CANONICAL_AUTHORITY_KEYS - {"resolved_components"}:
        if type(item[key]) is not str or not item[key]:
            raise P30ComparisonEvidenceError(f"canonical_authority.{key} must be non-empty string")
    for component in item["resolved_components"]:
        if type(component) is not dict:
            raise P30ComparisonEvidenceError("canonical_authority component must be object")
        required = {"responsibility_id", "component_id", "contract_sha256", "artifact_git_blob_sha"}
        if set(component) != required or any(type(component[k]) is not str or not component[k] for k in required):
            raise P30ComparisonEvidenceError("canonical_authority component identity drifted")
    item["resolved_components"] = sorted(
        item["resolved_components"], key=lambda component: component["responsibility_id"]
    )
    responsibilities = {component["responsibility_id"] for component in item["resolved_components"]}
    if responsibilities != REQUIRED_CANONICAL_RESPONSIBILITIES:
        raise P30ComparisonEvidenceError("canonical authority responsibilities drifted")
    return item


def build_join_receipt(
    legacy_identity: Mapping[str, Any] | None,
    canonical_identity: Mapping[str, Any] | None,
    timing: Mapping[str, Any],
) -> dict[str, Any]:
    """Join only exact reviewed identities; no team-name or kickoff tolerance exists."""
    legacy = None if legacy_identity is None else normalize_fixture_identity(legacy_identity)
    canonical = None if canonical_identity is None else normalize_fixture_identity(canonical_identity)
    normalized_timing = normalize_timing(timing)
    if legacy is None and canonical is None:
        state, reasons = "EVIDENCE_INCOMPLETE", ["MISSING_FIXTURE_IDENTITIES"]
    elif legacy is None:
        state, reasons = "CANONICAL_ONLY", ["MISSING_LEGACY_FIXTURE_IDENTITY"]
    elif canonical is None:
        state, reasons = "LEGACY_ONLY", ["MISSING_CANONICAL_FIXTURE_IDENTITY"]
    elif not legacy["fixture_identity"] or not canonical["fixture_identity"]:
        state, reasons = "IDENTITY_AMBIGUOUS", ["FIXTURE_JOIN_UNPROVEN"]
    elif legacy["fixture_identity"] != canonical["fixture_identity"]:
        state, reasons = "IDENTITY_AMBIGUOUS", ["FIXTURE_IDENTITY_MISMATCH"]
    elif legacy["fixture_identity_policy"] != canonical["fixture_identity_policy"]:
        state, reasons = "IDENTITY_AMBIGUOUS", ["FIXTURE_IDENTITY_POLICY_MISMATCH"]
    elif legacy["kickoff"] and canonical["kickoff"] and legacy["kickoff"] != canonical["kickoff"]:
        state, reasons = "KICKOFF_MISMATCH", ["KICKOFF_MISMATCH"]
    elif (
        legacy["competition_identity"]
        and canonical["competition_identity"]
        and legacy["competition_identity"] != canonical["competition_identity"]
    ):
        state, reasons = "COMPETITION_MISMATCH", ["COMPETITION_MISMATCH"]
    elif not normalized_timing["common_as_of_proven"]:
        state, reasons = "AS_OF_NOT_PROVEN", ["COMMON_AS_OF_UNPROVEN"]
    else:
        state, reasons = "EXACT_SAME_FIXTURE_PROVEN", []
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "join_state": state,
        "reasons": reasons,
        "legacy_fixture_identity": legacy,
        "canonical_fixture_identity": canonical,
        "canonical_sha256": canonical_sha256(
            {
                "schema_version": SCHEMA_VERSION,
                "policy_id": POLICY_ID,
                "join_state": state,
                "reasons": reasons,
                "legacy_fixture_identity": legacy,
                "canonical_fixture_identity": canonical,
            }
        ),
    }


def _present(value: Any) -> bool:
    return value is not None


def build_fixture_record(
    fixture_capture_id: str,
    *,
    legacy_identity: Mapping[str, Any] | None,
    canonical_identity: Mapping[str, Any] | None,
    timing: Mapping[str, Any],
    canonical_authority: Mapping[str, Any] | None,
    legacy_input: Mapping[str, Any] | None = None,
    legacy_output: Mapping[str, Any] | None = None,
    canonical_fixture_state: Mapping[str, Any] | None = None,
    probability_bundle: Mapping[str, Any] | None = None,
    provider_semantics: Mapping[str, Any] | None = None,
    quote_snapshot: Mapping[str, Any] | None = None,
    price_all_output: Mapping[str, Any] | None = None,
    router_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one neutral evidence row; it cannot classify decision quality."""
    validate_contract()
    if type(fixture_capture_id) is not str or not fixture_capture_id:
        raise P30ComparisonEvidenceError("fixture_capture_id must be non-empty string")
    normalized_timing = normalize_timing(timing)
    legacy = None if legacy_identity is None else normalize_fixture_identity(legacy_identity)
    canonical = None if canonical_identity is None else normalize_fixture_identity(canonical_identity)
    authority = None if canonical_authority is None else normalize_canonical_authority(canonical_authority)
    values = {
        "legacy_input": _plain_mapping(legacy_input, "legacy_input"),
        "legacy_output": _plain_mapping(legacy_output, "legacy_output"),
        "canonical_fixture_state": _plain_mapping(canonical_fixture_state, "canonical_fixture_state"),
        "probability_bundle": _plain_mapping(probability_bundle, "probability_bundle"),
        "provider_semantics": _plain_mapping(provider_semantics, "provider_semantics"),
        "quote_snapshot": _plain_mapping(quote_snapshot, "quote_snapshot"),
        "price_all_output": _plain_mapping(price_all_output, "price_all_output"),
        "router_output": _plain_mapping(router_output, "router_output"),
    }
    join = build_join_receipt(legacy, canonical, normalized_timing)
    missing: list[str] = []
    for key, reason in (
        ("canonical_authority", "MISSING_CANONICAL_AUTHORITY"),
        ("legacy_input", "MISSING_LEGACY_CONTEXT"),
        ("legacy_output", "MISSING_LEGACY_OUTPUT"),
        ("canonical_fixture_state", "MISSING_CANONICAL_FIXTURE_STATE"),
        ("probability_bundle", "MISSING_MARKET_PROBABILITY_BUNDLE"),
        ("provider_semantics", "MISSING_PROVIDER_SEMANTIC_IDENTITY"),
        ("quote_snapshot", "MISSING_QUOTE"),
        ("price_all_output", "MISSING_PRICE_ALL_OUTPUT"),
        ("router_output", "MISSING_ROUTER_OUTPUT"),
    ):
        if key == "canonical_authority":
            present = authority is not None
        else:
            present = _present(values[key])
        if not present:
            missing.append(reason)
    if normalized_timing["provider_quote_observed_at"] is None:
        missing.append("MISSING_QUOTE_OBSERVED_AT")
    if join["join_state"] != "EXACT_SAME_FIXTURE_PROVEN":
        missing.extend(join["reasons"] or ["FIXTURE_JOIN_UNPROVEN"])
    missing = sorted(set(missing))
    if join["join_state"] in {"IDENTITY_AMBIGUOUS", "KICKOFF_MISMATCH", "COMPETITION_MISMATCH"}:
        completeness = "P3_0_CAPTURE_UNUSABLE"
    elif missing:
        completeness = "P3_0_CAPTURE_PARTIAL"
    else:
        completeness = "P3_0_CAPTURE_COMPLETE"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "fixture_capture_id": fixture_capture_id,
        "legacy_fixture_identity": legacy,
        "canonical_fixture_identity": canonical,
        "timing": normalized_timing,
        "canonical_authority": authority,
        **values,
        "join_receipt": join,
        "completeness_receipt": {"state": completeness, "missing_reasons": missing},
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def _validate_fixture_record(value: Any) -> dict[str, Any]:
    item = _plain_mapping(value, "fixture_record")
    assert item is not None
    expected = {
        "schema_version", "policy_id", "fixture_capture_id", "legacy_fixture_identity",
        "canonical_fixture_identity", "timing", "canonical_authority", "legacy_input",
        "legacy_output", "canonical_fixture_state", "probability_bundle", "provider_semantics",
        "quote_snapshot", "price_all_output", "router_output", "join_receipt",
        "completeness_receipt", "canonical_sha256",
    }
    _exact_keys(item, frozenset(expected), "fixture_record")
    if item["schema_version"] != SCHEMA_VERSION or item["policy_id"] != POLICY_ID:
        raise P30ComparisonEvidenceError("fixture record policy identity drifted")
    expected_hash = canonical_sha256({key: value for key, value in item.items() if key != "canonical_sha256"})
    if item["canonical_sha256"] != expected_hash:
        raise P30ComparisonEvidenceError("fixture record canonical SHA-256 drifted")
    return item


def build_capture_bundle(
    *,
    repository_commit_sha: str,
    capture_id: str,
    capture_started_at: str,
    capture_completed_at: str,
    requested_dates: Sequence[str],
    legacy_execution_identity: Mapping[str, Any],
    canonical_execution_identity: Mapping[str, Any],
    authority_state: Mapping[str, Any],
    source_artifacts: Sequence[Mapping[str, Any]],
    fixture_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic run bundle from explicit captured observations."""
    validate_contract()
    if (
        type(repository_commit_sha) is not str
        or len(repository_commit_sha) != 40
        or any(character not in "0123456789abcdef" for character in repository_commit_sha)
    ):
        raise P30ComparisonEvidenceError("repository_commit_sha must be exact 40-character SHA")
    if type(capture_id) is not str or not capture_id:
        raise P30ComparisonEvidenceError("capture_id must be non-empty string")
    if type(capture_started_at) is not str or type(capture_completed_at) is not str:
        raise P30ComparisonEvidenceError("capture timestamps must be explicit strings")
    if type(requested_dates) not in (list, tuple) or not requested_dates or any(type(x) is not str for x in requested_dates):
        raise P30ComparisonEvidenceError("requested_dates must be non-empty string sequence")
    if list(requested_dates) != sorted(set(requested_dates)):
        raise P30ComparisonEvidenceError("requested_dates must be unique and sorted")
    records = [_validate_fixture_record(item) for item in fixture_records]
    if len({item["fixture_capture_id"] for item in records}) != len(records):
        raise P30ComparisonEvidenceError("duplicate fixture_capture_id")
    records.sort(key=lambda item: item["fixture_capture_id"])
    sources = [_plain_mapping(item, "source_artifact") for item in source_artifacts]
    if any(item is None for item in sources):
        raise P30ComparisonEvidenceError("source_artifact cannot be null")
    sources = [item for item in sources if item is not None]
    sources.sort(key=canonical_json_bytes)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_commit_sha": repository_commit_sha,
        "capture_id": capture_id,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_dates": list(requested_dates),
        "legacy_execution_identity": _plain_mapping(legacy_execution_identity, "legacy_execution_identity"),
        "canonical_execution_identity": _plain_mapping(canonical_execution_identity, "canonical_execution_identity"),
        "authority_state": _plain_mapping(authority_state, "authority_state"),
        "source_artifacts": sources,
        "fixture_records": records,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def verify_capture_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract()
    item = _plain_mapping(value, "capture_bundle")
    assert item is not None
    expected = {
        "schema_version", "policy_id", "repository_commit_sha", "capture_id", "capture_started_at",
        "capture_completed_at", "requested_dates", "legacy_execution_identity",
        "canonical_execution_identity", "authority_state", "source_artifacts", "fixture_records",
        "canonical_sha256",
    }
    _exact_keys(item, frozenset(expected), "capture_bundle")
    if item["schema_version"] != SCHEMA_VERSION or item["policy_id"] != POLICY_ID:
        raise P30ComparisonEvidenceError("capture bundle policy identity drifted")
    expected_hash = canonical_sha256({key: value for key, value in item.items() if key != "canonical_sha256"})
    if item["canonical_sha256"] != expected_hash:
        raise P30ComparisonEvidenceError("capture bundle canonical SHA-256 drifted")
    # Re-run record validation and ordering checks rather than trusting a bundle
    # merely because its top-level digest was supplied by the caller.
    return build_capture_bundle(
        repository_commit_sha=item["repository_commit_sha"],
        capture_id=item["capture_id"],
        capture_started_at=item["capture_started_at"],
        capture_completed_at=item["capture_completed_at"],
        requested_dates=item["requested_dates"],
        legacy_execution_identity=item["legacy_execution_identity"],
        canonical_execution_identity=item["canonical_execution_identity"],
        authority_state=item["authority_state"],
        source_artifacts=item["source_artifacts"],
        fixture_records=item["fixture_records"],
    )


def _write_json(path: Path, value: Any) -> str:
    raw = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def write_capture_artifact(bundle: Mapping[str, Any], output_directory: str | Path) -> Path:
    """Write a new immutable artifact directory and return its final path.

    The function rejects an existing output path. It never performs acquisition,
    imports a provider boundary, or serializes objects supplied by application
    code implicitly.
    """
    validate_contract()
    checked = verify_capture_bundle(bundle)
    destination = Path(output_directory)
    if destination.exists():
        raise P30ComparisonEvidenceError("capture output directory already exists")
    parent = destination.parent
    if not parent.exists() or not parent.is_dir():
        raise P30ComparisonEvidenceError("capture output parent must already exist")
    temporary = Path(tempfile.mkdtemp(prefix="p3-0-evidence-", dir=parent))
    try:
        manifest_entries: list[dict[str, str]] = []
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "capture_id": checked["capture_id"],
            "capture_state": (
                "CAPTURE_FAILED"
                if not checked["fixture_records"]
                else (
                    "CAPTURE_COMPLETE"
                    if all(record["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE" for record in checked["fixture_records"])
                    else "CAPTURE_PARTIAL"
                )
            ),
            "fixture_count": len(checked["fixture_records"]),
            "canonical_sha256": checked["canonical_sha256"],
        }
        for relative, content in (("capture-receipt.json", receipt), ("bundle.json", checked)):
            digest = _write_json(temporary / relative, content)
            manifest_entries.append({"path": relative, "sha256": digest})
        for record in checked["fixture_records"]:
            base = Path("fixtures") / record["fixture_capture_id"]
            pieces = {
                "join-receipt.json": record["join_receipt"],
                "completeness-receipt.json": record["completeness_receipt"],
                "legacy-input.json": record["legacy_input"],
                "legacy-output.json": record["legacy_output"],
                "canonical-fixture-state.json": record["canonical_fixture_state"],
                "probability-bundle.json": record["probability_bundle"],
                "provider-semantics.json": record["provider_semantics"],
                "quote-snapshot.json": record["quote_snapshot"],
                "price-all-output.json": record["price_all_output"],
                "router-output.json": record["router_output"],
            }
            for filename, content in pieces.items():
                if content is None:
                    continue
                relative = (base / filename).as_posix()
                digest = _write_json(temporary / relative, content)
                manifest_entries.append({"path": relative, "sha256": digest})
        manifest_entries.sort(key=lambda item: item["path"])
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "capture_id": checked["capture_id"],
            "bundle_canonical_sha256": checked["canonical_sha256"],
            "files": manifest_entries,
        }
        _write_json(temporary / "manifest.json", manifest)
        os.replace(temporary, destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_capture_artifact(directory: str | Path) -> dict[str, Any]:
    validate_contract()
    root = Path(directory)
    manifest = load_json_bytes((root / "manifest.json").read_bytes())
    if type(manifest) is not dict or manifest.get("policy_id") != POLICY_ID:
        raise P30ComparisonEvidenceError("capture artifact manifest identity drifted")
    if type(manifest.get("files")) is not list:
        raise P30ComparisonEvidenceError("capture artifact manifest files drifted")
    for entry in manifest["files"]:
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise P30ComparisonEvidenceError("capture artifact manifest entry drifted")
        candidate = root / entry["path"]
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != entry["sha256"]:
            raise P30ComparisonEvidenceError("capture artifact file digest mismatch")
    bundle = load_json_bytes((root / "bundle.json").read_bytes())
    checked = verify_capture_bundle(bundle)
    if checked["canonical_sha256"] != manifest.get("bundle_canonical_sha256"):
        raise P30ComparisonEvidenceError("capture artifact bundle identity drifted")
    return checked


__all__ = [
    "CANONICAL_AUTHORITY_KEYS",
    "COMPLETENESS_STATES",
    "EXPECTED_CONTRACT_SHA256",
    "FIXTURE_IDENTITY_KEYS",
    "JOIN_STATES",
    "LegacyEvidenceObserver",
    "P30ComparisonEvidenceError",
    "POLICY_ID",
    "REQUIRED_CANONICAL_RESPONSIBILITIES",
    "SCHEMA_VERSION",
    "TIMING_KEYS",
    "build_capture_bundle",
    "build_fixture_record",
    "build_join_receipt",
    "calculate_contract_sha256",
    "canonical_json_bytes",
    "canonical_sha256",
    "load_json_bytes",
    "normalize_canonical_authority",
    "normalize_fixture_identity",
    "normalize_timing",
    "verify_capture_artifact",
    "verify_capture_bundle",
    "validate_contract",
    "write_capture_artifact",
]
