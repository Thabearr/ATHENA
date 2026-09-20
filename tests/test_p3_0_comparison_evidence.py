from tests._p3_0_comparison_evidence_support import *  # noqa: F401,F403

def test_contract_is_re_pinned_after_hardening():
    assert evidence.validate_contract() == "d7bb3dac550ab662374be6a7aa6c6c17870ed2925f0fa155dae8d24e07c713b7"


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
    # general credential-key exception. The canonical probability contract
    # includes authority.wager=false, so that exact false receipt is admitted.
    evidence.canonical_json_bytes({"wager": False, "wager_placed": False, "staking": False})
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.canonical_json_bytes({"wager": True})


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


def test_contract_payload_pins_publication_envelope_and_taxonomy():
    assert evidence.P3_CAPTURE_ARTIFACT_ENVELOPE_RELATIVE == "artifacts/p3-0-comparison-evidence"
    assert evidence.P3_CAPTURE_IMMUTABLE_CHILD_RELATIVE == "artifacts/p3-0-comparison-evidence/capture"
    assert evidence.P3_CAPTURE_PUBLICATION_POLICY_ID == "P3_E1_READINESS_ENVELOPE_IMMUTABLE_CAPTURE_CHILD_V1"
    assert evidence.P3_PARTIAL_CORPUS_PROCESS_POLICY_ID == "P3_E1_PARTIAL_CORPUS_NONZERO_IMMUTABLE_V1"
    assert evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID == "P3_E1_FAILURE_RECEIPT_ONLY_WHEN_CAPTURE_DESTINATION_ABSENT_V1"
    assert evidence.P3_CAPTURE_STAGE_FAILURE_TAXONOMY == frozenset({
        "LEGACY_EVIDENCE_OBSERVER_INCOMPLETE",
        "PAIRED_CAPTURE_PARTIAL",
        "CAPTURE_ARTIFACT_PUBLICATION_FAILED",
    })
    payload = evidence._contract_payload()
    assert payload["capture_artifact_envelope_relative"] == "artifacts/p3-0-comparison-evidence"
    assert payload["capture_immutable_child_relative"] == "artifacts/p3-0-comparison-evidence/capture"
    assert payload["capture_publication_policy_id"] == "P3_E1_READINESS_ENVELOPE_IMMUTABLE_CAPTURE_CHILD_V1"
    assert payload["partial_corpus_process_policy_id"] == "P3_E1_PARTIAL_CORPUS_NONZERO_IMMUTABLE_V1"
    assert payload["failure_receipt_destination_policy_id"] == "P3_E1_FAILURE_RECEIPT_ONLY_WHEN_CAPTURE_DESTINATION_ABSENT_V1"
    assert payload["capture_stage_failure_taxonomy"] == [
        "CAPTURE_ARTIFACT_PUBLICATION_FAILED",
        "LEGACY_EVIDENCE_OBSERVER_INCOMPLETE",
        "PAIRED_CAPTURE_PARTIAL",
    ]


def test_legacy_numpy_json_normalization_policy_and_rules():
    assert evidence.LEGACY_NUMPY_JSON_NORMALIZATION_POLICY_ID == "P3_LEGACY_NUMPY_JSON_NORMALIZATION_V1"
    assert evidence.LEGACY_NUMPY_JSON_NORMALIZATION_RULES == (
        "NUMPY_GENERIC_ITEM_TO_CANONICAL_JSON_RECURSIVE",
        "NUMPY_NDARRAY_TOLIST_TO_CANONICAL_JSON_RECURSIVE",
        "DUCK_TYPED_TOLIST_ITEM_FORBIDDEN",
        "PYTHON_NON_JSON_CONTAINERS_FORBIDDEN",
        "NONFINITE_NUMBERS_FORBIDDEN",
    )
    payload = evidence._contract_payload()
    assert payload["legacy_numpy_json_normalization_policy_id"] == "P3_LEGACY_NUMPY_JSON_NORMALIZATION_V1"
    assert payload["legacy_numpy_json_normalization_rules"] == list(evidence.LEGACY_NUMPY_JSON_NORMALIZATION_RULES)


