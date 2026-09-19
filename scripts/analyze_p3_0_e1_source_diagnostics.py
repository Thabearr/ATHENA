"""Offline-only audit of a retained P3.0-E1 source-diagnostics artifact.

This tool describes captured identity evidence; it never grants reconciliation
authority, writes identity state, or contacts a provider.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable, Mapping
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.competition_review_priority import (
    resolve_source_competition_review_priority,
)
from domain import current_shadow_fixture_identity_aliases as aliases


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P3_0_E1_RETAINED_SOURCE_DIAGNOSTICS_AUDIT_V1"
FAILURE_RECEIPT = "artifacts/p3-0-comparison-evidence/p3-0-capture-failure.json"


class SourceDiagnosticsAuditError(RuntimeError):
    """The retained artifact is malformed or does not meet the audit contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _zip_entries(path: Path) -> Mapping[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            entries: dict[str, bytes] = {}
            for info in archive.infolist():
                name = info.filename
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or name in entries:
                    raise SourceDiagnosticsAuditError("unsafe or duplicate ZIP entry")
                if info.is_dir():
                    continue
                entries[name] = archive.read(info)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SourceDiagnosticsAuditError("malformed source-diagnostics ZIP") from exc
    return entries


def _directory_entries(path: Path) -> Mapping[str, bytes]:
    if not path.is_dir():
        raise SourceDiagnosticsAuditError("artifact path must be a ZIP or directory")
    entries: dict[str, bytes] = {}
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(path).as_posix()
        if ".." in PurePosixPath(relative).parts:
            raise SourceDiagnosticsAuditError("unsafe artifact directory entry")
        entries[relative] = file_path.read_bytes()
    return entries


def _json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceDiagnosticsAuditError(f"malformed JSON: {label}") from exc


def _utc_text(value: Any) -> str | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_kickoff(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OSError, OverflowError):
        return None


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            yield current
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)


