import ast
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

import domain.fixture_model_features as feature_module
from domain.fixture_intelligence import (
    DATASET_NAME as INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as INTELLIGENCE_SCHEMA_VERSION,
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
    canonical_snapshot_bytes,
    sha256_bytes,
)
from domain.fixture_model_features import (
    DATASET_NAME,
    SCHEMA_VERSION,
    FixtureModelFeatureError,
    FixtureModelFeatureSnapshot,
    MODEL_FEATURE_BINDINGS,
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureResolution,
    ModelFeatureStatus,
    build_model_feature_snapshot,
    canonical_model_feature_snapshot_bytes,
    model_feature_snapshot_to_dict,
    sha256_model_feature_snapshot,
)
from domain.model_status import MODEL_STATUS_REGISTRY, ProbabilityInputNamespace


UTC = dt.timezone.utc
KICKOFF = dt.datetime(2026, 8, 10, 18, 0, tzinfo=UTC)
AS_OF = dt.datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

EXPECTED_FEATURES = {
    "home_form",
    "away_form",
    "home_elo",
    "away_elo",
    "fatigue",
    "live_data_freshness",
}
EXPECTED_BINDINGS = {
    ModelFeatureId.HOME_FORM: (IntelligenceCategory.FORM, "home_form"),
    ModelFeatureId.AWAY_FORM: (IntelligenceCategory.FORM, "away_form"),
    ModelFeatureId.HOME_ELO: (IntelligenceCategory.PERFORMANCE, "home_elo"),
    ModelFeatureId.AWAY_ELO: (IntelligenceCategory.PERFORMANCE, "away_elo"),
    ModelFeatureId.FATIGUE: (IntelligenceCategory.SCHEDULE_LOAD, "fatigue"),
    ModelFeatureId.LIVE_DATA_FRESHNESS: (
        IntelligenceCategory.FIXTURE_CONTEXT,
        "live_data_freshness",
    ),
}
SAFETY_KEYS = {
    "network_acquisition_authorized",
    "scraping_authorized",
    "browser_automation_authorized",
    "probability_inference_authorized",
    "probability_adjustment_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "bet_authorized",
}


def fact(
    feature_id=ModelFeatureId.HOME_FORM,
    *,
    value=0.75,
    status=IntelligenceFactStatus.SUPPORTED,
    sha="a" * 64,
    provider="fotmob-reviewed",
    source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
    category=None,
    field=None,
):
    bound_category, bound_field = EXPECTED_BINDINGS[feature_id]
    return FixtureIntelligenceFact(
        category=category or bound_category,
        field=field or bound_field,
        status=status,
        value=value,
        source_provider=provider,
        source_role=source_role,
        source_reference="reviewed:fixture-evidence",
        observed_at=AS_OF - dt.timedelta(hours=1),
        evidence_file_path=f"evidence/{sha[:8]}.json",
        evidence_sha256=sha,
    )


def intelligence_snapshot(facts=(), *, fixture_identifier="fixture-31", kickoff=KICKOFF, as_of=AS_OF):
    return build_snapshot(fixture_identifier, kickoff, as_of, list(facts))


def mapped(facts=(), **kwargs):
    return build_model_feature_snapshot(intelligence_snapshot(facts, **kwargs))


def resolution(snapshot, feature_id):
    return next(item for item in snapshot.features if item.feature_id is feature_id)


def safety():
    return {key: False for key in SAFETY_KEYS}


def missing_resolution(feature_id):
    category, field = EXPECTED_BINDINGS[feature_id]
    return ModelFeatureResolution(
        feature_id=feature_id,
        status=ModelFeatureStatus.MISSING,
        value=None,
        source_category=category,
        source_field=field,
        blockers=(),
        evidence_sha256s=(),
    )


def all_missing_features():
    return tuple(
        sorted(
            (missing_resolution(feature_id) for feature_id in ModelFeatureId),
            key=lambda item: item.feature_id.value,
        )
    )


