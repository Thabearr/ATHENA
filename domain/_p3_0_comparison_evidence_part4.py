from domain._p3_0_comparison_evidence_part3 import *  # noqa: F401,F403

def build_capture_bundle(*, repository_commit_sha: str, capture_id: str, capture_started_at: str,
                         capture_completed_at: str, requested_dates: Sequence[str],
                         legacy_execution_identity: Mapping[str, Any],
                         canonical_execution_identity: Mapping[str, Any], authority_state: Mapping[str, Any],
                         source_artifacts: Sequence[Mapping[str, Any]], fixture_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    validate_contract()
    _sha40(repository_commit_sha, "repository_commit_sha")
    _safe_fixture_capture_id(capture_id)
    start_s, start = _utc_iso(capture_started_at, "capture_started_at")
    end_s, end = _utc_iso(capture_completed_at, "capture_completed_at")
    if end < start:
        raise P30ComparisonEvidenceError("capture completed before it started")
    if type(requested_dates) not in (list, tuple) or not requested_dates or any(type(x) is not str or len(x) != 8 or not x.isdigit() for x in requested_dates):
        raise P30ComparisonEvidenceError("requested_dates must be non-empty canonical YYYYMMDD sequence")
    if list(requested_dates) != sorted(set(requested_dates)):
        raise P30ComparisonEvidenceError("requested_dates must be sorted unique")
    records = [_validate_fixture_record(item) for item in fixture_records]
    for record in records:
        proof = record["as_of_proof"]
        if (
            proof["capture_id"] != capture_id
            or proof["capture_started_at"] != start_s
            or proof["capture_completed_at"] != end_s
        ):
            raise P30ComparisonEvidenceError(
                "fixture record is not bound to this capture window"
            )
    if len({item["fixture_capture_id"] for item in records}) != len(records):
        raise P30ComparisonEvidenceError("duplicate fixture_capture_id")
    if len({item["fixture_storage_key"] for item in records}) != len(records):
        raise P30ComparisonEvidenceError("duplicate fixture storage key")
    records.sort(key=lambda item: item["fixture_capture_id"])
    source_values = [_normalize_source_artifact(item) for item in source_artifacts]
    source_values.sort(key=canonical_json_bytes)
    source_keys = {
        (
            item["fixture_identity"], item["provider_event_id"],
            item["source_raw_sha256"], item["source_manifest_sha256"],
            item["source_inventory_sha256"], item["fixture_reconciliation_sha256"],
        )
        for item in source_values
    }
    if len(source_keys) != len(source_values):
        raise P30ComparisonEvidenceError("duplicate source artifact identity")
    for record in records:
        state = record.get("canonical_fixture_state")
        if state is None:
            continue
        required_source = (
            state["fixture_identity"], state["provider_event_id"],
            state["source_raw_sha256"], state["source_manifest_sha256"],
            state["source_inventory_sha256"], state["fixture_reconciliation_sha256"],
        )
        if required_source not in source_keys:
            raise P30ComparisonEvidenceError(
                "canonical fixture state lacks matching source artifact lineage"
            )
    payload = {
        "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
        "repository_commit_sha": repository_commit_sha, "capture_id": capture_id,
        "capture_started_at": start_s, "capture_completed_at": end_s,
        "requested_dates": list(requested_dates),
        "legacy_execution_identity": _plain_mapping(legacy_execution_identity, "legacy_execution_identity"),
        "canonical_execution_identity": _plain_mapping(canonical_execution_identity, "canonical_execution_identity"),
        "authority_state": _plain_mapping(authority_state, "authority_state"),
        "source_artifacts": source_values, "fixture_records": records,
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def verify_capture_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract()
    item = _plain_mapping(value, "capture_bundle")
    assert item is not None
    expected = frozenset({
        "schema_version", "policy_id", "repository_commit_sha", "capture_id",
        "capture_started_at", "capture_completed_at", "requested_dates",
        "legacy_execution_identity", "canonical_execution_identity", "authority_state",
        "source_artifacts", "fixture_records", "canonical_sha256",
    })
    _exact_keys(item, expected, "capture_bundle")
    expected_hash = canonical_sha256({k: v for k, v in item.items() if k != "canonical_sha256"})
    if item["canonical_sha256"] != expected_hash:
        raise P30ComparisonEvidenceError("capture bundle canonical SHA-256 drifted")
    return build_capture_bundle(
        repository_commit_sha=item["repository_commit_sha"], capture_id=item["capture_id"],
        capture_started_at=item["capture_started_at"], capture_completed_at=item["capture_completed_at"],
        requested_dates=item["requested_dates"], legacy_execution_identity=item["legacy_execution_identity"],
        canonical_execution_identity=item["canonical_execution_identity"], authority_state=item["authority_state"],
        source_artifacts=item["source_artifacts"], fixture_records=item["fixture_records"],
    )


def _write_json(path: Path, value: Any) -> str:
    raw = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _safe_manifest_relative(raw: Any) -> PurePosixPath:
    if type(raw) is not str or not raw or "\\" in raw or "\x00" in raw:
        raise P30ComparisonEvidenceError("manifest path is unsafe")
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or any(part in {"", ".", ".."} for part in posix.parts):
        raise P30ComparisonEvidenceError("manifest path traversal/absolute path is forbidden")
    if posix.as_posix() != raw:
        raise P30ComparisonEvidenceError("manifest path is not normalized")
    return posix


def write_capture_artifact(bundle: Mapping[str, Any], output_directory: str | Path) -> Path:
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
        entries: list[dict[str, str]] = []
        receipt = {
            "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
            "capture_id": checked["capture_id"],
            "capture_state": (
                "CAPTURE_FAILED" if not checked["fixture_records"] else
                "CAPTURE_COMPLETE" if all(row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE" for row in checked["fixture_records"])
                else "CAPTURE_PARTIAL"
            ),
            "fixture_count": len(checked["fixture_records"]),
            "complete_fixture_count": sum(row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE" for row in checked["fixture_records"]),
            "canonical_sha256": checked["canonical_sha256"],
        }
        for relative, content in (("capture-receipt.json", receipt), ("bundle.json", checked)):
            entries.append({"path": relative, "sha256": _write_json(temporary / relative, content)})
        piece_names = {
            "join-receipt.json": "join_receipt", "as-of-proof.json": "as_of_proof",
            "completeness-receipt.json": "completeness_receipt", "legacy-input.json": "legacy_input",
            "legacy-output.json": "legacy_output", "canonical-fixture-state.json": "canonical_fixture_state",
            "probability-bundle.json": "probability_bundle", "provider-semantics.json": "provider_semantics",
            "quote-snapshot.json": "quote_snapshot", "price-all-output.json": "price_all_output",
            "router-output.json": "router_output", "canonical-authority.json": "canonical_authority",
        }
        for record in checked["fixture_records"]:
            base = PurePosixPath("fixtures") / record["fixture_storage_key"]
            for filename, key in piece_names.items():
                content = record[key]
                if content is None:
                    continue
                relative = (base / filename).as_posix()
                entries.append({"path": relative, "sha256": _write_json(temporary / relative, content)})
        entries.sort(key=lambda item: item["path"])
        manifest = {
            "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
            "capture_id": checked["capture_id"], "bundle_canonical_sha256": checked["canonical_sha256"],
            "files": entries,
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
    if root.is_symlink() or not root.is_dir():
        raise P30ComparisonEvidenceError("capture artifact root is invalid")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise P30ComparisonEvidenceError("capture artifact manifest is invalid")
    manifest = load_json_bytes(manifest_path.read_bytes())
    expected_manifest_keys = {
        "schema_version", "policy_id", "capture_id", "bundle_canonical_sha256", "files"
    }
    if (
        type(manifest) is not dict
        or set(manifest) != expected_manifest_keys
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("policy_id") != POLICY_ID
        or type(manifest.get("capture_id")) is not str
        or type(manifest.get("files")) is not list
    ):
        raise P30ComparisonEvidenceError("capture artifact manifest identity drifted")
    _sha64(manifest.get("bundle_canonical_sha256"), "manifest bundle canonical sha256")
    declared: dict[str, str] = {}
    for entry in manifest["files"]:
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise P30ComparisonEvidenceError("capture artifact manifest entry drifted")
        rel = _safe_manifest_relative(entry["path"]).as_posix()
        if rel == "manifest.json" or rel in declared:
            raise P30ComparisonEvidenceError("duplicate/reserved manifest path")
        declared[rel] = _sha64(entry["sha256"], "manifest file sha256")
        candidate = root.joinpath(*PurePosixPath(rel).parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise P30ComparisonEvidenceError("manifested artifact file is absent or symlinked")
        try:
            candidate.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise P30ComparisonEvidenceError("manifest path escaped artifact root") from exc
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != declared[rel]:
            raise P30ComparisonEvidenceError("capture artifact file digest mismatch")
    actual = {"manifest.json"}
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise P30ComparisonEvidenceError("symlinked artifact entry is forbidden")
        if candidate.is_file():
            actual.add(candidate.relative_to(root).as_posix())
    expected = {"manifest.json", *declared}
    if actual != expected:
        raise P30ComparisonEvidenceError("artifact contains missing or unmanifested files")
    bundle = load_json_bytes((root / "bundle.json").read_bytes())
    checked = verify_capture_bundle(bundle)
    if (
        checked["canonical_sha256"] != manifest.get("bundle_canonical_sha256")
        or checked["capture_id"] != manifest.get("capture_id")
    ):
        raise P30ComparisonEvidenceError("capture artifact bundle identity drifted")
    receipt = load_json_bytes((root / "capture-receipt.json").read_bytes())
    expected_receipt_keys = {
        "schema_version", "policy_id", "capture_id", "capture_state",
        "fixture_count", "complete_fixture_count", "canonical_sha256",
    }
    if type(receipt) is not dict or set(receipt) != expected_receipt_keys:
        raise P30ComparisonEvidenceError("capture receipt fields drifted")
    expected_state = (
        "CAPTURE_FAILED" if not checked["fixture_records"] else
        "CAPTURE_COMPLETE" if all(
            row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE"
            for row in checked["fixture_records"]
        ) else "CAPTURE_PARTIAL"
    )
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["policy_id"] != POLICY_ID
        or receipt["capture_id"] != checked["capture_id"]
        or receipt["capture_state"] != expected_state
        or receipt["fixture_count"] != len(checked["fixture_records"])
        or receipt["complete_fixture_count"] != sum(
            row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE"
            for row in checked["fixture_records"]
        )
        or receipt["canonical_sha256"] != checked["canonical_sha256"]
    ):
        raise P30ComparisonEvidenceError("capture receipt does not bind verified bundle")
    return checked


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
        "as_of_proof_policy_id": AS_OF_PROOF_POLICY_ID,
        "price_output_kind": PRICE_OUTPUT_KIND, "router_output_kind": ROUTER_OUTPUT_KIND,
        "fixture_identity_keys": sorted(FIXTURE_IDENTITY_KEYS), "timing_keys": sorted(TIMING_KEYS),
        "canonical_authority_keys": sorted(CANONICAL_AUTHORITY_KEYS),
        "expected_components": dict(sorted(EXPECTED_COMPONENTS.items())),
        "expected_canonical_core_policy_id": EXPECTED_CANONICAL_CORE_POLICY_ID,
        "expected_canonical_core_contract_sha256": EXPECTED_CANONICAL_CORE_CONTRACT_SHA256,
        "expected_provider_semantics_contract_sha256": EXPECTED_PROVIDER_SEMANTICS_CONTRACT_SHA256,
        "expected_provider_registry_policy_id": EXPECTED_PROVIDER_REGISTRY_POLICY_ID,
        "expected_component_identities": {key: list(value) for key, value in sorted(EXPECTED_COMPONENT_IDENTITIES.items())},
        "join_states": sorted(JOIN_STATES), "completeness_states": sorted(COMPLETENESS_STATES),
        "legacy_input_fields": sorted(_LEGACY_INPUT_FIELDS),
        "legacy_analysis_fields": sorted(_LEGACY_ANALYSIS_FIELDS),
        "legacy_exported_fields": sorted(_LEGACY_EXPORTED_FIELDS),
        "forbidden_exact_keys": sorted(_FORBIDDEN_EXACT_KEYS),
        "forbidden_tokens": sorted(_FORBIDDEN_TOKENS),
        "allowed_false_safety_keys": sorted(_ALLOWED_FALSE_SAFETY_KEYS),
        "quote_snapshot_empty_list_is_observed_unavailability": True,
        "quote_identity_policy": "EXACT_SHADOW_QUOTE_TO_DICT_COMPACT_SHA256_REPLAY_V1",
        "cross_projection_binding": "FIXTURE_PROVIDER_QUOTE_PRICE_ROUTER_EXACT_LINEAGE_V1",
        "fixture_record_verification": "EXACT_SEMANTIC_REBUILD_AND_DIGEST_CASCADE_V1",
        "capture_binding": "FIXTURE_RECORD_AS_OF_PROOF_EXACT_CAPTURE_WINDOW_V1",
        "source_artifact_binding": "CANONICAL_FIXTURE_STATE_EXACT_SOURCE_LINEAGE_V1",
        "artifact_path_policy": "SHA256_STORAGE_KEY_PLUS_NORMALIZED_RELATIVE_MANIFEST_V1",
        "artifact_manifest_policy": "EXACT_FILE_SET_DIGEST_AND_RECEIPT_BINDING_V1",
    }


def calculate_contract_sha256() -> str:
    return canonical_sha256(_contract_payload())

# Re-pinned after the P3.0-E1 trust-boundary hardening in PR #353.
EXPECTED_CONTRACT_SHA256 = "f93922d028c40b8a0d4a246f98c99cb9c208a4e83c7b9e6618fb62cd36788f75"


def validate_contract() -> str:
    actual = calculate_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise P30ComparisonEvidenceError("P3.0 comparison evidence contract drifted")
    return actual


__all__ = [
    "AS_OF_PROOF_POLICY_ID", "CANONICAL_AUTHORITY_KEYS", "COMPLETENESS_STATES",
    "EXPECTED_COMPONENTS", "EXPECTED_CONTRACT_SHA256", "FIXTURE_IDENTITY_KEYS",
    "JOIN_STATES", "LegacyEvidenceObserver", "P30ComparisonEvidenceError", "POLICY_ID",
    "PRICE_OUTPUT_KIND", "REQUIRED_CANONICAL_RESPONSIBILITIES", "ROUTER_OUTPUT_KIND",
    "SCHEMA_VERSION", "TIMING_KEYS", "build_as_of_proof", "build_capture_bundle",
    "build_fixture_record", "build_join_receipt", "calculate_contract_sha256",
    "canonical_json_bytes", "canonical_sha256", "fixture_storage_key", "load_json_bytes",
    "normalize_canonical_authority", "normalize_canonical_fixture_state",
    "normalize_price_all_output", "normalize_probability_bundle", "normalize_provider_semantics",
    "normalize_quote_snapshot", "normalize_router_output", "normalize_fixture_identity",
    "normalize_timing", "project_legacy_input", "project_legacy_output", "validate_contract",
    "verify_capture_artifact", "verify_capture_bundle", "write_capture_artifact",
]