def _provider_events(entries: Mapping[str, bytes]) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    paths = sorted(path for path in entries if "/tournaments/" in path and path.endswith(".json"))
    paginated_paths = sorted(
        path for path in entries
        if "/sportybet-current-event-discovery/" in path
        and path.endswith(".json")
        and not path.endswith("manifest.json")
    )
    upcoming_paths = sorted(
        path
        for path in entries
        if "/current-shadow-sportybet-upcoming-discovery/" in path
        and path.endswith("/upcoming.raw.json")
    )
    if not paths and not paginated_paths and not upcoming_paths:
        raise SourceDiagnosticsAuditError("retained SportyBet discovery/tournament evidence missing")
    for path in paths:
        raw = entries[path]
        for value in _walk(_json(raw, path)):
            event_id = value.get("eventId")
            sport = value.get("sport")
            if type(event_id) is not str or type(sport) is not dict:
                continue
            category = sport.get("category")
            tournament = category.get("tournament") if type(category) is dict else None
            kickoff = _provider_kickoff(value.get("estimateStartTime"))
            fields = (value.get("homeTeamId"), value.get("homeTeamName"), value.get("awayTeamId"), value.get("awayTeamName"), category.get("id") if type(category) is dict else None, tournament.get("id") if type(tournament) is dict else None, tournament.get("name") if type(tournament) is dict else None)
            if kickoff is None or not all(type(item) is str for item in fields):
                continue
            row = {"provider_event_id": event_id, "provider_category_id": fields[4], "provider_tournament_id": fields[5], "provider_competition": fields[6], "provider_home_competitor_id": fields[0], "provider_home": fields[1], "provider_away_competitor_id": fields[2], "provider_away": fields[3], "kickoff_utc": kickoff, "provider_raw_sha256": [hashlib.sha256(raw).hexdigest()]}
            prior = events.get(event_id)
            if prior is not None and {key: value for key, value in prior.items() if key != "provider_raw_sha256"} != {key: value for key, value in row.items() if key != "provider_raw_sha256"}:
                raise SourceDiagnosticsAuditError("conflicting retained provider event")
            if prior is None:
                events[event_id] = row
            elif row["provider_raw_sha256"][0] not in prior["provider_raw_sha256"]:
                prior["provider_raw_sha256"].append(row["provider_raw_sha256"][0])
    for path in paginated_paths:
        raw = entries[path]
        for value in _walk(_json(raw, path)):
            event_id = value.get("eventId")
            if type(event_id) is not str:
                continue
            kickoff = _provider_kickoff(value.get("estimateStartTime"))
            fields = (
                value.get("homeTeamId") or value.get("homeTeamName"),
                value.get("homeTeamName"),
                value.get("awayTeamId") or value.get("awayTeamName"),
                value.get("awayTeamName"),
                value.get("categoryId") or "discovery_category",
                value.get("tournamentId") or "discovery_tournament",
                value.get("tournamentName") or value.get("leagueName") or "discovery_competition",
            )
            if kickoff is None or not all(type(item) is str for item in fields):
                continue
            row = {
                "provider_event_id": event_id,
                "provider_category_id": fields[4],
                "provider_tournament_id": fields[5],
                "provider_competition": fields[6],
                "provider_home_competitor_id": fields[0],
                "provider_home": fields[1],
                "provider_away_competitor_id": fields[2],
                "provider_away": fields[3],
                "kickoff_utc": kickoff,
                "provider_raw_sha256": [hashlib.sha256(raw).hexdigest()],
            }
            prior = events.get(event_id)
            if prior is not None and {key: value for key, value in prior.items() if key != "provider_raw_sha256"} != {key: value for key, value in row.items() if key != "provider_raw_sha256"}:
                raise SourceDiagnosticsAuditError("conflicting retained provider event")
            if prior is None:
                events[event_id] = row
            elif row["provider_raw_sha256"][0] not in prior["provider_raw_sha256"]:
                prior["provider_raw_sha256"].append(row["provider_raw_sha256"][0])
    for path in upcoming_paths:
        raw = entries[path]
        payload = _json(raw, path)
        data = payload.get("data") if type(payload) is dict else None
        if type(data) is not list:
            raise SourceDiagnosticsAuditError("upcoming raw discovery data is missing")
        for value in data:
            if type(value) is not dict:
                continue
            event_id = value.get("eventId")
            sport = value.get("sport")
            category = sport.get("category") if type(sport) is dict else None
            tournament = category.get("tournament") if type(category) is dict else None
            kickoff = _provider_kickoff(value.get("estimateStartTime"))
            fields = (
                value.get("homeTeamId"),
                value.get("homeTeamName"),
                value.get("awayTeamId"),
                value.get("awayTeamName"),
                category.get("id") if type(category) is dict else None,
                tournament.get("id") if type(tournament) is dict else None,
                tournament.get("name") if type(tournament) is dict else None,
            )
            if (
                type(event_id) is not str
                or kickoff is None
                or not all(type(item) is str for item in fields)
            ):
                continue
            row = {
                "provider_event_id": event_id,
                "provider_category_id": fields[4],
                "provider_tournament_id": fields[5],
                "provider_competition": fields[6],
                "provider_home_competitor_id": fields[0],
                "provider_home": fields[1],
                "provider_away_competitor_id": fields[2],
                "provider_away": fields[3],
                "kickoff_utc": kickoff,
                "provider_raw_sha256": [hashlib.sha256(raw).hexdigest()],
                "provider_source": "CURRENT_SHADOW_UPCOMING_DISCOVERY",
                "event_status": value.get("status"),
                "booking_status": value.get("bookingStatus"),
                "match_status": value.get("matchStatus"),
                "prematch_bookable_observed": (
                    str(value.get("bookingStatus") or "").strip().casefold() != "unavailable"
                    and value.get("status") in (None, 0, "0")
                    and value.get("setScore") in (None, "")
                    and value.get("playedSeconds") in (None, "")
                    and (
                        not str(value.get("matchStatus") or "").strip()
                        or "not start" in str(value.get("matchStatus") or "").strip().casefold()
                        or str(value.get("matchStatus") or "").strip().casefold() == "ns"
                    )
                ),
            }
            prior = events.get(event_id)
            core_keys = {
                "provider_event_id",
                "provider_category_id",
                "provider_tournament_id",
                "provider_competition",
                "provider_home_competitor_id",
                "provider_home",
                "provider_away_competitor_id",
                "provider_away",
                "kickoff_utc",
            }
            if prior is not None and {
                key: prior.get(key) for key in core_keys
            } != {key: row.get(key) for key in core_keys}:
                raise SourceDiagnosticsAuditError("conflicting retained provider event")
            if prior is None:
                events[event_id] = row
            else:
                prior.update({
                    key: value for key, value in row.items()
                    if key not in {"provider_raw_sha256"}
                })
                if row["provider_raw_sha256"][0] not in prior["provider_raw_sha256"]:
                    prior["provider_raw_sha256"].append(row["provider_raw_sha256"][0])
    for row in events.values():
        row["provider_raw_sha256"].sort()
    return [events[key] for key in sorted(events)]