def direct_snapshot(**overrides):
    values = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "fixture_identifier": "fixture-31",
        "kickoff": KICKOFF,
        "as_of": AS_OF,
        "source_snapshot_dataset_name": INTELLIGENCE_DATASET_NAME,
        "source_snapshot_schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "source_snapshot_sha256": "a" * 64,
        "features": all_missing_features(),
        "safety": safety(),
    }
    values.update(overrides)
    return FixtureModelFeatureSnapshot(**values)


def direct_resolution(
    *,
    feature_id=ModelFeatureId.HOME_FORM,
    status=ModelFeatureStatus.AVAILABLE,
    value=0.5,
    blockers=(),
    evidence_sha256s=("a" * 64,),
    category=None,
    field=None,
):
    bound_category, bound_field = EXPECTED_BINDINGS[feature_id]
    return ModelFeatureResolution(
        feature_id=feature_id,
        status=status,
        value=value,
        source_category=category or bound_category,
        source_field=field or bound_field,
        blockers=blockers,
        evidence_sha256s=evidence_sha256s,
    )


# Contract basics and deliberate model-status drift alarm.
def test_exact_dataset_name_and_schema_version():
    snapshot = mapped()
    assert snapshot.dataset_name == "athena-fixture-model-feature-snapshot-v1"
    assert snapshot.schema_version == 1
    assert type(snapshot.schema_version) is int


@pytest.mark.parametrize("bad_version", [True, 1.0, "1", 0, 2])
def test_non_exact_schema_versions_are_rejected(bad_version):
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(schema_version=bad_version)


def test_exact_feature_registry_and_bindings():
    assert {member.value for member in ModelFeatureId} == EXPECTED_FEATURES
    assert len(ModelFeatureId) == 6
    assert isinstance(MODEL_FEATURE_BINDINGS, tuple)
    assert tuple(binding.feature_id.value for binding in MODEL_FEATURE_BINDINGS) == tuple(
        sorted(EXPECTED_FEATURES)
    )
    assert {
        binding.feature_id: (binding.source_category, binding.source_field)
        for binding in MODEL_FEATURE_BINDINGS
    } == EXPECTED_BINDINGS


def test_generic_model_status_probability_inputs_match_feature_registry_exactly():
    probability_inputs = {
        item
        for definition in MODEL_STATUS_REGISTRY.values()
        for item in definition.probability_inputs
        if item
        and definition.probability_input_namespace
        is ProbabilityInputNamespace.GENERIC_FIXTURE_MODEL_FEATURES
    }
    assert probability_inputs == EXPECTED_FEATURES
    assert probability_inputs == {feature.value for feature in ModelFeatureId}
    assert "bookmaker_odds" not in {feature.value for feature in ModelFeatureId}


# Source snapshot anchor.
def test_source_snapshot_contract_and_sha_are_copied_exactly():
    source = intelligence_snapshot([fact()])
    snapshot = build_model_feature_snapshot(source)
    assert snapshot.source_snapshot_dataset_name == source.dataset_name
    assert snapshot.source_snapshot_schema_version == source.schema_version
    assert snapshot.source_snapshot_sha256 == sha256_bytes(
        canonical_snapshot_bytes(source)
    )


def test_source_fact_change_changes_source_anchor():
    first = mapped([fact(value=0.6)])
    second = mapped([fact(value=0.7)])
    assert first.source_snapshot_sha256 != second.source_snapshot_sha256


def test_logically_identical_source_snapshots_have_same_anchor():
    first_fact = fact(sha="a" * 64, provider="a")
    second_fact = fact(sha="b" * 64, provider="b")
    forward = mapped([first_fact, second_fact])
    reverse = mapped([second_fact, first_fact])
    assert forward.source_snapshot_sha256 == reverse.source_snapshot_sha256


