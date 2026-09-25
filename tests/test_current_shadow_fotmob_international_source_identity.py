from __future__ import annotations

import copy

import pytest

from config.competition_review_priority import (
    CompetitionKind,
    CompetitionScope,
    INTERNATIONAL_COMPETITION_REVIEW_PRIORITY,
)
from domain.current_shadow_fotmob_international_source_identity import (
    OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES,
    P4_4K_ARTIFACT_ID,
    P4_4K_ARTIFACT_SHA256,
    P4_4K_CAPTURE_MANIFEST_SHA256,
    P4_4K_CAPTURE_RAW_SHA256,
    P4_4K_EXACT_MAIN_SHA,
    P4_4K_REQUEST_DATE,
    P4_4K_WORKFLOW_RUN_ID,
    PINNED_POLICY_SHA256,
    POLICY_ID,
    InternationalSourceCoverageState,
    international_hierarchy_coverage_table,
    international_source_identity_policy_payload,
    international_source_identity_policy_sha256,
    resolve_current_shadow_international_source_priority,
    reviewed_current_fotmob_international_source_identity,
)


EXPECTED_ACTIVE = {
    ("INT", 9806): ("Nations League", "INT-D", 40, CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE),
    ("INT", 9807): ("Nations League", "INT-D", 40, CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE),
    ("INT", 9808): ("Nations League", "INT-D", 40, CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE),
    ("INT", 9821): ("Nations League", "INT-D", 40, CompetitionKind.INTERNATIONAL_NATIONS_LEAGUE),
    ("INT", 10608): (
        "Continental Championship Qualification",
        "INT-C",
        30,
        CompetitionKind.INTERNATIONAL_QUALIFIER,
    ),
    ("INT", 114): (
        "International Friendly",
        "INT-F",
        60,
        CompetitionKind.INTERNATIONAL_FRIENDLY,
    ),
    ("INT", 10437): (
        "Youth / Olympic International",
        "INT-G",
        70,
        CompetitionKind.INTERNATIONAL_YOUTH,
    ),
    ("INT", 9833): (
        "Youth / Olympic International",
        "INT-G",
        70,
        CompetitionKind.INTERNATIONAL_YOUTH,
    ),
}


@pytest.mark.parametrize("key,expected", sorted(EXPECTED_ACTIVE.items()))
def test_exact_reviewed_current_source_identity_resolves_into_existing_hierarchy(
    key, expected
) -> None:
    entry = resolve_current_shadow_international_source_priority(
        source_competition_ccode=key[0],
        source_competition_primary_id=key[1],
    )
    assert entry is not None
    assert (entry.canonical_name, entry.priority_band, entry.rank, entry.kind) == expected
    assert entry.scope is CompetitionScope.INTERNATIONAL


@pytest.mark.parametrize("key", sorted(EXPECTED_ACTIVE))
def test_wrong_source_country_code_never_resolves(key) -> None:
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode="NGA",
            source_competition_primary_id=key[1],
        )
        is None
    )


@pytest.mark.parametrize("primary_id", [10437, 9833, 13287])
def test_unqualified_or_observation_only_source_identities_fail_closed(primary_id) -> None:
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode="INT",
            source_competition_primary_id=primary_id,
        )
        is not None
    ) is (primary_id in {10437, 9833})


def test_display_name_is_not_an_identity_key_but_metadata_may_change() -> None:
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode="INT",
            source_competition_primary_id=999999,
        )
        is None
    )
    record = reviewed_current_fotmob_international_source_identity(
        source_competition_ccode="INT",
        source_competition_primary_id=9806,
    )
    assert record is not None
    assert record.key == ("INT", 9806)
    # Runtime resolution takes no display-name argument: labels are evidence
    # metadata, not identity selectors.
    assert record.observed_source_labels == ("UEFA Nations League A Grp. 1",)


@pytest.mark.parametrize("bad_ccode", [None, 1, True, "", " int", "INT "])
def test_malformed_country_code_fails_closed(bad_ccode) -> None:
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode=bad_ccode,
            source_competition_primary_id=9806,
        )
        is None
    )