def _fotmob_fixtures(entries: Mapping[str, bytes]) -> list[dict[str, Any]]:
    fixtures: dict[int, dict[str, Any]] = {}
    paths = sorted(path for path in entries if "/fotmob-data-matches-captures/" in path and path.endswith("/response.json"))
    if not paths:
        raise SourceDiagnosticsAuditError("retained FotMob captures missing")
    for path in paths:
        raw = entries[path]
        payload = _json(raw, path)
        leagues = payload.get("leagues") if type(payload) is dict else None
        if type(leagues) is not list:
            raise SourceDiagnosticsAuditError("retained FotMob capture has no leagues")
        for league in leagues:
            matches = league.get("matches") if type(league) is dict else None
            if type(matches) is not list:
                continue
            for match in matches:
                home = match.get("home") if type(match) is dict else None
                away = match.get("away") if type(match) is dict else None
                status = match.get("status") if type(match) is dict else None
                if not all(type(item) is dict for item in (home, away, status)):
                    continue
                kickoff = _utc_text(status.get("utcTime"))
                fixture_id = match.get("id")
                values = (league.get("ccode"), league.get("primaryId"), league.get("name"), home.get("id"), home.get("name"), home.get("longName"), away.get("id"), away.get("name"), away.get("longName"))
                if (
                    type(fixture_id) is not int
                    or kickoff is None
                    or type(values[0]) is not str
                    or type(values[1]) is not int
                    or type(values[2]) is not str
                    or type(values[3]) is not int
                    or type(values[4]) is not str
                    or type(values[5]) is not str
                    or type(values[6]) is not int
                    or type(values[7]) is not str
                    or type(values[8]) is not str
                ):
                    continue
                row = {"fotmob_fixture_id": fixture_id, "ccode": values[0], "primary_competition_id": values[1], "competition": values[2], "home_team_id": values[3], "home": values[4], "home_long_name": values[5], "away_team_id": values[6], "away": values[7], "away_long_name": values[8], "kickoff_utc": kickoff, "fotmob_raw_sha256": hashlib.sha256(raw).hexdigest()}
                prior = fixtures.get(fixture_id)
                if prior is not None and prior != row:
                    raise SourceDiagnosticsAuditError("conflicting retained FotMob fixture")
                fixtures[fixture_id] = row
    return [fixtures[key] for key in sorted(fixtures)]


def _candidate_kind(event: Mapping[str, Any], fixture: Mapping[str, Any]) -> str | None:
    priority = resolve_source_competition_review_priority(
        fixture.get("ccode", ""), fixture.get("competition", "")
    )
    if priority is None:
        return None
    home = aliases.team_identity_matches(competition=fixture["competition"], fotmob_name=fixture["home"], sportybet_name=event["provider_home"])
    away = aliases.team_identity_matches(competition=fixture["competition"], fotmob_name=fixture["away"], sportybet_name=event["provider_away"])
    if not (home and away):
        return None
    if fixture["home"] == event["provider_home"] and fixture["away"] == event["provider_away"]:
        return "EXACT_LITERAL"
    return "EXPLICIT_ALIAS_COMPATIBLE"


