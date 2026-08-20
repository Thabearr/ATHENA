"""Frozen SportyBet Nigeria 1UP/2UP provider-settlement evidence.

This receipt records reviewed provider semantics and exact Nigeria provider
identity ancestry only. It is not a price snapshot and grants no pricing,
selection, execution, or betting authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from domain.markets import MarketId


SCHEMA_VERSION = 2
DATASET_NAME = "athena-sportybet-ng-early-payout-settlement-semantics-v2"
REVIEW_SCOPE = "EXACT_SPORTYBET_NIGERIA_1UP_2UP_PROVIDER_SETTLEMENT_REVIEW"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_EVIDENCE_PATH = REPOSITORY_ROOT / "artifacts" / "research-manifests" / "sportybet-ng-early-payout-settlement-source-evidence-v1.json"
SOURCE_EVIDENCE_SHA256 = "af371490fb3e72dc9b5d3422a6b36af28ff4246ee6ead23b0c957e26c398afe4"
SOURCE_EVIDENCE_SIZE = 2_059
OFFICIAL_NIGERIA_FOOTBALL_HELP_URL = "https://lite.sportybet.com/ng/help?nav=sports"
OFFICIAL_NIGERIA_HELP_SECTION_SHA256 = "b28ce8535057454e5ff93f562dea3fb6178439707f7cbf542c155366ef5cdab7"
OFFICIAL_NIGERIA_HELP_SECTION_SIZE = 1_125
PRESERVED_NIGERIA_CONFIGURATION_FILE = "www_sportybet_com 2.html"
PRESERVED_NIGERIA_CONFIGURATION_SHA256 = "c27ea6ee2eff74eb1f6ca8c90d241d63ece333171196225439c0e97a2faf86c7"
PRESERVED_NIGERIA_CONFIGURATION_SIZE = 118_608
ONE_UP_PROVIDER_SOURCE_MARKET_ID = "1"
ONE_UP_PROVIDER_MAPPED_MARKET_ID = "60200"
TWO_UP_PROVIDER_SOURCE_MARKET_ID = "1"
TWO_UP_PROVIDER_MAPPED_MARKET_ID = "60100"

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
_EXPECTED_CLAUSES = {
    "1X2": "Which team will win the match. Overtime not included.",
    "1UP": "1UP will reward you earlier if your team takes a one-goal lead, e.g. 1-0, 2-1. Once settled, the final result no longer matters - win, lose or draw!",
    "1UP_DRAW": "Betting on the draw in this market is the same as in regular 1X2, it is resulted on the full-time score regardless of how and when any goals are scored (which is why the odds are the same).",
    "2UP": "2UP will reward you earlier if your team takes a two-goal lead, e.g. 2-0, 0-2, 3-1, 1-3. Once settled, the final result no longer matters - win, lose or draw!",
    "2UP_ABANDONMENT": "If a match is abandoned and a team has gone two or more goals ahead then bets on that selection will still be paid as winners.",
    "FOOTBALL_INTERRUPTION": "If a match is interrupted and continued within 48h after initial kickoff, all open bets will be settled with the final result. Otherwise all undecided bets are considered void.",
}
_EXPECTED_MARKET_MAPPINGS = (
    {"enabled": {"live": True, "pre_match": True}, "mapped_market_id": "60200", "name": "1UP", "provider_configuration_key": "one_x_two_one_up", "source_market_id": "1", "support_sport_ids": ["sr:sport:1"]},
    {"enabled": {"live": True, "pre_match": True}, "mapped_market_id": "60100", "name": "2UP", "provider_configuration_key": "one_x_two_two_up", "source_market_id": "1", "support_sport_ids": ["sr:sport:1"]},
)


class SportyBetEarlyPayoutSettlementError(ValueError):
    """Raised when the reviewed provider-settlement boundary drifts."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SportyBetEarlyPayoutSettlementError("source evidence is not canonical JSON") from exc


