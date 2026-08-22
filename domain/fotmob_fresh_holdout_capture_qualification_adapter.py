"""Reviewed live-capture adapter for the FotMob fresh-holdout runner.

The original PR149 fresh-holdout implementation intentionally remains frozen.
Live ``data/matches`` responses can contain later-reviewed terminal-state fields
and non-null ``eliminatedTeamId`` values, so this adapter first proves the exact
PR89 structural chain before reusing PR149's provider-native identity extractor.
No terminal-state field is interpreted as football meaning and no downstream
model, pricing, selection, or betting authority is added here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


ADAPTER_ID = "FOTMOB_FRESH_HOLDOUT_REVIEWED_SCHEMA_ADAPTER_V1"
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
PR149_FRESH_HOLDOUT_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"


class FreshHoldoutCaptureQualificationAdapterError(RuntimeError):
    """Raised when the reviewed structural bridge cannot fail closed."""


def _error(message: str) -> FreshHoldoutCaptureQualificationAdapterError:
    return FreshHoldoutCaptureQualificationAdapterError(message)


def _blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    """Pin the frozen PR89, PR149, and capture-contract implementations."""
    pins = (
        (Path(pr89.__file__), PR89_IMPLEMENTATION_BLOB_SHA, "PR89 value-domain implementation"),
        (Path(fresh.__file__), PR149_FRESH_HOLDOUT_BLOB_SHA, "PR149 fresh-holdout implementation"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "FotMob capture contract"),
    )
    for path, expected, label in pins:
        try:
            actual = _blob(path)
        except OSError as exc:
            raise _error(f"could not inspect {label}") from exc
        if actual != expected:
            raise _error(f"{label} blob changed")


def qualify_capture_fixtures(
    raw_json: bytes,
    manifest: capture_contract.FotMobDataMatchesCaptureManifest,
) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    """Qualify one live capture through PR89, preserving original evidence lineage.

    PR89 re-runs the reviewed PR87 terminal-state extension and the frozen PR39
    base projection. Only after that chain succeeds do we reuse PR149's pinned
    provider-native identity extractor on the original bytes. The returned
    fixtures remain bound to the original network capture manifest/raw hashes,
    never to an internal compatibility projection.
    """
    verify_reviewed_dependencies()
    if type(raw_json) is not bytes or not raw_json:
        raise _error("raw capture must be non-empty exact bytes")
    if not isinstance(manifest, capture_contract.FotMobDataMatchesCaptureManifest):
        raise _error("manifest must be the reviewed FotMob capture manifest type")
    if manifest.network_acquisition_performed is not True:
        raise _error("fresh-holdout adapter requires proven live network acquisition")
    if hashlib.sha256(raw_json).hexdigest() != manifest.raw_sha256:
        raise _error("raw capture SHA-256 does not match original manifest")

    try:
        assessment = pr89.assess_fotmob_data_matches_eliminated_team_id_value_domain(
            raw_json,
            manifest,
        )
    except Exception as exc:
        raise _error("reviewed PR89 structural qualification failed") from exc

    if (
        assessment.status
        is not pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    ):
        raise _error("PR89 did not return its exact qualified structural status")
    if assessment.status_reason_semantics_qualified is not False:
        raise _error("PR89 unexpectedly qualified status.reason semantics")
    if assessment.final_result_semantics_qualified is not False:
        raise _error("PR89 unexpectedly qualified final-result semantics")

    original_manifest_sha = capture_contract.sha256_data_matches_capture_manifest(manifest)
    if assessment.source_capture_manifest_sha256 != original_manifest_sha:
        raise _error("PR89 assessment manifest lineage differs from original capture")
    if assessment.source_raw_sha256 != manifest.raw_sha256:
        raise _error("PR89 assessment raw lineage differs from original capture")
    if assessment.source_observed_at != manifest.observed_at:
        raise _error("PR89 assessment observation time differs from original capture")

    try:
        qualified = fresh._qualify_provider_identity_payload(
            raw_json,
            capture_observed_at=manifest.observed_at,
            capture_manifest_sha256=original_manifest_sha,
            capture_raw_sha256=manifest.raw_sha256,
        )
    except Exception as exc:
        raise _error("pinned PR149 provider-native identity extraction failed") from exc

    if len(qualified) != assessment.pr87_match_count:
        raise _error("PR149 identity population disagrees with reviewed PR89 match population")
    if any(
        item.capture_manifest_sha256 != original_manifest_sha
        or item.capture_raw_sha256 != manifest.raw_sha256
        or item.capture_observed_at != manifest.observed_at
        for item in qualified
    ):
        raise _error("qualified fixture escaped original live-capture lineage")
    return qualified


__all__ = [
    "ADAPTER_ID",
    "CAPTURE_CONTRACT_BLOB_SHA",
    "FreshHoldoutCaptureQualificationAdapterError",
    "PR149_FRESH_HOLDOUT_BLOB_SHA",
    "PR89_IMPLEMENTATION_BLOB_SHA",
    "qualify_capture_fixtures",
    "verify_reviewed_dependencies",
]
