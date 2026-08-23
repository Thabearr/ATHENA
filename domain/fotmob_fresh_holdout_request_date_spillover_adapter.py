"""Reviewed request-date bucket spillover compatibility for fresh FotMob captures.

A preserved 2026-08-23 live ``/api/data/matches`` capture showed that FotMob can
place already-live fixtures in the requested calendar bucket even when their
explicit ``status.utcTime`` is on the immediately previous UTC date.  The two
observed rows retained a provider display ``time`` date equal to the requested
bucket and internally consistent ``status.utcTime``/``timeTS`` identities.

This adapter keeps PR39 and the PR208 adapter frozen.  It admits only that narrow
structural bucket condition: an off-request-date fixture must be on the
immediately previous UTC date and its provider display date must equal the exact
request date.  Every UTC-date partition is separately re-run through the already
reviewed PR89 -> PR87 -> PR39 structural chain.  Only the exact request-UTC-date
partition is eligible for fresh fixture-candidate output; previous-date spillover
is validated but excluded from the prospective candidate population.

All returned fixtures remain bound to the original network capture bytes and
manifest.  Validation projections are never promoted to source evidence.  No
kickoff is rewritten, no missed observation is reconstructed, and no football,
model, pricing, selection, production, or betting semantics are added.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import re
from pathlib import Path
from typing import Any

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_schema as pr39_schema
import domain.fotmob_fixture_candidates as fixture_candidates
import domain.fotmob_fresh_holdout_capture_qualification_adapter as pr208_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


SCHEMA_VERSION = 1
ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_REQUEST_DATE_SPILLOVER_ADAPTER_V1"
ADAPTER_STATE = (
    "REVIEWED_PREVIOUS_UTC_DATE_BUCKET_SPILLOVER_STRUCTURAL_COMPATIBILITY_ONLY"
)

PR208_ADAPTER_BLOB_SHA = "b6bbbda19b13a81c17ff5386e402f0a585249cb7"
FRESH_HOLDOUT_CORE_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
FIXTURE_CANDIDATE_BLOB_SHA = "a3434951e87cfbd90dd2c43cccd413e7edfb08e0"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"

SOURCE_WORKFLOW_RUN_ID = 32612280129
SOURCE_ACTIONS_ARTIFACT_ID = 9485854548
SOURCE_ACTIONS_ARTIFACT_NAME = "failure-20260823T013700Z-run-32612280129.tar.gz"
SOURCE_ARCHIVE_SHA256 = "359524b3477da9fc46a60dde41a0a2179631d735e1de4bfce7cea6fb1c6aa60c"
SOURCE_REQUEST_DATE = "20260823"
SOURCE_CAPTURE_OBSERVED_AT = "2026-08-23T02:13:12.040926Z"
SOURCE_CAPTURE_RAW_SHA256 = "445bc09a013fabf3bd953e2980ee54bee6e1fb8ab50f4686ab2de67bea02c023"
SOURCE_CAPTURE_MANIFEST_SHA256 = "7b763b0e55126529f1fd4879a2fe0170215ee3f467a28caad538ef77c8b561a8"
SOURCE_SPILLOVER_FIXTURE_IDS = (1000008693, 1000014538)
SOURCE_SPILLOVER_KICKOFFS = (
    "2026-08-22T23:07:00.000Z",
    "2026-08-22T23:30:00.000Z",
)

_DISPLAY_TIME_RE = re.compile(
    r"^(?P<day>[0-9]{2})\.(?P<month>[0-9]{2})\.(?P<year>[0-9]{4}) "
    r"[0-9]{2}:[0-9]{2}$",
    flags=re.ASCII,
)

SAFETY_KEYS = (
    "football_semantics_promoted",
    "request_date_reinterpreted_as_kickoff_date",
    "kickoff_rewritten",
    "spillover_promoted_to_fresh_candidate",
    "source_capability_changed",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutRequestDateSpilloverAdapterError(RuntimeError):
    """Raised when request-bucket spillover cannot be proven structurally."""


def _error(message: str) -> FreshHoldoutRequestDateSpilloverAdapterError:
    return FreshHoldoutRequestDateSpilloverAdapterError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    pins = (
        (Path(pr208_adapter.__file__), PR208_ADAPTER_BLOB_SHA, "PR208 adapter"),
        (Path(fresh.__file__), FRESH_HOLDOUT_CORE_BLOB_SHA, "fresh-holdout core"),
        (Path(pr39_schema.__file__), PR39_SCHEMA_BLOB_SHA, "PR39 schema"),
        (Path(pr89.__file__), PR89_IMPLEMENTATION_BLOB_SHA, "PR89 implementation"),
        (Path(fixture_candidates.__file__), FIXTURE_CANDIDATE_BLOB_SHA, "fixture candidate builder"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "capture contract"),
    )
    try:
        for path, expected, label in pins:
            if _git_blob_sha(path) != expected:
                raise _error(f"{label} implementation blob changed")
    except OSError as exc:
        raise _error("could not verify request-date spillover dependencies") from exc
    pr208_adapter.verify_reviewed_dependencies()


def _request_date(value: Any) -> dt.date:
    if type(value) is not str or not re.fullmatch(r"[0-9]{8}", value):
        raise _error("request_date must be exact YYYYMMDD text")
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise _error("request_date is not a valid calendar date") from exc


def _kickoff(value: Any) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error("status.utcTime must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error("status.utcTime is malformed") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise _error("status.utcTime must be explicit UTC")
    if parsed.microsecond % 1000:
        raise _error("status.utcTime must be compatible with epoch milliseconds")
    return parsed.astimezone(dt.timezone.utc)


def _display_date(value: Any) -> dt.date:
    if type(value) is not str:
        raise _error("spillover match.time must be an exact string")
    match = _DISPLAY_TIME_RE.fullmatch(value)
    if match is None:
        raise _error("spillover match.time escaped reviewed DD.MM.YYYY HH:MM shape")
    try:
        return dt.date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as exc:
        raise _error("spillover match.time contains an invalid calendar date") from exc


def _projection_manifest(
    source: capture_contract.FotMobDataMatchesCaptureManifest,
    raw: bytes,
    *,
    request_date: str,
) -> capture_contract.FotMobDataMatchesCaptureManifest:
    request_target = (
        f"/api/data/matches?date={request_date}"
        f"&timezone={source.timezone}&ccode3={source.ccode3}"
    )
    content_length = None if source.content_length is None else len(raw)
    try:
        return dataclasses.replace(
            source,
            request_date=request_date,
            request_target=request_target,
            content_length=content_length,
            network_acquisition_performed=False,
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            raw_size=len(raw),
        )
    except Exception as exc:
        raise _error("request-date validation projection manifest failed") from exc


def _partition_payload(
    payload: dict[str, Any],
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[dict[str, dict[str, Any]], tuple[int, ...]]:
    if set(payload) != pr39_schema.TOP_LEVEL_KEYS:
        raise _error("source top-level keys escaped frozen PR39 contract")
    if payload.get("date") != manifest.request_date:
        raise _error("source payload date does not equal exact request date")
    leagues = payload.get("leagues")
    if type(leagues) is not list:
        raise _error("source payload leagues must be a list")

    request_day = _request_date(manifest.request_date)
    previous_day = request_day - dt.timedelta(days=1)
    request_text = request_day.strftime("%Y%m%d")
    previous_text = previous_day.strftime("%Y%m%d")
    groups: dict[str, dict[str, Any]] = {
        request_text: {"date": request_text, "leagues": []},
    }
    spillover_ids: list[int] = []
    seen_fixture_ids: set[int] = set()

    for league_index, league in enumerate(leagues):
        if type(league) is not dict:
            raise _error(f"leagues[{league_index}] must be an object")
        matches = league.get("matches")
        if type(matches) is not list:
            raise _error(f"leagues[{league_index}].matches must be a list")
        by_date: dict[str, list[dict[str, Any]]] = {}
        for match_index, match in enumerate(matches):
            if type(match) is not dict:
                raise _error(
                    f"leagues[{league_index}].matches[{match_index}] must be an object"
                )
            fixture_id = match.get("id")
            if type(fixture_id) is not int or fixture_id < 1 or fixture_id in seen_fixture_ids:
                raise _error("source fixture id is invalid or duplicated")
            seen_fixture_ids.add(fixture_id)
            status = match.get("status")
            if type(status) is not dict:
                raise _error("source match status must be an object")
            kickoff_day = _kickoff(status.get("utcTime")).date()
            kickoff_text = kickoff_day.strftime("%Y%m%d")
            if kickoff_day == request_day:
                pass
            elif kickoff_day == previous_day:
                if _display_date(match.get("time")) != request_day:
                    raise _error(
                        "previous-UTC-date spillover requires provider display date equal request date"
                    )
                spillover_ids.append(fixture_id)
                groups.setdefault(
                    previous_text,
                    {"date": previous_text, "leagues": []},
                )
            else:
                raise _error(
                    "off-request-date fixture escaped reviewed immediately-previous-UTC-date spillover"
                )
            by_date.setdefault(kickoff_text, []).append(copy.deepcopy(match))

        for date_text, date_matches in sorted(by_date.items()):
            projected_league = copy.deepcopy(league)
            projected_league["matches"] = date_matches
            groups[date_text]["leagues"].append(projected_league)

    return groups, tuple(sorted(spillover_ids))


def _assess_partition(
    payload: dict[str, Any],
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[
    dict[str, Any],
    capture_contract.FotMobDataMatchesCaptureManifest,
    Any,
    tuple[int, ...],
]:
    groups, spillover_ids = _partition_payload(payload, manifest)
    request_assessment = None
    request_payload = None
    request_manifest = None

    for date_text, group in sorted(groups.items()):
        reviewed_payload = pr208_adapter._remove_reviewed_extra_halfs(group)
        reviewed_raw = pr208_adapter._canonical(reviewed_payload)
        projected_manifest = _projection_manifest(
            manifest,
            reviewed_raw,
            request_date=date_text,
        )
        try:
            assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
                reviewed_raw,
                projected_manifest,
            )
        except Exception as exc:
            raise _error(
                f"reviewed PR89->PR87->PR39 structural partition failed for {date_text}"
            ) from exc
        if (
            assessment.status
            is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
        ):
            raise _error("reviewed structural partition did not return exact qualified status")
        if assessment.status_reason_semantics_qualified or assessment.final_result_semantics_qualified:
            raise _error("request-date partition unexpectedly promoted football semantics")
        if date_text == manifest.request_date:
            request_assessment = assessment
            request_payload = reviewed_payload
            request_manifest = projected_manifest

    if request_assessment is None or request_payload is None or request_manifest is None:
        raise _error("exact request-date structural partition was not validated")
    return request_payload, request_manifest, request_assessment, spillover_ids


def assess_pr89_request_date_partition(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
):
    """Validate every UTC-date group, returning only the request-date PR89 receipt."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("spillover compatibility requires an actual reviewed network capture")
    if type(raw_json) is not bytes or not raw_json:
        raise _error("raw capture must be non-empty exact bytes")
    if manifest.raw_size != len(raw_json):
        raise _error("raw capture size does not match original manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")
    payload = pr208_adapter._strict_json(raw_json)
    _request_payload, _request_manifest, assessment, _spillover_ids = _assess_partition(
        payload,
        manifest,
    )
    return assessment