def _source_manifest(value: bytes) -> dict[str, Any]:
    if type(value) is not bytes:
        raise SportyBetEarlyPayoutSettlementError("source evidence manifest must be exact bytes")
    if len(value) != SOURCE_EVIDENCE_SIZE or _sha256(value) != SOURCE_EVIDENCE_SHA256:
        raise SportyBetEarlyPayoutSettlementError("source evidence manifest identity differs from reviewed evidence")
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SportyBetEarlyPayoutSettlementError("source evidence manifest is invalid JSON") from exc
    if type(parsed) is not dict or _canonical_json_bytes(parsed) != value:
        raise SportyBetEarlyPayoutSettlementError("source evidence manifest is not exact canonical JSON")
    if parsed.get("schema_version") != 1 or parsed.get("dataset_name") != "athena-sportybet-ng-early-payout-settlement-source-evidence-v1":
        raise SportyBetEarlyPayoutSettlementError("source evidence manifest identity drifted")
    if parsed.get("official_help") != {
        "capture_kind": "OFFICIAL_NIGERIA_RENDERED_HELP_SECTION",
        "captured_at": "2026-08-20T09:40:08Z",
        "clauses": _EXPECTED_CLAUSES,
        "jurisdiction": "Nigeria",
        "url": OFFICIAL_NIGERIA_FOOTBALL_HELP_URL,
    }:
        raise SportyBetEarlyPayoutSettlementError("official Nigeria help evidence drifted")
    if parsed.get("configuration_capture") != {
        "byte_size": PRESERVED_NIGERIA_CONFIGURATION_SIZE,
        "canonical_url": "https://www.sportybet.com/ng/sport/football/England/Premier_League/Arsenal_vs_Coventry_City/sr:match:72221154",
        "country_code": "234",
        "country_name": "Nigeria",
        "file_name": PRESERVED_NIGERIA_CONFIGURATION_FILE,
        "market_mappings": list(_EXPECTED_MARKET_MAPPINGS),
        "prefix": "ng",
        "settlement_feature_lists": {"one_up": [[1, 60200]], "two_up": [[1, 60100]]},
        "sha256": PRESERVED_NIGERIA_CONFIGURATION_SHA256,
    }:
        raise SportyBetEarlyPayoutSettlementError("preserved Nigeria configuration ancestry drifted")
    return parsed


def source_evidence_manifest_bytes() -> bytes:
    try:
        value = SOURCE_EVIDENCE_PATH.read_bytes()
    except OSError as exc:
        raise SportyBetEarlyPayoutSettlementError("reviewed source evidence manifest is unavailable") from exc
    _source_manifest(value)
    return value


