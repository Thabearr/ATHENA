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
        half_time_score=CapabilityAvailability.CONFIRMED,
        event_timestamps=CapabilityAvailability.NOT_CAPTURED,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.CONFIRMED,
        evidence=(
            (
                "workers/historical_results_loader.py: score.fullTime, "
                "score.halfTime, lastUpdated"
            ),
            (
                "services/half_time_observation_store.py: validated "
                "half_time_observations persistence"
            ),
            "workers/api_loader.py: match id and utcDate",
        ),
        notes=(
            "The historical loader validates and stores explicit half-time "
            "scores from the existing finished-match payload. Provider "
            "lastUpdated is captured only when timezone-aware; utcDate remains "
            "kickoff time and no event timeline is captured."
        ),
    ),
    "football_data_uk_csv": SourceCapabilities(
        source="football_data_uk_csv",
        full_time_score=CapabilityAvailability.CONFIRMED,
        half_time_score=CapabilityAvailability.CONFIRMED,
        event_timestamps=CapabilityAvailability.NOT_CAPTURED,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.CONFIRMED,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            (
                "scripts/import_football_data_uk.py: Div, Date, Time, "
                "HomeTeam, AwayTeam, FTHG, FTAG, HTHG, HTAG"
            ),
            (
                "scripts/import_football_data_uk.py: deterministic SHA-256 "
                "fixture identity and HalfTimeObservationStore persistence"
            ),
        ),
        notes=(
            "The importer stores official historical CSV full-time scores and "
            "explicit half-time score pairs. Missing half-time scores remain "
            "missing. The files do not provide observation freshness or a "
            "goal-event timeline."
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
    "fotmob_data_matches_reviewed_catalog": SourceCapabilities(
        source="fotmob_data_matches_reviewed_catalog",
        full_time_score=CapabilityAvailability.NOT_CAPTURED,
        half_time_score=CapabilityAvailability.NOT_CAPTURED,
        event_timestamps=CapabilityAvailability.NOT_CAPTURED,
        reliable_fixture_identity=CapabilityAvailability.CONFIRMED,
        historical_coverage=CapabilityAvailability.UNKNOWN,
        freshness_metadata=CapabilityAvailability.NOT_CAPTURED,
        evidence=(
            (
                "domain/fotmob_data_matches_schema.py: strict fixture, team, "
                "competition and kickoff structure"
            ),
            (
                "domain/fotmob_fixture_candidates.py: provenance-backed UNREVIEWED "
                "source match, team, competition and kickoff mapping"
            ),
            (
                "domain/fotmob_fixture_candidate_review.py: exact candidate "
                "review key, conflict blockers and explicit APPROVED decision"
            ),
            (
                "domain/fotmob_fixture_catalog_handoff.py: exact reviewed "
                "candidate bundle reconstruction before catalog input"
            ),
            (
                "domain/fixture_catalog.py: source-scoped FOTMOB fixture identity "
                "and strict provenance normalization"
            ),
            (
                "scripts/manage_fotmob_reviewed_fixture_catalog.py: reviewed "
                "handoff preflight before PR #29 output commit"
            ),
        ),
        notes=(
            "This capability applies only to fixtures that pass the reviewed "
            "PR #38 through PR #43 data-matches catalog path. Reliable fixture "
            "identity means a source-scoped FOTMOB:<match id> identity with "
            "reviewed teams, competition and kickoff; it does not establish "
            "global team identity, source completeness, score semantics, source "
            "freshness, Fixture Intelligence trust, model readiness, pricing, "
            "selection, or betting authorization."
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
