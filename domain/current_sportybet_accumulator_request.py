"""Fixed target-only request entry point for the current accumulator chain.

The reviewed current FotMob chain still withholds production model/probability/
Phase 6 authority.  This service makes that exact stop an explicit terminal
result instead of accepting a caller factory or hand-assembled provider IDs.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import types
from collections.abc import Mapping
from typing import Any

from domain import current_fotmob_latest_durable_fresh_history as current_fotmob
from domain import current_sportybet_accumulator_execution as execution
from domain import market_router_v3_current_provider as router_v3
from domain import portfolio_optimizer_v3_current_provider as portfolio_v3
from domain import price_all_v3_current_provider as price_v3

DATASET_NAME = "athena-current-sportybet-accumulator-request-v1"
MAXIMUM_TARGET_SIZE = 50
STATUS_PHASE6_AUTHORITY_REQUIRED = "NO_CODE_CURRENT_PHASE6_AUTHORITY_REQUIRED"
BLOCKED_AT = current_fotmob.NEXT_REQUIRED_BOUNDARY

AUTHORITY = types.MappingProxyType({
    "fixed_request_entry_point": True,
    "target_size_request": True,
    "caller_factory": False,
    "caller_event_ids": False,
    "caller_native_market_outcome_ids": False,
    "caller_odds": False,
    "caller_preselected_slip": False,
    "production_model": False,
    "probability": False,
    "phase6": False,
    "sportybet_execution": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class CurrentSportyBetAccumulatorRequestError(ValueError):
    pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def validate_current_request_dependencies() -> Mapping[str, str]:
    if (
        current_fotmob.DATASET_NAME != "athena-current-fotmob-latest-durable-fresh-history-v1"
        or current_fotmob.STATUS != "VERIFIED_COMPLETE_CURRENT_PR151_DURABLE_HISTORY_PREFIX"
        or current_fotmob.NEXT_REQUIRED_BOUNDARY != "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION"
    ):
        raise CurrentSportyBetAccumulatorRequestError("current FotMob authority boundary drifted")
    try:
        price = price_v3.validate_price_all_v3_contract()
        router = router_v3.validate_market_router_v3_contract()
        portfolio = portfolio_v3.validate_portfolio_optimizer_v3_contract()
        current_execution = execution.validate_current_execution_contract()
    except Exception as exc:
        raise CurrentSportyBetAccumulatorRequestError("downstream current chain contract validation failed") from exc
    return types.MappingProxyType({
        "price_all_v3_contract_sha256": price["price_all_v3_contract_sha256"],
        "market_router_v3_contract_sha256": router["market_router_v3_contract_sha256"],
        "portfolio_optimizer_v3_contract_sha256": portfolio["portfolio_optimizer_v3_contract_sha256"],
        "current_execution_contract_sha256": current_execution["current_execution_contract_sha256"],
        "blocked_at": BLOCKED_AT,
    })


@dataclasses.dataclass(frozen=True)
class CurrentSportyBetAccumulatorRequestResult:
    requested_target_size: int
    evaluation_time: datetime
    status: str
    blocked_at: str
    contract_identities: Mapping[str, str]
    real_current_provider_execution_attempted: bool
    wager_placed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": DATASET_NAME,
            "requested_target_size": self.requested_target_size,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "status": self.status,
            "blocked_at": self.blocked_at,
            "reason": (
                "The latest reviewed current FotMob handoff explicitly withholds "
                "production model, score-matrix, probability, and Phase 6 authority."
            ),
            "contract_identities": dict(self.contract_identities),
            "real_current_provider_execution_attempted": self.real_current_provider_execution_attempted,
            "authority": dict(AUTHORITY),
            "wager_placed": False,
        }


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(payload), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def execute_current_accumulator_request(
    *, target_size: int, output_dir: Path,
) -> CurrentSportyBetAccumulatorRequestResult:
    if type(target_size) is not int or not 1 <= target_size <= MAXIMUM_TARGET_SIZE:
        raise CurrentSportyBetAccumulatorRequestError("target_size must be an integer from 1 through 50")
    if not isinstance(output_dir, Path):
        raise CurrentSportyBetAccumulatorRequestError("output_dir must be Path")
    identities = validate_current_request_dependencies()
    result = CurrentSportyBetAccumulatorRequestResult(
        requested_target_size=target_size,
        evaluation_time=_now_utc(),
        status=STATUS_PHASE6_AUTHORITY_REQUIRED,
        blocked_at=BLOCKED_AT,
        contract_identities=identities,
        real_current_provider_execution_attempted=False,
        wager_placed=False,
    )
    _write(output_dir / "current-sportybet-accumulator-request.json", result.to_dict())
    return result


__all__ = [name for name in globals() if not name.startswith("_")]