@dataclass(frozen=True)
class SportyBetSettlementSourceEvidence:
    source_identity: str
    evidence_kind: str
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        if type(self.source_identity) is not str or not self.source_identity or self.source_identity != self.source_identity.strip():
            raise SportyBetEarlyPayoutSettlementError("source identity must be exact non-empty text")
        if self.evidence_kind not in {"OFFICIAL_NIGERIA_RENDERED_HELP_SECTION", "PRESERVED_NIGERIA_RAW_SITE_CONFIGURATION"}:
            raise SportyBetEarlyPayoutSettlementError("source evidence kind drifted")
        if type(self.sha256) is not str or _SHA_RE.fullmatch(self.sha256) is None:
            raise SportyBetEarlyPayoutSettlementError("source SHA-256 is invalid")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise SportyBetEarlyPayoutSettlementError("source byte size is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"source_identity": self.source_identity, "evidence_kind": self.evidence_kind, "sha256": self.sha256, "byte_size": self.byte_size}


@dataclass(frozen=True)
class SportyBetEarlyPayoutMarketRule:
    market_id: MarketId
    provider_configuration_key: str
    provider_source_market_id: str
    provider_mapped_market_id: str
    provider_pre_match_enabled: bool
    provider_live_enabled: bool
    provider_settlement_feature_enabled: bool
    lead_threshold: int
    event_topology: str
    selected_team_settlement: str
    draw_settlement: str
    full_time_win_fallback: bool
    early_trigger_irreversible: bool
    triggered_selection_abandonment_proof_clause_ids: tuple[str, ...]
    triggered_selection_stands_if_abandoned: bool

    def __post_init__(self) -> None:
        expected = {
            MarketId.MATCH_RESULT_1UP: ("one_x_two_one_up", "1", "60200", 1),
            MarketId.MATCH_RESULT_2UP: ("one_x_two_two_up", "1", "60100", 2),
        }
        if type(self.market_id) is not MarketId or self.market_id not in expected:
            raise SportyBetEarlyPayoutSettlementError("unsupported early-payout market")
        if (self.provider_configuration_key, self.provider_source_market_id, self.provider_mapped_market_id, self.lead_threshold) != expected[self.market_id]:
            raise SportyBetEarlyPayoutSettlementError("provider identity or lead threshold drifted")
        if self.provider_pre_match_enabled is not True or self.provider_live_enabled is not True or self.provider_settlement_feature_enabled is not True:
            raise SportyBetEarlyPayoutSettlementError("provider early-payout enablement ancestry drifted")
        if self.event_topology != "OVERLAPPING_EVENTS":
            raise SportyBetEarlyPayoutSettlementError("event topology drifted")
        if self.selected_team_settlement != "LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN":
            raise SportyBetEarlyPayoutSettlementError("selected-team settlement semantics drifted")
        if self.draw_settlement != "REGULATION_TIME_FULL_TIME_DRAW":
            raise SportyBetEarlyPayoutSettlementError("draw settlement drifted")
        expected_abandonment_clauses = {
            MarketId.MATCH_RESULT_1UP: ("1UP", "FOOTBALL_INTERRUPTION"),
            MarketId.MATCH_RESULT_2UP: ("2UP_ABANDONMENT",),
        }[self.market_id]
        if self.triggered_selection_abandonment_proof_clause_ids != expected_abandonment_clauses:
            raise SportyBetEarlyPayoutSettlementError("abandonment proof ancestry drifted")
        if self.full_time_win_fallback is not True or self.early_trigger_irreversible is not True or self.triggered_selection_stands_if_abandoned is not True:
            raise SportyBetEarlyPayoutSettlementError("reviewed early-payout rule booleans must remain true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "provider_configuration_key": self.provider_configuration_key,
            "provider_source_market_id": self.provider_source_market_id,
            "provider_mapped_market_id": self.provider_mapped_market_id,
            "provider_pre_match_enabled": self.provider_pre_match_enabled,
            "provider_live_enabled": self.provider_live_enabled,
            "provider_settlement_feature_enabled": self.provider_settlement_feature_enabled,
            "lead_threshold": self.lead_threshold,
            "event_topology": self.event_topology,
            "selected_team_settlement": self.selected_team_settlement,
            "draw_settlement": self.draw_settlement,
            "full_time_win_fallback": self.full_time_win_fallback,
            "early_trigger_irreversible": self.early_trigger_irreversible,
            "triggered_selection_abandonment_proof_clause_ids": list(
                self.triggered_selection_abandonment_proof_clause_ids
            ),
            "triggered_selection_stands_if_abandoned": self.triggered_selection_stands_if_abandoned,
        }


@dataclass(frozen=True)
class SportyBetEarlyPayoutSettlementReceipt:
    schema_version: int
    dataset_name: str
    review_scope: str
    source_evidence_manifest_sha256: str
    source_evidence_manifest_size: int
    sources: tuple[SportyBetSettlementSourceEvidence, ...]
    market_rules: tuple[SportyBetEarlyPayoutMarketRule, ...]
    full_time_fallback_proof: str
    normal_completion_probability_scope: str
    safety: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.review_scope) != (SCHEMA_VERSION, DATASET_NAME, REVIEW_SCOPE):
            raise SportyBetEarlyPayoutSettlementError("receipt identity drifted")
        if self.source_evidence_manifest_sha256 != SOURCE_EVIDENCE_SHA256 or self.source_evidence_manifest_size != SOURCE_EVIDENCE_SIZE:
            raise SportyBetEarlyPayoutSettlementError("source evidence manifest anchor drifted")
        if type(self.sources) is not tuple or len(self.sources) != 2 or any(type(item) is not SportyBetSettlementSourceEvidence for item in self.sources):
            raise SportyBetEarlyPayoutSettlementError("receipt requires two exact sources")
        if self.sources != (
            SportyBetSettlementSourceEvidence(
                OFFICIAL_NIGERIA_FOOTBALL_HELP_URL,
                "OFFICIAL_NIGERIA_RENDERED_HELP_SECTION",
                OFFICIAL_NIGERIA_HELP_SECTION_SHA256,
                OFFICIAL_NIGERIA_HELP_SECTION_SIZE,
            ),
            SportyBetSettlementSourceEvidence(
                PRESERVED_NIGERIA_CONFIGURATION_FILE,
                "PRESERVED_NIGERIA_RAW_SITE_CONFIGURATION",
                PRESERVED_NIGERIA_CONFIGURATION_SHA256,
                PRESERVED_NIGERIA_CONFIGURATION_SIZE,
            ),
        ):
            raise SportyBetEarlyPayoutSettlementError("receipt source ancestry drifted")
        if type(self.market_rules) is not tuple or any(type(item) is not SportyBetEarlyPayoutMarketRule for item in self.market_rules):
            raise SportyBetEarlyPayoutSettlementError("receipt rule type drifted")
        if tuple(rule.market_id for rule in self.market_rules) != (MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
            raise SportyBetEarlyPayoutSettlementError("receipt market order drifted")
        if self.full_time_fallback_proof != "OFFICIAL_NIGERIA_1X2_FULL_TIME_WIN_CONTRACT_PLUS_DEDICATED_EARLY_PAYOUT_TRIGGER":
            raise SportyBetEarlyPayoutSettlementError("full-time fallback proof drifted")
        if self.normal_completion_probability_scope != "REGULATION_TIME_FOOTBALL_PATH_ONLY_ABANDONMENT_FREQUENCY_NOT_MODELED":
            raise SportyBetEarlyPayoutSettlementError("probability scope drifted")
        if self.safety != _SAFETY:
            raise SportyBetEarlyPayoutSettlementError("receipt safety drifted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "review_scope": self.review_scope,
            "source_evidence_manifest_sha256": self.source_evidence_manifest_sha256,
            "source_evidence_manifest_size": self.source_evidence_manifest_size,
            "sources": [item.to_dict() for item in self.sources],
            "market_rules": [item.to_dict() for item in self.market_rules],
            "full_time_fallback_proof": self.full_time_fallback_proof,
            "normal_completion_probability_scope": self.normal_completion_probability_scope,
            "safety": dict(self.safety),
        }


def _abandonment_proof(
    clauses: dict[str, str], market_id: MarketId
) -> tuple[tuple[str, ...], bool]:
    if market_id is MarketId.MATCH_RESULT_1UP:
        clause_ids = ("1UP", "FOOTBALL_INTERRUPTION")
        proven = (
            "Once settled, the final result no longer matters"
            in clauses["1UP"]
            and "all undecided bets are considered void"
            in clauses["FOOTBALL_INTERRUPTION"]
        )
    elif market_id is MarketId.MATCH_RESULT_2UP:
        clause_ids = ("2UP_ABANDONMENT",)
        proven = (
            "bets on that selection will still be paid as winners"
            in clauses["2UP_ABANDONMENT"]
        )
    else:
        raise SportyBetEarlyPayoutSettlementError(
            "abandonment proof requested for unsupported market"
        )
    return clause_ids, proven


def build_sportybet_early_payout_settlement_receipt(*, source_evidence_manifest_bytes: bytes) -> SportyBetEarlyPayoutSettlementReceipt:
    """Build only from the exact reviewed Nigeria source-evidence manifest."""
    manifest = _source_manifest(source_evidence_manifest_bytes)
    help_bytes = _canonical_json_bytes(manifest["official_help"])
    configuration = manifest["configuration_capture"]
    sources = (
        SportyBetSettlementSourceEvidence(OFFICIAL_NIGERIA_FOOTBALL_HELP_URL, "OFFICIAL_NIGERIA_RENDERED_HELP_SECTION", _sha256(help_bytes), len(help_bytes)),
        SportyBetSettlementSourceEvidence(PRESERVED_NIGERIA_CONFIGURATION_FILE, "PRESERVED_NIGERIA_RAW_SITE_CONFIGURATION", configuration["sha256"], configuration["byte_size"]),
    )
    rules_list = []
    for market_id, key, source_id, mapped_id, threshold in (
        (MarketId.MATCH_RESULT_1UP, "one_x_two_one_up", "1", "60200", 1),
        (MarketId.MATCH_RESULT_2UP, "one_x_two_two_up", "1", "60100", 2),
    ):
        proof_clause_ids, abandonment_proven = _abandonment_proof(
            manifest["official_help"]["clauses"], market_id
        )
        rules_list.append(SportyBetEarlyPayoutMarketRule(
            market_id=market_id,
            provider_configuration_key=key,
            provider_source_market_id=source_id,
            provider_mapped_market_id=mapped_id,
            provider_pre_match_enabled=True,
            provider_live_enabled=True,
            provider_settlement_feature_enabled=True,
            lead_threshold=threshold,
            event_topology="OVERLAPPING_EVENTS",
            selected_team_settlement="LEAD_THRESHOLD_HIT_OR_REGULATION_TIME_WIN",
            draw_settlement="REGULATION_TIME_FULL_TIME_DRAW",
            full_time_win_fallback=True,
            early_trigger_irreversible=True,
            triggered_selection_abandonment_proof_clause_ids=proof_clause_ids,
            triggered_selection_stands_if_abandoned=abandonment_proven,
        ))
    rules = tuple(rules_list)
    return SportyBetEarlyPayoutSettlementReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        review_scope=REVIEW_SCOPE,
        source_evidence_manifest_sha256=SOURCE_EVIDENCE_SHA256,
        source_evidence_manifest_size=SOURCE_EVIDENCE_SIZE,
        sources=sources,
        market_rules=rules,
        full_time_fallback_proof="OFFICIAL_NIGERIA_1X2_FULL_TIME_WIN_CONTRACT_PLUS_DEDICATED_EARLY_PAYOUT_TRIGGER",
        normal_completion_probability_scope="REGULATION_TIME_FOOTBALL_PATH_ONLY_ABANDONMENT_FREQUENCY_NOT_MODELED",
        safety=_SAFETY,
    )


