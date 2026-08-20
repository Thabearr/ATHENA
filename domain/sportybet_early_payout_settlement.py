"""Frozen SportyBet 1UP/2UP provider-settlement evidence.

This receipt records reviewed provider semantics only.  It is not a price
snapshot and grants no pricing, selection, execution, or betting authority.
The source inputs are small exact review projections of the official help
content and the previously captured site-configuration market keys; callers
cannot silently replace either source while retaining the receipt identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from domain.markets import MarketId


SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-early-payout-settlement-semantics-v1"
REVIEW_SCOPE = "EXACT_SPORTYBET_1UP_2UP_PROVIDER_SETTLEMENT_REVIEW"

OFFICIAL_FOOTBALL_HELP_URL = "https://www.sportybet.com/gh/help?nav=sports"
OFFICIAL_EARLY_PAYOUT_HELP_URL = "https://www.sportybet.com/tz/help?nav=others"
CAPTURED_SITE_CONFIGURATION_ID = (
    "REVIEWED_CAPTURED_SPORTYBET_SITE_CONFIGURATION_MARKET_KEYS"
)

# Exact UTF-8 review projections.  These are intentionally not described as
# complete HTML captures: the official pages are client-rendered.  The receipt
# binds the exact reviewed clauses and their official URLs.
OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES = (
    "1X2\n"
    "Which team will win the match. Overtime not included.\n"
    "1UP\n"
    "1UP will reward you earlier if your team takes a one-goal lead, e.g. "
    "1-0, 2-1. Once settled, the final result no longer matters - win, lose "
    "or draw!\n"
    "Betting on the draw in this market is the same as in regular 1X2, it is "
    "resulted on the full-time score regardless of how and when any goals are "
    "scored (which is why the odds are the same).\n"
    "2UP\n"
    "2UP will reward you earlier if your team takes a two-goal lead, e.g. "
    "2-0, 0-2, 3-1, 1-3. Once settled, the final result no longer matters - "
    "win, lose or draw!\n"
    "If a match is abandoned and a team has gone two or more goals ahead then "
    "bets on that selection will still be paid as winners.\n"
).encode("utf-8")

OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES = (
    "1UP offers an early payout if your team leads by 1 goal, regardless of "
    "the final result – win, lose, draw, or even if the match is abandoned.\n"
    "1UP is currently available on select football leagues for pre-match bets "
    "in the dedicated 1X2 - 1UP market.\n"
    "2UP offers an early payout if your team leads by 2 goals, regardless of "
    "the final result - win, lose, draw, or even if the match is abandoned.\n"
    "2UP is currently available on select football leagues on pre-match bets "
    "with a dedicated 1X2 - 2UP market.\n"
).encode("utf-8")

CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES = (
    b'["one_x_two_one_up","one_x_two_two_up"]\n'
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_SAFETY = (
    ("abandonment_probability_modeled", False),
    ("bet_authorized", False),
    ("execution_authorized", False),
    ("fresh_price_authorized", False),
    ("pricing_authorized", False),
    ("selection_authorized", False),
    ("value_authorized", False),
)


class SportyBetEarlyPayoutSettlementError(ValueError):
    """Raised when the reviewed provider-settlement boundary drifts."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_bytes(value: Any, expected: bytes, label: str) -> bytes:
    if type(value) is not bytes:
        raise SportyBetEarlyPayoutSettlementError(f"{label} must be exact bytes")
    if value != expected:
        raise SportyBetEarlyPayoutSettlementError(
            f"{label} differs from the exact reviewed source projection"
        )
    return value


