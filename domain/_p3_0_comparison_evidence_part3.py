from domain._p3_0_comparison_evidence_part2 import *  # noqa: F401,F403

def build_as_of_proof(*, capture_id: str, fixture_identity: str, capture_started_at: str,
                      capture_completed_at: str, timing: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_timing(timing)
    start_s, start = _utc_iso(capture_started_at, "capture_started_at")
    end_s, end = _utc_iso(capture_completed_at, "capture_completed_at")
    reasons: list[str] = []
    if end < start:
        reasons.append("CAPTURE_WINDOW_REVERSED")
    parsed: dict[str, datetime | None] = {}
    for key, raw in normalized.items():
        parsed[key] = None if raw is None else _utc_iso(raw, f"timing.{key}")[1]
    required = tuple(TIMING_KEYS)
    for key in required:
        if parsed[key] is None:
            reasons.append(f"MISSING_{key.upper()}")
    kickoff = parsed["kickoff_time"]
    if kickoff is not None:
        for key in TIMING_KEYS - {"kickoff_time"}:
            dt = parsed[key]
            if dt is not None and dt >= kickoff:
                reasons.append(f"{key.upper()}_NOT_PREMATCH")
    for key in TIMING_KEYS - {"kickoff_time"}:
        dt = parsed[key]
        if dt is not None and not (start <= dt <= end):
            reasons.append(f"{key.upper()}_OUTSIDE_CAPTURE_WINDOW")
    quote = parsed["provider_quote_observed_at"]
    probability = parsed["probability_evaluation_time"]
    price = parsed["canonical_price_all_evaluation_time"]
    router = parsed["canonical_router_evaluation_time"]
    if quote is not None and price is not None and quote > price:
        reasons.append("QUOTE_FUTURE_DATED_AT_PRICE_ALL")
    if probability is not None and price is not None and probability > price:
        reasons.append("PROBABILITY_FUTURE_DATED_AT_PRICE_ALL")
    if price is not None and router is not None and price > router:
        reasons.append("PRICE_ALL_AFTER_ROUTER")
    result = "PROVEN" if not reasons else "UNPROVEN"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": AS_OF_PROOF_POLICY_ID,
        "capture_id": capture_id,
        "fixture_identity": fixture_identity,
        "capture_started_at": start_s,
        "capture_completed_at": end_s,
        "timing": normalized,
        "result": result,
        "reasons": sorted(set(reasons)),
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def build_join_receipt(legacy_identity: Mapping[str, Any] | None,
                       canonical_identity: Mapping[str, Any] | None,
                       as_of_proof: Mapping[str, Any]) -> dict[str, Any]:
    legacy = None if legacy_identity is None else normalize_fixture_identity(legacy_identity)
    canonical = None if canonical_identity is None else normalize_fixture_identity(canonical_identity)
    proof = _plain_mapping(as_of_proof, "as_of_proof")
    assert proof is not None
    if legacy is None and canonical is None:
        state, reasons = "EVIDENCE_INCOMPLETE", ["MISSING_FIXTURE_IDENTITIES"]
    elif legacy is None:
        state, reasons = "CANONICAL_ONLY", ["MISSING_LEGACY_FIXTURE_IDENTITY"]
    elif canonical is None:
        state, reasons = "LEGACY_ONLY", ["MISSING_CANONICAL_FIXTURE_IDENTITY"]
    elif legacy["fixture_identity"] != canonical["fixture_identity"]:
        state, reasons = "IDENTITY_AMBIGUOUS", ["FIXTURE_IDENTITY_MISMATCH"]
    elif legacy["fixture_identity_policy"] != canonical["fixture_identity_policy"]:
        state, reasons = "IDENTITY_AMBIGUOUS", ["FIXTURE_IDENTITY_POLICY_MISMATCH"]
    elif legacy["kickoff"] and canonical["kickoff"] and legacy["kickoff"] != canonical["kickoff"]:
        state, reasons = "KICKOFF_MISMATCH", ["KICKOFF_MISMATCH"]
    elif legacy["competition_identity"] and canonical["competition_identity"] and legacy["competition_identity"] != canonical["competition_identity"]:
        state, reasons = "COMPETITION_MISMATCH", ["COMPETITION_MISMATCH"]
    elif proof.get("result") != "PROVEN":
        state, reasons = "AS_OF_NOT_PROVEN", ["COMMON_AS_OF_UNPROVEN", *proof.get("reasons", [])]
    else:
        state, reasons = "EXACT_SAME_FIXTURE_PROVEN", []
    payload = {
        "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
        "join_state": state, "reasons": sorted(set(reasons)),
        "legacy_fixture_identity": legacy, "canonical_fixture_identity": canonical,
        "as_of_proof_sha256": proof.get("canonical_sha256"),
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def _safe_fixture_capture_id(value: Any) -> str:
    if type(value) is not str or _SAFE_CAPTURE_ID.fullmatch(value) is None:
        raise P30ComparisonEvidenceError("fixture_capture_id contains unsafe characters or length")
    if value in {".", ".."} or "/" in value or "\\" in value or PureWindowsPath(value).drive:
        raise P30ComparisonEvidenceError("fixture_capture_id is not a safe logical ID")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise P30ComparisonEvidenceError("fixture_capture_id contains control character")
    return value


def fixture_storage_key(fixture_capture_id: str) -> str:
    logical = _safe_fixture_capture_id(fixture_capture_id)
    return hashlib.sha256(logical.encode("utf-8")).hexdigest()


def _cross_bind_fixture_evidence(
    normalized: dict[str, Any], canonical: Mapping[str, Any] | None, missing: list[str]
) -> None:
    """Bind independently validated projections to one exact canonical source chain."""
    if canonical is None:
        return
    fixture_identity = canonical["fixture_identity"]
    state = normalized.get("canonical_fixture_state")
    provider = normalized.get("provider_semantics")
    quotes = normalized.get("quote_snapshot")
    price = normalized.get("price_all_output")
    router = normalized.get("router_output")

    if state is not None and state["fixture_identity"] != fixture_identity:
        normalized["canonical_fixture_state"] = None
        state = None
        missing.append("CANONICAL_FIXTURE_STATE_IDENTITY_MISMATCH")
    if normalized.get("probability_bundle") is not None and normalized["probability_bundle"]["payload"].get("fixture_identity") != fixture_identity:
        normalized["probability_bundle"] = None
        missing.append("PROBABILITY_FIXTURE_IDENTITY_MISMATCH")
    if price is not None and price["payload"].get("fixture_identity") != fixture_identity:
        normalized["price_all_output"] = None
        price = None
        missing.append("PRICE_ALL_FIXTURE_IDENTITY_MISMATCH")
    if router is not None and router["payload"].get("fixture_identity") != fixture_identity:
        normalized["router_output"] = None
        router = None
        missing.append("ROUTER_FIXTURE_IDENTITY_MISMATCH")

    if state is not None and provider is not None:
        if (
            provider["provider_event_id"] != state["provider_event_id"]
            or provider["source_raw_sha256"] != state["source_raw_sha256"]
            or provider["source_manifest_sha256"] != state["source_manifest_sha256"]
            or provider["source_inventory_sha256"] != state["source_inventory_sha256"]
            or provider["fixture_reconciliation_sha256"] != state["fixture_reconciliation_sha256"]
        ):
            normalized["provider_semantics"] = None
            provider = None
            missing.append("PROVIDER_SEMANTICS_SOURCE_LINEAGE_MISMATCH")

    if state is not None and quotes is not None:
        quote_mismatch = (
            quotes["fixture_identity"] != fixture_identity
            or quotes["provider_event_id"] != state["provider_event_id"]
        )
        if not quote_mismatch:
            for quote in quotes["quotes"]:
                if (
                    quote["source_raw_sha256"] != state["source_raw_sha256"]
                    or quote["source_manifest_sha256"] != state["source_manifest_sha256"]
                    or quote["source_inventory_sha256"] != state["source_inventory_sha256"]
                    or quote["fixture_reconciliation_sha256"] != state["fixture_reconciliation_sha256"]
                ):
                    quote_mismatch = True
                    break
        if quote_mismatch:
            normalized["quote_snapshot"] = None
            quotes = None
            missing.append("QUOTE_SOURCE_LINEAGE_MISMATCH")

    if provider is not None and quotes is not None:
        if any(quote["provider_registry_sha256"] != provider["registry_sha256"] for quote in quotes["quotes"]):
            normalized["quote_snapshot"] = None
            quotes = None
            missing.append("QUOTE_PROVIDER_REGISTRY_MISMATCH")

    if state is not None and price is not None:
        price_mismatch = False
        quote_ids = set() if quotes is None else {
            quote["quote_identity_sha256"] for quote in quotes["quotes"]
        }
        for result in price["payload"]["results"]:
            if result.get("provider_event_id") not in (None, state["provider_event_id"]):
                price_mismatch = True
                break
            for result_key, state_key in (
                ("source_raw_sha256", "source_raw_sha256"),
                ("source_manifest_sha256", "source_manifest_sha256"),
                ("source_inventory_sha256", "source_inventory_sha256"),
            ):
                if result.get(result_key) not in (None, state[state_key]):
                    price_mismatch = True
                    break
            if price_mismatch:
                break
            if provider is not None and result.get("provider_registry_sha256") != provider["registry_sha256"]:
                price_mismatch = True
                break
            quote_id = result.get("quote_identity_sha256")
            if quote_id is not None and quote_id not in quote_ids:
                price_mismatch = True
                break
        if price_mismatch:
            normalized["price_all_output"] = None
            price = None
            missing.append("PRICE_ALL_SOURCE_LINEAGE_MISMATCH")

    if price is not None and router is not None:
        if router["payload"].get("price_all_bundle_sha256") != price["payload_sha256"]:
            normalized["router_output"] = None
            missing.append("ROUTER_PRICE_ALL_IDENTITY_MISMATCH")
            return
        price_rows = {canonical_json_bytes(result) for result in price["payload"]["results"]}
        if any(
            canonical_json_bytes(opportunity["price_result"]) not in price_rows
            for opportunity in router["payload"]["opportunities"]
        ):
            normalized["router_output"] = None
            missing.append("ROUTER_PRICE_RESULT_LINEAGE_MISMATCH")


def build_fixture_record(
    fixture_capture_id: str, *, capture_id: str, capture_started_at: str,
    capture_completed_at: str, legacy_identity: Mapping[str, Any] | None,
    canonical_identity: Mapping[str, Any] | None, timing: Mapping[str, Any],
    canonical_authority: Mapping[str, Any] | None, legacy_input: Mapping[str, Any] | None = None,
    legacy_output: Mapping[str, Any] | None = None, canonical_fixture_state: Mapping[str, Any] | None = None,
    probability_bundle: Mapping[str, Any] | None = None, provider_semantics: Mapping[str, Any] | None = None,
    quote_snapshot: Mapping[str, Any] | None = None, price_all_output: Mapping[str, Any] | None = None,
    router_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # Contract validation is defined by the final split module. Resolve it lazily
    # at call time so this implementation slice remains importable without a
    # forward-name dependency during cumulative module loading.
    from domain._p3_0_comparison_evidence_part4 import validate_contract as _validate_contract
    _validate_contract()
    logical_id = _safe_fixture_capture_id(fixture_capture_id)
    normalized_timing = normalize_timing(timing)
    legacy = None if legacy_identity is None else normalize_fixture_identity(legacy_identity)
    canonical = None if canonical_identity is None else normalize_fixture_identity(canonical_identity)
    fixture_id = (canonical or legacy or {}).get("fixture_identity")
    proof = build_as_of_proof(
        capture_id=capture_id, fixture_identity=fixture_id or "UNKNOWN",
        capture_started_at=capture_started_at, capture_completed_at=capture_completed_at,
        timing=normalized_timing,
    )
    join = build_join_receipt(legacy, canonical, proof)
    normalized: dict[str, Any] = {}
    missing: list[str] = []
    validators = (
        ("canonical_authority", canonical_authority, normalize_canonical_authority, "MISSING_CANONICAL_AUTHORITY"),
        ("legacy_input", legacy_input, project_legacy_input, "MISSING_LEGACY_CONTEXT"),
        ("legacy_output", legacy_output, lambda v: project_legacy_output(v["legacy_analysis_before_runtime_gate"], v["authorized_analysis"], v["exported_row"]), "MISSING_LEGACY_OUTPUT"),
        ("canonical_fixture_state", canonical_fixture_state, normalize_canonical_fixture_state, "MISSING_CANONICAL_FIXTURE_STATE"),
        ("probability_bundle", probability_bundle, normalize_probability_bundle, "MISSING_MARKET_PROBABILITY_BUNDLE"),
        ("provider_semantics", provider_semantics, normalize_provider_semantics, "MISSING_PROVIDER_SEMANTIC_IDENTITY"),
        ("quote_snapshot", quote_snapshot, normalize_quote_snapshot, "MISSING_QUOTE"),
        ("price_all_output", price_all_output, normalize_price_all_output, "MISSING_PRICE_ALL_OUTPUT"),
        ("router_output", router_output, normalize_router_output, "MISSING_ROUTER_OUTPUT"),
    )
    for key, raw, validator, missing_reason in validators:
        if raw is None:
            normalized[key] = None
            missing.append(missing_reason)
            continue
        try:
            normalized[key] = validator(raw)
        except Exception as exc:
            normalized[key] = None
            missing.append(f"INVALID_{key.upper()}")
            if isinstance(exc, P30ComparisonEvidenceError):
                continue
            continue
    if proof["result"] != "PROVEN":
        missing.append("COMMON_AS_OF_UNPROVEN")
    if join["join_state"] != "EXACT_SAME_FIXTURE_PROVEN":
        missing.extend(join["reasons"] or ["FIXTURE_JOIN_UNPROVEN"])
    _cross_bind_fixture_evidence(normalized, canonical, missing)
    missing = sorted(set(missing))
    if join["join_state"] in {"IDENTITY_AMBIGUOUS", "KICKOFF_MISMATCH", "COMPETITION_MISMATCH"}:
        completeness = "P3_0_CAPTURE_UNUSABLE"
    elif missing:
        completeness = "P3_0_CAPTURE_PARTIAL"
    else:
        completeness = "P3_0_CAPTURE_COMPLETE"
    payload = {
        "schema_version": SCHEMA_VERSION, "policy_id": POLICY_ID,
        "fixture_capture_id": logical_id, "fixture_storage_key": fixture_storage_key(logical_id),
        "legacy_fixture_identity": legacy, "canonical_fixture_identity": canonical,
        "timing": normalized_timing, "as_of_proof": proof,
        **normalized, "join_receipt": join,
        "completeness_receipt": {"state": completeness, "missing_reasons": missing},
    }
    payload["canonical_sha256"] = canonical_sha256(payload)
    return payload


def _validate_fixture_record(value: Any) -> dict[str, Any]:
    """Rebuild one record so nested semantics and every digest binding are replayed."""
    item = _plain_mapping(value, "fixture_record")
    assert item is not None
    expected = frozenset({
        "schema_version", "policy_id", "fixture_capture_id", "fixture_storage_key",
        "legacy_fixture_identity", "canonical_fixture_identity", "timing", "as_of_proof",
        "canonical_authority", "legacy_input", "legacy_output", "canonical_fixture_state",
        "probability_bundle", "provider_semantics", "quote_snapshot", "price_all_output",
        "router_output", "join_receipt", "completeness_receipt", "canonical_sha256",
    })
    _exact_keys(item, expected, "fixture_record")
    if item["schema_version"] != SCHEMA_VERSION or item["policy_id"] != POLICY_ID:
        raise P30ComparisonEvidenceError("fixture record policy identity drifted")
    if item["fixture_storage_key"] != fixture_storage_key(item["fixture_capture_id"]):
        raise P30ComparisonEvidenceError("fixture storage identity drifted")
    proof = item.get("as_of_proof")
    if type(proof) is not dict:
        raise P30ComparisonEvidenceError("fixture record omitted as-of proof")
    for key in ("capture_id", "capture_started_at", "capture_completed_at"):
        if key not in proof:
            raise P30ComparisonEvidenceError(f"fixture as-of proof omitted {key}")
    rebuilt = build_fixture_record(
        item["fixture_capture_id"],
        capture_id=proof["capture_id"],
        capture_started_at=proof["capture_started_at"],
        capture_completed_at=proof["capture_completed_at"],
        legacy_identity=item["legacy_fixture_identity"],
        canonical_identity=item["canonical_fixture_identity"],
        timing=item["timing"],
        canonical_authority=item["canonical_authority"],
        legacy_input=item["legacy_input"],
        legacy_output=item["legacy_output"],
        canonical_fixture_state=item["canonical_fixture_state"],
        probability_bundle=item["probability_bundle"],
        provider_semantics=item["provider_semantics"],
        quote_snapshot=item["quote_snapshot"],
        price_all_output=item["price_all_output"],
        router_output=item["router_output"],
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(item):
        raise P30ComparisonEvidenceError(
            "fixture record differs from exact semantic reconstruction"
        )
    return rebuilt


def _normalize_source_artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "source_artifact")
    assert item is not None
    expected = frozenset({
        "fixture_identity", "provider_event_id", "source_raw_sha256",
        "source_manifest_sha256", "source_inventory_sha256",
        "fixture_reconciliation_sha256",
    })
    _exact_keys(item, expected, "source_artifact")
    for key in ("fixture_identity", "provider_event_id"):
        if type(item[key]) is not str or not item[key]:
            raise P30ComparisonEvidenceError(f"source_artifact.{key} is required")
    for key in (
        "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256",
        "fixture_reconciliation_sha256",
    ):
        item[key] = _sha64(item[key], f"source_artifact.{key}")
    return item



# Internal cumulative export for the next implementation slice.
__all__ = tuple(name for name in globals() if not name.startswith("__"))