# AVAILABLE.
@pytest.mark.parametrize("value, expected", [(4, 4.0), (0.625, 0.625)])
def test_supported_finite_numeric_value_is_available_float(value, expected):
    item = resolution(mapped([fact(value=value)]), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.AVAILABLE
    assert item.value == expected
    assert type(item.value) is float
    assert item.blockers == ()
    assert item.evidence_sha256s == ("a" * 64,)


def test_equivalent_supported_values_do_not_conflict_and_hashes_are_unique_sorted():
    facts = [
        fact(value=0.75, sha="b" * 64, provider="b"),
        fact(value=0.75, sha="a" * 64, provider="a"),
        fact(value=0.75, sha="a" * 64, provider="c"),
    ]
    item = resolution(mapped(facts), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.AVAILABLE
    assert item.value == 0.75
    assert item.evidence_sha256s == ("a" * 64, "b" * 64)


# MISSING.
def test_absent_fields_are_missing_without_defaults_or_evidence():
    snapshot = mapped()
    assert len(snapshot.features) == 6
    for item in snapshot.features:
        assert item.status is ModelFeatureStatus.MISSING
        assert item.value is None
        assert item.blockers == ()
        assert item.evidence_sha256s == ()


# STALE and UNVERIFIED.
def test_stale_only_evidence_is_blocked():
    item = resolution(
        mapped([fact(status=IntelligenceFactStatus.STALE)]),
        ModelFeatureId.HOME_FORM,
    )
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.value is None
    assert item.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.STALE_EVIDENCE_PRESENT,
    )


def test_unverified_only_evidence_is_blocked():
    item = resolution(
        mapped([fact(status=IntelligenceFactStatus.UNVERIFIED)]),
        ModelFeatureId.HOME_FORM,
    )
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT,
    )


def test_discovery_only_evidence_never_becomes_available():
    item = resolution(
        mapped(
            [
                fact(
                    status=IntelligenceFactStatus.UNVERIFIED,
                    source_role=SourceRole.DISCOVERY_ONLY,
                )
            ]
        ),
        ModelFeatureId.HOME_FORM,
    )
    assert item.status is ModelFeatureStatus.BLOCKED
    assert ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT in item.blockers


def test_stale_and_unverified_blockers_have_deterministic_order():
    facts = [
        fact(status=IntelligenceFactStatus.UNVERIFIED, sha="b" * 64),
        fact(status=IntelligenceFactStatus.STALE, sha="a" * 64),
    ]
    item = resolution(mapped(facts), ModelFeatureId.HOME_FORM)
    assert item.blockers == tuple(sorted(item.blockers, key=lambda value: value.value))
    assert item.blockers == (
        ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
        ModelFeatureBlocker.STALE_EVIDENCE_PRESENT,
        ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT,
    )