def reviewed_sportybet_early_payout_settlement_receipt() -> SportyBetEarlyPayoutSettlementReceipt:
    return build_sportybet_early_payout_settlement_receipt(source_evidence_manifest_bytes=source_evidence_manifest_bytes())


def canonical_sportybet_early_payout_settlement_receipt_bytes(receipt: SportyBetEarlyPayoutSettlementReceipt) -> bytes:
    if type(receipt) is not SportyBetEarlyPayoutSettlementReceipt:
        raise TypeError("receipt must be exact SportyBetEarlyPayoutSettlementReceipt")
    rebuilt = SportyBetEarlyPayoutSettlementReceipt(
        schema_version=receipt.schema_version,
        dataset_name=receipt.dataset_name,
        review_scope=receipt.review_scope,
        source_evidence_manifest_sha256=receipt.source_evidence_manifest_sha256,
        source_evidence_manifest_size=receipt.source_evidence_manifest_size,
        sources=tuple(receipt.sources),
        market_rules=tuple(receipt.market_rules),
        full_time_fallback_proof=receipt.full_time_fallback_proof,
        normal_completion_probability_scope=receipt.normal_completion_probability_scope,
        safety=tuple(receipt.safety),
    )
    return _canonical_json_bytes(rebuilt.to_dict())


