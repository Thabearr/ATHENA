from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

import domain.fotmob_reviewed_match_details_probability_model_readiness as module
from domain.fixture_intelligence import IntelligenceCategory
from domain.fixture_model_features import (
    FixtureModelFeatureSnapshot,
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureStatus,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    canonical_reviewed_match_details_model_feature_handoff_bytes,
)
from domain.fotmob_reviewed_match_details_probability_model_readiness import (
    DATASET_NAME,
    READINESS_SCOPE,
    REVIEWED_MISSING_INPUT_POLICY,
    SCHEMA_VERSION,
    DeclaredInputStatus,
    FotMobReviewedMatchDetailsProbabilityModelReadinessError,
    ProbabilityReadinessReason,
    ProbabilityReadinessStatus,
    ReviewedMatchDetailsProbabilityModelReadiness,
    build_reviewed_match_details_probability_model_readiness,
    canonical_model_status_registry_view_bytes,
    canonical_reviewed_match_details_probability_model_readiness_bytes,
    revalidate_reviewed_match_details_probability_model_readiness,
    sha256_model_status_registry_view,
    sha256_reviewed_match_details_probability_model_readiness,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.markets import MarketId
from domain.model_status import (
    MODEL_STATUS_REGISTRY,
    MarketModelStatus,
    MissingInputPolicy,
    ModelStatus,
)


UTC = datetime.timezone.utc


def _pr66_helper():
    path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_model_feature_handoff.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr67_pr66_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #66 helper")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _chain_kwargs(pr66_result=None):
    helper = _pr66_helper()
    if pr66_result is None:
        handoff, handoff_bytes, pr65_result = helper._handoff()
    else:
        handoff, handoff_bytes, pr65_result = helper._handoff(pr66_result)
    artifact, artifact_bytes, bundle = pr65_result
    inputs, candidate, candidate_bytes, admission, admission_bytes = bundle
    return {
        "materialization_inputs": inputs,
        "candidate_set": candidate,
        "candidate_set_bytes": candidate_bytes,
        "admission": admission,
        "admission_bytes": admission_bytes,
        "artifact": artifact,
        "artifact_bytes": artifact_bytes,
        "handoff": handoff,
        "handoff_bytes": handoff_bytes,
    }


def _build(pr66_result=None):
    kwargs = _chain_kwargs(pr66_result)
    readiness = build_reviewed_match_details_probability_model_readiness(**kwargs)
    readiness_bytes = canonical_reviewed_match_details_probability_model_readiness_bytes(
        readiness
    )
    return readiness, readiness_bytes, kwargs


def _revalidate(readiness, readiness_bytes, kwargs):
    return revalidate_reviewed_match_details_probability_model_readiness(
        **kwargs,
        readiness=readiness,
        readiness_bytes=readiness_bytes,
    )


def _market(readiness, market_id):
    return next(item for item in readiness.market_readiness if item.market_id is market_id)


def _custom_full_available_pr66_result():
    pr66 = _pr66_helper()
    pr65 = pr66._pr65_helper()
    pr63 = pr65._pr64_helper()._pr63_helper()
    pr62 = pr63._pr62_helper()
    pr60 = pr62._pr61_helper()._pr60_helper()
    pr58 = pr60._pr58_helper()

    values = {
        "away_elo": 1490,
        "away_form": 0.55,
        "fatigue": 0.20,
        "home_elo": 1510,
        "home_form": 0.65,
        "live_data_freshness": 1.0,
    }
    bindings = {
        "away_elo": IntelligenceCategory.PERFORMANCE,
        "away_form": IntelligenceCategory.FORM,
        "fatigue": IntelligenceCategory.SCHEDULE_LOAD,
        "home_elo": IntelligenceCategory.PERFORMANCE,
        "home_form": IntelligenceCategory.FORM,
        "live_data_freshness": IntelligenceCategory.FIXTURE_CONTEXT,
    }
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    approved = tuple(
        pr58._approved(
            f"/{field}",
            JsonValueKind.NUMBER if isinstance(value, float) else JsonValueKind.INTEGER,
            bindings[field],
            field,
        )
        for field, value in sorted(values.items())
    )
    (
        policy,
        policy_bytes,
        qualification,
        qualification_bytes,
        fact_bundle,
        fact_bytes,
        chain,
    ) = pr60._build_policy(raw, approved)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    inputs = {
        "raw": raw,
        "policy": policy,
        "policy_bytes": policy_bytes,
        "qualification": qualification,
        "qualification_bytes": qualification_bytes,
        "fact_bundle": fact_bundle,
        "fact_bytes": fact_bytes,
        "evidence": evidence,
        "receipt": receipt,
        "manifest": manifest,
        "assessment": assessment,
        "assessment_bytes": assessment_bytes,
        "review": review,
        "review_bytes": review_bytes,
    }
    chain_input = pr63._chain(inputs, policy.policy_reviewed_at)
    return pr66._pr65_result(pr65._chain_bundle(chain_input))


def test_contract_and_exact_full_chain_are_deterministic() -> None:
    readiness, readiness_bytes, kwargs = _build()
    rebuilt = _revalidate(readiness, readiness_bytes, kwargs)

    assert SCHEMA_VERSION == 1 and type(SCHEMA_VERSION) is int
    assert DATASET_NAME == (
        "athena-fotmob-reviewed-match-details-probability-model-readiness-v1"
    )
    assert READINESS_SCOPE == "EXACT_REVALIDATED_PR66_FEATURE_STATE_ONLY"
    assert REVIEWED_MISSING_INPUT_POLICY == "REJECT_NON_AVAILABLE"
    assert type(readiness) is ReviewedMatchDetailsProbabilityModelReadiness
    assert readiness_bytes.endswith(b"\n") and not readiness_bytes.endswith(b"\n\n")
    assert canonical_reviewed_match_details_probability_model_readiness_bytes(
        rebuilt
    ) == readiness_bytes
    assert sha256_reviewed_match_details_probability_model_readiness(
        readiness
    ) == hashlib.sha256(readiness_bytes).hexdigest()


def test_every_market_is_evaluated_once_and_sorted() -> None:
    readiness, _, _ = _build()
    expected = tuple(sorted(MarketId, key=lambda item: item.value))

    assert tuple(item.market_id for item in readiness.market_readiness) == expected
    assert len(readiness.market_readiness) == len(MarketId)


def test_default_one_available_feature_blocks_declared_six_input_markets() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)

    assert record.model_status is ModelStatus.ACTIVE
    assert record.declared_input_status is DeclaredInputStatus.BLOCKED
    assert record.readiness_status is ProbabilityReadinessStatus.BLOCKED_FEATURE_INPUTS
    assert record.unavailable_feature_ids == (
        ModelFeatureId.AWAY_FORM,
        ModelFeatureId.HOME_ELO,
        ModelFeatureId.AWAY_ELO,
        ModelFeatureId.FATIGUE,
        ModelFeatureId.LIVE_DATA_FRESHNESS,
    )
    assert record.blocked_feature_ids == ()
    home = next(
        item
        for item in record.required_feature_records
        if item.feature_id is ModelFeatureId.HOME_FORM
    )
    assert home.status is ModelFeatureStatus.AVAILABLE
    assert all(
        item.status is ModelFeatureStatus.MISSING
        for item in record.required_feature_records
        if item.feature_id is not ModelFeatureId.HOME_FORM
    )