@pytest.mark.parametrize(
    "other_status",
    [IntelligenceFactStatus.STALE, IntelligenceFactStatus.UNVERIFIED],
)
def test_supported_evidence_remains_available_with_nonconflicting_lower_status_evidence(
    other_status,
):
    facts = [
        fact(value=0.6, sha="a" * 64, status=IntelligenceFactStatus.SUPPORTED),
        fact(value=999, sha="b" * 64, status=other_status, provider="other"),
    ]
    item = resolution(mapped(facts), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.AVAILABLE
    assert item.value == 0.6
    assert item.evidence_sha256s == ("a" * 64, "b" * 64)


# Conflicts.
def test_differing_supported_values_are_blocked_as_conflict():
    facts = [
        fact(value=0.5, sha="a" * 64, provider="official"),
        fact(value=0.8, sha="b" * 64, provider="fotmob"),
    ]
    item = resolution(mapped(facts), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.value is None
    assert item.blockers == (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)
    assert item.evidence_sha256s == ("a" * 64, "b" * 64)


def test_explicit_conflicted_fact_is_blocked():
    item = resolution(
        mapped([fact(status=IntelligenceFactStatus.CONFLICTED)]),
        ModelFeatureId.HOME_FORM,
    )
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.blockers == (ModelFeatureBlocker.CONFLICTED_EVIDENCE,)


def test_official_source_does_not_win_a_conflict():
    facts = [
        fact(value=1, sha="a" * 64, provider="official-club"),
        fact(value=2, sha="b" * 64, provider="fotmob-reviewed"),
    ]
    item = resolution(mapped(facts), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.value is None


# Invalid supported values.
@pytest.mark.parametrize("bad_value", [True, False, "0.5", [0.5], {"v": 0.5}, None])
def test_invalid_supported_values_are_blocked_not_missing(bad_value):
    item = resolution(mapped([fact(value=bad_value)]), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.BLOCKED
    assert item.value is None
    assert item.blockers == (ModelFeatureBlocker.INVALID_SUPPORTED_VALUE,)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_supported_values_cannot_become_features(bad_value):
    with pytest.raises(FixtureIntelligenceError):
        fact(value=bad_value)
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(value=bad_value)


def test_huge_integer_that_cannot_convert_to_float_is_blocked():
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(value=10**10000)


# Resolution validation.
def test_builder_rejects_non_intelligence_snapshot_without_duck_typing():
    class Duck:
        facts = ()

    for bad in (None, {}, Duck()):
        with pytest.raises(FixtureModelFeatureError):
            build_model_feature_snapshot(bad)


def test_string_feature_id_is_rejected():
    with pytest.raises(FixtureModelFeatureError):
        ModelFeatureResolution(
            feature_id="home_form",
            status=ModelFeatureStatus.MISSING,
            value=None,
            source_category=IntelligenceCategory.FORM,
            source_field="home_form",
            blockers=(),
            evidence_sha256s=(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": IntelligenceCategory.WEATHER},
        {"field": "other_form"},
    ],
)
def test_resolution_must_use_exact_fixed_binding(kwargs):
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(**kwargs)


@pytest.mark.parametrize("sha", ["A" * 64, "abc", "g" * 64])
def test_malformed_or_uppercase_evidence_sha_is_rejected(sha):
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(evidence_sha256s=(sha,))


def test_duplicate_and_unsorted_evidence_hashes_are_rejected():
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(evidence_sha256s=("a" * 64, "a" * 64))
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(evidence_sha256s=("b" * 64, "a" * 64))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": None},
        {"value": True},
        {"value": float("nan")},
        {"blockers": (ModelFeatureBlocker.INVALID_SUPPORTED_VALUE,)},
        {"evidence_sha256s": ()},
    ],
)
def test_available_resolution_invariants(kwargs):
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": 0.0},
        {"blockers": (ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,)},
        {"evidence_sha256s": ("a" * 64,)},
    ],
)
def test_missing_resolution_invariants(kwargs):
    values = {
        "status": ModelFeatureStatus.MISSING,
        "value": None,
        "blockers": (),
        "evidence_sha256s": (),
    }
    values.update(kwargs)
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(**values)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": 0.0},
        {"blockers": ()},
        {"evidence_sha256s": ()},
    ],
)
def test_blocked_resolution_invariants(kwargs):
    values = {
        "status": ModelFeatureStatus.BLOCKED,
        "value": None,
        "blockers": (ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,),
        "evidence_sha256s": ("a" * 64,),
    }
    values.update(kwargs)
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(**values)


def test_duplicate_and_unsorted_blockers_are_rejected():
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(
            status=ModelFeatureStatus.BLOCKED,
            value=None,
            blockers=(
                ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
                ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
            ),
        )
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(
            status=ModelFeatureStatus.BLOCKED,
            value=None,
            blockers=(
                ModelFeatureBlocker.STALE_EVIDENCE_PRESENT,
                ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE,
            ),
        )


# Snapshot feature-set validation.
def test_duplicate_missing_and_unsorted_feature_resolutions_are_rejected():
    features = all_missing_features()
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(features=features + (features[0],))
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(features=features[:-1])
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(features=tuple(reversed(features)))
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(features=list(features))


# Time and identity.
def test_times_are_normalized_to_utc_and_fixture_identity_is_exact():
    plus_two = dt.timezone(dt.timedelta(hours=2))
    source = intelligence_snapshot(
        fixture_identifier="fixture-exact",
        kickoff=KICKOFF.astimezone(plus_two),
        as_of=AS_OF.astimezone(plus_two),
    )
    snapshot = build_model_feature_snapshot(source)
    assert snapshot.fixture_identifier == "fixture-exact"
    assert snapshot.kickoff == KICKOFF
    assert snapshot.as_of == AS_OF
    assert snapshot.kickoff.tzinfo is UTC
    assert snapshot.as_of.tzinfo is UTC


