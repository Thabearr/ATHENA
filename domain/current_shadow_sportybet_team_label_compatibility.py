"""Evidence-bound SportyBet team-label compatibility for current Shadow fanout.

The provider evidence captured by workflow run 33743684967 proved exactly two
current event labels with one trailing ASCII space. This module does not define a
generic trimming rule. It admits only the exact reviewed (event id, source field,
raw label) tuples below and projects them to the exact reviewed label used by the
existing reconciliation boundary.

The retained raw provider response and SHA-256 remain the source evidence. This
policy grants no fixture-reconciliation, model, pricing, selection, transport,
login, wallet, staking, BET, or wager authority by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_EXACT_PROVIDER_TRAILING_SPACE_LABEL_COMPATIBILITY_V1"
EVIDENCE_WORKFLOW_RUN_ID = 33743684967
EVIDENCE_ARTIFACT_ID = 9888817924
EVIDENCE_ARTIFACT_SHA256 = (
    "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef"
)
EXPECTED_POLICY_SHA256 = (
    "babb46c993d589b00b57968c9a2a1b445b4ab50cdf01e48e38b33d4f27ed4db0"
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
            ),
        )
    )
)

_PROJECTION_BY_KEY = MappingProxyType(
    {
        (row.event_id, row.field, row.raw_source_label): row.projected_label
        for row in REVIEWED_PROJECTIONS
    }
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
        "evidence": {
            "workflow_run_id": EVIDENCE_WORKFLOW_RUN_ID,
            "artifact_id": EVIDENCE_ARTIFACT_ID,
            "artifact_sha256": EVIDENCE_ARTIFACT_SHA256,
        },
        "projections": [
            {
                "event_id": row.event_id,
                "field": row.field,
                "raw_source_label": row.raw_source_label,
                "projected_label": row.projected_label,
                "category_id": row.category_id,
                "tournament_id": row.tournament_id,
                "source_raw_sha256": row.source_raw_sha256,
            }
            for row in REVIEWED_PROJECTIONS
        ],
        "rules": {
            "exact_tuple_only": True,
            "generic_strip": False,
            "leading_space": False,
            "multiple_trailing_spaces": False,
            "tabs_or_other_whitespace": False,
            "unknown_event_or_label": False,
            "raw_source_bytes_remain_authoritative": True,
            "fixture_reconciliation_authority": False,
            "pricing_authority": False,
            "selection_authority": False,
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
        }
    )


def project_team_label(*, event_id: Any, field: str, value: Any) -> str:
    """Return exact source text or one exact reviewed evidence-bound projection.

    Already-trimmed labels pass through unchanged. Any non-trimmed label must match
    one of the two exact reviewed tuples above. No dynamic ``strip`` or other
    normalization is performed.
    """
    if field not in ("homeTeamName", "awayTeamName"):
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "team-label compatibility field is not reviewed"
        )
    if type(event_id) is not str or not event_id:
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "team-label compatibility event_id is invalid"
        )
    if type(value) is not str or not value or any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value
    ):
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "provider team label must be bounded source text"
        )
    if value == value.strip():
        return value
    projected = _PROJECTION_BY_KEY.get((event_id, field, value))
    if projected is None:
        raise CurrentShadowSportyBetTeamLabelCompatibilityError(
            "provider team label whitespace shape is outside reviewed evidence"
        )
    return projected


validate_policy()