@dataclass(frozen=True)
class SportyBetSettlementSourceEvidence:
    source_identity: str
    evidence_kind: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        if (
            type(self.source_identity) is not str
            or not self.source_identity
            or self.source_identity != self.source_identity.strip()
        ):
            raise SportyBetEarlyPayoutSettlementError(
                "source identity must be exact non-empty text"
            )
        if self.evidence_kind not in {
            "OFFICIAL_HELP_EXACT_REVIEW_PROJECTION",
            "CAPTURED_SITE_CONFIGURATION_CANONICAL_KEY_PROJECTION",
        }:
            raise SportyBetEarlyPayoutSettlementError("source evidence kind drifted")
        if type(self.sha256) is not str or _SHA_RE.fullmatch(self.sha256) is None:
            raise SportyBetEarlyPayoutSettlementError("source SHA-256 is invalid")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise SportyBetEarlyPayoutSettlementError("source byte size is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_identity": self.source_identity,
            "evidence_kind": self.evidence_kind,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True)
class SportyBetEarlyPayoutMarketRule:
    market_id: MarketId
    provider_configuration_key: str
    lead_threshold: int
    event_topology: str
    selected_team_settlement: str
    draw_settlement: str
    full_time_win_fallback: bool
    early_trigger_irreversible: bool
    triggered_selection_stands_if_abandoned: bool

    def __post_init__(self) -> None:
        expected = {
            MarketId.MATCH_RESULT_1UP: ("one_x_two_one_up", 1),
            MarketId.MATCH_RESULT_2UP: ("one_x_two_two_up", 2),
        }
        if type(self.market_id) is not MarketId or self.market_id not in expected:
            raise SportyBetEarlyPayoutSettlementError("unsupported early-payout market")
        if (self.provider_configuration_key, self.lead_threshold) != expected[
            self.market_id
        ]:
            raise SportyBetEarlyPayoutSettlementError(
                "provider key or lead threshold drifted"
            )
        if self.event_topology != "OVERLAPPING_EVENTS":
            raise SportyBetEarlyPayoutSettlementError("event topology drifted")
        if self.selected_team_settlement != (
            "LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN"
        ):
            raise SportyBetEarlyPayoutSettlementError(
                "selected-team settlement semantics drifted"
            )
        if self.draw_settlement != "REGULATION_TIME_FULL_TIME_DRAW":
            raise SportyBetEarlyPayoutSettlementError("draw settlement drifted")
        if (
            self.full_time_win_fallback is not True
            or self.early_trigger_irreversible is not True
            or self.triggered_selection_stands_if_abandoned is not True
        ):
            raise SportyBetEarlyPayoutSettlementError(
                "reviewed early-payout rule booleans must remain true"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "provider_configuration_key": self.provider_configuration_key,
            "lead_threshold": self.lead_threshold,
            "event_topology": self.event_topology,
            "selected_team_settlement": self.selected_team_settlement,
            "draw_settlement": self.draw_settlement,
            "full_time_win_fallback": self.full_time_win_fallback,
            "early_trigger_irreversible": self.early_trigger_irreversible,
            "triggered_selection_stands_if_abandoned": (
                self.triggered_selection_stands_if_abandoned
            ),
        }


