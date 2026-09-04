"""Reviewed live-capture identity compatibility for the FotMob fresh holdout.

The frozen PR39 fixture-candidate schema predates reviewed terminal-state fields.
This adapter grants no football semantics. It admits only the reviewed additive
capture compatibility needed by preserved live evidence, re-runs the existing
PR89 -> PR87 -> PR39 structural chain, and rebuilds the PR40 fixture-candidate
population from validation-only projections.

Two opaque ``status.halfs`` strings remain admitted from PR208. In addition, a
request bucket may contain fixtures whose exact ``status.utcTime`` falls on the
immediately previous UTC date while the provider's opaque display ``time`` date
matches the requested date. Such rows are structurally revalidated in a separate
previous-date projection and excluded from fresh candidate qualification. No
provider bucket, timezone, kickoff, or football semantics are inferred.

A second bounded structural compatibility covers the exact 20260905 provider
shape preserved by fresh-holdout run 33823663641: wrapper id/primaryId 10369 is
repeated exactly twice for opaque groups ``A`` and ``B``. Each wrapper is
validated independently through the frozen structural/candidate chain so the
reviewed group labels are never merged or reinterpreted. Provider-native fixture
identity is still extracted from the exact original raw capture.

Returned qualified fixture identity remains extracted from the exact original
network capture and bound to the original manifest. Compatibility projections
are validation-only and are never promoted to source evidence.
"""
from __future__ import annotations

from collections import Counter
import copy
import dataclasses
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_data_matches_terminal_state_schema_extension as pr87
import domain.fotmob_fixture_candidates as fixture_candidates
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


SCHEMA_VERSION = 1
ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_REVIEWED_SCHEMA_ADAPTER_V2"
ADAPTER_STATE = "REVIEWED_STRUCTURAL_COMPATIBILITY_ONLY_NO_FOOTBALL_SEMANTIC_PROMOTION"

FRESH_HOLDOUT_CORE_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR87_IMPLEMENTATION_BLOB_SHA = "fc120476739293abbb5db4374a0b4d7cfe8a1fc3"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
FIXTURE_CANDIDATE_BLOB_SHA = "a3434951e87cfbd90dd2c43cccd413e7edfb08e0"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"

