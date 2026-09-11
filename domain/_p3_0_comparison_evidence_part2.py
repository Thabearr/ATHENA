from domain._p3_0_comparison_evidence_part1 import *  # noqa: F401,F403

def normalize_fixture_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "fixture_identity")
    assert item is not None
    _exact_keys(item, FIXTURE_IDENTITY_KEYS, "fixture_identity")
    for key in FIXTURE_IDENTITY_KEYS - {"home_source_id", "away_source_id"}:
        if item[key] is not None and type(item[key]) is not str:
            raise P30ComparisonEvidenceError(f"fixture_identity.{key} must be string or null")
    for key in ("home_source_id", "away_source_id"):
        if item[key] is not None and type(item[key]) not in (str, int):
            raise P30ComparisonEvidenceError(f"fixture_identity.{key} must be string, integer, or null")
    if type(item["fixture_identity"]) is not str or not item["fixture_identity"].strip():
        raise P30ComparisonEvidenceError("fixture_identity.fixture_identity is required")
    if type(item["fixture_identity_policy"]) is not str or not item["fixture_identity_policy"].strip():
        raise P30ComparisonEvidenceError("fixture identity policy is required")
    if item["kickoff"] is not None:
        item["kickoff"] = _utc_iso(item["kickoff"], "fixture_identity.kickoff")[0]
    for key in ("fixture_source_artifact_sha256", "fixture_source_manifest_sha256"):
        if item[key] is not None:
            item[key] = _sha64(item[key], f"fixture_identity.{key}")
    return item


def normalize_timing(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "timing")
    assert item is not None
    _exact_keys(item, TIMING_KEYS, "timing")
    for key in TIMING_KEYS:
        if item[key] is not None:
            item[key] = _utc_iso(item[key], f"timing.{key}")[0]
    return item


def normalize_canonical_authority(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "canonical_authority")
    assert item is not None
    _exact_keys(item, CANONICAL_AUTHORITY_KEYS, "canonical_authority")
    if item["authority_profile"] != "SHADOW":
        raise P30ComparisonEvidenceError("canonical evidence must remain SHADOW-only")
    if item["canonical_core_policy_id"] != EXPECTED_CANONICAL_CORE_POLICY_ID:
        raise P30ComparisonEvidenceError("canonical core policy identity drifted")
    for key in ("canonical_core_contract_sha256", "authority_manifest_sha256", "registry_canonical_sha256"):
        item[key] = _sha64(item[key], f"canonical_authority.{key}")
    if item["canonical_core_contract_sha256"] != EXPECTED_CANONICAL_CORE_CONTRACT_SHA256:
        raise P30ComparisonEvidenceError("canonical core contract identity drifted")
    components = item["resolved_components"]
    if type(components) is not list or len(components) != len(EXPECTED_COMPONENTS):
        raise P30ComparisonEvidenceError("canonical authority must contain exactly five components")
    by_responsibility: dict[str, dict[str, Any]] = {}
    required = {"responsibility_id", "component_id", "contract_sha256", "artifact_git_blob_sha", "allowed_profiles", "main_authority"}
    for raw in components:
        if type(raw) is not dict or set(raw) != required:
            raise P30ComparisonEvidenceError("canonical authority component fields drifted")
        rid = raw["responsibility_id"]
        if rid in by_responsibility:
            raise P30ComparisonEvidenceError("duplicate canonical responsibility")
        if rid not in EXPECTED_COMPONENTS or raw["component_id"] != EXPECTED_COMPONENTS[rid]:
            raise P30ComparisonEvidenceError("canonical authority component owner drifted")
        if raw["allowed_profiles"] != ["SHADOW"] or raw["main_authority"] is not False:
            raise P30ComparisonEvidenceError("canonical authority escaped SHADOW-only state")
        checked = dict(raw)
        checked["contract_sha256"] = _sha64(raw["contract_sha256"], "component.contract_sha256")
        checked["artifact_git_blob_sha"] = _sha40(raw["artifact_git_blob_sha"], "component.artifact_git_blob_sha")
        expected_contract, expected_blob = EXPECTED_COMPONENT_IDENTITIES[rid]
        if checked["contract_sha256"] != expected_contract or checked["artifact_git_blob_sha"] != expected_blob:
            raise P30ComparisonEvidenceError("canonical component contract/artifact identity drifted")
        by_responsibility[rid] = checked
    if set(by_responsibility) != REQUIRED_CANONICAL_RESPONSIBILITIES:
        raise P30ComparisonEvidenceError("canonical responsibility set drifted")
    item["resolved_components"] = [by_responsibility[key] for key in sorted(by_responsibility)]
    return item