def analyze(path: str | Path, *, expected_zip_sha256: str | None = None) -> dict[str, Any]:
    artifact = Path(path)
    artifact_sha256 = None
    if artifact.is_file():
        artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if expected_zip_sha256 is not None and artifact_sha256 != expected_zip_sha256.lower():
            raise SourceDiagnosticsAuditError("source-diagnostics ZIP SHA-256 mismatch")
        entries = _zip_entries(artifact)
    else:
        if expected_zip_sha256 is not None:
            raise SourceDiagnosticsAuditError("expected ZIP SHA-256 requires a ZIP input")
        entries = _directory_entries(artifact)
    receipt_raw = entries.get(FAILURE_RECEIPT)
    if receipt_raw is None:
        raise SourceDiagnosticsAuditError("P3.0 failure receipt missing")
    receipt = _json(receipt_raw, FAILURE_RECEIPT)
    if type(receipt) is not dict or type(receipt.get("exact_commit_sha")) is not str:
        raise SourceDiagnosticsAuditError("P3.0 failure receipt malformed")
    fixtures = _fotmob_fixtures(entries)
    events = _provider_events(entries)
    upcoming_events = [
        event for event in events
        if event.get("provider_source") == "CURRENT_SHADOW_UPCOMING_DISCOVERY"
    ]
    upcoming_source_assessment: dict[str, Any] | None = None
    if upcoming_events:
        manifest_paths = sorted(
            path
            for path in entries
            if "/current-shadow-sportybet-upcoming-discovery/" in path
            and path.endswith("/manifest.json")
        )
        if not manifest_paths:
            raise SourceDiagnosticsAuditError(
                "active upcoming discovery manifest is missing"
            )
        manifests = [_json(entries[path], path) for path in manifest_paths]
        if len(manifests) != len(set(manifest.get("raw_sha256") for manifest in manifests)):
            raise SourceDiagnosticsAuditError("conflicting upcoming discovery manifests")
        first_manifest = manifests[0] if manifests else {}
        prematch_count = sum(
            event.get("prematch_bookable_observed") is True for event in upcoming_events
        )
        inplay_count = sum(event.get("event_status") in (1, "1") for event in upcoming_events)
        observed_at = first_manifest.get("observed_at")
        kickoff_evaluation = None
        if type(observed_at) is str:
            kickoff_evaluation = _utc_text(observed_at)
        future_lead_count = 0
        too_close_count = 0
        for event in upcoming_events:
            if kickoff_evaluation is None:
                continue
            kickoff = datetime.fromisoformat(event["kickoff_utc"].replace("Z", "+00:00"))
            observed = datetime.fromisoformat(kickoff_evaluation.replace("Z", "+00:00"))
            if (kickoff - observed).total_seconds() > 120 and event.get("prematch_bookable_observed") is True:
                future_lead_count += 1
            if (kickoff - observed).total_seconds() <= 120:
                too_close_count += 1
        source_method = first_manifest.get(
            "source_method",
            "PUBLIC_ANONYMOUS_FACTS_CENTER_WAP_CONFIGURABLE_UPCOMING_EVENTS_GET",
        )
        strategy_id = "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
        upcoming_source_assessment = {
            "provider_event_count": len(upcoming_events),
            "provider_prematch_bookable_count": prematch_count,
            "provider_inplay_count": inplay_count,
            "provider_future_lead_eligible_count": future_lead_count,
            "provider_too_close_count": too_close_count,
            "provider_discovery_source_method": source_method,
            "provider_discovery_strategy_id": strategy_id,
            "provider_discovery_observed_at": observed_at,
            "source_viability": (
                "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS"
                if prematch_count == 0
                else "PROSPECTIVE_DISCOVERY_ELIGIBLE"
                if future_lead_count > 0
                else "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS"
            ),
            "active_upcoming_manifest_count": len(manifests),
        }
    audited = []
    total_raw_counterparts = 0
    total_policy_approved_counterparts = 0
    total_reconciled_counterparts = 0
    unadmitted_competitions: set[str] = set()

    for event in events:
        same_kickoff = [fixture for fixture in fixtures if fixture["kickoff_utc"] == event["kickoff_utc"]]
        candidates = []
        compatible = []
        for fixture in same_kickoff:
            total_raw_counterparts += 1
            is_policy_approved = resolve_source_competition_review_priority(
                fixture.get("ccode", ""), fixture.get("competition", "")
            ) is not None
            if not is_policy_approved:
                kind = None
                identity_result = "POLICY_UNAPPROVED_COMPETITION"
                unadmitted_competitions.add(fixture["competition"])
            else:
                total_policy_approved_counterparts += 1
                kind = _candidate_kind(event, fixture)
                identity_result = kind or "UNSUPPORTED"
                if kind is not None:
                    compatible.append((fixture, kind))
                    total_reconciled_counterparts += 1
            candidates.append({
                **fixture,
                "policy_approved": is_policy_approved,
                "identity_result": identity_result,
            })
        if not candidates:
            classification = "NO_SAME_KICKOFF_CANDIDATE"
        elif len(compatible) == 1:
            classification = compatible[0][1]
        elif len(compatible) > 1:
            classification = "AMBIGUOUS"
        elif any(c.get("policy_approved") for c in candidates):
            classification = "SAME_KICKOFF_UNSUPPORTED"
        else:
            classification = "SAME_KICKOFF_POLICY_EXCLUDED"
        audited.append({**event, "same_kickoff_candidates": candidates, "classification": classification})

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "artifact_sha256": artifact_sha256,
        "failure_run_id": receipt.get("capture_id"),
        "executed_commit_sha": receipt["exact_commit_sha"],
        "provider_event_count": len(events),
        "active_upcoming_source_assessment": upcoming_source_assessment,
        "historical_paginated_source_present": any(
            "/sportybet-current-event-discovery/" in path for path in entries
        ),
        "fotmob_fixture_count": len(fixtures),
        "events": audited,
        "summary": {
            **{key: sum(row["classification"] == key for row in audited) for key in sorted({row["classification"] for row in audited})},
            "raw_counterparts_total": total_raw_counterparts,
            "policy_approved_counterparts_total": total_policy_approved_counterparts,
            "reconciliation_authorized_counterparts_total": total_reconciled_counterparts,
            "unadmitted_competitions_excluded": sorted(unadmitted_competitions),
        },
        "authority": {
            "audit_only": True,
            "fixture_reconciliation": False,
            "persistent_identity_mutation": False,
            "network": False,
            "provider_acquisition": False,
            "pricing": False,
            "selection": False,
            "wager": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact")
    parser.add_argument("--expected-zip-sha256")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.artifact, expected_zip_sha256=args.expected_zip_sha256)
    except SourceDiagnosticsAuditError as exc:
        parser.error(str(exc))
    sys.stdout.buffer.write(_canonical(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