@dataclass(frozen=True)
class SportyBetEarlyPayoutSettlementReceipt:
    schema_version: int
    dataset_name: str
    review_scope: str
    sources: tuple[SportyBetSettlementSourceEvidence, ...]
    market_rules: tuple[SportyBetEarlyPayoutMarketRule, ...]
    full_time_fallback_proof: str
    normal_completion_probability_scope: str
    safety: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.review_scope) != (
            SCHEMA_VERSION,
            DATASET_NAME,
            REVIEW_SCOPE,
        ):
            raise SportyBetEarlyPayoutSettlementError("receipt identity drifted")
        if type(self.sources) is not tuple or len(self.sources) != 3:
            raise SportyBetEarlyPayoutSettlementError("receipt requires three sources")
        if any(type(item) is not SportyBetSettlementSourceEvidence for item in self.sources):
            raise SportyBetEarlyPayoutSettlementError("receipt source type drifted")
        if type(self.market_rules) is not tuple or any(
            type(item) is not SportyBetEarlyPayoutMarketRule
            for item in self.market_rules
        ):
            raise SportyBetEarlyPayoutSettlementError("receipt rule type drifted")
        if tuple(rule.market_id for rule in self.market_rules) != (
            MarketId.MATCH_RESULT_1UP,
            MarketId.MATCH_RESULT_2UP,
        ):
            raise SportyBetEarlyPayoutSettlementError("receipt market order drifted")
        if self.full_time_fallback_proof != (
            "OFFICIAL_1X2_FULL_TIME_WIN_CONTRACT_PLUS_DEDICATED_EARLY_PAYOUT_TRIGGER"
        ):
            raise SportyBetEarlyPayoutSettlementError("full-time fallback proof drifted")
        if self.normal_completion_probability_scope != (
            "REGULATION_TIME_FOOTBALL_PATH_ONLY_ABANDONMENT_FREQUENCY_NOT_MODELED"
        ):
            raise SportyBetEarlyPayoutSettlementError("probability scope drifted")
        if self.safety != _SAFETY:
            raise SportyBetEarlyPayoutSettlementError("receipt safety drifted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "review_scope": self.review_scope,
            "sources": [item.to_dict() for item in self.sources],
            "market_rules": [item.to_dict() for item in self.market_rules],
            "full_time_fallback_proof": self.full_time_fallback_proof,
            "normal_completion_probability_scope": (
                self.normal_completion_probability_scope
            ),
            "safety": dict(self.safety),
        }


def build_sportybet_early_payout_settlement_receipt(
    *,
    official_football_help_review_bytes: bytes,
    official_early_payout_help_review_bytes: bytes,
    captured_site_configuration_projection_bytes: bytes,
) -> SportyBetEarlyPayoutSettlementReceipt:
    """Build the receipt only from the three exact reviewed source projections."""

    football = _exact_bytes(
        official_football_help_review_bytes,
        OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
        "official football help review",
    )
    early = _exact_bytes(
        official_early_payout_help_review_bytes,
        OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES,
        "official early-payout help review",
    )
    configuration = _exact_bytes(
        captured_site_configuration_projection_bytes,
        CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES,
        "captured site-configuration projection",
    )
    sources = (
        SportyBetSettlementSourceEvidence(
            OFFICIAL_FOOTBALL_HELP_URL,
            "OFFICIAL_HELP_EXACT_REVIEW_PROJECTION",
            _sha256(football),
            len(football),
        ),
        SportyBetSettlementSourceEvidence(
            OFFICIAL_EARLY_PAYOUT_HELP_URL,
            "OFFICIAL_HELP_EXACT_REVIEW_PROJECTION",
            _sha256(early),
            len(early),
        ),
        SportyBetSettlementSourceEvidence(
            CAPTURED_SITE_CONFIGURATION_ID,
            "CAPTURED_SITE_CONFIGURATION_CANONICAL_KEY_PROJECTION",
            _sha256(configuration),
            len(configuration),
        ),
    )
    rules = tuple(
        SportyBetEarlyPayoutMarketRule(
            market_id=market_id,
            provider_configuration_key=configuration_key,
            lead_threshold=threshold,
            event_topology="OVERLAPPING_EVENTS",
            selected_team_settlement=(
                "LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN"
            ),
            draw_settlement="REGULATION_TIME_FULL_TIME_DRAW",
            full_time_win_fallback=True,
            early_trigger_irreversible=True,
            triggered_selection_stands_if_abandoned=True,
        )
        for market_id, configuration_key, threshold in (
            (MarketId.MATCH_RESULT_1UP, "one_x_two_one_up", 1),
            (MarketId.MATCH_RESULT_2UP, "one_x_two_two_up", 2),
        )
    )
    return SportyBetEarlyPayoutSettlementReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        review_scope=REVIEW_SCOPE,
        sources=sources,
        market_rules=rules,
        full_time_fallback_proof=(
            "OFFICIAL_1X2_FULL_TIME_WIN_CONTRACT_PLUS_DEDICATED_EARLY_PAYOUT_TRIGGER"
        ),
        normal_completion_probability_scope=(
            "REGULATION_TIME_FOOTBALL_PATH_ONLY_ABANDONMENT_FREQUENCY_NOT_MODELED"
        ),
        safety=_SAFETY,
    )