def normalize_probability_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "probability_bundle")
    assert item is not None
    _exact_keys(item, frozenset({"policy_id", "canonical_sha256", "payload"}), "probability_bundle")
    item["canonical_sha256"] = _sha64(item["canonical_sha256"], "probability_bundle.canonical_sha256")
    try:
        from domain.market_probabilities import MarketProbabilityBundle, canonical_sha256 as probability_sha
        rebuilt = MarketProbabilityBundle.from_dict(item["payload"])
    except Exception as exc:
        raise P30ComparisonEvidenceError("MarketProbabilityBundle projection is invalid") from exc
    if item["policy_id"] != item["payload"].get("policy_id"):
        raise P30ComparisonEvidenceError("probability bundle policy identity drifted")
    if probability_sha(rebuilt) != item["canonical_sha256"]:
        raise P30ComparisonEvidenceError("probability bundle canonical identity drifted")
    item["payload"] = rebuilt.to_dict()
    return item


def normalize_provider_semantics(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "provider_semantics")
    assert item is not None
    expected = frozenset({
        "canonical_contract_sha256", "registry_sha256", "registry_policy_id",
        "registry_evaluation_time", "provider_event_id", "source_raw_sha256",
        "source_manifest_sha256", "source_inventory_sha256",
        "fixture_reconciliation_sha256",
    })
    _exact_keys(item, expected, "provider_semantics")
    for key in ("canonical_contract_sha256", "registry_sha256", "source_raw_sha256",
                "source_manifest_sha256", "source_inventory_sha256", "fixture_reconciliation_sha256"):
        item[key] = _sha64(item[key], f"provider_semantics.{key}")
    if any(type(item[key]) is not str or not item[key] for key in ("registry_policy_id", "provider_event_id")):
        raise P30ComparisonEvidenceError("provider semantics text identity is required")
    if item["canonical_contract_sha256"] != EXPECTED_PROVIDER_SEMANTICS_CONTRACT_SHA256:
        raise P30ComparisonEvidenceError("provider semantics canonical contract drifted")
    if item["registry_policy_id"] != EXPECTED_PROVIDER_REGISTRY_POLICY_ID:
        raise P30ComparisonEvidenceError("provider semantics registry policy drifted")
    item["registry_evaluation_time"] = _utc_iso(item["registry_evaluation_time"], "provider semantics evaluation")[0]
    return item


