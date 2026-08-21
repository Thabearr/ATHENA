"""Offline, fail-closed Saturday 2026-08-22 fixture-universe inventory.

This boundary consumes only an exact PR40 FotMob fixture-candidate bundle.  It
answers which source fixtures exist on the Saturday target date and how their
literal competition names intersect ATHENA's reviewed accumulator bootstrap
registry.  It grants no candidate review, fixture admission, model, pricing,
selection, accumulator, or BET authority.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any

from config.league_priority import (
    PRIORITY_POLICY_VERSION,
    UNPRIORITIZED_RANK,
    resolve_league_priority,
)
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidateBundle,
    sha256_fotmob_fixture_candidate_bundle,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-saturday-2026-08-22-fixture-universe-v1"
TARGET_REQUEST_DATE = "20260822"
TARGET_KICKOFF_DATE_UTC = datetime.date(2026, 8, 22)
REQUEST_TIMEZONE = "UTC"
REQUEST_CCODE3 = "NGA"
TARGET_FOLD_SIZE = 20

_DOWNSTREAM_AUTHORITY_KEYS = (
    "candidate_review_authorized",
    "fixture_catalog_admission_authorized",
    "fixture_intelligence_authorized",
    "model_feature_authorized",
    "probability_authorized",
    "sportybet_reconciliation_authorized",
    "sportybet_market_mapping_authorized",
    "fresh_price_authorized",
    "pricing_authorized",
    "selection_authorized",
    "accumulator_authorized",
    "bet_authorized",
)


class SaturdayFixtureUniverseError(ValueError):
    """Raised when the frozen Saturday universe contract is violated."""


def safety_flags() -> dict[str, bool]:
    return {key: False for key in _DOWNSTREAM_AUTHORITY_KEYS}


def _candidate_record(candidate: Any) -> dict[str, Any]:
    if candidate.source_request_date != TARGET_REQUEST_DATE:
        raise SaturdayFixtureUniverseError(
            "candidate source request date differs from frozen Saturday request"
        )
    if candidate.kickoff_utc.date() != TARGET_KICKOFF_DATE_UTC:
        raise SaturdayFixtureUniverseError(
            "candidate kickoff is outside frozen Saturday UTC date"
        )

    entry = resolve_league_priority(candidate.source_competition_name)
    return {
        "fixture_id": f"FOTMOB:{candidate.source_match_id}",
        "source_match_id": candidate.source_match_id,
        "source_league_id": candidate.source_league_id,
        "source_competition_primary_id": candidate.source_competition_primary_id,
        "source_competition_name": candidate.source_competition_name,
        "source_competition_ccode": candidate.source_competition_ccode,
        "home_source_team_id": candidate.home_source_team_id,
        "home_name": candidate.home_name,
        "home_long_name": candidate.home_long_name,
        "away_source_team_id": candidate.away_source_team_id,
        "away_name": candidate.away_name,
        "away_long_name": candidate.away_long_name,
        "kickoff_utc": candidate.kickoff_utc.isoformat().replace("+00:00", "Z"),
        "review_status": candidate.review_status.value,
        "bootstrap_league_name": entry.canonical_name if entry else None,
        "bootstrap_league_rank": entry.rank if entry else UNPRIORITIZED_RANK,
        "bootstrap_league_tier": entry.tier if entry else None,
        "bootstrap_exact_name_match": entry is not None,
    }


def build_saturday_fixture_universe(bundle: FotMobFixtureCandidateBundle) -> dict[str, Any]:
    """Build a deterministic neutral inventory from one exact Saturday bundle."""

    if not isinstance(bundle, FotMobFixtureCandidateBundle):
        raise SaturdayFixtureUniverseError(
            "source must be an exact FotMobFixtureCandidateBundle"
        )
    if len(bundle.sources) != 1:
        raise SaturdayFixtureUniverseError(
            "Saturday universe requires exactly one source capture"
        )
    source = bundle.sources[0]
    if source.request_date != TARGET_REQUEST_DATE:
        raise SaturdayFixtureUniverseError("source request date is not 20260822")
    if source.timezone != REQUEST_TIMEZONE:
        raise SaturdayFixtureUniverseError("source timezone must remain UTC")
    if source.ccode3 != REQUEST_CCODE3:
        raise SaturdayFixtureUniverseError("source ccode3 must remain NGA")

    saturday_candidates = tuple(
        candidate
        for candidate in bundle.candidates
        if candidate.kickoff_utc.date() == TARGET_KICKOFF_DATE_UTC
    )
    if len(saturday_candidates) != len(bundle.candidates):
        raise SaturdayFixtureUniverseError(
            "PR40 bundle contains a kickoff outside the requested Saturday UTC date"
        )

    records = [_candidate_record(candidate) for candidate in saturday_candidates]
    records.sort(
        key=lambda item: (
            item["bootstrap_league_rank"],
            item["kickoff_utc"],
            item["source_match_id"],
        )
    )

    league_counts: dict[str, int] = {}
    for item in records:
        key = item["bootstrap_league_name"] or item["source_competition_name"]
        league_counts[key] = league_counts.get(key, 0) + 1

    prioritized_count = sum(
        1 for item in records if item["bootstrap_exact_name_match"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "target_request_date": TARGET_REQUEST_DATE,
        "target_kickoff_date_utc": TARGET_KICKOFF_DATE_UTC.isoformat(),
        "request_timezone": REQUEST_TIMEZONE,
        "request_ccode3": REQUEST_CCODE3,
        "requested_fold_size": TARGET_FOLD_SIZE,
        "priority_policy_version": PRIORITY_POLICY_VERSION,
        "source_candidate_bundle_sha256": sha256_fotmob_fixture_candidate_bundle(bundle),
        "source_capture_manifest_sha256": source.source_capture_manifest_sha256,
        "source_raw_sha256": source.source_raw_sha256,
        "source_observed_at": source.source_observed_at.isoformat().replace("+00:00", "Z"),
        "candidate_count": len(records),
        "bootstrap_exact_name_match_count": prioritized_count,
        "unprioritized_literal_competition_count": len(records) - prioritized_count,
        "enough_source_fixtures_for_requested_fold": len(records) >= TARGET_FOLD_SIZE,
        "league_counts": dict(sorted(league_counts.items())),
        "candidates": records,
        "safety": safety_flags(),
    }


def canonical_saturday_fixture_universe_bytes(value: dict[str, Any]) -> bytes:
    if not isinstance(value, dict):
        raise SaturdayFixtureUniverseError("fixture universe must be a dict")
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_saturday_fixture_universe(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_saturday_fixture_universe_bytes(value)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "REQUEST_CCODE3",
    "REQUEST_TIMEZONE",
    "SCHEMA_VERSION",
    "TARGET_FOLD_SIZE",
    "TARGET_KICKOFF_DATE_UTC",
    "TARGET_REQUEST_DATE",
    "SaturdayFixtureUniverseError",
    "build_saturday_fixture_universe",
    "canonical_saturday_fixture_universe_bytes",
    "safety_flags",
    "sha256_saturday_fixture_universe",
]
