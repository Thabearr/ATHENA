"""Narrow SportyBet source-schema compatibility for team-label fields.

Five retained hosted captures contain six immutable event-bound evidence rows
with exactly one trailing ASCII U+0020. V6 promotes only that repeated shape:
already-trimmed labels pass unchanged, and exactly one final ASCII space may be
projected away. The six historical rows remain evidence examples, not an
event-based admission allowlist. Raw provider bytes and page-SHA ancestry remain
authoritative.

This policy grants source-schema compatibility only; it independently grants
no fixture-reconciliation, model, pricing, selection, transport, account, or
wager authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA_VERSION = 6
POLICY_ID = "ATHENA_CURRENT_SHADOW_EXACT_ONE_TRAILING_ASCII_SPACE_LABEL_COMPATIBILITY_V6"
EVIDENCE_WORKFLOW_RUN_ID = 33743684967
EVIDENCE_ARTIFACT_ID = 9888817924
EVIDENCE_ARTIFACT_SHA256 = (
    "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef"
)
LATEST_EVIDENCE_WORKFLOW_RUN_ID = 33907719257
LATEST_EVIDENCE_ARTIFACT_ID = 9950240221
LATEST_EVIDENCE_ARTIFACT_SHA256 = (
    "87b379f9b8163717869d3fd3d8834fc0434d548c4f2a2522120c28c0508aa609"
)
CURRENT_EVIDENCE_WORKFLOW_RUN_ID = 34243048761
CURRENT_EVIDENCE_ARTIFACT_ID = 10062892966
CURRENT_EVIDENCE_ARTIFACT_SHA256 = (
    "bbc5434425443b38a20d0807cc3e85a269a02a446ff229ea7025d28b4cd0dea4"
)
P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID = 34689842174
P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID = 10296832530
P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256 = (
    "0077d93de5c9cf729cf9bf6a0a1a9aaff91f4967ec8f0065d350baef0ce79db0"
)
P3_E1_BLOCKER_EVIDENCE_CATALOG_RAW_SHA256 = (
    "94d5826c753c675063cbae29a4adcd76f85e30f5ca9913efefe981cd2c70a1e5"
)
P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256 = (
    "46a549f09d3d4864f8b00185b8634d427d11d219e4e0545a5e3746198ec22b11"
)
P3_E1_BLOCKER_EVIDENCE_OBSERVED_AT = "2026-09-12T11:01:42.950736Z"
POST_PR360_P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID = 34897587697
POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID = 10369576508
POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256 = (
    "d056a7a93adf8c8780355ade436b4c02a772684d3ad08325aecb41f485677f9c"
)
POST_PR360_P3_E1_BLOCKER_EVIDENCE_CATALOG_RAW_SHA256 = (
    "57d15deab140a60aa39c92ce24799e1a56a99cf549c753a7bb0a5a8e53696d1b"
)
POST_PR360_P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256 = (
    "652a5fd4a33b95a4b0ed261740d486156c8fe85b8c842c659a5bc0bc39a00ce9"
)
POST_PR360_P3_E1_BLOCKER_EVIDENCE_OBSERVED_AT = "2026-09-14T21:16:10.040050Z"
EXPECTED_POLICY_SHA256 = (
    "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
)


class CurrentShadowSportyBetTeamLabelCompatibilityError(ValueError):
    """Raised when a source label is outside the exact reviewed compatibility set."""


@dataclass(frozen=True, order=True)
class ReviewedTeamLabelProjection:
    event_id: str
    field: str
    raw_source_label: str
    projected_label: str
    category_id: str
    tournament_id: str
    source_raw_sha256: str
    evidence_workflow_run_id: int
    evidence_artifact_id: int
    evidence_artifact_sha256: str


REVIEWED_PROJECTIONS = tuple(
    sorted(
        (
            ReviewedTeamLabelProjection(
                event_id="sr:match:73831434",
                field="homeTeamName",
                raw_source_label="Jeugd Royal Francs Borains ",
                projected_label="Jeugd Royal Francs Borains",
                category_id="sr:category:33",
                tournament_id="sr:tournament:1117",
                source_raw_sha256=(
                    "9df644f04346dee648eeaaeb40756d3e063fe81f3aa68359277dceb7730033f4"
                ),
                evidence_workflow_run_id=EVIDENCE_WORKFLOW_RUN_ID,
                evidence_artifact_id=EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=EVIDENCE_ARTIFACT_SHA256,
            ),
            ReviewedTeamLabelProjection(
                event_id="sr:match:74207246",
                field="awayTeamName",
                raw_source_label="Comunicaciones FC ",
                projected_label="Comunicaciones FC",
                category_id="sr:category:365",
                tournament_id="sr:tournament:27396",
                source_raw_sha256=(
                    "6ca26904b3682f13cf936d1b43fa273fcffd3521668c196c6e625992e272ac80"
                ),
                evidence_workflow_run_id=EVIDENCE_WORKFLOW_RUN_ID,
                evidence_artifact_id=EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=EVIDENCE_ARTIFACT_SHA256,
            ),
            ReviewedTeamLabelProjection(
                event_id="sr:match:73805972",
                field="homeTeamName",
                raw_source_label="SC Kiyovu ",
                projected_label="SC Kiyovu",
                category_id="sr:category:951",
                tournament_id="sr:tournament:20162",
                source_raw_sha256=(
                    "aaffe08813262c4356a53acec4f697d05dcc155862cb3854385965bd779a5597"
                ),
                evidence_workflow_run_id=LATEST_EVIDENCE_WORKFLOW_RUN_ID,
                evidence_artifact_id=LATEST_EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=LATEST_EVIDENCE_ARTIFACT_SHA256,
            ),
            ReviewedTeamLabelProjection(
                event_id="sr:match:74170884",
                field="homeTeamName",
                raw_source_label="Comunicaciones FC ",
                projected_label="Comunicaciones FC",
                category_id="sr:category:365",
                tournament_id="sr:tournament:27396",
                source_raw_sha256=(
                    "d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54"
                ),
                evidence_workflow_run_id=CURRENT_EVIDENCE_WORKFLOW_RUN_ID,
                evidence_artifact_id=CURRENT_EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=CURRENT_EVIDENCE_ARTIFACT_SHA256,
            ),
            ReviewedTeamLabelProjection(
                event_id="sr:match:72474956",
                field="awayTeamName",
                raw_source_label="Comunicaciones FC ",
                projected_label="Comunicaciones FC",
                category_id="sr:category:365",
                tournament_id="sr:tournament:27396",
                source_raw_sha256=P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256,
                evidence_workflow_run_id=P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID,
                evidence_artifact_id=P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256,
            ),
            ReviewedTeamLabelProjection(
                event_id="sr:match:73806008",
                field="homeTeamName",
                raw_source_label="SC Kiyovu ",
                projected_label="SC Kiyovu",
                category_id="sr:category:951",
                tournament_id="sr:tournament:20162",
                source_raw_sha256=(
                    POST_PR360_P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256
                ),
                evidence_workflow_run_id=(
                    POST_PR360_P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID
                ),
                evidence_artifact_id=POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID,
                evidence_artifact_sha256=(
                    POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256
                ),
            ),
        )
    )
)

AUTHORITY = MappingProxyType(
    {
        "source_schema_compatibility": True,
        "fixture_reconciliation": False,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "share_code_transport": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def policy_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "evidence_artifacts": [
            {
                "workflow_run_id": EVIDENCE_WORKFLOW_RUN_ID,
                "artifact_id": EVIDENCE_ARTIFACT_ID,
                "artifact_sha256": EVIDENCE_ARTIFACT_SHA256,
            },
            {
                "workflow_run_id": LATEST_EVIDENCE_WORKFLOW_RUN_ID,
                "artifact_id": LATEST_EVIDENCE_ARTIFACT_ID,
                "artifact_sha256": LATEST_EVIDENCE_ARTIFACT_SHA256,
            },
            {
                "workflow_run_id": CURRENT_EVIDENCE_WORKFLOW_RUN_ID,
                "artifact_id": CURRENT_EVIDENCE_ARTIFACT_ID,
                "artifact_sha256": CURRENT_EVIDENCE_ARTIFACT_SHA256,
            },
            {
                "workflow_run_id": P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID,
                "artifact_id": P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID,
                "artifact_sha256": P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256,
            },
            {
                "workflow_run_id": POST_PR360_P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID,
                "artifact_id": POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID,
                "artifact_sha256": (
                    POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256
                ),
            },
        ],
        "historical_evidence_examples": [
            {
                "event_id": row.event_id,
                "field": row.field,
                "raw_source_label": row.raw_source_label,
                "projected_label": row.projected_label,
                "category_id": row.category_id,
                "tournament_id": row.tournament_id,
                "source_raw_sha256": row.source_raw_sha256,
                "evidence_workflow_run_id": row.evidence_workflow_run_id,
                "evidence_artifact_id": row.evidence_artifact_id,
                "evidence_artifact_sha256": row.evidence_artifact_sha256,
            }
            for row in REVIEWED_PROJECTIONS
        ],
        "rules": {
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
        },
    }


def policy_sha256() -> str:
    return hashlib.sha256(_canonical(policy_payload())).hexdigest()


def validate_policy() -> Mapping[str, str]:
    actual = policy_sha256()
    if actual != EXPECTED_POLICY_SHA256:
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "SportyBet team-label compatibility policy identity drifted"
        )
    return MappingProxyType(
        {
            "policy_id": POLICY_ID,
            "policy_sha256": actual,
            "evidence_artifact_sha256": EVIDENCE_ARTIFACT_SHA256,
            "latest_evidence_artifact_sha256": LATEST_EVIDENCE_ARTIFACT_SHA256,
            "current_evidence_artifact_sha256": CURRENT_EVIDENCE_ARTIFACT_SHA256,
            "p3_e1_blocker_evidence_artifact_sha256": (
                P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256
            ),
            "post_pr360_p3_e1_blocker_evidence_artifact_sha256": (
                POST_PR360_P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256
            ),
        }
    )


def project_team_label(*, event_id: Any, field: str, value: Any) -> str:
    """Return exact text, or project exactly one final ASCII U+0020.

    ``event_id`` remains validated contextual evidence, but is not an admission
    key. ``strip`` is used only as an equality predicate; output projection is
    the exact prefix obtained by removing one final ASCII space.
    """
    if field not in ("homeTeamName", "awayTeamName"):
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "team-label compatibility field is not reviewed"
        )
    if type(event_id) is not str or not event_id:
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "team-label compatibility event_id is invalid"
        )
    if (
        type(value) is not str
        or not value
        or len(value) > 300
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "provider team label must be bounded source text"
        )
    if value == value.strip():
        return value
    if not value.endswith(" "):
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "provider team label whitespace shape is outside reviewed evidence"
        )
    base = value[:-1]
    if not base or base != base.strip():
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "provider team label whitespace shape is outside reviewed evidence"
        )
    return base


validate_policy()