def normalize_quote_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "quote_snapshot")
    assert item is not None
    _exact_keys(
        item,
        frozenset({"fixture_identity", "provider_event_id", "evaluation_time", "quotes", "canonical_sha256"}),
        "quote_snapshot",
    )
    if type(item["fixture_identity"]) is not str or not item["fixture_identity"]:
        raise P30ComparisonEvidenceError("quote snapshot fixture identity is required")
    if type(item["provider_event_id"]) is not str or not item["provider_event_id"]:
        raise P30ComparisonEvidenceError("quote snapshot provider event identity is required")
    item["evaluation_time"] = _utc_iso(item["evaluation_time"], "quote_snapshot.evaluation_time")[0]
    item["canonical_sha256"] = _sha64(item["canonical_sha256"], "quote_snapshot.canonical_sha256")
    if type(item["quotes"]) is not list:
        raise P30ComparisonEvidenceError("quote snapshot quotes must be an exact list")
    quote_payload_keys = frozenset({
        "fixture_identity", "provider_event_id", "market_id", "outcome_id", "line",
        "provider_line", "provider_market_id", "provider_market_name", "provider_specifier",
        "provider_outcome_id", "provider_outcome_name", "odds_raw", "decimal_odds",
        "observed_at", "kickoff_utc", "source_raw_sha256", "source_manifest_sha256",
        "source_inventory_sha256", "provider_semantic_status", "provider_registry_sha256",
        "provider_observation_sha256", "fixture_reconciliation_sha256",
        "current_mapping_rebind_sha256", "bridge_bundle_sha256", "bookable",
    })
    expected_quote_keys = quote_payload_keys | {"quote_identity_sha256"}
    seen: set[str] = set()
    normalized_quotes: list[dict[str, Any]] = []
    for quote in item["quotes"]:
        if type(quote) is not dict or set(quote) != expected_quote_keys:
            raise P30ComparisonEvidenceError("quote snapshot row fields drifted")
        q = _plain_mapping(quote, "quote_snapshot.quote")
        assert q is not None
        qid = _sha64(q["quote_identity_sha256"], "quote.quote_identity_sha256")
        if qid in seen:
            raise P30ComparisonEvidenceError("duplicate exact quote identity")
        seen.add(qid)
        if q["fixture_identity"] != item["fixture_identity"] or q["provider_event_id"] != item["provider_event_id"]:
            raise P30ComparisonEvidenceError("quote snapshot fixture/event identity drifted")
        for key in ("market_id", "outcome_id", "provider_market_id", "provider_market_name", "provider_outcome_id", "provider_outcome_name", "odds_raw", "provider_semantic_status"):
            if type(q[key]) is not str or not q[key]:
                raise P30ComparisonEvidenceError(f"quote.{key} is required")
        for key in ("provider_line", "provider_specifier"):
            if q[key] is not None and (type(q[key]) is not str or not q[key]):
                raise P30ComparisonEvidenceError(f"quote.{key} must be non-empty string or null")
        if q["line"] is not None and (
            isinstance(q["line"], bool) or not isinstance(q["line"], (int, float))
            or not math.isfinite(float(q["line"]))
        ):
            raise P30ComparisonEvidenceError("quote line is invalid")
        for key in (
            "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256",
            "provider_registry_sha256", "provider_observation_sha256",
            "fixture_reconciliation_sha256",
        ):
            q[key] = _sha64(q[key], f"quote.{key}")
        for key in ("current_mapping_rebind_sha256", "bridge_bundle_sha256"):
            if q[key] is not None:
                q[key] = _sha64(q[key], f"quote.{key}")
        q["observed_at"] = _utc_iso(q["observed_at"], "quote.observed_at")[0]
        q["kickoff_utc"] = _utc_iso(q["kickoff_utc"], "quote.kickoff_utc")[0]
        if (
            type(q["decimal_odds"]) not in (int, float)
            or isinstance(q["decimal_odds"], bool)
            or not math.isfinite(float(q["decimal_odds"]))
            or float(q["decimal_odds"]) <= 1.0
        ):
            raise P30ComparisonEvidenceError("quote decimal odds are invalid")
        if type(q["bookable"]) is not bool:
            raise P30ComparisonEvidenceError("quote bookable flag is invalid")
        source_payload = {key: q[key] for key in quote_payload_keys}
        if _compact_sha256(source_payload) != qid:
            raise P30ComparisonEvidenceError("exact quote identity differs from projected source payload")
        normalized_quotes.append(q)
    normalized_quotes.sort(key=lambda row: row["quote_identity_sha256"])
    item["quotes"] = normalized_quotes
    expected_hash = canonical_sha256(
        {key: item[key] for key in ("fixture_identity", "provider_event_id", "evaluation_time", "quotes")}
    )
    if item["canonical_sha256"] != expected_hash:
        raise P30ComparisonEvidenceError("quote snapshot canonical identity drifted")
    return item