def qualify_capture_fixtures(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Qualify exact request-date fixture identity while validating spillover separately."""
    verify_reviewed_dependencies()
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("spillover compatibility requires an actual reviewed network capture")
    if type(raw_json) is not bytes or not raw_json:
        raise _error("raw capture must be non-empty exact bytes")
    if manifest.raw_size != len(raw_json):
        raise _error("raw capture size does not match original manifest")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")

    payload = pr208_adapter._strict_json(raw_json)
    groups, spillover_ids = _partition_payload(payload, manifest)
    if not spillover_ids:
        return pr208_adapter.qualify_capture_fixtures(raw_json, manifest)

    request_payload, request_manifest, _assessment, validated_spillover_ids = (
        _assess_partition(payload, manifest)
    )
    if validated_spillover_ids != spillover_ids:
        raise _error("spillover fixture population changed during structural validation")

    candidate_payload = pr208_adapter._project_to_pr39(request_payload)
    candidate_raw = pr208_adapter._canonical(candidate_payload)
    candidate_manifest = _projection_manifest(
        manifest,
        candidate_raw,
        request_date=manifest.request_date,
    )
    try:
        bundle = fixture_candidates.build_fotmob_fixture_candidate_bundle(
            ((candidate_raw, candidate_manifest),)
        )
    except Exception as exc:
        raise _error("reviewed request-date PR39 fixture-candidate projection failed") from exc

    original_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(manifest)
    all_qualified = fresh._qualify_provider_identity_payload(
        raw_json,
        capture_observed_at=manifest.observed_at,
        capture_manifest_sha256=original_manifest_sha,
        capture_raw_sha256=manifest.raw_sha256,
    )
    request_qualified = tuple(
        item
        for item in all_qualified
        if item.kickoff_utc.strftime("%Y%m%d") == manifest.request_date
    )
    off_date_ids = tuple(
        sorted(
            item.fixture_id
            for item in all_qualified
            if item.kickoff_utc.strftime("%Y%m%d") != manifest.request_date
        )
    )
    if off_date_ids != spillover_ids:
        raise _error("provider-native off-date identity disagrees with reviewed spillover partition")

    candidates = {item.source_match_id: item for item in bundle.candidates}
    if len(candidates) != len(bundle.candidates) or len(request_qualified) != len(bundle.candidates):
        raise _error("request-date candidate and exact identity populations disagree")

    projected_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(
        candidate_manifest
    )
    for item in request_qualified:
        candidate = candidates.get(item.fixture_id)
        if candidate is None:
            raise _error("qualified request-date fixture absent from reviewed candidate population")
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
            raise _error("exact request-date provider identity disagrees with reviewed projection")
        if (
            candidate.source_request_date != manifest.request_date
            or candidate.source_raw_sha256 != candidate_manifest.raw_sha256
            or candidate.source_capture_manifest_sha256 != projected_manifest_sha
        ):
            raise _error("request-date candidate projection lineage is inconsistent")
        if (
            item.capture_raw_sha256 != manifest.raw_sha256
            or item.capture_manifest_sha256 != original_manifest_sha
        ):
            raise _error("returned request-date fixture escaped original network lineage")

    return request_qualified


def adapter_receipt() -> dict[str, Any]:
    verify_reviewed_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_state": ADAPTER_STATE,
        "source_workflow_run_id": SOURCE_WORKFLOW_RUN_ID,
        "source_actions_artifact_id": SOURCE_ACTIONS_ARTIFACT_ID,
        "source_actions_artifact_name": SOURCE_ACTIONS_ARTIFACT_NAME,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "source_request_date": SOURCE_REQUEST_DATE,
        "source_capture_observed_at": SOURCE_CAPTURE_OBSERVED_AT,
        "source_capture_raw_sha256": SOURCE_CAPTURE_RAW_SHA256,
        "source_capture_manifest_sha256": SOURCE_CAPTURE_MANIFEST_SHA256,
        "source_spillover_fixture_ids": list(SOURCE_SPILLOVER_FIXTURE_IDS),
        "source_spillover_kickoffs": list(SOURCE_SPILLOVER_KICKOFFS),
        "spillover_rule": (
            "ONLY_IMMEDIATELY_PREVIOUS_UTC_DATE_AND_PROVIDER_DISPLAY_DATE_EQUALS_REQUEST_DATE"
        ),
        "all_utc_date_partitions_revalidated_through_pr89_pr87_pr39": True,
        "spillover_excluded_from_fresh_candidate_population": True,
        "original_network_capture_lineage_preserved_in_returned_fixtures": True,
        "validation_projections_are_not_source_evidence": True,
        "network_acquisition_performed": False,
        "safety": {key: False for key in SAFETY_KEYS},
    }


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_STATE",
    "FreshHoldoutRequestDateSpilloverAdapterError",
    "adapter_receipt",
    "assess_pr89_request_date_partition",
    "qualify_capture_fixtures",
    "verify_reviewed_dependencies",
]