@pytest.mark.parametrize(
    "overrides",
    [
        {"kickoff": KICKOFF.replace(tzinfo=None)},
        {"as_of": AS_OF.replace(tzinfo=None)},
        {"as_of": KICKOFF},
        {"as_of": KICKOFF + dt.timedelta(seconds=1)},
    ],
)
def test_invalid_snapshot_time_contract_is_rejected(overrides):
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(**overrides)


def test_builder_has_no_wall_clock_dependency():
    source = intelligence_snapshot([fact(value=0.4)])
    expected = canonical_model_feature_snapshot_bytes(
        build_model_feature_snapshot(source)
    )
    actual = canonical_model_feature_snapshot_bytes(
        build_model_feature_snapshot(source)
    )
    assert actual == expected


# Safety immutability.
def test_exact_safety_contract_all_false():
    snapshot = mapped()
    assert set(snapshot.safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in snapshot.safety.values())


@pytest.mark.parametrize("bad_value", [0, None, True, "false"])
def test_safety_values_must_be_exact_false(bad_value):
    values = safety()
    values["bet_authorized"] = bad_value
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(safety=values)


def test_missing_and_extra_safety_keys_are_rejected():
    missing = safety()
    missing.pop("bet_authorized")
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(safety=missing)
    extra = safety()
    extra["other"] = False
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(safety=extra)


def test_caller_safety_mutation_cannot_change_snapshot_or_canonical_bytes():
    caller_safety = safety()
    snapshot = direct_snapshot(safety=caller_safety)
    before = canonical_model_feature_snapshot_bytes(snapshot)
    caller_safety["bet_authorized"] = True
    assert snapshot.safety["bet_authorized"] is False
    assert canonical_model_feature_snapshot_bytes(snapshot) == before
    with pytest.raises(TypeError):
        snapshot.safety["bet_authorized"] = True


def test_tuple_fields_remain_tuples_and_cannot_follow_caller_list_mutation():
    caller_list = list(all_missing_features())
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(features=caller_list)
    snapshot = direct_snapshot(features=tuple(caller_list))
    caller_list.clear()
    assert isinstance(snapshot.features, tuple)
    assert len(snapshot.features) == 6
    assert all(isinstance(item.blockers, tuple) for item in snapshot.features)


# Serialization.
def test_to_dict_is_json_compatible_and_module_helper_delegates():
    snapshot = mapped([fact(value=0.42)])
    payload = snapshot.to_dict()
    assert model_feature_snapshot_to_dict(snapshot) == payload
    json.dumps(payload, allow_nan=False)


