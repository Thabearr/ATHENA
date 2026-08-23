"""Settlement bridge for reviewed FotMob request-date bucket spillover.

PR212 remains frozen.  Its proxy type is extended only at the structural PR89
hook so every request-date/previous-UTC-date partition is validated by the
reviewed spillover adapter before the frozen ordinary-FT adapter reads the
original network bytes.  No score, reason, kickoff, result, or betting semantics
are changed here.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_fresh_holdout_ordinary_ft_settlement_schema_adapter as pr212_adapter
import domain.fotmob_fresh_holdout_request_date_spillover_adapter as spillover_adapter


SCHEMA_VERSION = 1
ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_REQUEST_DATE_SPILLOVER_SETTLEMENT_BRIDGE_V1"
ADAPTER_STATE = "REVIEWED_STRUCTURAL_BRIDGE_ONLY_FROZEN_ORDINARY_FT_SEMANTICS_UNCHANGED"

PR212_ADAPTER_BLOB_SHA = "986376b892e01cc739f65fca6d38c3ceec26b418"
SPILLOVER_ADAPTER_BLOB_SHA = "e4df727f192dfb1c0e7c3076d0c0b1124b8b10b2"

SAFETY_KEYS = (
    "football_semantics_promoted",
    "ordinary_ft_score_semantics_changed",
    "request_date_reinterpreted_as_kickoff_date",
    "kickoff_rewritten",
    "source_capability_changed",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutRequestDateSpilloverSettlementAdapterError(RuntimeError):
    pass


def _error(message: str) -> FreshHoldoutRequestDateSpilloverSettlementAdapterError:
    return FreshHoldoutRequestDateSpilloverSettlementAdapterError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    try:
        if _git_blob_sha(Path(pr212_adapter.__file__)) != PR212_ADAPTER_BLOB_SHA:
            raise _error("PR212 settlement adapter implementation blob changed")
        if _git_blob_sha(Path(spillover_adapter.__file__)) != SPILLOVER_ADAPTER_BLOB_SHA:
            raise _error("request-date spillover adapter implementation blob changed")
    except OSError as exc:
        raise _error("could not verify request-date spillover settlement bridge") from exc
    pr212_adapter.verify_reviewed_dependencies()
    spillover_adapter.verify_reviewed_dependencies()


class ReviewedPr89RequestDateSpilloverSettlementProxy(
    pr212_adapter.ReviewedPr89SettlementCompatibilityProxy
):
    """Keep PR212 delegation, replacing only its structural assessment hook."""

    __slots__ = ()

    def assess_fotmob_data_matches_eliminated_team_id_value_domain(
        self,
        raw_json: bytes,
        manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    ):
        verify_reviewed_dependencies()
        try:
            return spillover_adapter.assess_pr89_request_date_partition(
                raw_json,
                manifest,
            )
        except Exception as exc:
            raise _error(
                "reviewed request-date spillover structural settlement validation failed"
            ) from exc


def build_pr89_settlement_compatibility_proxy(
) -> ReviewedPr89RequestDateSpilloverSettlementProxy:
    verify_reviewed_dependencies()
    return ReviewedPr89RequestDateSpilloverSettlementProxy()


def adapter_receipt() -> dict[str, object]:
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_state": ADAPTER_STATE,
        "pr212_adapter_frozen": True,
        "spillover_partition_validation_required_before_frozen_score_adapter": True,
        "ordinary_ft_adapter_consumes_original_network_bytes": True,
        "network_acquisition_performed": False,
        "safety": {key: False for key in SAFETY_KEYS},
    }


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_STATE",
    "FreshHoldoutRequestDateSpilloverSettlementAdapterError",
    "ReviewedPr89RequestDateSpilloverSettlementProxy",
    "adapter_receipt",
    "build_pr89_settlement_compatibility_proxy",
    "verify_reviewed_dependencies",
]
