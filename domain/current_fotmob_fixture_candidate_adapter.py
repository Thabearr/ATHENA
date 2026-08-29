"""Current-only adapter from reviewed FotMob additive schemas to frozen PR39 candidates.

The PR39 candidate builder is a pinned historical implementation and must remain
byte-for-byte unchanged.  This adapter first delegates to that frozen builder.
Only when PR39 rejects the source specifically at its schema-assessment boundary
may the already-reviewed PR87/PR89 structural extension chain qualify the exact
current capture.  Candidate extraction remains fixture-identity only and retains
the original PR38 raw/manifest ancestry; no terminal-state semantics or model,
pricing, selection, production, or betting authority is created here.
"""
from __future__ import annotations

from typing import Any

from domain import fotmob_fixture_candidates as pr39_candidates
from domain import fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
from domain.fotmob_data_matches_schema import FotMobDataMatchesSchemaError


POLICY_ID = "CURRENT_FOTMOB_PR39_OR_REVIEWED_PR87_PR89_ADDITIVE_SCHEMA_V1"


class CurrentFotMobFixtureCandidateAdapterError(ValueError):
    """Raised when the current additive-schema adapter cannot fail closed."""


def _extended_candidate_bundle(
    raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
) -> pr39_candidates.FotMobFixtureCandidateBundle:
    raw, manifest, manifest_sha = pr39_candidates._validated_capture(
        raw_json, source_manifest
    )
    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            raw, manifest
        )
    except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed PR87/PR89 additive schema assessment failed"
        ) from exc
    if (
        assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        or assessment.status_reason_semantics_qualified is not False
        or assessment.final_result_semantics_qualified is not False
    ):
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed PR87/PR89 structural assessment changed authority"
        )

    payload = pr39_candidates._strict_json(raw)
    source_candidates: list[pr39_candidates.FotMobFixtureCandidate] = []
    try:
        for league in payload["leagues"]:
            for match in league["matches"]:
                home = match["home"]
                away = match["away"]
                source_candidates.append(
                    pr39_candidates.FotMobFixtureCandidate(
                        review_status=pr39_candidates.FixtureCandidateReviewStatus.UNREVIEWED,
                        source=pr39_candidates.SOURCE_NAME,
                        source_match_id=match["id"],
                        source_league_id=league["id"],
                        source_competition_primary_id=league["primaryId"],
                        source_competition_name=league["name"],
                        source_competition_ccode=league["ccode"],
                        home_source_team_id=home["id"],
                        home_name=home["name"],
                        home_long_name=home["longName"],
                        away_source_team_id=away["id"],
                        away_name=away["name"],
                        away_long_name=away["longName"],
                        kickoff_utc=pr39_candidates._reviewed_kickoff(
                            match["status"]["utcTime"]
                        ),
                        source_capture_manifest_sha256=manifest_sha,
                        source_raw_sha256=manifest.raw_sha256,
                        source_request_date=manifest.request_date,
                        source_observed_at=manifest.observed_at,
                    )
                )
    except (KeyError, TypeError) as exc:
        # PR87/PR89 should already have structurally validated these base fields;
        # never turn unexpected extraction drift into a partially trusted bundle.
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed additive source cannot be extracted as PR39 fixture identity"
        ) from exc

    if len(source_candidates) != assessment.pr87_match_count:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed additive assessment and fixture extraction counts differ"
        )

    candidates = tuple(sorted(source_candidates, key=pr39_candidates._candidate_sort_key))
    duplicate_count, fixture_conflicts = pr39_candidates._make_fixture_observations(
        candidates
    )
    team_conflicts = pr39_candidates._make_team_conflicts(candidates)
    competition_conflicts = pr39_candidates._make_competition_conflicts(candidates)
    source = pr39_candidates.FotMobFixtureCandidateSource(
        source_capture_dataset_name=manifest.dataset_name,
        source_capture_schema_version=manifest.schema_version,
        source_capture_manifest_sha256=manifest_sha,
        source_raw_sha256=manifest.raw_sha256,
        source_raw_size=manifest.raw_size,
        source_observed_at=manifest.observed_at,
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        schema_assessment_sha256=(
            pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(
                assessment
            )
        ),
        candidate_count=len(candidates),
    )
    return pr39_candidates.FotMobFixtureCandidateBundle(
        schema_version=pr39_candidates.SCHEMA_VERSION,
        dataset_name=pr39_candidates.DATASET_NAME,
        sources=(source,),
        candidate_count=len(candidates),
        candidates=candidates,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=pr39_candidates._default_safety(),
    )


def build_current_fotmob_fixture_candidate_bundle(
    raw_json: Any,
    source_manifest: Any,
) -> pr39_candidates.FotMobFixtureCandidateBundle:
    """Build current fixture candidates without mutating/bypassing frozen PR39."""

    try:
        return pr39_candidates.build_fotmob_fixture_candidate_bundle(
            ((raw_json, source_manifest),)
        )
    except pr39_candidates.FotMobFixtureCandidateError as exc:
        # The additive path is legal only when frozen PR39 reached and rejected
        # its schema assessment.  Any other PR39 failure remains authoritative.
        if not isinstance(exc.__cause__, FotMobDataMatchesSchemaError):
            raise
        return _extended_candidate_bundle(raw_json, source_manifest)


__all__ = [
    "POLICY_ID",
    "CurrentFotMobFixtureCandidateAdapterError",
    "build_current_fotmob_fixture_candidate_bundle",
]
