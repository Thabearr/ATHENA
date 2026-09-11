from tests._p3_0_comparison_evidence_support import *  # noqa: F401,F403

def test_contract_is_re_pinned_after_hardening():
    assert evidence.validate_contract() == "f93922d028c40b8a0d4a246f98c99cb9c208a4e83c7b9e6618fb62cd36788f75"


def test_complete_requires_semantic_evidence_and_explicit_asof_proof():
    row = _record()
    assert row["join_receipt"]["join_state"] == "EXACT_SAME_FIXTURE_PROVEN"
    assert row["as_of_proof"]["result"] == "PROVEN"
    assert row["completeness_receipt"] == {"state": "P3_0_CAPTURE_COMPLETE", "missing_reasons": []}


@pytest.mark.parametrize("field", ["probability_bundle", "provider_semantics", "quote_snapshot", "price_all_output", "router_output"])
def test_empty_or_placeholder_canonical_evidence_cannot_be_complete(field):
    assert _record(**{field: {}})["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"
    assert _record(**{field: {"foo": "bar"}})["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"


def test_empty_quote_list_is_valid_observed_price_unavailability_snapshot():
    core = {
        "fixture_identity": FIXTURE,
        "provider_event_id": "100",
        "evaluation_time": CANONICAL,
        "quotes": [],
    }
    snapshot = {**core, "canonical_sha256": evidence.canonical_sha256(core)}
    assert evidence.normalize_quote_snapshot(snapshot)["quotes"] == []


def test_malformed_probability_quote_price_router_identities_cannot_be_complete():
    probability = _probability(); probability["canonical_sha256"] = "0" * 64
    assert _record(probability_bundle=probability)["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"
    quote = _quote(); quote["quotes"][0]["quote_identity_sha256"] = "not-a-sha"
    assert _record(quote_snapshot=quote)["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"
    price = _price(); price["payload_sha256"] = "1" * 64
    assert _record(price_all_output=price)["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"
    router = _router(); router["payload_sha256"] = "2" * 64
    assert _record(router_output=router)["completeness_receipt"]["state"] == "P3_0_CAPTURE_PARTIAL"


def test_authority_requires_exact_reviewed_five_component_shadow_set():
    value = _authority()
    value["resolved_components"].append(copy.deepcopy(value["resolved_components"][0]))
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.normalize_canonical_authority(value)
    value = _authority(); value["resolved_components"][0]["component_id"] = "domain.fake"
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.normalize_canonical_authority(value)
    value = _authority(); value["resolved_components"][0]["artifact_git_blob_sha"] = "A" * 40
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.normalize_canonical_authority(value)
    value = _authority(authority_profile="MAIN")
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.normalize_canonical_authority(value)


def test_asof_is_derived_not_naked_boolean():
    timing = _timing(provider_quote_observed_at=None)
    row = _record(timing=timing)
    assert row["as_of_proof"]["result"] == "UNPROVEN"
    assert "COMMON_AS_OF_UNPROVEN" in row["completeness_receipt"]["missing_reasons"]
    timing = _timing(legacy_evaluation_time="2026-09-30T13:00:00Z")
    row = _record(timing=timing)
    assert row["as_of_proof"]["result"] == "UNPROVEN"
    assert "LEGACY_EVALUATION_TIME_OUTSIDE_CAPTURE_WINDOW" in row["as_of_proof"]["reasons"]


@pytest.mark.parametrize("bad", ["../outside", "..", ".", "/tmp/out", r"C:\temp\out", "a/b", r"a\b"])
def test_fixture_capture_id_cannot_escape_artifact_root(bad):
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.build_fixture_record(
            bad,
            capture_id="capture-20260930-a", capture_started_at=START, capture_completed_at=END,
            legacy_identity=_identity(), canonical_identity=_identity(), timing=_timing(),
            canonical_authority=_authority(),
        )


def test_storage_uses_digest_not_logical_fixture_name():
    row = _record()
    assert len(row["fixture_storage_key"]) == 64
    assert row["fixture_storage_key"] != row["fixture_capture_id"]


def test_possession_is_allowed_but_session_credentials_remain_forbidden():
    projected = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE,
        "decision_status": "ANALYTICAL_CANDIDATE",
        "evidence_report": {"possession": {"home": 55.0, "away": 45.0}},
    })
    assert projected["exported_row"]["evidence_report"]["possession"]["home"] == 55.0
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.project_legacy_input({**_legacy_input(), "current_home_form": {"session_id": "forbidden"}})
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.project_legacy_input({**_legacy_input(), "bookmaker_odds": {"cookie_value": "forbidden"}})
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.project_legacy_input({**_legacy_input(), "current_home_form": {"password": False}})
    # Explicit false safety receipts remain representable without opening the
    # general credential-key exception.
    evidence.canonical_json_bytes({"wager_placed": False, "staking": False})


def test_staking_advice_is_quarantined_from_legacy_projection():
    projected = _legacy_output()
    raw = evidence.canonical_json_bytes(projected).decode()
    assert "kelly_stake_pct" not in raw
    assert "legacy_kelly_stake_pct_before_runtime_gate" not in raw


def test_bundle_replays_nested_semantics_not_only_outer_hashes():
    bundle = _bundle()
    tampered = copy.deepcopy(bundle)
    tampered["fixture_records"][0]["completeness_receipt"] = {
        "state": "P3_0_CAPTURE_COMPLETE",
        "missing_reasons": ["FORGED_REASON"],
    }
    record = tampered["fixture_records"][0]
    record["canonical_sha256"] = evidence.canonical_sha256(
        {key: value for key, value in record.items() if key != "canonical_sha256"}
    )
    tampered["canonical_sha256"] = evidence.canonical_sha256(
        {key: value for key, value in tampered.items() if key != "canonical_sha256"}
    )
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_bundle(tampered)


def test_capture_bundle_rejects_fixture_record_from_different_capture_window():
    foreign = evidence.build_fixture_record(
        "FOTMOB-fixture-100",
        capture_id="capture-foreign",
        capture_started_at=START,
        capture_completed_at=END,
        legacy_identity=_identity(),
        canonical_identity=_identity(),
        timing=_timing(),
        canonical_authority=_authority(),
        legacy_input=_legacy_input(),
        legacy_output=_legacy_output(),
        canonical_fixture_state=_fixture_state(),
        probability_bundle=_probability(),
        provider_semantics=_provider(),
        quote_snapshot=_quote(),
        price_all_output=_price(),
        router_output=_router(),
    )
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        _bundle(records=[foreign])


def test_capture_bundle_requires_exact_source_lineage_for_canonical_fixture_state():
    record = _record()
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.build_capture_bundle(
            repository_commit_sha="c" * 40,
            capture_id="capture-20260930-a",
            capture_started_at=START,
            capture_completed_at=END,
            requested_dates=["20261001"],
            legacy_execution_identity={"path": "AnalysisPipeline.run_pipeline_snapshot"},
            canonical_execution_identity={"path": "Current Shadow Price-All -> Router"},
            authority_state={"main_authority": False, "authority_profile": "SHADOW", "wager_placed": False},
            source_artifacts=[{
                "fixture_identity": FIXTURE,
                "provider_event_id": "100",
                "source_raw_sha256": "0" * 64,
                "source_manifest_sha256": "4" * 64,
                "source_inventory_sha256": "5" * 64,
                "fixture_reconciliation_sha256": "6" * 64,
            }],
            fixture_records=[record],
        )


def test_price_and_router_are_cross_bound_to_exact_quote_and_price_rows():
    price = _price()
    price["payload"]["results"][0]["quote_identity_sha256"] = "0" * 64
    price["payload_sha256"] = _compact_sha(price["payload"])
    row = _record(price_all_output=price)
    assert row["price_all_output"] is None
    assert "PRICE_ALL_SOURCE_LINEAGE_MISMATCH" in row["completeness_receipt"]["missing_reasons"]

    router = _router()
    router["payload"]["opportunities"][0]["price_result"]["model_probability"] = 0.61
    router["payload_sha256"] = _compact_sha(router["payload"])
    row = _record(router_output=router)
    assert row["router_output"] is None
    assert "ROUTER_PRICE_RESULT_LINEAGE_MISMATCH" in row["completeness_receipt"]["missing_reasons"]
