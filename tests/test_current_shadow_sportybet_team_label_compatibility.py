from __future__ import annotations

import pytest

from domain import current_shadow_sportybet_team_label_compatibility as labels


def test_v6_policy_is_pinned_and_only_grants_source_schema_compatibility():
    assert labels.SCHEMA_VERSION == 6
    assert labels.POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_EXACT_ONE_TRAILING_ASCII_SPACE_LABEL_COMPATIBILITY_V6"
    )
    assert labels.policy_sha256() == labels.EXPECTED_POLICY_SHA256 == (
        "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
    )
    rules = labels.policy_payload()["rules"]
    assert rules == {
        "admission_basis": "EXACTLY_ONE_TRAILING_ASCII_U_0020_ONLY",
        "field_scope": ["homeTeamName", "awayTeamName"],
        "already_trimmed_passthrough": True,
        "event_bound_allowlist_required": False,
        "generic_strip": False,
        "leading_whitespace": False,
        "multiple_trailing_spaces": False,
        "trailing_non_ascii_whitespace": False,
        "tabs_or_control_whitespace": False,
        "empty_after_projection": False,
        "raw_source_bytes_remain_authoritative": True,
        "raw_source_sha_ancestry_required": True,
        "fixture_reconciliation_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "share_code_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet_authority": False,
        "wager_placed": False,
    }
    assert labels.AUTHORITY["source_schema_compatibility"] is True
    assert all(value is False for key, value in labels.AUTHORITY.items() if key != "source_schema_compatibility")


def test_six_retained_historical_rows_remain_unchanged_and_still_project():
    expected = {
        "sr:match:73831434": (
            "homeTeamName", "Jeugd Royal Francs Borains ", "Jeugd Royal Francs Borains",
            "sr:category:33", "sr:tournament:1117",
            "9df644f04346dee648eeaaeb40756d3e063fe81f3aa68359277dceb7730033f4",
            33743684967, 9888817924,
            "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef",
        ),
        "sr:match:74207246": (
            "awayTeamName", "Comunicaciones FC ", "Comunicaciones FC",
            "sr:category:365", "sr:tournament:27396",
            "6ca26904b3682f13cf936d1b43fa273fcffd3521668c196c6e625992e272ac80",
            33743684967, 9888817924,
            "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef",
        ),
        "sr:match:73805972": (
            "homeTeamName", "SC Kiyovu ", "SC Kiyovu",
            "sr:category:951", "sr:tournament:20162",
            "aaffe08813262c4356a53acec4f697d05dcc155862cb3854385965bd779a5597",
            33907719257, 9950240221,
            "87b379f9b8163717869d3fd3d8834fc0434d548c4f2a2522120c28c0508aa609",
        ),
        "sr:match:74170884": (
            "homeTeamName", "Comunicaciones FC ", "Comunicaciones FC",
            "sr:category:365", "sr:tournament:27396",
            "d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54",
            34243048761, 10062892966,
            "bbc5434425443b38a20d0807cc3e85a269a02a446ff229ea7025d28b4cd0dea4",
        ),
        "sr:match:72474956": (
            "awayTeamName", "Comunicaciones FC ", "Comunicaciones FC",
            "sr:category:365", "sr:tournament:27396",
            "46a549f09d3d4864f8b00185b8634d427d11d219e4e0545a5e3746198ec22b11",
            34689842174, 10296832530,
            "0077d93de5c9cf729cf9bf6a0a1a9aaff91f4967ec8f0065d350baef0ce79db0",
        ),
        "sr:match:73806008": (
            "homeTeamName", "SC Kiyovu ", "SC Kiyovu",
            "sr:category:951", "sr:tournament:20162",
            "652a5fd4a33b95a4b0ed261740d486156c8fe85b8c842c659a5bc0bc39a00ce9",
            34897587697, 10369576508,
            "d056a7a93adf8c8780355ade436b4c02a772684d3ad08325aecb41f485677f9c",
        ),
    }
    assert len(labels.REVIEWED_PROJECTIONS) == 6
    assert len({row.evidence_workflow_run_id for row in labels.REVIEWED_PROJECTIONS}) == 5
    for row in labels.REVIEWED_PROJECTIONS:
        assert (
            row.field, row.raw_source_label, row.projected_label,
            row.category_id, row.tournament_id, row.source_raw_sha256,
            row.evidence_workflow_run_id, row.evidence_artifact_id,
            row.evidence_artifact_sha256,
        ) == expected[row.event_id]
        assert labels.project_team_label(
            event_id=row.event_id, field=row.field, value=row.raw_source_label
        ) == row.projected_label


def test_novel_event_exact_one_trailing_ascii_space_and_trimmed_passthrough():
    event_id = "sr:match:99999999991"
    assert labels.project_team_label(
        event_id=event_id, field="homeTeamName", value="Example Athletic "
    ) == "Example Athletic"
    assert labels.project_team_label(
        event_id=event_id, field="awayTeamName", value="Example Athletic"
    ) == "Example Athletic"


@pytest.mark.parametrize(
    "value",
    (
        " Team",
        "Team  ",
        "Team   ",
        "Team\t",
        "Team\n",
        "Team\r",
        "Team\u00a0",
        "Team\u2009",
        "Team\u3000",
        "\u00a0Team",
        "Team\u00a0 ",
        " Team ",
        " ",
        "",
        "Team\x01",
        "Team\x7f",
    ),
)
def test_all_unreviewed_or_unsafe_whitespace_shapes_fail_closed(value):
    with pytest.raises(labels.CurrentShadowSportyBetTeamLabelCompatibilityError):
        labels.project_team_label(
            event_id="sr:match:99999999991", field="homeTeamName", value=value
        )


def test_invalid_field_type_and_source_bounds_fail_closed():
    for field in ("teamName", "home_team_name", "" ):
        with pytest.raises(labels.CurrentShadowSportyBetTeamLabelCompatibilityError):
            labels.project_team_label(
                event_id="sr:match:99999999991", field=field, value="Example"
            )
    for event_id in (None, ""):
        with pytest.raises(labels.CurrentShadowSportyBetTeamLabelCompatibilityError):
            labels.project_team_label(
                event_id=event_id, field="homeTeamName", value="Example"
            )
    for value in (None, 42, "x" * 301):
        with pytest.raises(labels.CurrentShadowSportyBetTeamLabelCompatibilityError):
            labels.project_team_label(
                event_id="sr:match:99999999991", field="homeTeamName", value=value
            )