def test_blocked_feature_preserves_blockers_and_never_satisfies() -> None:
    readiness, _, _ = _build(_pr66_helper()._stale_pr65_result())
    record = _market(readiness, MarketId.MATCH_RESULT)
    home = next(
        item
        for item in record.required_feature_records
        if item.feature_id is ModelFeatureId.HOME_FORM
    )

    assert home.status is ModelFeatureStatus.BLOCKED
    assert home.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.STALE_EVIDENCE_PRESENT,
    )
    assert ModelFeatureId.HOME_FORM in record.unavailable_feature_ids
    assert ModelFeatureId.HOME_FORM in record.blocked_feature_ids
    assert record.declared_input_status is DeclaredInputStatus.BLOCKED


def test_legacy_default_policy_is_audited_but_never_substitutes() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)

    assert record.legacy_missing_input_policy is MissingInputPolicy.DEFAULT_AND_DISCLOSE
    assert record.reviewed_missing_input_policy == "REJECT_NON_AVAILABLE"
    assert record.declared_input_status is DeclaredInputStatus.BLOCKED
    payload = readiness.to_dict()
    assert "default_value" not in json.dumps(payload, sort_keys=True)


def test_disabled_market_remains_model_status_blocked() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.HOME_WIN_EITHER_HALF)

    assert record.model_status is ModelStatus.DISABLED
    assert record.declared_probability_inputs == ()
    assert record.declared_input_status is DeclaredInputStatus.SATISFIED
    assert record.readiness_status is ProbabilityReadinessStatus.BLOCKED_MODEL_STATUS
    assert record.readiness_reasons == (
        ProbabilityReadinessReason.MODEL_STATUS_DISABLED,
    )


