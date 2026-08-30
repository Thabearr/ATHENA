"""Current-only PR149 provider-native qualification after reviewed schema replay.

The current FotMob candidate adapter is the schema-review boundary.  It either
replays frozen PR39 directly or, for already-reviewed additive provider drift,
replays the bounded PR87/PR89 current-schema extension before producing a
candidate bundle that retains the original PR38 capture lineage.

PR149's public ``qualify_capture_fixtures`` entrypoint cannot be called after
that boundary because it re-enters frozen PR39 and can therefore reject the
same already-reviewed current additive capture a second time.  This module
keeps PR149's frozen dependency verification and its provider-native identity
parser, then requires every current candidate to match that exact provider
identity and original capture lineage.

This is research/replay plumbing only.  It grants no model, probability,
pricing, selection, SportyBet execution, production, or betting authority.
"""
from __future__ import annotations

import dataclasses

from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidates import FotMobFixtureCandidateBundle
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


class CurrentFotMobProviderNativeQualificationError(ValueError):
    """Raised when current reviewed candidates lose exact provider lineage."""


def _error(message: str) -> CurrentFotMobProviderNativeQualificationError:
    return CurrentFotMobProviderNativeQualificationError(message)


def qualify_current_fotmob_capture(
    candidates: FotMobFixtureCandidateBundle,
    *,
    raw_json: bytes,
    manifest: FotMobDataMatchesCaptureManifest,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Qualify only current-reviewed candidates through PR149 identity rules."""

    if type(candidates) is not FotMobFixtureCandidateBundle:
        raise _error("current candidate bundle type mismatch")
    if type(raw_json) is not bytes or not raw_json:
        raise _error("current raw capture must be non-empty exact bytes")
    if type(manifest) is not FotMobDataMatchesCaptureManifest:
        raise _error("current manifest type mismatch")
    if manifest.network_acquisition_performed is not True:
        raise _error("current manifest must prove transparent network acquisition")

    manifest_sha = sha256_data_matches_capture_manifest(manifest)
    if len(candidates.sources) != 1:
        raise _error("current qualification requires exactly one candidate source")
    candidate_source = candidates.sources[0]
    expected_source = (
        manifest_sha,
        manifest.raw_sha256,
        manifest.raw_size,
        manifest.observed_at,
        manifest.request_date,
        manifest.timezone,
        manifest.ccode3,
    )
    actual_source = (
        candidate_source.source_capture_manifest_sha256,
        candidate_source.source_raw_sha256,
        candidate_source.source_raw_size,
        candidate_source.source_observed_at,
        candidate_source.request_date,
        candidate_source.timezone,
        candidate_source.ccode3,
    )
    if actual_source != expected_source:
        raise _error("current candidate source differs from exact capture lineage")

    try:
        fresh.verify_reviewed_dependencies()
        qualified_raw = fresh._qualify_provider_identity_payload(
            raw_json,
            capture_observed_at=manifest.observed_at,
            capture_manifest_sha256=manifest_sha,
            capture_raw_sha256=manifest.raw_sha256,
        )
    except Exception as exc:
        raise _error("reviewed PR149 provider-native identity replay failed") from exc

    by_id = {fixture.fixture_id: fixture for fixture in qualified_raw}
    if len(by_id) != len(qualified_raw):
        raise _error("provider-native replay returned duplicate fixture IDs")

    qualified: list[fresh.QualifiedCaptureFixture] = []
    for candidate in candidates.candidates:
        fixture = by_id.get(candidate.source_match_id)
        if fixture is None:
            raise _error("current candidate absent from provider-native source replay")
        expected = (
            candidate.source_competition_primary_id,
            candidate.source_league_id,
            candidate.home_source_team_id,
            candidate.away_source_team_id,
            candidate.kickoff_utc,
            candidate.source_observed_at,
            candidate.source_raw_sha256,
            candidate.source_capture_manifest_sha256,
        )
        actual = (
            fixture.provider_primary_id,
            fixture.wrapper_id,
            fixture.home_team_id,
            fixture.away_team_id,
            fixture.kickoff_utc,
            fixture.capture_observed_at,
            fixture.capture_raw_sha256,
            fixture.capture_manifest_sha256,
        )
        if actual != expected:
            raise _error("current candidate disagrees with PR149 provider-native identity")
        qualified.append(dataclasses.replace(fixture))

    return tuple(sorted(qualified, key=lambda item: (item.kickoff_utc, item.fixture_id)))
