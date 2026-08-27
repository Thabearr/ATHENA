"""Source-bound Fixture Intelligence issuance for legacy live FotMob responses.

This is deliberately a provenance boundary, not a source qualification or
model-feature boundary.  The legacy runtime's browser-compatible transport is
recorded honestly and every fact issued here remains ``UNVERIFIED``.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    FixtureIntelligenceSnapshot,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-live-fotmob-runtime-evidence-v1"
EVIDENCE_ROOT = Path(".cache/athena-runtime/fotmob-live-evidence")
RAW_FILENAME = "response.json"
MANIFEST_FILENAME = "manifest.json"
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_FIXTURE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", re.ASCII)


class LiveFotMobFixtureIntelligenceError(ValueError):
    pass


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiveFotMobFixtureIntelligenceError(f"{label} must be timezone-aware datetime")
    return value.astimezone(dt.timezone.utc)


def _fixture(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or (match := _FIXTURE.fullmatch(value)) is None:
        raise LiveFotMobFixtureIntelligenceError("fixture_identifier must be FOTMOB:<positive id>")
    return value, match.group(1)


def _json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise LiveFotMobFixtureIntelligenceError("manifest serialization failed") from exc


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveFotMobFixtureIntelligenceError("raw FotMob evidence is not UTF-8 JSON") from exc
    if type(value) is not dict:
        raise LiveFotMobFixtureIntelligenceError("raw FotMob evidence root must be an object")
    return value


@dataclasses.dataclass(frozen=True)
class LiveFotMobEvidenceReceipt:
    """A pointer to one immutable raw response captured by the runtime."""

    kind: str
    fixture_identifier: str
    source_reference: str
    observed_at: dt.datetime
    evidence_directory: Path
    evidence_file_path: str
    evidence_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        if self.kind not in {"FIXTURE_LIST", "MATCH_DETAILS"}:
            raise LiveFotMobFixtureIntelligenceError("unsupported live FotMob evidence kind")
        _fixture(self.fixture_identifier)
        if not isinstance(self.source_reference, str) or not self.source_reference.startswith("https://www.fotmob.com/api/data/"):
            raise LiveFotMobFixtureIntelligenceError("source_reference must be exact FotMob data endpoint")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if not isinstance(self.evidence_directory, Path) or self.evidence_directory.is_absolute():
            raise LiveFotMobFixtureIntelligenceError("evidence_directory must be relative")
        if self.evidence_file_path != RAW_FILENAME:
            raise LiveFotMobFixtureIntelligenceError("evidence_file_path must be response.json")
        for value in (self.evidence_sha256, self.manifest_sha256):
            if not isinstance(value, str) or _SHA.fullmatch(value) is None:
                raise LiveFotMobFixtureIntelligenceError("evidence identities must be SHA-256")


def persist_live_fotmob_evidence(
    *, kind: str, fixture_identifier: str, source_reference: str, observed_at: dt.datetime,
    raw_bytes: bytes, repository_root: Path, output_root: Path = EVIDENCE_ROOT,
) -> LiveFotMobEvidenceReceipt:
    """Durably preserve exact source bytes before normalizing any runtime value."""
    fixture_id, source_id = _fixture(fixture_identifier)
    observed = _utc(observed_at, "observed_at")
    if kind not in {"FIXTURE_LIST", "MATCH_DETAILS"} or type(raw_bytes) is not bytes or not raw_bytes:
        raise LiveFotMobFixtureIntelligenceError("invalid live FotMob evidence capture")
    if not isinstance(source_reference, str) or not source_reference.startswith(
        "https://www.fotmob.com/api/data/"
    ):
        raise LiveFotMobFixtureIntelligenceError("source_reference must be exact FotMob data endpoint")
    _strict_json(raw_bytes)
    root = (repository_root / output_root).resolve()
    if root != (repository_root / EVIDENCE_ROOT).resolve():
        raise LiveFotMobFixtureIntelligenceError("live evidence root must be repository-local fixed root")
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    observed_text = observed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    capture_name = f"{source_id}--{kind.lower()}--{observed.strftime('%Y%m%dT%H%M%S%fZ')}--{raw_sha}"
    relative = output_root / capture_name
    directory = repository_root / relative
    if directory.exists() or directory.is_symlink():
        raise LiveFotMobFixtureIntelligenceError("live evidence capture already exists")
    manifest = {
        "schema_version": SCHEMA_VERSION, "dataset_name": DATASET_NAME, "kind": kind,
        "fixture_identifier": fixture_id, "source_reference": source_reference,
        "observed_at": observed_text, "raw_file_name": RAW_FILENAME,
        "raw_sha256": raw_sha, "raw_size": len(raw_bytes),
        "network_acquisition_performed": True, "browser_impersonation_performed": True,
        "intelligence_fact_authorized": False, "model_feature_authorized": False,
        "probability_authorized": False, "pricing_authorized": False,
        "selection_authorized": False, "bet_authorized": False,
    }
    manifest_bytes = _json_bytes(manifest)
    try:
        directory.mkdir(parents=True, exist_ok=False)
        for name, content in ((RAW_FILENAME, raw_bytes), (MANIFEST_FILENAME, manifest_bytes)):
            descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError("live evidence publication failed") from exc
    return LiveFotMobEvidenceReceipt(
        kind=kind, fixture_identifier=fixture_id, source_reference=source_reference,
        observed_at=observed, evidence_directory=relative,
        evidence_file_path=RAW_FILENAME, evidence_sha256=raw_sha,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def _replay(receipt: LiveFotMobEvidenceReceipt, *, repository_root: Path) -> dict[str, Any]:
    if type(receipt) is not LiveFotMobEvidenceReceipt:
        raise LiveFotMobFixtureIntelligenceError("receipt must be exact live FotMob evidence receipt")
    directory = repository_root / receipt.evidence_directory
    if directory.is_symlink() or not directory.is_dir():
        raise LiveFotMobFixtureIntelligenceError("live evidence directory is unavailable")
    try:
        raw = (directory / RAW_FILENAME).read_bytes()
        manifest_bytes = (directory / MANIFEST_FILENAME).read_bytes()
    except OSError as exc:
        raise LiveFotMobFixtureIntelligenceError("live evidence bytes unavailable") from exc
    if hashlib.sha256(raw).hexdigest() != receipt.evidence_sha256:
        raise LiveFotMobFixtureIntelligenceError("live evidence raw SHA-256 mismatch")
    if hashlib.sha256(manifest_bytes).hexdigest() != receipt.manifest_sha256:
        raise LiveFotMobFixtureIntelligenceError("live evidence manifest SHA-256 mismatch")
    manifest = _strict_json(manifest_bytes)
    if _json_bytes(manifest) != manifest_bytes:
        raise LiveFotMobFixtureIntelligenceError("live evidence manifest is not canonical")
    required = {"schema_version", "dataset_name", "kind", "fixture_identifier", "source_reference", "observed_at", "raw_file_name", "raw_sha256", "raw_size", "network_acquisition_performed", "browser_impersonation_performed", "intelligence_fact_authorized", "model_feature_authorized", "probability_authorized", "pricing_authorized", "selection_authorized", "bet_authorized"}
    if set(manifest) != required or manifest["schema_version"] != SCHEMA_VERSION or manifest["dataset_name"] != DATASET_NAME:
        raise LiveFotMobFixtureIntelligenceError("live evidence manifest contract mismatch")
    if any(manifest[key] is not False for key in ("intelligence_fact_authorized", "model_feature_authorized", "probability_authorized", "pricing_authorized", "selection_authorized", "bet_authorized")):
        raise LiveFotMobFixtureIntelligenceError("live evidence attempted authority upgrade")
    if (manifest["kind"], manifest["fixture_identifier"], manifest["source_reference"], manifest["raw_file_name"], manifest["raw_sha256"], manifest["raw_size"]) != (receipt.kind, receipt.fixture_identifier, receipt.source_reference, RAW_FILENAME, receipt.evidence_sha256, len(raw)):
        raise LiveFotMobFixtureIntelligenceError("live evidence receipt/manifest identity mismatch")
    observed = _utc(dt.datetime.fromisoformat(manifest["observed_at"].replace("Z", "+00:00")), "manifest observed_at")
    if observed != receipt.observed_at:
        raise LiveFotMobFixtureIntelligenceError("live evidence observation time mismatch")
    return _strict_json(raw)


def _form(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    entries = value.get("recentResults", value.get("form", []))
    if not isinstance(entries, list):
        return {"matches": [], "summary": ""}
    matches = []
    for item in entries[:5]:
        if isinstance(item, dict):
            matches.append({"result": item.get("resultString", item.get("result", "")), "opponent": item.get("against", item.get("opponent", ""))})
    return {"matches": matches, "summary": "".join(str(item["result"])[:1].upper() for item in matches)}


def issue_live_fotmob_fixture_intelligence(
    *, fixture_evidence: LiveFotMobEvidenceReceipt, match_details_evidence: LiveFotMobEvidenceReceipt,
    repository_root: Path,
) -> FixtureIntelligenceSnapshot:
    """Replay evidence bytes and issue only exact, unverified source facts."""
    fixture_payload = _replay(fixture_evidence, repository_root=repository_root)
    details_payload = _replay(match_details_evidence, repository_root=repository_root)
    if fixture_evidence.kind != "FIXTURE_LIST" or match_details_evidence.kind != "MATCH_DETAILS" or fixture_evidence.fixture_identifier != match_details_evidence.fixture_identifier:
        raise LiveFotMobFixtureIntelligenceError("fixture/details evidence identity mismatch")
    fixture_id, source_id = _fixture(fixture_evidence.fixture_identifier)
    candidates = []
    for league in fixture_payload.get("leagues", []):
        if not isinstance(league, dict):
            continue
        for match in league.get("matches", []):
            if isinstance(match, dict) and str(match.get("id")) == source_id:
                candidates.append(match)
    if len(candidates) != 1:
        raise LiveFotMobFixtureIntelligenceError("fixture raw evidence does not resolve exact unique fixture")
    match = candidates[0]
    try:
        kickoff = _utc(dt.datetime.fromisoformat(str(match["status"]["utcTime"]).replace("Z", "+00:00")), "kickoff")
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveFotMobFixtureIntelligenceError("fixture evidence has no exact kickoff") from exc
    if match_details_evidence.observed_at >= kickoff or fixture_evidence.observed_at >= kickoff:
        raise LiveFotMobFixtureIntelligenceError("live evidence is not pre-match")
    details_id = details_payload.get("general", {}).get("matchId", details_payload.get("header", {}).get("matchId"))
    if details_id is not None and str(details_id) != source_id:
        raise LiveFotMobFixtureIntelligenceError("match-details evidence fixture identity mismatch")
    team_form = details_payload.get("content", {}).get("matchFacts", {}).get("teamForm", [])
    values = (("home_form", _form(team_form[0]) if isinstance(team_form, list) and len(team_form) > 0 else None), ("away_form", _form(team_form[1]) if isinstance(team_form, list) and len(team_form) > 1 else None))
    facts = []
    for field, value in values:
        if value is not None:
            facts.append(FixtureIntelligenceFact(
                category=IntelligenceCategory.FORM, field=field, status=IntelligenceFactStatus.UNVERIFIED,
                value=value, source_provider="FotMob", source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
                source_reference=match_details_evidence.source_reference, observed_at=match_details_evidence.observed_at,
                evidence_file_path=(match_details_evidence.evidence_directory / RAW_FILENAME).as_posix(),
                evidence_sha256=match_details_evidence.evidence_sha256,
            ))
    facts.append(FixtureIntelligenceFact(
        category=IntelligenceCategory.FIXTURE_CONTEXT, field="live_fixture_context", status=IntelligenceFactStatus.UNVERIFIED,
        value={"home_team": match.get("home", {}).get("name"), "away_team": match.get("away", {}).get("name")},
        source_provider="FotMob", source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
        source_reference=fixture_evidence.source_reference, observed_at=fixture_evidence.observed_at,
        evidence_file_path=(fixture_evidence.evidence_directory / RAW_FILENAME).as_posix(), evidence_sha256=fixture_evidence.evidence_sha256,
    ))
    return build_snapshot(fixture_id, kickoff, max(fixture_evidence.observed_at, match_details_evidence.observed_at), facts)


__all__ = ["EVIDENCE_ROOT", "LiveFotMobEvidenceReceipt", "LiveFotMobFixtureIntelligenceError", "issue_live_fotmob_fixture_intelligence", "persist_live_fotmob_evidence"]