EXTRA_HALFS_KEYS = ("firstExtraHalfStarted", "secondExtraHalfStarted")
EXTRA_HALFS_RULE = (
    "OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_OPAQUE_NO_EXTRA_TIME_SEMANTICS"
)
REQUEST_BUCKET_SPILLOVER_RULE = (
    "EXCLUDE_ONLY_IMMEDIATELY_PREVIOUS_UTC_DATE_FIXTURES_WITH_EXACT_TIMETS_"
    "AND_REQUEST_DATE_DISPLAY_TEXT_NO_PROVIDER_BUCKET_OR_TIMEZONE_SEMANTICS"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_RULE = (
    "EXACT_20260905_WRAPPER_10369_GROUP_A_B_SEPARATE_VALIDATION_ONLY_"
    "NO_GROUP_SEMANTICS_NO_MERGE_NO_FUZZY"
)

SOURCE_WORKFLOW_RUN_ID = 32583079461
SOURCE_ACTIONS_ARTIFACT_ID = 9478318255
SOURCE_ACTIONS_ARTIFACT_NAME = "failure-20260822T153700Z-run-32583079461.tar.gz"
SOURCE_RELEASE_TAG = "athena-fresh-holdout-evidence-2026-W34"
SOURCE_RELEASE_ASSET_NAME = SOURCE_ACTIONS_ARTIFACT_NAME
SOURCE_CAPTURE_LINEAGES = (
    {
        "request_date": "20260821",
        "manifest_sha256": "1cacc67a60889c498dbc0877b2604382c619197c0e68a2e3253bf2739b3bae9d",
        "raw_sha256": "a0273b704e786fdce00abf27487a710a06fbdbeef3b4902a83d9ccf00f9e0176",
        "firstExtraHalfStarted_occurrences": 1,
        "secondExtraHalfStarted_occurrences": 1,
    },
    {
        "request_date": "20260822",
        "manifest_sha256": "aaacdc3ec7c7d4dce5b4a9bd1b8bcd3e222f2eb4a696c629bb4e5896457e58ff",
        "raw_sha256": "595e63c57f7b7a3876f9d7f3c6498b8a0fab84c13c7adac275ba30bf3e5a2730",
        "firstExtraHalfStarted_occurrences": 3,
        "secondExtraHalfStarted_occurrences": 3,
    },
)
SPILLOVER_SOURCE_WORKFLOW_RUN_ID = 32612280129
SPILLOVER_SOURCE_ACTIONS_ARTIFACT_ID = 9485854548
SPILLOVER_SOURCE_ACTIONS_ARTIFACT_NAME = (
    "failure-20260823T013700Z-run-32612280129.tar.gz"
)
SPILLOVER_SOURCE_REQUEST_DATE = "20260823"
SPILLOVER_SOURCE_OBSERVED_AT = "2026-08-23T02:13:12.040926Z"
SPILLOVER_SOURCE_MANIFEST_SHA256 = (
    "7b763b0e55126529f1fd4879a2fe0170215ee3f467a28caad538ef77c8b561a8"
)
SPILLOVER_SOURCE_RAW_SHA256 = (
    "445bc09a013fabf3bd953e2980ee54bee6e1fb8ab50f4686ab2de67bea02c023"
)
SPILLOVER_SOURCE_FIXTURE_IDS = (1000008693, 1000014538)

REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_WORKFLOW_RUN_ID = 33823663641
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_ID = 9919255715
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_SHA256 = (
    "792ddba3b8f4b38bc494f8d0a660a80dceb5c8c9f2a9bcdaf88cbba43ac5f43a"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_CAPTURE_ID = "797133444d500f22a60b03d4"
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_OBSERVED_AT = "2026-09-04T00:59:19.213485Z"
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_MANIFEST_SHA256 = (
    "e34365e25fce42c7106e9c54b0fc1df77a97311cb499a5895c6322c8d7bb8781"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_RAW_SHA256 = (
    "a19c50ca3c3e7c9c57d83f2b83a43d1cc3d75c92b9a788f25d74473de3ed0b19"
)
REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE = "20260905"
REVIEWED_DUPLICATE_GROUP_WRAPPER_ID = 10369
REVIEWED_DUPLICATE_GROUP_PRIMARY_ID = 10369
REVIEWED_DUPLICATE_GROUP_LABEL_PAIRS = (
    ("A", "Women's World Cup U20 Grp. A"),
    ("B", "Women's World Cup U20 Grp. B"),
)
REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME = "FIFA U-20 World Cup"

_DISPLAY_TIME_RE = re.compile(
    r"^[0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}$",
    flags=re.ASCII,
)

SAFETY_KEYS = (
    "football_semantics_promoted",
    "final_result_semantics_promoted",
    "extra_time_semantics_promoted",
    "request_bucket_semantics_promoted",
    "timezone_semantics_promoted",
    "source_capability_changed",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutCaptureQualificationAdapterError(RuntimeError):
    """Raised when structural compatibility cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutCaptureQualificationAdapterError:
    return FreshHoldoutCaptureQualificationAdapterError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    """Fail closed if any reviewed implementation dependency moved."""
    pins = (
        (Path(fresh.__file__), FRESH_HOLDOUT_CORE_BLOB_SHA, "fresh-holdout core"),
        (Path(pr39_schema.__file__), PR39_SCHEMA_BLOB_SHA, "PR39 schema"),
        (Path(pr87.__file__), PR87_IMPLEMENTATION_BLOB_SHA, "PR87 terminal extension"),
        (Path(pr89.__file__), PR89_IMPLEMENTATION_BLOB_SHA, "PR89 eliminatedTeamId extension"),
        (Path(fixture_candidates.__file__), FIXTURE_CANDIDATE_BLOB_SHA, "PR40 fixture candidates"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "PR38 capture contract"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify reviewed adapter dependencies") from exc


def _strict_json(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error("raw capture must be non-empty exact bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise _error(f"raw capture contains duplicate JSON key {key!r}")
            out[key] = value
        return out

    def constant(token: str) -> None:
        raise _error(f"raw capture contains forbidden JSON constant {token!r}")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except FreshHoldoutCaptureQualificationAdapterError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("raw capture is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise _error("raw capture top level must be an object")
    return value


def _canonical(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("compatibility projection serialization failed") from exc


def _projected_manifest(
    source_manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    projected_raw: bytes,
    *,
    request_date: str | None = None,
) -> capture_contract.FotMobDataMatchesCaptureManifest:
    content_length = (
        None if source_manifest.content_length is None else len(projected_raw)
    )
    projected_request_date = (
        source_manifest.request_date if request_date is None else request_date
    )
    try:
        return dataclasses.replace(
            source_manifest,
            request_date=projected_request_date,
            request_target=capture_contract._target(
                projected_request_date,
                source_manifest.timezone,
                source_manifest.ccode3,
            ),
            content_length=content_length,
            network_acquisition_performed=False,
            raw_sha256=hashlib.sha256(projected_raw).hexdigest(),
            raw_size=len(projected_raw),
        )
    except Exception as exc:
        raise _error("compatibility projection manifest failed validation") from exc


def _remove_reviewed_extra_halfs(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove only the two reviewed opaque keys after exact-type validation."""
    projected = copy.deepcopy(payload)
    leagues = projected.get("leagues")
    if type(leagues) is not list:
        return projected
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
            for key in EXTRA_HALFS_KEYS:
                if key not in halfs:
                    continue
                value = halfs[key]
                if type(value) is not str:
                    raise _error(
                        f"leagues[{league_index}].matches[{match_index}]."
                        f"status.halfs.{key} must be an exact string"
                    )
                del halfs[key]
    return projected


def _request_date(value: str) -> dt.date:
    if type(value) is not str or len(value) != 8 or not value.isascii() or not value.isdigit():
        raise _error("request_date must be exact YYYYMMDD text")
    try:
        parsed = dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise _error("request_date is not a valid calendar date") from exc
    if parsed.strftime("%Y%m%d") != value:
        raise _error("request_date is not canonical YYYYMMDD text")
    return parsed


def _kickoff_utc(value: Any) -> dt.datetime | None:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.utcoffset() != dt.timedelta(0) or parsed.microsecond % 1000:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _epoch_milliseconds(value: dt.datetime) -> int:
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    delta = value - epoch
    return (
        delta.days * 86_400_000
        + delta.seconds * 1_000
        + delta.microseconds // 1_000
    )


def _wrapper_id(league: Any) -> int:
    if type(league) is not dict:
        raise _error("reviewed duplicate group wrapper league shape changed")
    value = league.get("id")
    if type(value) is not int or value < 1:
        raise _error("reviewed duplicate group wrapper league.id must be exact positive integer")
    return value


def _reviewed_duplicate_group_wrapper_present(
    payload: dict[str, Any],
    *,
    request_date: str,
) -> bool:
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error("reviewed duplicate group wrapper requires leagues list")
    wrapper_ids = [_wrapper_id(league) for league in leagues]
    duplicated = {
        wrapper_id
        for wrapper_id, count in Counter(wrapper_ids).items()
        if count > 1
    }
    if not duplicated:
        return False
    if duplicated != {REVIEWED_DUPLICATE_GROUP_WRAPPER_ID}:
        raise _error("unreviewed duplicate competition wrapper id in fresh holdout capture")
    if request_date != REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE:
        raise _error("reviewed duplicate group wrapper escaped exact request date")
    if payload.get("date") != request_date:
        raise _error("reviewed duplicate group wrapper top-level date changed")

    wrappers = [
        league
        for league in leagues
        if _wrapper_id(league) == REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    ]
    if len(wrappers) != 2:
        raise _error("reviewed duplicate group wrapper occurrence count changed")

    metadata: list[dict[str, Any]] = []
    label_pairs: list[tuple[str, str]] = []
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


def _reviewed_duplicate_group_fixture_ids(payload: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for league in payload["leagues"]:
        if _wrapper_id(league) != REVIEWED_DUPLICATE_GROUP_WRAPPER_ID:
            continue
        for match in league["matches"]:
            if type(match) is not dict:
                raise _error("reviewed duplicate group wrapper match shape changed")
            fixture_id = match.get("id")
            if type(fixture_id) is not int or fixture_id < 1:
                raise _error("reviewed duplicate group wrapper fixture id changed")
            if fixture_id in result:
                raise _error("fixture id duplicated in reviewed duplicate group wrappers")
            result.add(fixture_id)
    return result


def _partition_reviewed_duplicate_group_structural_payloads(
    payload: dict[str, Any],
    *,
    request_date: str,
) -> tuple[tuple[dict[str, Any], str], ...]:
    if not _reviewed_duplicate_group_wrapper_present(
        payload,
        request_date=request_date,
    ):
        return ((copy.deepcopy(payload), "requested-date candidate population"),)

    ordinary = []
    groups = []
    for league in payload["leagues"]:
        if _wrapper_id(league) == REVIEWED_DUPLICATE_GROUP_WRAPPER_ID:
            groups.append(copy.deepcopy(league))
        else:
            ordinary.append(copy.deepcopy(league))

    partitions: list[tuple[dict[str, Any], str]] = []
    if ordinary:
        projected = copy.deepcopy(payload)
        projected["leagues"] = ordinary
        partitions.append(
            (projected, "requested-date non-duplicated wrapper population")
        )
    for league in sorted(groups, key=lambda item: item["groupName"]):
        projected = copy.deepcopy(payload)
        projected["leagues"] = [league]
        partitions.append(
            (
                projected,
                f"requested-date reviewed duplicate group {league['groupName']} population",
            )
        )
    if not partitions:
        raise _error("reviewed duplicate group structural partition is empty")
    return tuple(partitions)


def _validate_previous_utc_day_spillover(
    match: dict[str, Any],
    *,
    request_date: dt.date,
    kickoff: dt.datetime,
    label: str,
) -> int:
    fixture_id = match.get("id")
    if type(fixture_id) is not int or fixture_id < 1:
        raise _error(f"{label}.id must be an exact positive integer")
    timestamp_ms = match.get("timeTS")
    if type(timestamp_ms) is not int or timestamp_ms != _epoch_milliseconds(kickoff):
        raise _error(f"{label}.timeTS must exactly match previous-day status.utcTime")
    display_time = match.get("time")
    expected_display_date = request_date.strftime("%d.%m.%Y")
    if (
        type(display_time) is not str
        or _DISPLAY_TIME_RE.fullmatch(display_time) is None
        or not display_time.startswith(expected_display_date + " ")
    ):
        raise _error(
            f"{label}.time must carry the exact request-date display text for reviewed spillover"
        )
    return fixture_id


def partition_reviewed_request_bucket_spillover(
    payload: dict[str, Any],
    request_date: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[int, ...]]:
    """Partition only the reviewed previous-UTC-day request-bucket spillover shape.

    Both returned payloads are validation-only copies. The primary payload retains
    only fixtures whose UTC kickoff date is not the exact reviewed previous-day
    spillover shape. The optional spillover payload contains only those reviewed
    rows and rewrites only its top-level request date so the frozen structural
    chain can validate the rows against their unchanged UTC kickoff identities.
    """
    if type(payload) is not dict:
        raise _error("request-bucket payload must be an object")
    requested = _request_date(request_date)
    if payload.get("date") != request_date:
        return copy.deepcopy(payload), None, ()
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        return copy.deepcopy(payload), None, ()

    previous = requested - dt.timedelta(days=1)
    primary = copy.deepcopy(payload)
    spillover = copy.deepcopy(payload)
    primary_leagues: list[dict[str, Any]] = []
    spillover_leagues: list[dict[str, Any]] = []
    seen_fixture_ids: set[int] = set()
    spillover_ids: list[int] = []

    for league_index, raw_league in enumerate(leagues):
        if type(raw_league) is not dict or type(raw_league.get("matches")) is not list:
            raise _error(f"leagues[{league_index}] shape changed before spillover review")
        primary_league = copy.deepcopy(raw_league)
        spillover_league = copy.deepcopy(raw_league)
        primary_matches: list[Any] = []
        spillover_matches: list[Any] = []
        for match_index, raw_match in enumerate(raw_league["matches"]):
            label = f"leagues[{league_index}].matches[{match_index}]"
            if type(raw_match) is not dict:
                raise _error(f"{label} must be an object")
            fixture_id = raw_match.get("id")
            if type(fixture_id) is not int or fixture_id < 1:
                raise _error(f"{label}.id must be an exact positive integer")
            if fixture_id in seen_fixture_ids:
                raise _error("fixture id duplicated in original request bucket")
            seen_fixture_ids.add(fixture_id)
            status = raw_match.get("status")
            kickoff = (
                None
                if type(status) is not dict
                else _kickoff_utc(status.get("utcTime"))
            )
            if kickoff is not None and kickoff.date() == previous:
                reviewed_id = _validate_previous_utc_day_spillover(
                    raw_match,
                    request_date=requested,
                    kickoff=kickoff,
                    label=label,
                )
                spillover_matches.append(copy.deepcopy(raw_match))
                spillover_ids.append(reviewed_id)
            else:
                primary_matches.append(copy.deepcopy(raw_match))
        primary_league["matches"] = primary_matches
        primary_leagues.append(primary_league)
        if spillover_matches:
            spillover_league["matches"] = spillover_matches
            spillover_leagues.append(spillover_league)

    primary["leagues"] = primary_leagues
    if not spillover_ids:
        return primary, None, ()
    spillover["date"] = previous.strftime("%Y%m%d")
    spillover["leagues"] = spillover_leagues
    return primary, spillover, tuple(sorted(spillover_ids))


def _assess_reviewed_structural_payload(
    payload: dict[str, Any],
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
    *,
    request_date: str | None = None,
    label: str,
) -> tuple[dict[str, Any], capture_contract.FotMobDataMatchesCaptureManifest]:
    pr89_payload = _remove_reviewed_extra_halfs(payload)
    pr89_raw = _canonical(pr89_payload)
    pr89_manifest = _projected_manifest(
        manifest,
        pr89_raw,
        request_date=request_date,
    )
    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            pr89_raw,
            pr89_manifest,
        )
    except Exception as exc:
        raise _error(f"reviewed PR89->PR87->PR39 structural chain failed for {label}") from exc
    if (
        assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    ):
        raise _error(f"reviewed PR89 chain did not return exact qualified status for {label}")
    if assessment.status_reason_semantics_qualified or assessment.final_result_semantics_qualified:
        raise _error("reviewed structural chain unexpectedly promoted semantics")
    return pr89_payload, pr89_manifest


def _project_to_pr39(payload: dict[str, Any]) -> dict[str, Any]:
    """Project only fields already qualified by PR89/PR87 down to frozen PR39."""
    projected = copy.deepcopy(payload)
    leagues = projected.get("leagues")
    if type(leagues) is not list:
        raise _error("qualified projection lost leagues list")
    for league in leagues:
        if type(league) is not dict:
            raise _error("qualified projection league is not an object")
        matches = league.get("matches")
        if type(matches) is not list:
            raise _error("qualified projection lost match list")
        for match in matches:
            if type(match) is not dict:
                raise _error("qualified projection match is not an object")
            match["eliminatedTeamId"] = None
            for side in ("home", "away"):
                team = match.get(side)
                if type(team) is not dict:
                    raise _error("qualified projection team is not an object")
                for key in tuple(team):
                    if key not in pr39_schema.TEAM_KEYS:
                        del team[key]
            status = match.get("status")
            if type(status) is not dict:
                raise _error("qualified projection status is not an object")
            for key in tuple(status):
                if key not in pr39_schema.STATUS_ALLOWED_KEYS:
                    del status[key]
            halfs = status.get("halfs")
            if type(halfs) is not dict:
                raise _error("qualified projection halfs is not an object")
            for key in tuple(halfs):
                if key not in pr39_schema.HALFS_KEYS:
                    del halfs[key]
    return projected


def _build_reviewed_candidate_population(
    primary_payload: dict[str, Any],
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[dict[int, Any], dict[int, tuple[str, str]], int]:
    candidates: dict[int, Any] = {}
    lineage: dict[int, tuple[str, str]] = {}
    candidate_count = 0
    for structural_payload, label in _partition_reviewed_duplicate_group_structural_payloads(
        primary_payload,
        request_date=manifest.request_date,
    ):
        pr89_payload, _pr89_manifest = _assess_reviewed_structural_payload(
            structural_payload,
            manifest,
            label=label,
        )
        candidate_payload = _project_to_pr39(pr89_payload)
        candidate_raw = _canonical(candidate_payload)
        candidate_manifest = _projected_manifest(manifest, candidate_raw)
        try:
            bundle = fixture_candidates.build_fotmob_fixture_candidate_bundle(
                ((candidate_raw, candidate_manifest),)
            )
        except Exception as exc:
            raise _error(f"reviewed PR39 fixture-candidate projection failed for {label}") from exc
        projected_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(
            candidate_manifest
        )
        candidate_count += len(bundle.candidates)
        for candidate in bundle.candidates:
            fixture_id = candidate.source_match_id
            if fixture_id in candidates:
                raise _error("fixture id duplicated across reviewed structural partitions")
            candidates[fixture_id] = candidate
            lineage[fixture_id] = (
                candidate_manifest.raw_sha256,
                projected_manifest_sha,
            )
    return candidates, lineage, candidate_count


def _qualify_original_provider_identity(
    raw_json: bytes,
    *,
    payload: dict[str, Any],
    capture_observed_at: Any,
    capture_manifest_sha256: str,
    capture_raw_sha256: str,
    request_date: str,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
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
        raise _error("reviewed duplicate group raw capture SHA-256 lineage changed")
    observed = fresh._utc(capture_observed_at, "capture_observed_at")
    manifest_sha = fresh._sha256(capture_manifest_sha256, "capture_manifest_sha256")
    raw_sha = fresh._sha256(capture_raw_sha256, "capture_raw_sha256")

    result: list[fresh.QualifiedCaptureFixture] = []
    seen_fixtures: set[int] = set()
    for league in payload["leagues"]:
        if type(league) is not dict or type(league.get("matches")) is not list:
            raise _error("league wrapper shape changed during duplicate group replay")
        primary_id = fresh._positive_int(league.get("primaryId"), "league.primaryId")
        wrapper_id = fresh._positive_int(league.get("id"), "league.id")
        for match in league["matches"]:
            if type(match) is not dict:
                raise _error("match shape changed during duplicate group replay")
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


def qualify_capture_fixtures(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Qualify same-request-date fixture identity while preserving source lineage."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("fresh holdout adapter requires an actual reviewed network capture")
    if type(raw_json) is not bytes:
        raise _error("raw capture must be exact bytes")
    if manifest.raw_size != len(raw_json):
        raise _error("raw capture size does not match original manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")

    payload = _strict_json(raw_json)
    duplicate_group_present = _reviewed_duplicate_group_wrapper_present(
        payload,
        request_date=manifest.request_date,
    )
    duplicate_group_fixture_ids = (
        _reviewed_duplicate_group_fixture_ids(payload)
        if duplicate_group_present
        else set()
    )
    primary_payload, spillover_payload, spillover_ids = (
        partition_reviewed_request_bucket_spillover(payload, manifest.request_date)
    )
    if duplicate_group_fixture_ids & set(spillover_ids):
        raise _error(
            "reviewed duplicate group wrapper cannot combine with previous-day spillover"
        )

    candidates, candidate_lineage, candidate_count = _build_reviewed_candidate_population(
        primary_payload,
        manifest,
    )
    if spillover_payload is not None:
        previous_date = (_request_date(manifest.request_date) - dt.timedelta(days=1)).strftime(
            "%Y%m%d"
        )
        _assess_reviewed_structural_payload(
            spillover_payload,
            manifest,
            request_date=previous_date,
            label="reviewed previous-UTC-day spillover population",
        )

    original_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(
        manifest
    )
    original_qualified = _qualify_original_provider_identity(
        raw_json,
        payload=payload,
        capture_observed_at=manifest.observed_at,
        capture_manifest_sha256=original_manifest_sha,
        capture_raw_sha256=manifest.raw_sha256,
        request_date=manifest.request_date,
    )

    candidate_ids = set(candidates)
    spillover_id_set = set(spillover_ids)
    original_ids = {item.fixture_id for item in original_qualified}
    if (
        len(candidates) != candidate_count
        or candidate_ids & spillover_id_set
        or original_ids != candidate_ids | spillover_id_set
        or len(original_ids) != len(original_qualified)
    ):
        raise _error("reviewed candidate, spillover, and exact identity populations disagree")

    qualified = tuple(
        item for item in original_qualified if item.fixture_id in candidate_ids
    )
    if len(qualified) != candidate_count:
        raise _error("reviewed candidate and retained identity populations disagree")
    previous_date = _request_date(manifest.request_date) - dt.timedelta(days=1)
    for item in original_qualified:
        if item.fixture_id in spillover_id_set and item.kickoff_utc.date() != previous_date:
            raise _error("excluded spillover fixture escaped reviewed previous UTC date")

    for item in qualified:
        candidate = candidates.get(item.fixture_id)
        if candidate is None:
            raise _error("qualified fixture absent from reviewed candidate population")
        expected_identity = (
            candidate.source_competition_primary_id,
            candidate.source_league_id,
            candidate.home_source_team_id,
            candidate.away_source_team_id,
            candidate.kickoff_utc,
            candidate.source_observed_at,
        )
        actual_identity = (
            item.provider_primary_id,
            item.wrapper_id,
            item.home_team_id,
            item.away_team_id,
            item.kickoff_utc,
            item.capture_observed_at,
        )
        if actual_identity != expected_identity:
            raise _error(
                "exact provider identity disagrees with reviewed candidate projection"
            )
        projected_raw_sha, projected_manifest_sha = candidate_lineage[item.fixture_id]
        if (
            candidate.source_request_date != manifest.request_date
            or candidate.source_raw_sha256 != projected_raw_sha
            or candidate.source_capture_manifest_sha256 != projected_manifest_sha
        ):
            raise _error("candidate projection lineage is internally inconsistent")
        if (
            item.capture_raw_sha256 != manifest.raw_sha256
            or item.capture_manifest_sha256 != original_manifest_sha
        ):
            raise _error("returned fixture escaped original network capture lineage")
    return qualified


def adapter_receipt() -> dict[str, Any]:
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_state": ADAPTER_STATE,
        "reviewed_extra_halfs_keys": list(EXTRA_HALFS_KEYS),
        "reviewed_extra_halfs_rule": EXTRA_HALFS_RULE,
        "reviewed_request_bucket_spillover_rule": REQUEST_BUCKET_SPILLOVER_RULE,
        "reviewed_duplicate_group_wrapper_rule": REVIEWED_DUPLICATE_GROUP_WRAPPER_RULE,
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_actions_artifact_id": SOURCE_ACTIONS_ARTIFACT_ID,
        "source_actions_artifact_name": SOURCE_ACTIONS_ARTIFACT_NAME,
        "source_release_tag": SOURCE_RELEASE_TAG,
        "source_release_asset_name": SOURCE_RELEASE_ASSET_NAME,
        "source_capture_lineages": [dict(item) for item in SOURCE_CAPTURE_LINEAGES],
        "spillover_source_workflow_run_id": SPILLOVER_SOURCE_WORKFLOW_RUN_ID,
        "spillover_source_actions_artifact_id": SPILLOVER_SOURCE_ACTIONS_ARTIFACT_ID,
        "spillover_source_actions_artifact_name": SPILLOVER_SOURCE_ACTIONS_ARTIFACT_NAME,
        "spillover_source_request_date": SPILLOVER_SOURCE_REQUEST_DATE,
        "spillover_source_observed_at": SPILLOVER_SOURCE_OBSERVED_AT,
        "spillover_source_manifest_sha256": SPILLOVER_SOURCE_MANIFEST_SHA256,
        "spillover_source_raw_sha256": SPILLOVER_SOURCE_RAW_SHA256,
        "spillover_source_fixture_ids": list(SPILLOVER_SOURCE_FIXTURE_IDS),
        "duplicate_group_source_workflow_run_id": (
            REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_WORKFLOW_RUN_ID
        ),
        "duplicate_group_source_actions_artifact_id": (
            REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_ID
        ),
        "duplicate_group_source_actions_artifact_sha256": (
            REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_SHA256
        ),
        "duplicate_group_source_capture_id": REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_CAPTURE_ID,
        "duplicate_group_source_observed_at": REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_OBSERVED_AT,
        "duplicate_group_source_manifest_sha256": (
            REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_MANIFEST_SHA256
        ),
        "duplicate_group_source_raw_sha256": REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_RAW_SHA256,
        "duplicate_group_request_date": REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE,
        "duplicate_group_wrapper_id": REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "duplicate_group_primary_id": REVIEWED_DUPLICATE_GROUP_PRIMARY_ID,
        "duplicate_group_label_pairs": [list(item) for item in REVIEWED_DUPLICATE_GROUP_LABEL_PAIRS],
        "duplicate_group_parent_league_name": REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME,
        "duplicate_group_wrappers_structurally_revalidated_separately": True,
        "duplicate_group_labels_not_merged_or_semantically_interpreted": True,
        "spillover_rows_excluded_from_fresh_candidate_population": True,
        "spillover_rows_structurally_revalidated_separately": True,
        "original_network_capture_lineage_preserved_in_returned_fixtures": True,
        "compatibility_projection_is_not_source_evidence": True,
        "network_acquisition_performed": False,
        "safety": {key: False for key in SAFETY_KEYS},
    }


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_STATE",
    "EXTRA_HALFS_KEYS",
    "EXTRA_HALFS_RULE",
    "FreshHoldoutCaptureQualificationAdapterError",
    "REQUEST_BUCKET_SPILLOVER_RULE",
    "REVIEWED_DUPLICATE_GROUP_LABEL_PAIRS",
    "REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME",
    "REVIEWED_DUPLICATE_GROUP_PRIMARY_ID",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_ID",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_RULE",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_ID",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_ACTIONS_ARTIFACT_SHA256",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_CAPTURE_ID",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_MANIFEST_SHA256",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_OBSERVED_AT",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_RAW_SHA256",
    "REVIEWED_DUPLICATE_GROUP_WRAPPER_SOURCE_WORKFLOW_RUN_ID",
    "SOURCE_ACTIONS_ARTIFACT_ID",
    "SOURCE_ACTIONS_ARTIFACT_NAME",
    "SOURCE_CAPTURE_LINEAGES",
    "SOURCE_RELEASE_ASSET_NAME",
    "SOURCE_RELEASE_TAG",
    "SOURCE_WORKFLOW_RUN_ID",
    "SPILLOVER_SOURCE_ACTIONS_ARTIFACT_ID",
    "SPILLOVER_SOURCE_ACTIONS_ARTIFACT_NAME",
    "SPILLOVER_SOURCE_FIXTURE_IDS",
    "SPILLOVER_SOURCE_MANIFEST_SHA256",
    "SPILLOVER_SOURCE_OBSERVED_AT",
    "SPILLOVER_SOURCE_RAW_SHA256",
    "SPILLOVER_SOURCE_REQUEST_DATE",
    "SPILLOVER_SOURCE_WORKFLOW_RUN_ID",
    "adapter_receipt",
    "partition_reviewed_request_bucket_spillover",
    "qualify_capture_fixtures",
    "verify_reviewed_dependencies",
]
