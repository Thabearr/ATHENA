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

A bounded current-only compatibility is also retained for one reviewed provider
shape first observed in Shadow run 33787560018: request date 20260905 carried
competition wrapper id/primaryId 10369 twice, once for opaque group ``A`` and
once for opaque group ``B``.  The two wrappers are identical outside ``name``,
``groupName`` and ``matches`` and every match still carries ``leagueId=10369``.
Frozen PR149 rejects any repeated wrapper id before fixture identity is checked.
For this exact reviewed shape only, current replay keeps the original raw bytes
and manifest ancestry, enforces globally unique fixture ids, and applies the
same PR149 provider-native fixture checks without inventing group semantics.
Any other repeated-wrapper shape still fails closed.

This is research/replay plumbing only.  It grants no model, probability,
pricing, selection, SportyBet execution, production, or betting authority.
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
from typing import Any

from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidates import FotMobFixtureCandidateBundle
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


REVIEWED_DUPLICATE_GROUP_WRAPPER_COMPATIBILITY_ID = (
    "CURRENT_FOTMOB_REVIEWED_DUPLICATE_GROUP_WRAPPER_20260905_V1"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_RUN_ID = 33787560018
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ARTIFACT_ID = 9907200985
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ARTIFACT_SHA256 = (
    "e09c6fd746eeb13436c85dfb557a8daa8165455b1034a6ab3cf6e03cdf3831a4"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_RAW_SHA256 = (
    "697948307624d0d71cb3ffd464de2a77b7c395c0835a4f37b78ba4b34a323de1"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE = "20260905"
REVIEWED_DUPLICATE_GROUP_WRAPPER_ID = 10369
REVIEWED_DUPLICATE_GROUP_PRIMARY_ID = 10369
REVIEWED_DUPLICATE_GROUP_NAMES = ("A", "B")
REVIEWED_DUPLICATE_GROUP_LEAGUE_NAMES = (
    "Women's World Cup U20 Grp. A",
    "Women's World Cup U20 Grp. B",
)
REVIEWED_DUPLICATE_GROUP_LABEL_PAIRS = (
    ("A", "Women's World Cup U20 Grp. A"),
    ("B", "Women's World Cup U20 Grp. B"),
)
REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME = "FIFA U-20 World Cup"


class CurrentFotMobProviderNativeQualificationError(ValueError):
    """Raised when current reviewed candidates lose exact provider lineage."""


def _error(message: str) -> CurrentFotMobProviderNativeQualificationError:
    return CurrentFotMobProviderNativeQualificationError(message)


def _wrapper_id(league: Any) -> int:
    if type(league) is not dict:
        raise _error("current provider league wrapper shape changed")
    value = league.get("id")
    if type(value) is not int or value < 1:
        raise _error("current provider league.id must be exact positive integer")
    return value


def _reviewed_duplicate_group_wrapper_present(
    payload: dict[str, Any],
    *,
    request_date: str,
) -> bool:
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error("current provider leagues must be a list")

    wrapper_ids = [_wrapper_id(league) for league in leagues]
    counts = collections.Counter(wrapper_ids)
    duplicated = {wrapper_id for wrapper_id, count in counts.items() if count > 1}
    if not duplicated:
        return False
    if duplicated != {REVIEWED_DUPLICATE_GROUP_WRAPPER_ID}:
        raise _error("unreviewed duplicate competition wrapper id in current capture")
    if request_date != REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE:
        raise _error("reviewed duplicate group wrapper escaped exact request date")

    wrappers = [
        league
        for league in leagues
        if _wrapper_id(league) == REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    ]
    if len(wrappers) != 2:
        raise _error("reviewed duplicate group wrapper occurrence count changed")

    metadata = []
    label_pairs = []
    for league in wrappers:
        if type(league.get("matches")) is not list:
            raise _error("reviewed duplicate group wrapper matches shape changed")
        if league.get("primaryId") != REVIEWED_DUPLICATE_GROUP_PRIMARY_ID:
            raise _error("reviewed duplicate group wrapper primaryId changed")
        if league.get("isGroup") is not True:
            raise _error("reviewed duplicate group wrapper lost exact isGroup=true")
        if league.get("ccode") != "INT":
            raise _error("reviewed duplicate group wrapper ccode changed")
        if league.get("parentLeagueName") != REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME:
            raise _error("reviewed duplicate group wrapper parentLeagueName changed")
        if league.get("internalRank") != 0 or league.get("simpleLeague") is not False:
            raise _error("reviewed duplicate group wrapper opaque metadata changed")
        group_name = league.get("groupName")
        league_name = league.get("name")
        if type(group_name) is not str or type(league_name) is not str:
            raise _error("reviewed duplicate group wrapper labels changed type")
        label_pairs.append((group_name, league_name))
        metadata.append(
            {
                key: value
                for key, value in league.items()
                if key not in {"groupName", "name", "matches"}
            }
        )

    if tuple(sorted(label_pairs)) != REVIEWED_DUPLICATE_GROUP_LABEL_PAIRS:
        raise _error("reviewed duplicate group wrapper label pairing changed")
    if metadata[0] != metadata[1]:
        raise _error("reviewed duplicate group wrappers differ outside opaque group labels")
    return True


def _qualify_reviewed_duplicate_group_wrapper_payload(
    raw_json: bytes,
    *,
    capture_observed_at: Any,
    capture_manifest_sha256: str,
    capture_raw_sha256: str,
    request_date: str,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Replay PR149 identity checks for the one reviewed repeated-wrapper shape."""

    payload = fresh._strict_json(raw_json)
    if not _reviewed_duplicate_group_wrapper_present(
        payload,
        request_date=request_date,
    ):
        return fresh._qualify_provider_identity_payload(
            raw_json,
            capture_observed_at=capture_observed_at,
            capture_manifest_sha256=capture_manifest_sha256,
            capture_raw_sha256=capture_raw_sha256,
        )

    if hashlib.sha256(raw_json).hexdigest() != capture_raw_sha256:
        raise _error("current raw capture SHA-256 lineage changed")
    observed = fresh._utc(capture_observed_at, "capture_observed_at")
    manifest_sha = fresh._sha256(capture_manifest_sha256, "capture_manifest_sha256")
    raw_sha = fresh._sha256(capture_raw_sha256, "capture_raw_sha256")

    leagues = payload["leagues"]
    result: list[fresh.QualifiedCaptureFixture] = []
    seen_fixtures: set[int] = set()
    for league in leagues:
        if type(league) is not dict or type(league.get("matches")) is not list:
            raise _error("league wrapper shape changed")
        primary_id = fresh._positive_int(league.get("primaryId"), "league.primaryId")
        wrapper_id = fresh._positive_int(league.get("id"), "league.id")
        for match in league["matches"]:
            if type(match) is not dict:
                raise _error("match shape changed")
            fixture_id = fresh._positive_int(match.get("id"), "match.id")
            if fixture_id in seen_fixtures:
                raise _error("fixture id duplicated in one capture")
            seen_fixtures.add(fixture_id)
            match_league_id = fresh._positive_int(match.get("leagueId"), "match.leagueId")
            if match_league_id != wrapper_id:
                raise _error("match.leagueId does not equal containing league.id")
            home = match.get("home")
            away = match.get("away")
            status = match.get("status")
            if type(home) is not dict or type(away) is not dict or type(status) is not dict:
                raise _error("match home/away/status shape changed")
            home_id = fresh._positive_int(home.get("id"), "match.home.id")
            away_id = fresh._positive_int(away.get("id"), "match.away.id")
            if home_id == away_id:
                raise _error("match cannot use one team twice")
            kickoff = fresh._parse_utc(status.get("utcTime"), "status.utcTime")
            result.append(
                fresh.QualifiedCaptureFixture(
                    fixture_id=fixture_id,
                    provider_primary_id=primary_id,
                    wrapper_id=wrapper_id,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    kickoff_utc=kickoff,
                    capture_observed_at=observed,
                    capture_manifest_sha256=manifest_sha,
                    capture_raw_sha256=raw_sha,
                )
            )
    result.sort(key=lambda item: (item.kickoff_utc, item.fixture_id))
    return tuple(result)


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
        qualified_raw = _qualify_reviewed_duplicate_group_wrapper_payload(
            raw_json,
            capture_observed_at=manifest.observed_at,
            capture_manifest_sha256=manifest_sha,
            capture_raw_sha256=manifest.raw_sha256,
            request_date=manifest.request_date,
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