def test_all_six_available_still_blocks_active_expected_goals_transform() -> None:
    readiness, _, _ = _build(_custom_full_available_pr66_result())
    record = _market(readiness, MarketId.MATCH_RESULT)

    assert len(record.required_feature_records) == len(ModelFeatureId)
    assert all(
        item.status is ModelFeatureStatus.AVAILABLE
        for item in record.required_feature_records
    )
    assert record.declared_input_status is DeclaredInputStatus.SATISFIED
    assert record.unavailable_feature_ids == ()
    assert record.readiness_status is (
        ProbabilityReadinessStatus.BLOCKED_UNREVIEWED_TRANSFORM
    )
    assert record.readiness_reasons == (
        ProbabilityReadinessReason.REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED,
    )


def test_all_six_available_experimental_is_research_only() -> None:
    readiness, _, _ = _build(_custom_full_available_pr66_result())
    record = _market(readiness, MarketId.BTTS)

    assert record.model_status is ModelStatus.EXPERIMENTAL
    assert record.declared_input_status is DeclaredInputStatus.SATISFIED
    assert record.readiness_status is (
        ProbabilityReadinessStatus.RESEARCH_ONLY_UNREVIEWED_TRANSFORM
    )
    assert record.readiness_reasons == (
        ProbabilityReadinessReason.EXPERIMENTAL_RESEARCH_ONLY,
        ProbabilityReadinessReason.REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED,
    )
    assert all("READY" not in item.value for item in ProbabilityReadinessStatus)


def test_pricing_inputs_are_audited_but_not_probability_requirements() -> None:
    readiness, _, _ = _build(_custom_full_available_pr66_result())
    record = _market(readiness, MarketId.MATCH_RESULT)

    assert record.declared_pricing_inputs == ("bookmaker_odds",)
    assert record.declared_input_status is DeclaredInputStatus.SATISFIED
    assert all(
        item.feature_id in ModelFeatureId
        for item in record.required_feature_records
    )


def test_registry_identity_is_deterministic_and_complete() -> None:
    first = canonical_model_status_registry_view_bytes()
    second = canonical_model_status_registry_view_bytes()
    payload = json.loads(first)

    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert sha256_model_status_registry_view() == hashlib.sha256(first).hexdigest()
    assert [item["market_id"] for item in payload["markets"]] == sorted(
        item.value for item in MarketId
    )
    assert len(payload["markets"]) == len(MarketId)


@pytest.mark.parametrize(
    "mutation",
    ("incomplete", "unknown_input", "duplicate_input", "missing_method"),
)
def test_malformed_registry_fails_closed(monkeypatch, mutation) -> None:
    registry = dict(MODEL_STATUS_REGISTRY)
    if mutation == "incomplete":
        registry.pop(MarketId.MATCH_RESULT)
    else:
        base = registry[MarketId.MATCH_RESULT]
        if mutation == "unknown_input":
            replacement = dataclasses.replace(base, probability_inputs=("unknown",))
        elif mutation == "duplicate_input":
            replacement = dataclasses.replace(
                base,
                probability_inputs=("home_form", "home_form"),
            )
        else:
            replacement = dataclasses.replace(base, probability_method=None)
        registry[MarketId.MATCH_RESULT] = replacement
    monkeypatch.setattr(module, "MODEL_STATUS_REGISTRY", registry)
    monkeypatch.setattr(module, "get_model_status", lambda market_id: registry[market_id])

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        canonical_model_status_registry_view_bytes()