def _normalize_compatibility_output(value: Mapping[str, Any], *, router: bool) -> dict[str, Any]:
    label = "router_output" if router else "price_all_output"
    item = _plain_mapping(value, label)
    assert item is not None
    expected = frozenset({"owner_responsibility_id", "owner_component_id", "payload_kind", "payload_sha256", "payload"})
    _exact_keys(item, expected, label)
    responsibility = "market_router" if router else "price_all_and_de_vig"
    component = EXPECTED_COMPONENTS[responsibility]
    kind = ROUTER_OUTPUT_KIND if router else PRICE_OUTPUT_KIND
    if item["owner_responsibility_id"] != responsibility or item["owner_component_id"] != component or item["payload_kind"] != kind:
        raise P30ComparisonEvidenceError(f"{label} canonical owner binding drifted")
    item["payload_sha256"] = _sha64(item["payload_sha256"], f"{label}.payload_sha256")
    payload = item["payload"]
    if type(payload) is not dict:
        raise P30ComparisonEvidenceError(f"{label}.payload must be object")
    required = (
        {"schema_version", "dataset_name", "fixture_identity", "evaluation_time", "results", "authority", "wager_placed"}
        if not router else
        {"schema_version", "dataset_name", "fixture_identity", "status", "opportunities", "price_all_bundle_sha256", "router_policy_id", "authority", "wager_placed"}
    )
    if not required.issubset(payload) or payload.get("dataset_name") != SHADOW_PRICE_DATASET_NAME or payload.get("wager_placed") is not False:
        raise P30ComparisonEvidenceError(f"{label} compatibility payload identity drifted")
    if router:
        _sha64(payload["price_all_bundle_sha256"], "router price_all_bundle_sha256")
        if type(payload["opportunities"]) is not list or not payload["opportunities"]:
            raise P30ComparisonEvidenceError("router output contains no opportunities")
        opportunity_ids: set[str] = set()
        for opportunity in payload["opportunities"]:
            if type(opportunity) is not dict or not {"opportunity_id", "price_result", "eligibility", "rejection_reasons"}.issubset(opportunity):
                raise P30ComparisonEvidenceError("router opportunity lacks required reviewed fields")
            opportunity_id = _sha64(opportunity["opportunity_id"], "router opportunity_id")
            if opportunity_id in opportunity_ids:
                raise P30ComparisonEvidenceError("duplicate router opportunity identity")
            opportunity_ids.add(opportunity_id)
            if type(opportunity["price_result"]) is not dict or opportunity["price_result"].get("fixture_identity") != payload["fixture_identity"]:
                raise P30ComparisonEvidenceError("router opportunity price-result identity drifted")
            if type(opportunity["eligibility"]) is not str or type(opportunity["rejection_reasons"]) is not list:
                raise P30ComparisonEvidenceError("router opportunity eligibility fields drifted")
        for selected_key in ("selected_opportunity_id", "runner_up_opportunity_id", "strongest_rejected_opportunity_id", "value_first_selected_opportunity_id", "value_first_runner_up_opportunity_id", "value_first_counterfactual_opportunity_id"):
            selected = payload.get(selected_key)
            if selected is not None and selected not in opportunity_ids:
                raise P30ComparisonEvidenceError(f"router {selected_key} is not an observed opportunity")
    else:
        payload["evaluation_time"] = _utc_iso(payload["evaluation_time"], "price-all evaluation time")[0]
        if type(payload["results"]) is not list or not payload["results"]:
            raise P30ComparisonEvidenceError("price-all output contains no results")
        required_result = {"fixture_identity", "market_id", "outcome_id", "disposition", "model_probability", "decimal_odds", "quote_identity_sha256", "provider_event_id", "prc_scan_sha256", "prc_assessment_sha256", "provider_registry_sha256", "fixture_reconciliation_sha256", "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256"}
        for result in payload["results"]:
            if type(result) is not dict or not required_result.issubset(result):
                raise P30ComparisonEvidenceError("price-all result lacks required reviewed evidence")
            if result["fixture_identity"] != payload["fixture_identity"]:
                raise P30ComparisonEvidenceError("price-all result fixture identity drifted")
            for sha_key in ("prc_scan_sha256", "prc_assessment_sha256", "provider_registry_sha256", "fixture_reconciliation_sha256"):
                _sha64(result[sha_key], f"price-all result {sha_key}")
            for optional_sha in ("quote_identity_sha256", "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256"):
                if result[optional_sha] is not None:
                    _sha64(result[optional_sha], f"price-all result {optional_sha}")
    if _compact_sha256(payload) != item["payload_sha256"]:
        raise P30ComparisonEvidenceError(f"{label} payload digest drifted")
    return item


def normalize_price_all_output(value: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_compatibility_output(value, router=False)


def normalize_router_output(value: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_compatibility_output(value, router=True)


def normalize_canonical_fixture_state(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _plain_mapping(value, "canonical_fixture_state")
    assert item is not None
    required = {"fixture_identity", "provider_event_id", "home_team", "away_team", "competition", "kickoff_utc", "source_observed_at", "fixture_reconciliation_sha256", "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256"}
    if set(item) != required:
        raise P30ComparisonEvidenceError("canonical fixture-state fields drifted")
    for key in ("fixture_identity", "provider_event_id", "home_team", "away_team", "competition"):
        if type(item[key]) is not str or not item[key]:
            raise P30ComparisonEvidenceError(f"canonical_fixture_state.{key} is required")
    for key in ("kickoff_utc", "source_observed_at"):
        item[key] = _utc_iso(item[key], f"canonical_fixture_state.{key}")[0]
    for key in ("fixture_reconciliation_sha256", "source_raw_sha256", "source_manifest_sha256", "source_inventory_sha256"):
        item[key] = _sha64(item[key], f"canonical_fixture_state.{key}")
    return item



# Internal cumulative export for the next implementation slice.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
