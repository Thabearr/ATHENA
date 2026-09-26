from __future__ import annotations

import pytest

from domain import current_shadow_sportybet_international_provider_family_bridge as bridge


def _classify(source_primary: int, category: str, category_name: str, tournament: str, tournament_name: str):
    return bridge.classify_source_provider_family(
        source_ccode="INT",
        source_primary_id=source_primary,
        provider_category_id=category,
        provider_category_name=category_name,
        provider_tournament_id=tournament,
        provider_tournament_name=tournament_name,
    )


def test_policy_is_deterministic_and_binds_both_reviewed_receipt_ancestries():
    assert bridge.POLICY_ID == "ATHENA_CURRENT_SHADOW_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE_V1"
    assert bridge.calculate_policy_sha256() == bridge.PINNED_POLICY_SHA256
    payload = bridge.policy_payload()
    assert payload["source_authority"] == {
        "policy_id": bridge.SOURCE_POLICY_ID,
        "policy_sha256": "f4a50b836540d4dd797631f50215598d852aab05a9c2e9a65ff8069afcde570b",
        "receipt_sha256": "15f8b85ba2ef5c9a8dd65fa262eb44a49b61070040cd7ea09985416c063cd91f",
    }
    assert payload["provider_source_authority"] == {
        "policy_id": bridge.PROVIDER_SOURCE_POLICY_ID,
        "policy_sha256": "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075",
        "receipt_sha256": "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34",
    }
    assert payload["provider_only_unmapped_observation"]["tournament_id"] == "sr:tournament:622"
    assert payload["authority"]["current_shadow_runtime_discovery"] is False
    assert payload["authority"]["p3_runtime_discovery"] is False


@pytest.mark.parametrize(
    "source_primary,provider_tournament,provider_name,canonical,band,kind",
    [
        (9806, "sr:tournament:23755", "UEFA Nations League", "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9807, "sr:tournament:23755", "UEFA Nations League", "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9808, "sr:tournament:23755", "UEFA Nations League", "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9821, "sr:tournament:27420", "CONCACAF Nations League", "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (10608, "sr:tournament:1848", "Africa Cup of Nations Qualification", "Continental Championship Qualification", "INT-C", "INTERNATIONAL_QUALIFIER"),
        (114, "sr:tournament:851", "Int. Friendly Games", "International Friendly", "INT-F", "INTERNATIONAL_FRIENDLY"),
    ],
)
def test_only_exact_evidence_qualified_source_provider_pairs_resolve(
    source_primary, provider_tournament, provider_name, canonical, band, kind,
):
    result = _classify(source_primary, "sr:category:4", "International", provider_tournament, provider_name)
    assert result is bridge.InternationalProviderFamilyClassification.EXACT_REVIEWED_MAPPING
    row = bridge.mapping_for_exact_pair(
        source_ccode="INT", source_primary_id=source_primary,
        provider_category_id="sr:category:4", provider_category_name="International",
        provider_tournament_id=provider_tournament, provider_tournament_name=provider_name,
    )
    assert row is not None
    assert (row.source_canonical_name, row.source_priority_band, row.source_competition_kind.value) == (canonical, band, kind)


@pytest.mark.parametrize(
    "source_primary,provider_tournament,provider_name",
    [
        (9821, "sr:tournament:23755", "UEFA Nations League"),
        (9806, "sr:tournament:27420", "CONCACAF Nations League"),
        (10608, "sr:tournament:851", "Int. Friendly Games"),
        (114, "sr:tournament:1848", "Africa Cup of Nations Qualification"),
    ],
)
def test_known_source_cannot_be_relabelled_to_another_provider_family(source_primary, provider_tournament, provider_name):
    assert _classify(source_primary, "sr:category:4", "International", provider_tournament, provider_name) is bridge.InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT


def test_provider_pair_requires_permitted_source_key_and_exact_wrapper_labels():
    assert _classify(999999, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League") is bridge.InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT
    assert _classify(9821, "sr:category:9", "International", "sr:tournament:27420", "CONCACAF Nations League") is bridge.InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT
    assert _classify(9821, "sr:category:4", "International", "CONCACAF", "CONCACAF Nations League") is bridge.InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT
    assert _classify(9821, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League B Grp. 3") is bridge.InternationalProviderFamilyClassification.REVIEWED_SOURCE_PROVIDER_CONFLICT


@pytest.mark.parametrize(
    "source_primary,expected",
    [
        (10437, bridge.InternationalProviderFamilyClassification.QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING),
        (9833, bridge.InternationalProviderFamilyClassification.QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING),
        (13287, bridge.InternationalProviderFamilyClassification.OBSERVED_UNQUALIFIED_SOURCE_IDENTITY),
    ],
)
def test_unmapped_and_unqualified_international_identities_never_fall_through(source_primary, expected):
    assert _classify(source_primary, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League") is expected


def test_provider_only_gulf_cup_and_unknown_identities_remain_not_applicable():
    assert _classify(999999, "sr:category:4", "International", "sr:tournament:622", "Gulf Cup") is bridge.InternationalProviderFamilyClassification.NOT_APPLICABLE
    assert _classify(999999, "sr:category:26", "USA", "sr:tournament:242", "MLS") is bridge.InternationalProviderFamilyClassification.NOT_APPLICABLE
    assert bridge.provider_pair_is_reviewed_international_family("sr:category:4", "sr:tournament:622") is False


def test_source_and_provider_keys_are_type_strict_and_exact():
    for ccode, primary in (("int", 9821), ("INT", True), (None, 9821), ("INT", "9821")):
        assert bridge.classify_source_provider_family(
            source_ccode=ccode,
            source_primary_id=primary,
            provider_category_id="sr:category:4",
            provider_category_name="International",
            provider_tournament_id="sr:tournament:27420",
            provider_tournament_name="CONCACAF Nations League",
        ) is bridge.InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT


def test_uefa_many_to_one_is_bounded_to_exact_three_source_keys():
    rows = [row for row in bridge.REVIEWED_MAPPINGS if row.provider_tournament_id == "sr:tournament:23755"]
    assert {row.source_key for row in rows} == {("INT", 9806), ("INT", 9807), ("INT", 9808)}
    assert {row.mapping_cardinality for row in rows} == {"MANY_SOURCE_IDENTITIES_TO_ONE_PROVIDER_FAMILY"}
    assert len(bridge.REVIEWED_MAPPINGS) == 6