def test_exact_pr66_pr31_and_registry_anchors() -> None:
    readiness, _, kwargs = _build()
    pr66_bytes = kwargs["handoff_bytes"]
    feature_bytes = canonical_model_feature_snapshot_bytes(
        kwargs["handoff"].model_feature_snapshot
    )
    registry_bytes = canonical_model_status_registry_view_bytes()

    assert readiness.source_pr66_sha256 == hashlib.sha256(pr66_bytes).hexdigest()
    assert readiness.source_pr66_size == len(pr66_bytes)
    assert readiness.source_model_feature_snapshot_sha256 == hashlib.sha256(
        feature_bytes
    ).hexdigest()
    assert readiness.source_model_feature_snapshot_size == len(feature_bytes)
    assert readiness.model_status_registry_sha256 == hashlib.sha256(
        registry_bytes
    ).hexdigest()
    assert readiness.model_status_registry_size == len(registry_bytes)
    assert readiness.fixture_identifier == kwargs["handoff"].fixture_identifier
    assert readiness.source_match_id == kwargs["handoff"].source_match_id
    assert readiness.kickoff == kwargs["handoff"].kickoff
    assert readiness.as_of == kwargs["handoff"].as_of


@pytest.mark.parametrize(
    "attribute,replacement",
    (
        ("source_pr66_sha256", "0" * 64),
        ("source_pr66_size", 1),
        ("source_model_feature_snapshot_sha256", "0" * 64),
        ("source_model_feature_snapshot_size", 1),
        ("model_status_registry_sha256", "0" * 64),
        ("model_status_registry_size", 1),
        ("fixture_identifier", "FOTMOB:9"),
        ("source_match_id", "9"),
        ("kickoff", datetime.datetime(2026, 1, 2, tzinfo=UTC)),
        ("as_of", datetime.datetime(2026, 1, 1, tzinfo=UTC)),
    ),
)
def test_forced_wrapper_anchor_or_identity_mutation_fails_replay(
    attribute,
    replacement,
) -> None:
    readiness, readiness_bytes, kwargs = _build()
    object.__setattr__(readiness, attribute, replacement)

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        _revalidate(readiness, readiness_bytes, kwargs)


@pytest.mark.parametrize(
    "attribute,replacement",
    (
        ("readiness_status", ProbabilityReadinessStatus.BLOCKED_MODEL_STATUS),
        ("unavailable_feature_ids", ()),
        ("blocked_feature_ids", (ModelFeatureId.HOME_FORM,)),
    ),
)
def test_forced_market_readiness_mutation_is_rejected(attribute, replacement) -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)
    object.__setattr__(record, attribute, replacement)

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        canonical_reviewed_match_details_probability_model_readiness_bytes(readiness)


@pytest.mark.parametrize(
    "attribute,replacement",
    (
        ("status", ModelFeatureStatus.AVAILABLE),
        ("blockers", (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)),
        ("evidence_sha256s", ("f" * 64,)),
        ("feature_id", ModelFeatureId.HOME_FORM),
    ),
)
def test_forced_feature_audit_mutation_is_rejected(attribute, replacement) -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)
    audit = next(
        item
        for item in record.required_feature_records
        if item.feature_id is ModelFeatureId.AWAY_FORM
    )
    object.__setattr__(audit, attribute, replacement)

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        canonical_reviewed_match_details_probability_model_readiness_bytes(readiness)


@pytest.mark.parametrize(
    "bad",
    (b"{}\n", b"", bytearray(b"x"), memoryview(b"x"), "x"),
)
def test_wrong_noncanonical_or_mutable_readiness_bytes_are_rejected(bad) -> None:
    readiness, _, kwargs = _build()
    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        _revalidate(readiness, bad, kwargs)


def test_wrong_pr66_bytes_and_coordinated_local_feature_forgery_fail() -> None:
    readiness, readiness_bytes, kwargs = _build()
    forged_kwargs = dict(kwargs)
    object.__setattr__(
        forged_kwargs["handoff"],
        "model_feature_snapshot_sha256",
        "0" * 64,
    )
    forged_kwargs["handoff_bytes"] = b"{}\n"

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        _revalidate(readiness, readiness_bytes, forged_kwargs)