def test_canonical_bytes_are_compact_sorted_utf8_with_final_newline():
    snapshot = mapped([fact(value=0.42)])
    payload = canonical_model_feature_snapshot_bytes(snapshot)
    assert payload.endswith(b"\n")
    assert b"\r\n" not in payload
    assert payload == (
        json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert tuple(item.feature_id.value for item in snapshot.features) == tuple(
        sorted(EXPECTED_FEATURES)
    )


def test_source_fact_input_order_cannot_change_feature_bytes():
    facts = [
        fact(value=0.42, sha="a" * 64, provider="a"),
        fact(value=0.42, sha="b" * 64, provider="b"),
    ]
    first = canonical_model_feature_snapshot_bytes(mapped(facts))
    second = canonical_model_feature_snapshot_bytes(mapped(reversed(facts)))
    assert first == second


def test_sha_helper_hashes_exact_canonical_bytes():
    snapshot = mapped([fact(value=0.42)])
    expected = hashlib.sha256(canonical_model_feature_snapshot_bytes(snapshot)).hexdigest()
    assert sha256_model_feature_snapshot(snapshot) == expected


@pytest.mark.parametrize(
    "helper,bad",
    [
        (model_feature_snapshot_to_dict, None),
        (canonical_model_feature_snapshot_bytes, {}),
        (sha256_model_feature_snapshot, "snapshot"),
    ],
)
def test_serialization_helpers_fail_closed_on_wrong_types(helper, bad):
    with pytest.raises(FixtureModelFeatureError):
        helper(bad)


# Safety/scope: imports are verified structurally; behavior is verified above.
def test_domain_module_imports_only_standard_library_and_fixture_intelligence():
    path = Path(feature_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = {
        "requests",
        "httpx",
        "aiohttp",
        "selenium",
        "playwright",
        "intelligence.prediction_engine",
        "intelligence.match_analyst",
        "domain.pricing",
        "domain.score_matrix",
        "intelligence.ml_engine",
    }
    assert forbidden.isdisjoint(imports)
    assert all(
        name in {
            "__future__",
            "dataclasses",
            "datetime",
            "enum",
            "hashlib",
            "json",
            "math",
            "re",
            "types",
            "typing",
            "domain.fixture_intelligence",
        }
        for name in imports
    )


def test_output_contract_contains_no_probability_pricing_or_betting_results():
    payload = mapped([fact(value=0.42)]).to_dict()
    forbidden_keys = {
        "probability",
        "probability_adjustment",
        "impact_score",
        "odds",
        "edge",
        "expected_value",
        "kelly",
        "stake",
        "selection",
        "accumulator",
        "bet",
    }

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    assert forbidden_keys.isdisjoint(set(keys(payload)))
    assert payload["safety"]["probability_inference_authorized"] is False
    assert payload["safety"]["probability_adjustment_authorized"] is False
    assert payload["safety"]["pricing_authorized"] is False
    assert payload["safety"]["selection_authorized"] is False
    assert payload["safety"]["bet_authorized"] is False


def test_mapper_does_not_mutate_input_snapshot():
    source = intelligence_snapshot([fact(value=0.42)])
    before = canonical_snapshot_bytes(source)
    build_model_feature_snapshot(source)
    assert canonical_snapshot_bytes(source) == before


def test_all_six_bound_features_can_be_available_without_formula_changes():
    facts = [
        fact(feature_id, value=index + 0.25, sha=f"{index + 1:064x}")
        for index, feature_id in enumerate(ModelFeatureId)
    ]
    snapshot = mapped(facts)
    assert all(item.status is ModelFeatureStatus.AVAILABLE for item in snapshot.features)
    assert {item.value for item in snapshot.features} == {
        float(index + 0.25) for index in range(len(ModelFeatureId))
    }


def test_unbound_upstream_context_remains_upstream_and_does_not_create_features():
    source_fact = fact(
        category=IntelligenceCategory.WEATHER,
        field="temperature_c",
        value=31,
    )
    snapshot = mapped([source_fact])
    assert all(item.status is ModelFeatureStatus.MISSING for item in snapshot.features)


def test_wrong_source_snapshot_anchor_fields_fail_closed():
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(source_snapshot_dataset_name="other")
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(source_snapshot_schema_version=True)
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(source_snapshot_sha256="A" * 64)


def test_fixture_identifier_padding_is_rejected():
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(fixture_identifier=" fixture-31")


def test_direct_constructor_normalizes_available_int_to_float_without_rounding():
    integer = direct_resolution(value=7)
    precise = direct_resolution(value=0.12345678901234566)
    assert integer.value == 7.0 and type(integer.value) is float
    assert precise.value == 0.12345678901234566


def test_resolution_collections_must_be_tuples():
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(blockers=[])
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(evidence_sha256s=["a" * 64])


def test_invalid_normal_domain_inputs_do_not_leak_implementation_exceptions():
    invalid_build_inputs = [None, 3, "snapshot", object()]
    for value in invalid_build_inputs:
        with pytest.raises(FixtureModelFeatureError):
            build_model_feature_snapshot(value)
    for kwargs in (
        {"safety": None},
        {"features": None},
        {"kickoff": object()},
        {"source_snapshot_sha256": object()},
    ):
        with pytest.raises(FixtureModelFeatureError):
            direct_snapshot(**kwargs)


@pytest.mark.parametrize("feature_id", list(ModelFeatureId))
def test_each_fixed_binding_maps_supported_numeric_evidence(feature_id):
    item = resolution(
        mapped([fact(feature_id, value=2)]),
        feature_id,
    )
    expected_category, expected_field = EXPECTED_BINDINGS[feature_id]
    assert item.status is ModelFeatureStatus.AVAILABLE
    assert item.value == 2.0
    assert item.source_category is expected_category
    assert item.source_field == expected_field


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dataset_name": "other-dataset"},
        {"fixture_identifier": ""},
        {"fixture_identifier": "fixture-31 "},
        {"source_snapshot_schema_version": 1.0},
        {"source_snapshot_schema_version": "1"},
        {"source_snapshot_sha256": "short"},
    ],
)
def test_additional_snapshot_identity_invariants(kwargs):
    with pytest.raises(FixtureModelFeatureError):
        direct_snapshot(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "AVAILABLE"},
        {"category": "FORM"},
        {"field": " home_form"},
        {"value": object()},
        {"evidence_sha256s": (1,)},
    ],
)
def test_additional_resolution_type_boundaries(kwargs):
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(**kwargs)