def reviewed_sportybet_early_payout_settlement_receipt(
) -> SportyBetEarlyPayoutSettlementReceipt:
    return build_sportybet_early_payout_settlement_receipt(
        official_football_help_review_bytes=OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES,
        official_early_payout_help_review_bytes=(
            OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES
        ),
        captured_site_configuration_projection_bytes=(
            CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES
        ),
    )


def canonical_sportybet_early_payout_settlement_receipt_bytes(
    receipt: SportyBetEarlyPayoutSettlementReceipt,
) -> bytes:
    if type(receipt) is not SportyBetEarlyPayoutSettlementReceipt:
        raise TypeError("receipt must be exact SportyBetEarlyPayoutSettlementReceipt")
    rebuilt = SportyBetEarlyPayoutSettlementReceipt(
        schema_version=receipt.schema_version,
        dataset_name=receipt.dataset_name,
        review_scope=receipt.review_scope,
        sources=tuple(receipt.sources),
        market_rules=tuple(receipt.market_rules),
        full_time_fallback_proof=receipt.full_time_fallback_proof,
        normal_completion_probability_scope=receipt.normal_completion_probability_scope,
        safety=tuple(receipt.safety),
    )
    return (
        json.dumps(
            rebuilt.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_sportybet_early_payout_settlement_receipt(
    receipt: SportyBetEarlyPayoutSettlementReceipt,
) -> str:
    return _sha256(canonical_sportybet_early_payout_settlement_receipt_bytes(receipt))


def revalidate_sportybet_early_payout_settlement_receipt(
    *,
    receipt: SportyBetEarlyPayoutSettlementReceipt,
    receipt_bytes: bytes,
    official_football_help_review_bytes: bytes,
    official_early_payout_help_review_bytes: bytes,
    captured_site_configuration_projection_bytes: bytes,
) -> SportyBetEarlyPayoutSettlementReceipt:
    if type(receipt_bytes) is not bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt_bytes must be exact bytes")
    rebuilt = build_sportybet_early_payout_settlement_receipt(
        official_football_help_review_bytes=official_football_help_review_bytes,
        official_early_payout_help_review_bytes=(
            official_early_payout_help_review_bytes
        ),
        captured_site_configuration_projection_bytes=(
            captured_site_configuration_projection_bytes
        ),
    )
    rebuilt_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(rebuilt)
    if canonical_sportybet_early_payout_settlement_receipt_bytes(receipt) != rebuilt_bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt object differs from replay")
    if receipt_bytes != rebuilt_bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt bytes differ from replay")
    return rebuilt


__all__ = [
    "CAPTURED_SITE_CONFIGURATION_PROJECTION_BYTES",
    "DATASET_NAME",
    "OFFICIAL_EARLY_PAYOUT_HELP_REVIEW_BYTES",
    "OFFICIAL_EARLY_PAYOUT_HELP_URL",
    "OFFICIAL_FOOTBALL_HELP_REVIEW_BYTES",
    "OFFICIAL_FOOTBALL_HELP_URL",
    "REVIEW_SCOPE",
    "SCHEMA_VERSION",
    "SportyBetEarlyPayoutMarketRule",
    "SportyBetEarlyPayoutSettlementError",
    "SportyBetEarlyPayoutSettlementReceipt",
    "SportyBetSettlementSourceEvidence",
    "build_sportybet_early_payout_settlement_receipt",
    "canonical_sportybet_early_payout_settlement_receipt_bytes",
    "revalidate_sportybet_early_payout_settlement_receipt",
    "reviewed_sportybet_early_payout_settlement_receipt",
    "sha256_sportybet_early_payout_settlement_receipt",
]