def test_coordinated_pr31_pr66_pr67_forgery_fails_full_replay() -> None:
    readiness, _, kwargs = _build()
    original_handoff = kwargs["handoff"]
    original_feature_snapshot = original_handoff.model_feature_snapshot
    forged_features = tuple(
        dataclasses.replace(
            feature,
            status=ModelFeatureStatus.AVAILABLE,
            value=123.0,
            blockers=(),
            evidence_sha256s=("f" * 64,),
        )
        if feature.status is ModelFeatureStatus.MISSING
        else dataclasses.replace(feature)
        for feature in original_feature_snapshot.features
    )
    forged_feature_snapshot = FixtureModelFeatureSnapshot(
        schema_version=original_feature_snapshot.schema_version,
        dataset_name=original_feature_snapshot.dataset_name,
        fixture_identifier=original_feature_snapshot.fixture_identifier,
        kickoff=original_feature_snapshot.kickoff,
        as_of=original_feature_snapshot.as_of,
        source_snapshot_dataset_name=(
            original_feature_snapshot.source_snapshot_dataset_name
        ),
        source_snapshot_schema_version=(
            original_feature_snapshot.source_snapshot_schema_version
        ),
        source_snapshot_sha256=original_feature_snapshot.source_snapshot_sha256,
        features=forged_features,
        safety=original_feature_snapshot.safety,
    )
    forged_feature_bytes = canonical_model_feature_snapshot_bytes(
        forged_feature_snapshot
    )
    forged_handoff = dataclasses.replace(
        original_handoff,
        model_feature_snapshot=forged_feature_snapshot,
        model_feature_snapshot_sha256=hashlib.sha256(
            forged_feature_bytes
        ).hexdigest(),
        model_feature_snapshot_size=len(forged_feature_bytes),
    )
    forged_handoff_bytes = (
        canonical_reviewed_match_details_model_feature_handoff_bytes(forged_handoff)
    )
    forged_feature_by_id = {
        feature.feature_id: feature for feature in forged_feature_snapshot.features
    }
    forged_markets = module._build_market_readiness(forged_feature_by_id)
    forged_readiness = dataclasses.replace(
        readiness,
        source_pr66_sha256=hashlib.sha256(forged_handoff_bytes).hexdigest(),
        source_pr66_size=len(forged_handoff_bytes),
        source_model_feature_snapshot_sha256=hashlib.sha256(
            forged_feature_bytes
        ).hexdigest(),
        source_model_feature_snapshot_size=len(forged_feature_bytes),
        market_readiness=forged_markets,
    )
    forged_readiness_bytes = (
        canonical_reviewed_match_details_probability_model_readiness_bytes(
            forged_readiness
        )
    )
    forged_kwargs = dict(kwargs)
    forged_kwargs["handoff"] = forged_handoff
    forged_kwargs["handoff_bytes"] = forged_handoff_bytes

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        _revalidate(forged_readiness, forged_readiness_bytes, forged_kwargs)


def test_immutability_and_all_downstream_safety_false() -> None:
    readiness, _, _ = _build()

    assert readiness.safety == {key: False for key in readiness.safety}
    with pytest.raises(dataclasses.FrozenInstanceError):
        readiness.dataset_name = "forged"
    with pytest.raises(TypeError):
        readiness.safety["probability_inference_authorized"] = True


def test_builder_exposes_no_override_execution_or_market_parameters() -> None:
    parameters = set(
        inspect.signature(build_reviewed_match_details_probability_model_readiness).parameters
    )
    assert not parameters & {
        "market_id",
        "market_selection",
        "feature_values",
        "readiness_override",
        "home_expected_goals",
        "away_expected_goals",
        "probability",
        "bookmaker_odds",
    }


def test_production_ast_uses_replay_and_registry_without_execution_paths() -> None:
    path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_probability_model_readiness.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    names: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
            names.extend(item.name for item in node.names)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    for required in (
        "revalidate_reviewed_match_details_model_feature_handoff",
        "MODEL_STATUS_REGISTRY",
        "get_model_status",
        "ModelFeatureStatus",
        "ModelFeatureId",
    ):
        assert required in names
    assert "revalidate_reviewed_match_details_model_feature_handoff" in calls
    forbidden = {
        "Prediction",
        "MatchAnalyst",
        "ProbabilityEngine",
        "build_score_matrix",
        "joblib",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "open",
        "write_text",
        "write_bytes",
    }
    assert not forbidden.intersection(imports + names + calls)
    assert not any(
        root in item.lower()
        for root in (
            "prediction_engine",
            "probability_engine",
            "score_matrix",
            "pricing",
            "sportybet",
            "selection",
            "betting",
        )
        for item in imports
    )