def test_legacy_projection_normalizes_numpy_scalars_and_arrays():
    import numpy as np

    # 1. Exported row containing numpy scalars and arrays
    exported = {
        "fixture_id": np.int64(5749683),
        "decision_status": "ANALYTICAL_CANDIDATE",
        "risk_score": np.float64(0.75),
        "bookmaker_odds": np.float32(2.50),
        "viable_markets": np.array(["1X", "OVER_15"]),
        "evidence_report": {
            "probabilities": {
                "home_win": np.float64(0.55),
                "draw": np.float64(0.25),
                "away_win": np.float64(0.20),
            },
            "flags": [np.bool_(True), np.bool_(False)],
            "counts": np.array([np.int32(1), np.int32(2)]),
            "matrix": np.array([[np.float64(1.1), np.float64(2.2)], [np.float64(3.3), np.float64(4.4)]]),
            "zero_dim": np.array(np.float64(9.9)),
        },
    }
    projected = evidence.project_legacy_output(_analysis(), _analysis(), exported)
    row = projected["exported_row"]

    assert row["fixture_id"] == 5749683
    assert type(row["fixture_id"]) is int
    assert row["risk_score"] == 0.75
    assert type(row["risk_score"]) is float
    assert row["bookmaker_odds"] == float(np.float32(2.50))
    assert type(row["bookmaker_odds"]) is float
    assert row["viable_markets"] == ["1X", "OVER_15"]
    assert type(row["viable_markets"]) is list
    report = row["evidence_report"]
    assert report["probabilities"]["home_win"] == 0.55
    assert type(report["probabilities"]["home_win"]) is float
    assert report["flags"] == [True, False]
    assert type(report["flags"][0]) is bool
    assert report["counts"] == [1, 2]
    assert type(report["counts"][0]) is int
    assert report["matrix"] == [[1.1, 2.2], [3.3, 4.4]]
    assert type(report["matrix"]) is list
    assert report["zero_dim"] == 9.9
    assert type(report["zero_dim"]) is float

    # 2. Input context containing numpy scalars
    legacy_inp = {
        **_legacy_input(),
        "fixture_id": np.int64(5749683),
        "current_home_form": {"points": np.int64(12), "avg_goals": np.float64(1.8)},
    }
    projected_inp = evidence.project_legacy_input(legacy_inp)
    assert projected_inp["fixture_id"] == 5749683
    assert type(projected_inp["fixture_id"]) is int
    assert projected_inp["current_home_form"]["points"] == 12
    assert type(projected_inp["current_home_form"]["points"]) is int
    assert projected_inp["current_home_form"]["avg_goals"] == 1.8
    assert type(projected_inp["current_home_form"]["avg_goals"]) is float

    # 3. Canonical JSON encoding of projected outputs succeeds
    raw_bytes = evidence.canonical_json_bytes(projected)
    assert isinstance(raw_bytes, bytes)


