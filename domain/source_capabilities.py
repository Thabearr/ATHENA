"""Repository-confirmed data-source capabilities.

These entries describe only what ATHENA's current adapters capture. They do
not infer capabilities from provider marketing or undocumented APIs.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple


class CapabilityAvailability(str, Enum):
    CONFIRMED = "CONFIRMED"
    NOT_CAPTURED = "NOT_CAPTURED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SourceCapabilities:
    source: str
    full_time_score: CapabilityAvailability
    half_time_score: CapabilityAvailability
    event_timestamps: CapabilityAvailability
    reliable_fixture_identity: CapabilityAvailability
    historical_coverage: CapabilityAvailability
    freshness_metadata: CapabilityAvailability
    evidence: Tuple[str, ...]
    notes: str

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "full_time_score": self.full_time_score.value,
            "half_time_score": self.half_time_score.value,
            "event_timestamps": self.event_timestamps.value,
            "reliable_fixture_identity": (
                self.reliable_fixture_identity.value
            ),
            "historical_coverage": self.historical_coverage.value,
            "freshness_metadata": self.freshness_metadata.value,
            "evidence": list(self.evidence),
            "notes": self.notes,
        }


SOURCE_CAPABILITY_REGISTRY: Dict[str, SourceCapabilities] = {
    "openfootball_public_domain": SourceCapabilities(
        source="openfootball_public_domain",
        full_time_score=CapabilityAvailability.CONFIRMED,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.NOT_CAPTURED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=("workers/openfootball_loader.py: score.ft",),
        notes=(
            "The loader stores full-time scores and creates a local hash-based "
            "fixture identity. It does not read half-time scores or source "
            "observation timestamps."
        ),
    ),
    "football_data_org_live": SourceCapabilities(
        source="football_data_org_live",
        full_time_score=CapabilityAvailability.CONFIRMED,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.NOT_CAPTURED,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            "workers/historical_results_loader.py: score.fullTime",
            "workers/api_loader.py: match id and utcDate",
        ),
        notes=(
            "Current repository code stores provider match IDs and full-time "
            "scores only. utcDate is kickoff time, not freshness metadata."
        ),
    ),
    "api_football_2022_2024": SourceCapabilities(
        source="api_football_2022_2024",
        full_time_score=CapabilityAvailability.CONFIRMED,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            "workers/historical_results_loader.py: fixture.id and goals",
        ),
        notes=(
            "The historical loader stores regulation-time goals for its "
            "configured seasons. No half-time or observation timestamp field "
            "is captured."
        ),
    ),
    "fotmob_historical": SourceCapabilities(
        source="fotmob_historical",
        full_time_score=CapabilityAvailability.CONFIRMED,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.NOT_CAPTURED,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            "workers/historical_scraper.py: match.id and status.scoreStr",
        ),
        notes=(
            "The historical scraper parses a finished score string and source "
            "match ID. It does not capture half-time scores or fetch time."
        ),
    ),
    "fotmob_bypass": SourceCapabilities(
        source="fotmob_bypass",
        full_time_score=CapabilityAvailability.UNKNOWN,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.UNKNOWN,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            "workers/fotmob_advanced_scraper.py: match.id and team.score",
        ),
        notes=(
            "The advanced fixture adapter reads a current score without "
            "persisting explicit full-time settlement semantics. No verified "
            "half-time field is captured."
        ),
    ),
    "fotmob_unofficial": SourceCapabilities(
        source="fotmob_unofficial",
        full_time_score=CapabilityAvailability.UNKNOWN,
        half_time_score=CapabilityAvailability.UNKNOWN,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        historical_coverage=CapabilityAvailability.UNKNOWN,
        freshness_metadata=CapabilityAvailability.UNKNOWN,
        evidence=("api/fotmob_provider.py: raw response wrapper only",),
        notes=(
            "The wrapper returns raw undocumented responses and does not "
            "validate or persist any score, identity, or freshness fields."
        ),
    ),
    "legacy_untagged": SourceCapabilities(
        source="legacy_untagged",
        full_time_score=CapabilityAvailability.UNKNOWN,
        half_time_score=CapabilityAvailability.UNKNOWN,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        historical_coverage=CapabilityAvailability.UNKNOWN,
        freshness_metadata=CapabilityAvailability.UNKNOWN,
        evidence=(
            "database/schema.sql: historical_matches.data_source is additive",
        ),
        notes=(
            "Rows without a source tag cannot be assigned capabilities "
            "without external evidence."
        ),
    ),
    "unknown": SourceCapabilities(
        source="unknown",
        full_time_score=CapabilityAvailability.UNKNOWN,
        half_time_score=CapabilityAvailability.UNKNOWN,
        event_timestamps=CapabilityAvailability.UNKNOWN,
        reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        historical_coverage=CapabilityAvailability.UNKNOWN,
        freshness_metadata=CapabilityAvailability.UNKNOWN,
        evidence=("workers/api_loader.py: defensive unknown source default",),
        notes=(
            "An explicit unknown tag carries no verified capability claims."
        ),
    ),
}


__all__ = [
    "CapabilityAvailability",
    "SOURCE_CAPABILITY_REGISTRY",
    "SourceCapabilities",
]