def test_rejected_qualification_stays_blocked_feature_input() -> None:
    readiness, _, _ = _build(_pr66_helper()._unverified_pr65_result())
    record = _market(readiness, MarketId.MATCH_RESULT)
    home = next(
        item
        for item in record.required_feature_records
        if item.feature_id is ModelFeatureId.HOME_FORM
    )

    assert home.status is ModelFeatureStatus.BLOCKED
    assert ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT in home.blockers
    assert record.readiness_status is ProbabilityReadinessStatus.BLOCKED_FEATURE_INPUTS
    assert record.readiness_reasons == (
        ProbabilityReadinessReason.NON_AVAILABLE_DECLARED_FEATURES,
    )


def test_registry_reason_and_pricing_metadata_are_exactly_preserved() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)
    registry = MODEL_STATUS_REGISTRY[MarketId.MATCH_RESULT]

    assert record.probability_method == registry.probability_method
    assert record.declared_probability_inputs == tuple(
        ModelFeatureId(item) for item in registry.probability_inputs
    )
    assert record.declared_pricing_inputs == registry.pricing_inputs
    assert record.legacy_missing_input_policy is registry.missing_input_policy


def test_available_feature_value_is_not_serialized_or_transformed() -> None:
    readiness, _, _ = _build()
    payload = readiness.to_dict()
    records = payload["market_readiness"][0]["required_feature_records"]

    assert all("value" not in item for item in records)
    assert "home_expected_goals" not in json.dumps(payload)
    assert "away_expected_goals" not in json.dumps(payload)


def test_registry_view_contains_live_reason_without_secondary_registry() -> None:
    payload = json.loads(canonical_model_status_registry_view_bytes())
    match_result = next(
        item for item in payload["markets"] if item["market_id"] == "MATCH_RESULT"
    )

    assert match_result["reason"] == MODEL_STATUS_REGISTRY[MarketId.MATCH_RESULT].reason
    assert match_result["missing_input_policy"] == "DEFAULT_AND_DISCLOSE"
    assert match_result["probability_inputs"] == list(
        MODEL_STATUS_REGISTRY[MarketId.MATCH_RESULT].probability_inputs
    )
    assert match_result["analytical_probability_capability"] == "AVAILABLE"
    assert match_result["settlement_capability"] == "ORDINARY_EVENT_PROBABILITY"
    assert match_result["pricing_authority"] == "NOT_AUTHORIZED"
    assert match_result["selection_authority"] == "NOT_AUTHORIZED"


def test_experimental_missing_inputs_do_not_become_research_satisfied() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.BTTS)

    assert record.model_status is ModelStatus.EXPERIMENTAL
    assert record.declared_input_status is DeclaredInputStatus.BLOCKED
    assert record.readiness_status is ProbabilityReadinessStatus.BLOCKED_FEATURE_INPUTS
    assert record.readiness_reasons == (
        ProbabilityReadinessReason.NON_AVAILABLE_DECLARED_FEATURES,
    )


def test_no_probability_or_selection_values_exist_in_artifact() -> None:
    readiness, _, _ = _build()
    payload = json.dumps(readiness.to_dict(), sort_keys=True)

    assert '"probability":' not in payload
    assert '"odds":' not in payload
    assert '"selection":' not in payload
    assert '"edge":' not in payload


def test_wrong_schema_or_bool_schema_is_rejected() -> None:
    readiness, _, _ = _build()
    for schema in (True, 2):
        with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
            dataclasses.replace(readiness, schema_version=schema)


def test_market_status_and_audit_reconstruction_reject_object_mutation() -> None:
    readiness, _, _ = _build()
    record = _market(readiness, MarketId.MATCH_RESULT)
    object.__setattr__(record, "legacy_missing_input_policy", MissingInputPolicy.REJECT_MARKET)

    with pytest.raises(FotMobReviewedMatchDetailsProbabilityModelReadinessError):
        canonical_reviewed_match_details_probability_model_readiness_bytes(readiness)


def test_full_available_fixture_identity_and_time_stay_exact() -> None:
    readiness, _, kwargs = _build(_custom_full_available_pr66_result())

    assert readiness.fixture_identifier == kwargs["handoff"].fixture_identifier
    assert readiness.source_match_id == kwargs["handoff"].source_match_id
    assert readiness.kickoff == kwargs["handoff"].kickoff
    assert readiness.as_of == kwargs["handoff"].as_of


def test_qualification_disposition_is_not_accepted_as_readiness_override() -> None:
    parameters = inspect.signature(
        build_reviewed_match_details_probability_model_readiness
    ).parameters
    assert "qualification_disposition" not in parameters