@pytest.mark.parametrize("bad_id", [True, False, "9806", 9806.0, None])
def test_non_exact_integer_primary_id_fails_closed(bad_id) -> None:
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode="INT",
            source_competition_primary_id=bad_id,
        )
        is None
    )


def test_all_existing_international_hierarchy_entries_have_explicit_coverage() -> None:
    table = international_hierarchy_coverage_table()
    assert len(table) == len(INTERNATIONAL_COMPETITION_REVIEW_PRIORITY) == 12
    assert {(row.priority_band) for row in table} == {
        "INT-S", "INT-A", "INT-B", "INT-C", "INT-D", "INT-E", "INT-F", "INT-G"
    }
    assert all(row.scope is CompetitionScope.INTERNATIONAL for row in table)
    assert all(row.canonical_name and row.competition_kind for row in table)
    active = {
        (identity.source_competition_ccode, identity.source_competition_primary_id)
        for row in table
        for identity in row.active_source_identities
    }
    assert active == set(EXPECTED_ACTIVE)
    assert all(
        row.coverage_state is InternationalSourceCoverageState.QUALIFIED_CURRENT_SOURCE_IDENTITY
        for row in table
        if row.active_source_identities
    )
    assert all(
        row.coverage_state
        is InternationalSourceCoverageState.NO_REVIEWED_CURRENT_SOURCE_IDENTITY_EVIDENCE
        for row in table
        if not row.active_source_identities
    )


def test_p4_4k_class_evidence_keeps_youth_source_admission_separate_from_authority() -> None:
    youth_rows = [
        identity
        for row in international_hierarchy_coverage_table()
        if row.priority_band == "INT-G"
        for identity in row.active_source_identities
    ]
    assert {identity.source_competition_primary_id for identity in youth_rows} == {
        10437, 9833
    }
    assert all("U21" in item.class_evidence or "U23" in item.class_evidence for item in youth_rows)
    assert all(item.workflow_run_id == P4_4K_WORKFLOW_RUN_ID for item in youth_rows)
    assert all(item.artifact_id == P4_4K_ARTIFACT_ID for item in youth_rows)
    assert all(item.artifact_sha256 == P4_4K_ARTIFACT_SHA256 for item in youth_rows)


def test_13287_is_explicitly_observed_but_unqualified() -> None:
    assert len(OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES) == 1
    observed = OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES[0]
    assert observed.key == ("INT", 13287)
    assert "does not independently establish" in observed.reason
    assert (
        resolve_current_shadow_international_source_priority(
            source_competition_ccode="INT",
            source_competition_primary_id=13287,
        )
        is None
    )


def test_policy_payload_is_deterministic_and_p4_4k_anchors_are_exact() -> None:
    payload = international_source_identity_policy_payload()
    assert payload == copy.deepcopy(international_source_identity_policy_payload())
    assert payload["policy_id"] == POLICY_ID
    assert payload["p4_4k_evidence"] == {
        "workflow_run_id": 36136878384,
        "exact_main_sha": "b17e97dbea043d45d47db9ad2011354fe4682baf",
        "artifact_id": 10865656841,
        "artifact_sha256": "3d8733e2bd9ed1ad4eef94b877e22603e1043fa5a658801548223b5c298c48b8",
        "capture_manifest_sha256": "759eb16f0daac610efdc9d9532bd7d8348b153c35c11a041b772f2fc83ec1670",
        "capture_raw_sha256": "9246263b90f1b997fce87a2cff4d4918d06cc2e446055c3f80b7eef4bbfe6210",
        "request_date": "20260925",
        "capture_observed_at": "2026-09-25T12:47:40.911642Z",
        "capture_timezone": "UTC",
        "capture_ccode3": "NGA",
        "http_status": 200,
        "network_acquisition_performed_in_prior_evidence": True,
    }
    assert international_source_identity_policy_sha256() == PINNED_POLICY_SHA256
    assert PINNED_POLICY_SHA256 != "PENDING"


def test_policy_authority_flags_remain_false() -> None:
    assert all(value is False for value in international_source_identity_policy_payload()["authority"].values())
