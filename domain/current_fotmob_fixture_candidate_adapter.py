"""Current-only adapter from reviewed FotMob additive schemas to frozen PR39 candidates.

The PR39 candidate builder is a pinned historical implementation and must remain
byte-for-byte unchanged. This adapter first delegates to that frozen builder.
Only when PR39 rejects the source specifically at its schema-assessment boundary
may the already-reviewed PR87/PR89 structural extension chain qualify the exact
current capture.

Current live `/api/data/matches` evidence can also contain rows outside the exact
requested UTC date even when the request timezone is UTC. Frozen PR39 rejects the
whole response in that case. The current-only fallback therefore permits one
narrow deterministic projection: after validating that every source row stays
inside the already-reviewed PR87/PR89 additive key/value domains, rows whose
reviewed `status.utcTime` UTC date differs from the manifest request date are
excluded before the frozen PR87/PR89 assessment is replayed. This projection is
available only for exact `timezone="UTC"` captures and only when the original
failure chain proves the frozen PR39 request-date mismatch. Excluded rows never
become candidates, while every retained candidate keeps the original PR38 raw
and manifest ancestry.

Live run 33690015364 also re-observed the two opaque `status.halfs` timestamps
already reviewed for fresh-holdout capture compatibility:
`firstExtraHalfStarted` and `secondExtraHalfStarted`.  V2 admits only those exact
keys when their values are exact strings, removes them from a validation-only
projection, and then replays the frozen PR87/PR89 structural chain.  The raw
capture and manifest remain the authoritative candidate ancestry.  No extra-time
football semantics are inferred from the opaque strings.

Candidate extraction remains fixture-identity only. No terminal-state semantics
or model, pricing, selection, production, or betting authority is created here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from domain import fotmob_fixture_candidates as pr39_candidates
from domain import fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
from domain.fotmob_data_matches_schema import FotMobDataMatchesSchemaError


POLICY_ID = "CURRENT_FOTMOB_PR39_OR_REVIEWED_PR87_PR89_ADDITIVE_SCHEMA_V2"
_REQUEST_DATE_MISMATCH = "kickoff UTC date does not match source request date"
REVIEWED_EXTRA_HALFS_KEYS = ("firstExtraHalfStarted", "secondExtraHalfStarted")
REVIEWED_EXTRA_HALFS_RULE = (
    "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"
)
SOURCE_WORKFLOW_RUN_ID = 33690015364
SOURCE_ACTIONS_ARTIFACT_ID = 9869665644
SOURCE_CAPTURE_REQUEST_DATE = "20260902"
SOURCE_CAPTURE_MANIFEST_FILE_SHA256 = (
    "18dc76e89be17fbd24c048b17954c22c85dab07e5daeffe203f14c2040e0cb1d"
)
SOURCE_CAPTURE_RAW_SHA256 = (
    "070c63fa4480e470ba94b2e6726ad4959c89f2bcffd6c3929304590ac8ef5973"
)
SOURCE_CAPTURE_EXTRA_HALFS_OCCURRENCES = {
    "firstExtraHalfStarted": 4,
    "secondExtraHalfStarted": 4,
}


class CurrentFotMobFixtureCandidateAdapterError(ValueError):
    """Raised when the current additive-schema adapter cannot fail closed."""


def _contains_exact_request_date_mismatch(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, FotMobDataMatchesSchemaError) and str(current) == _REQUEST_DATE_MISMATCH:
            return True
        current = current.__cause__
    return False


def _contains_extra_halfs_boundary(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    expected_status = (
        pr89.pr87_implementation.TerminalStateSchemaExtensionStatus.
        BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET
    )
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if (
            isinstance(
                current,
                pr89.pr87_implementation.FotMobDataMatchesTerminalStateSchemaExtensionError,
            )
            and current.status is expected_status
            and ".status.halfs has keys outside the PR39 base plus PR86 extension"
            in str(current)
        ):
            return True
        current = current.__cause__
    return False


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "request-date projection serialization failed"
        ) from exc


def _strip_reviewed_extra_halfs(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    projected = copy.deepcopy(payload)
    counts = {key: 0 for key in REVIEWED_EXTRA_HALFS_KEYS}
    leagues = projected.get("leagues")
    if type(leagues) is not list:
        return projected, counts
    for league_index, league in enumerate(leagues):
        if type(league) is not dict:
            continue
        matches = league.get("matches")
        if type(matches) is not list:
            continue
        for match_index, match in enumerate(matches):
            if type(match) is not dict:
                continue
            status = match.get("status")
            if type(status) is not dict:
                continue
            halfs = status.get("halfs")
            if type(halfs) is not dict:
                continue
            for key in REVIEWED_EXTRA_HALFS_KEYS:
                if key not in halfs:
                    continue
                value = halfs[key]
                if type(value) is not str:
                    raise CurrentFotMobFixtureCandidateAdapterError(
                        f"leagues[{league_index}].matches[{match_index}]."
                        f"status.halfs.{key} must be an exact string"
                    )
                counts[key] += 1
                del halfs[key]
    return projected, counts


def _extra_halfs_projection(
    raw: bytes,
    manifest: FotMobDataMatchesCaptureManifest,
) -> tuple[bytes, FotMobDataMatchesCaptureManifest, dict[str, int]]:
    payload = pr39_candidates._strict_json(raw)
    projected, counts = _strip_reviewed_extra_halfs(payload)
    if sum(counts.values()) <= 0:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "extra-halfs compatibility path entered without a reviewed extra-halfs key"
        )
    projected_raw = _canonical_payload_bytes(projected)
    try:
        projected_manifest = pr89._projected_manifest(manifest, projected_raw)
    except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "extra-halfs compatibility manifest failed reviewed capture validation"
        ) from exc
    return projected_raw, projected_manifest, counts


def _validate_all_rows_inside_reviewed_additive_domains(payload: dict[str, Any]) -> None:
    """Reject unknown additive drift before any out-of-date row can be excluded."""

    try:
        pr87_input, _total, _nulls, _non_nulls = pr89._validate_and_project_eliminated_team_id(
            payload
        )
        pr89.pr87_implementation._validate_extension_fields_and_project(pr87_input)
    except (
        pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError,
        pr89.pr87_implementation.FotMobDataMatchesTerminalStateSchemaExtensionError,
    ) as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed PR87/PR89 additive structure changed before request-date projection"
        ) from exc


def _request_date_projection(
    raw: bytes,
    manifest: FotMobDataMatchesCaptureManifest,
) -> tuple[bytes, FotMobDataMatchesCaptureManifest, int]:
    if manifest.timezone != "UTC":
        raise CurrentFotMobFixtureCandidateAdapterError(
            "request-date projection is reviewed only for exact UTC captures"
        )
    payload = pr39_candidates._strict_json(raw)
    if payload.get("date") != manifest.request_date:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "source payload date differs from request-date projection identity"
        )

    _validate_all_rows_inside_reviewed_additive_domains(payload)

    projected_leagues: list[dict[str, Any]] = []
    excluded = 0
    try:
        for league in payload["leagues"]:
            retained_matches: list[dict[str, Any]] = []
            for match in league["matches"]:
                kickoff = pr39_candidates._reviewed_kickoff(match["status"]["utcTime"])
                if kickoff.strftime("%Y%m%d") == manifest.request_date:
                    retained_matches.append(match)
                else:
                    excluded += 1
            projected_league = dict(league)
            projected_league["matches"] = retained_matches
            projected_leagues.append(projected_league)
    except (KeyError, TypeError, pr39_candidates.FotMobFixtureCandidateError) as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "request-date projection could not prove reviewed kickoff identity"
        ) from exc

    if excluded <= 0:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "request-date projection was entered without an out-of-date source row"
        )

    projected_raw = _canonical_payload_bytes(
        {"date": payload["date"], "leagues": projected_leagues}
    )
    try:
        projected_manifest = pr89._projected_manifest(manifest, projected_raw)
    except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "request-date projection manifest failed reviewed capture validation"
        ) from exc
    return projected_raw, projected_manifest, excluded


def _projection_assessment_sha256(
    *,
    source_manifest_sha256: str,
    source_raw_sha256: str,
    projected_raw: bytes,
    excluded_count: int,
    pr89_assessment_sha256: str,
) -> str:
    descriptor = {
        "policy_id": POLICY_ID,
        "projection": "EXACT_UTC_REQUEST_DATE_ONLY",
        "source_manifest_sha256": source_manifest_sha256,
        "source_raw_sha256": source_raw_sha256,
        "projected_raw_sha256": hashlib.sha256(projected_raw).hexdigest(),
        "excluded_out_of_request_utc_date_count": excluded_count,
        "pr89_assessment_sha256": pr89_assessment_sha256,
    }
    return hashlib.sha256(_canonical_payload_bytes(descriptor)).hexdigest()


def _extra_halfs_assessment_sha256(
    *,
    source_manifest_sha256: str,
    source_raw_sha256: str,
    projected_raw: bytes,
    counts: dict[str, int],
    excluded_count: int,
    pr89_assessment_sha256: str,
) -> str:
    descriptor = {
        "policy_id": POLICY_ID,
        "projection": (
            "REVIEWED_OPAQUE_EXTRA_HALFS_ONLY"
            if excluded_count == 0
            else "REVIEWED_OPAQUE_EXTRA_HALFS_PLUS_EXACT_UTC_REQUEST_DATE"
        ),
        "source_manifest_sha256": source_manifest_sha256,
        "source_raw_sha256": source_raw_sha256,
        "projected_raw_sha256": hashlib.sha256(projected_raw).hexdigest(),
        "reviewed_extra_halfs_counts": {
            key: counts[key] for key in REVIEWED_EXTRA_HALFS_KEYS
        },
        "excluded_out_of_request_utc_date_count": excluded_count,
        "pr89_assessment_sha256": pr89_assessment_sha256,
    }
    return hashlib.sha256(_canonical_payload_bytes(descriptor)).hexdigest()


def _qualified_extended_payload(
    raw: bytes,
    manifest: FotMobDataMatchesCaptureManifest,
    manifest_sha: str,
) -> tuple[dict[str, Any], pr89.FotMobDataMatchesEliminatedTeamIdValueDomainAssessment, str]:
    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            raw, manifest
        )
        assessment_sha = pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(
            assessment
        )
        return pr39_candidates._strict_json(raw), assessment, assessment_sha
    except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as exc:
        if _contains_extra_halfs_boundary(exc):
            projected_raw, projected_manifest, counts = _extra_halfs_projection(
                raw, manifest
            )
            excluded_count = 0
            try:
                assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
                    projected_raw, projected_manifest
                )
            except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as projected_exc:
                if not _contains_exact_request_date_mismatch(projected_exc):
                    raise CurrentFotMobFixtureCandidateAdapterError(
                        "reviewed extra-halfs projection failed PR87/PR89 assessment"
                    ) from projected_exc
                projected_raw, projected_manifest, excluded_count = _request_date_projection(
                    projected_raw, projected_manifest
                )
                try:
                    assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
                        projected_raw, projected_manifest
                    )
                except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as final_exc:
                    raise CurrentFotMobFixtureCandidateAdapterError(
                        "reviewed extra-halfs plus request-date projection assessment failed"
                    ) from final_exc
            pr89_assessment_sha = (
                pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(
                    assessment
                )
            )
            assessment_sha = _extra_halfs_assessment_sha256(
                source_manifest_sha256=manifest_sha,
                source_raw_sha256=manifest.raw_sha256,
                projected_raw=projected_raw,
                counts=counts,
                excluded_count=excluded_count,
                pr89_assessment_sha256=pr89_assessment_sha,
            )
            return pr39_candidates._strict_json(projected_raw), assessment, assessment_sha
        if not _contains_exact_request_date_mismatch(exc):
            raise CurrentFotMobFixtureCandidateAdapterError(
                "reviewed PR87/PR89 additive schema assessment failed"
            ) from exc

    projected_raw, projected_manifest, excluded_count = _request_date_projection(
        raw, manifest
    )
    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            projected_raw, projected_manifest
        )
    except pr89.FotMobDataMatchesEliminatedTeamIdValueDomainExtensionError as exc:
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed PR87/PR89 request-date projection assessment failed"
        ) from exc
    pr89_assessment_sha = (
        pr89.sha256_fotmob_data_matches_eliminated_team_id_value_domain_assessment(
            assessment
        )
    )
    assessment_sha = _projection_assessment_sha256(
        source_manifest_sha256=manifest_sha,
        source_raw_sha256=manifest.raw_sha256,
        projected_raw=projected_raw,
        excluded_count=excluded_count,
        pr89_assessment_sha256=pr89_assessment_sha,
    )
    return pr39_candidates._strict_json(projected_raw), assessment, assessment_sha


def _extended_candidate_bundle(
    raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
) -> pr39_candidates.FotMobFixtureCandidateBundle:
    raw, manifest, manifest_sha = pr39_candidates._validated_capture(
        raw_json, source_manifest
    )
    payload, assessment, assessment_sha = _qualified_extended_payload(
        raw, manifest, manifest_sha
    )
    if (
        assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        or assessment.status_reason_semantics_qualified is not False
        or assessment.final_result_semantics_qualified is not False
    ):
        raise CurrentFotMobFixtureCandidateAdapterError(
            "reviewed PR87/PR89 structural assessment changed authority"
        )

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
        schema_assessment_sha256=assessment_sha,
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
        # its schema assessment. Any other PR39 failure remains authoritative.
        if not isinstance(exc.__cause__, FotMobDataMatchesSchemaError):
            raise
        return _extended_candidate_bundle(raw_json, source_manifest)


__all__ = [
    "POLICY_ID",
    "REVIEWED_EXTRA_HALFS_KEYS",
    "REVIEWED_EXTRA_HALFS_RULE",
    "SOURCE_ACTIONS_ARTIFACT_ID",
    "SOURCE_CAPTURE_EXTRA_HALFS_OCCURRENCES",
    "SOURCE_CAPTURE_MANIFEST_FILE_SHA256",
    "SOURCE_CAPTURE_RAW_SHA256",
    "SOURCE_CAPTURE_REQUEST_DATE",
    "SOURCE_WORKFLOW_RUN_ID",
    "CurrentFotMobFixtureCandidateAdapterError",
    "build_current_fotmob_fixture_candidate_bundle",
]