def test_blocker_members_must_be_exact_enum_values():
    with pytest.raises(FixtureModelFeatureError):
        direct_resolution(
            status=ModelFeatureStatus.BLOCKED,
            value=None,
            blockers=("NO_SUPPORTED_EVIDENCE",),
        )


def test_blocked_stale_evidence_retains_its_hash():
    item = resolution(
        mapped([fact(status=IntelligenceFactStatus.STALE, sha="c" * 64)]),
        ModelFeatureId.HOME_FORM,
    )
    assert item.evidence_sha256s == ("c" * 64,)


def test_canonical_payload_feature_and_blocker_values_are_plain_json_strings():
    item = resolution(
        mapped([fact(status=IntelligenceFactStatus.STALE)]),
        ModelFeatureId.HOME_FORM,
    )
    payload = mapped([fact(status=IntelligenceFactStatus.STALE)]).to_dict()
    row = next(entry for entry in payload["features"] if entry["feature_id"] == item.feature_id.value)
    assert row["status"] == "BLOCKED"
    assert row["source_category"] == "FORM"
    assert row["blockers"] == ["NO_SUPPORTED_EVIDENCE", "STALE_EVIDENCE_PRESENT"]


def test_canonical_snapshot_bytes_are_immutable_bytes():
    payload = canonical_model_feature_snapshot_bytes(mapped())
    assert isinstance(payload, bytes)
    with pytest.raises(TypeError):
        payload[0] = 0


def test_model_feature_bindings_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        MODEL_FEATURE_BINDINGS[0].source_field = "changed"
    with pytest.raises(TypeError):
        MODEL_FEATURE_BINDINGS[0] = MODEL_FEATURE_BINDINGS[1]


def test_nonmatching_same_field_name_in_wrong_category_remains_missing():
    source_fact = fact(
        category=IntelligenceCategory.WEATHER,
        field="home_form",
        value=0.9,
    )
    item = resolution(mapped([source_fact]), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.MISSING


def test_nonmatching_same_category_with_wrong_field_remains_missing():
    source_fact = fact(
        category=IntelligenceCategory.FORM,
        field="home_form_other",
        value=0.9,
    )
    item = resolution(mapped([source_fact]), ModelFeatureId.HOME_FORM)
    assert item.status is ModelFeatureStatus.MISSING


def test_builder_returns_fresh_detached_safety_mappings():
    source = intelligence_snapshot()
    first = build_model_feature_snapshot(source)
    second = build_model_feature_snapshot(source)
    assert first.safety == second.safety
    assert first.safety is not second.safety


def test_source_anchor_is_lowercase_hexadecimal():
    source_sha = mapped().source_snapshot_sha256
    assert len(source_sha) == 64
    assert source_sha == source_sha.lower()
    int(source_sha, 16)