def sha256_sportybet_early_payout_settlement_receipt(receipt: SportyBetEarlyPayoutSettlementReceipt) -> str:
    return _sha256(canonical_sportybet_early_payout_settlement_receipt_bytes(receipt))


def revalidate_sportybet_early_payout_settlement_receipt(*, receipt: SportyBetEarlyPayoutSettlementReceipt, receipt_bytes: bytes, source_evidence_manifest_bytes: bytes) -> SportyBetEarlyPayoutSettlementReceipt:
    if type(receipt_bytes) is not bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt_bytes must be exact bytes")
    rebuilt = build_sportybet_early_payout_settlement_receipt(source_evidence_manifest_bytes=source_evidence_manifest_bytes)
    rebuilt_bytes = canonical_sportybet_early_payout_settlement_receipt_bytes(rebuilt)
    if canonical_sportybet_early_payout_settlement_receipt_bytes(receipt) != rebuilt_bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt object differs from replay")
    if receipt_bytes != rebuilt_bytes:
        raise SportyBetEarlyPayoutSettlementError("receipt bytes differ from replay")
    return rebuilt


__all__ = [
    "DATASET_NAME", "OFFICIAL_NIGERIA_FOOTBALL_HELP_URL",
    "OFFICIAL_NIGERIA_HELP_SECTION_SHA256", "OFFICIAL_NIGERIA_HELP_SECTION_SIZE",
    "ONE_UP_PROVIDER_MAPPED_MARKET_ID", "ONE_UP_PROVIDER_SOURCE_MARKET_ID",
    "PRESERVED_NIGERIA_CONFIGURATION_FILE", "PRESERVED_NIGERIA_CONFIGURATION_SHA256",
    "PRESERVED_NIGERIA_CONFIGURATION_SIZE", "REVIEW_SCOPE", "SCHEMA_VERSION",
    "SOURCE_EVIDENCE_PATH", "SOURCE_EVIDENCE_SHA256", "SOURCE_EVIDENCE_SIZE",
    "TWO_UP_PROVIDER_MAPPED_MARKET_ID", "TWO_UP_PROVIDER_SOURCE_MARKET_ID",
    "SportyBetEarlyPayoutMarketRule", "SportyBetEarlyPayoutSettlementError",
    "SportyBetEarlyPayoutSettlementReceipt", "SportyBetSettlementSourceEvidence",
    "build_sportybet_early_payout_settlement_receipt",
    "canonical_sportybet_early_payout_settlement_receipt_bytes",
    "revalidate_sportybet_early_payout_settlement_receipt",
    "reviewed_sportybet_early_payout_settlement_receipt",
    "sha256_sportybet_early_payout_settlement_receipt", "source_evidence_manifest_bytes",
]
