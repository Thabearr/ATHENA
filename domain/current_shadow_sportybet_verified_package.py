"""Source-replay-sealed package for the current ATHENA research shadow lane.

The raw field-trial value objects intentionally remain easy to inspect in tests,
but no network-capable shadow execution should trust them by themselves. This
module closes that boundary: every decision retains the exact complete PR151
history handoff and exact PR252 mapping rebind that produced it, and every
portfolio package is rebuilt from those retained sources before it can be used
by the canonical anonymous share-code wrapper.

Nothing here creates production Phase 6, production selection, staking, or BET
authority.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import current_direct_provider_canonical_market_mapping_rebind as current_mapping
from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain import current_shadow_sportybet_field_trial as field_trial


SCHEMA_VERSION = 1
DECISION_DATASET_NAME = "athena-current-shadow-verified-decision-source-v1"
PORTFOLIO_DATASET_NAME = "athena-current-shadow-verified-portfolio-package-v1"
STATUS_DECISION = "RESEARCH_SHADOW_DECISION_EXACT_SOURCE_REPLAY_VERIFIED"
STATUS_PORTFOLIO = "RESEARCH_SHADOW_PORTFOLIO_EXACT_SOURCE_REPLAY_VERIFIED"

AUTHORITY = types.MappingProxyType(
    {
        "exact_research_decision_source_replay": True,
        "exact_research_portfolio_source_replay": True,
        "research_shadow_execution_input": True,
        "production_model": False,
        "phase6": False,
        "production_selection": False,
        "production_sportybet_execution": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CurrentShadowVerifiedPackageError(ValueError):
    """Raised when a shadow decision/portfolio cannot be re-proved from sources."""


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CurrentShadowVerifiedPackageError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowVerifiedPackageError(f"{label} is invalid") from exc


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowVerifiedPackageError(
            "canonical serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _history_sha(
    value: latest_history.CurrentLatestDurableFreshHistoryHandoff,
) -> str:
    try:
        return latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(
            value
        )
    except Exception as exc:
        raise CurrentShadowVerifiedPackageError(
            "complete current history identity could not be canonicalized"
        ) from exc


def _mapping_sha(
    value: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> str:
    try:
        return _sha(value.to_dict())
    except Exception as exc:
        raise CurrentShadowVerifiedPackageError(
            "current mapping identity could not be canonicalized"
        ) from exc


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedResearchDecisionSource:
    dataset_name: str
    status: str
    decision: field_trial.ResearchFixtureDecision
    decision_sha256: str
    complete_current_history_sha256: str
    current_mapping_rebind_sha256: str
    evaluation_time: datetime
    authority: Mapping[str, bool]
    _complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff
    _current_mapping_rebind: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowVerifiedPackageError(
            "verified research decision sources are builder-only"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "decision_sha256": self.decision_sha256,
            "complete_current_history_sha256": (
                self.complete_current_history_sha256
            ),
            "current_mapping_rebind_sha256": (
                self.current_mapping_rebind_sha256
            ),
            "evaluation_time": self.evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "fixture_identifier": self.decision.fixture.fixture_identifier,
            "event_id": self.decision.fixture.event_id,
            "decision_status": self.decision.status,
            "selected_opportunity_id": self.decision.selected_opportunity_id,
            "decision": self.decision.to_dict(),
            "authority": dict(self.authority),
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())



def build_verified_research_decision_source(
    *,
    complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    current_mapping_rebind: current_mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    evaluation_time: datetime,
) -> VerifiedResearchDecisionSource:
    evaluation = _utc(evaluation_time, "evaluation_time")
    try:
        decision = field_trial.build_source_bound_total_goals_research_decision(
            complete_current_history=complete_current_history,
            current_mapping_rebind=current_mapping_rebind,
            evaluation_time=evaluation,
        )
    except Exception as exc:
        raise CurrentShadowVerifiedPackageError(
            "research decision could not be rebuilt from exact current sources"
        ) from exc

    history_sha = _history_sha(complete_current_history)
    mapping_sha = _mapping_sha(current_mapping_rebind)
    if (
        decision.latest_history_sha256 != history_sha
        or decision.current_mapping_rebind_sha256 != mapping_sha
        or decision.evaluation_time != evaluation
    ):
        raise CurrentShadowVerifiedPackageError(
            "research decision source identities differ from retained inputs"
        )

    value = object.__new__(VerifiedResearchDecisionSource)
    return _set_frozen(
        value,
        {
            "dataset_name": DECISION_DATASET_NAME,
            "status": STATUS_DECISION,
            "decision": decision,
            "decision_sha256": decision.canonical_sha256,
            "complete_current_history_sha256": history_sha,
            "current_mapping_rebind_sha256": mapping_sha,
            "evaluation_time": evaluation,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "_complete_current_history": complete_current_history,
            "_current_mapping_rebind": current_mapping_rebind,
        },
    )


def verify_verified_research_decision_source(
    value: Any,
) -> VerifiedResearchDecisionSource:
    if type(value) is not VerifiedResearchDecisionSource:
        raise CurrentShadowVerifiedPackageError(
            "exact VerifiedResearchDecisionSource is required"
        )
    rebuilt = build_verified_research_decision_source(
        complete_current_history=value._complete_current_history,
        current_mapping_rebind=value._current_mapping_rebind,
        evaluation_time=value.evaluation_time,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise CurrentShadowVerifiedPackageError(
            "verified research decision differs from exact source replay"
        )
    return rebuilt


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedResearchShadowPortfolio:
    dataset_name: str
    status: str
    portfolio: field_trial.ResearchShadowPortfolio
    portfolio_sha256: str
    evaluation_time: datetime
    requested_target_size: int
    source_decision_receipt_sha256s: tuple[str, ...]
    authority: Mapping[str, bool]
    _decision_sources: tuple[VerifiedResearchDecisionSource, ...]

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentShadowVerifiedPackageError(
            "verified research shadow portfolios are builder-only"
        )

    @property
    def decisions(self) -> tuple[field_trial.ResearchFixtureDecision, ...]:
        return tuple(item.decision for item in self._decision_sources)

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "portfolio_sha256": self.portfolio_sha256,
            "evaluation_time": self.evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "requested_target_size": self.requested_target_size,
            "source_decision_receipt_sha256s": list(
                self.source_decision_receipt_sha256s
            ),
            "source_decision_count": len(self._decision_sources),
            "portfolio": self.portfolio.to_dict(),
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def build_verified_research_shadow_portfolio(
    decision_sources: Sequence[VerifiedResearchDecisionSource],
    *,
    target_size: int,
    evaluation_time: datetime,
) -> VerifiedResearchShadowPortfolio:
    if (
        isinstance(decision_sources, (str, bytes))
        or not isinstance(decision_sources, Sequence)
    ):
        raise CurrentShadowVerifiedPackageError(
            "decision_sources must be a sequence"
        )
    supplied = tuple(decision_sources)
    if any(type(item) is not VerifiedResearchDecisionSource for item in supplied):
        raise CurrentShadowVerifiedPackageError(
            "decision_sources contain invalid item"
        )
    verified = tuple(
        verify_verified_research_decision_source(item)
        for item in supplied
    )
    receipt_shas = tuple(sorted(item.canonical_sha256 for item in verified))
    if len(receipt_shas) != len(set(receipt_shas)):
        raise CurrentShadowVerifiedPackageError(
            "duplicate verified decision-source receipts are forbidden"
        )
    evaluation = _utc(evaluation_time, "evaluation_time")
    try:
        portfolio = field_trial.optimize_research_shadow_portfolio(
            tuple(item.decision for item in verified),
            target_size=target_size,
            evaluation_time=evaluation,
        )
    except Exception as exc:
        raise CurrentShadowVerifiedPackageError(
            "research portfolio could not be rebuilt from verified decision sources"
        ) from exc

    value = object.__new__(VerifiedResearchShadowPortfolio)
    return _set_frozen(
        value,
        {
            "dataset_name": PORTFOLIO_DATASET_NAME,
            "status": STATUS_PORTFOLIO,
            "portfolio": portfolio,
            "portfolio_sha256": portfolio.canonical_sha256,
            "evaluation_time": evaluation,
            "requested_target_size": target_size,
            "source_decision_receipt_sha256s": receipt_shas,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "_decision_sources": verified,
        },
    )


def verify_verified_research_shadow_portfolio(
    value: Any,
) -> VerifiedResearchShadowPortfolio:
    if type(value) is not VerifiedResearchShadowPortfolio:
        raise CurrentShadowVerifiedPackageError(
            "exact VerifiedResearchShadowPortfolio is required"
        )
    rebuilt = build_verified_research_shadow_portfolio(
        value._decision_sources,
        target_size=value.requested_target_size,
        evaluation_time=value.evaluation_time,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise CurrentShadowVerifiedPackageError(
            "verified research shadow portfolio differs from exact source replay"
        )
    return rebuilt


__all__ = [
    "AUTHORITY",
    "DECISION_DATASET_NAME",
    "PORTFOLIO_DATASET_NAME",
    "SCHEMA_VERSION",
    "STATUS_DECISION",
    "STATUS_PORTFOLIO",
    "CurrentShadowVerifiedPackageError",
    "VerifiedResearchDecisionSource",
    "VerifiedResearchShadowPortfolio",
    "build_verified_research_decision_source",
    "build_verified_research_shadow_portfolio",
    "verify_verified_research_decision_source",
    "verify_verified_research_shadow_portfolio",
]