def test_legacy_numpy_and_containers_fail_closed_adversarial_suite():
    import numpy as np

    # Point 1: np.float64 normalizes to float (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.float64(3.14)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is float

    # Point 2: np.float32 normalizes to float (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.float32(2.71)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is float

    # Point 3: np.int64 normalizes to int (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.int64(42)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is int

    # Point 4: np.int32 normalizes to int (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.int32(7)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is int

    # Point 5: np.bool_ normalizes to bool (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.bool_(True)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is bool

    # Point 6: np.ndarray (1D) normalizes to list (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.array([1, 2, 3])},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is list

    # Point 7: np.ndarray (2D) normalizes to nested list (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.array([[1, 2], [3, 4]])},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is list
    assert type(res["exported_row"]["evidence_report"]["val"][0]) is list

    # Point 8: np.ndarray (0D) normalizes to scalar (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.array(100)},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is int

    # Point 9: np.nan rejected fail-closed in scalar and array
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-finite number"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.nan},
        })
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-finite number"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.array([1.0, np.nan])},
        })

    # Point 10: np.inf rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-finite number"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.inf},
        })

    # Point 11: -np.inf rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-finite number"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": -np.inf},
        })

    # Point 12: np.complex128 rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.complex128(1 + 2j)},
        })

    # Point 13: np.complex64 rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.complex64(1 + 2j)},
        })

    # Point 14: Duck-typed object with .item() rejected without calling .item()
    class SentinelItem:
        called = False
        def item(self):
            SentinelItem.called = True
            return 1.0

    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": SentinelItem()},
        })
    assert SentinelItem.called is False

    # Point 15: Duck-typed object with .tolist() rejected without calling .tolist()
    class SentinelToList:
        called = False
        def tolist(self):
            SentinelToList.called = True
            return [1.0]

    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": SentinelToList()},
        })
    assert SentinelToList.called is False

    # Point 16: Python tuple rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": (1, 2)},
        })

    # Point 17: Python set rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": {1, 2}},
        })

    # Point 18: Python frozenset rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": frozenset([1, 2])},
        })

    # Point 19: Nested tuple inside list rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": [1, (2, 3)]},
        })

    # Point 20: Nested set inside dict rejected fail-closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="non-JSON value"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": {"inner_set": {"a", "b"}}},
        })

    # Point 21: Sensitive credential key rejected fail-closed even if nested in object array
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="sensitive evidence key is forbidden"):
        evidence.project_legacy_output(_analysis(), _analysis(), {
            "fixture_id": FIXTURE, "decision_status": "NO_BET",
            "evidence_report": {"val": np.array([{"password": "secret"}], dtype=object)},
        })

    # Point 22: Staking keys and runtime safety keys quarantined properly
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "kelly_stake_pct": 0.05,
        "runtime_authorization_state": "BLOCKED",
        "runtime_authorization_reasons": ["test"],
        "evidence_report": {
            "kelly_stake_pct": 0.05,
            "legacy_kelly_stake_pct_before_runtime_gate": 0.05,
            "runtime_authorization_state": "BLOCKED",
            "runtime_authorization_reasons": ["test"],
            "clean_metric": 42,
        },
    })
    raw_str = evidence.canonical_json_bytes(res).decode()
    assert "kelly_stake_pct" not in raw_str
    assert "legacy_kelly_stake_pct_before_runtime_gate" not in raw_str
    assert "runtime_authorization_state" not in raw_str
    assert "runtime_authorization_reasons" not in raw_str
    assert res["exported_row"]["evidence_report"]["clean_metric"] == 42

    # Point 23: np.str_ normalizes to str (positive verification)
    res = evidence.project_legacy_output(_analysis(), _analysis(), {
        "fixture_id": FIXTURE, "decision_status": "NO_BET",
        "evidence_report": {"val": np.str_("string_val")},
    })
    assert type(res["exported_row"]["evidence_report"]["val"]) is str
    assert res["exported_row"]["evidence_report"]["val"] == "string_val"


def test_readiness_check_i_normalization_coverage():
    from scripts.verify_p3_0_e1_live_readiness import check_i_pre_router_pipeline_readiness
    root = Path(__file__).resolve().parents[1]
    res = check_i_pre_router_pipeline_readiness(root)
    assert res["status"] == "PASSED"
    assert res["legacy_numpy_normalization_verified"] is True
    assert res["legacy_numpy_normalization_readiness_assertions"] == [
        "NP_FLOAT64_NORMALIZED",
        "DUCK_ITEM_REJECTED_WITHOUT_INVOCATION",
        "DUCK_TOLIST_REJECTED_WITHOUT_INVOCATION",
        "TUPLE_REJECTED",
        "SET_REJECTED",
        "FROZENSET_REJECTED",
        "NONFINITE_REJECTED",
    ]
