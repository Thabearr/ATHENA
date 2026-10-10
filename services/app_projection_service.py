"""Fail-closed D5 boundary for authenticated, disposable decision projections.

The current RunReceipt selection mappings do not prove normalized fixture,
market, odds, confidence, Router or Portfolio fields. This service verifies
receipt lineage, then returns an explicit typed source-contract limitation; it
never writes projection rows or invokes decision code.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re

from database.app_migration_evidence import contained
from database.app_root_lock import app_root_lock
from database.app_storage_access import app_store_connection
from database.run_repository import DurableRunRepository
from domain.run_contracts import RunReceipt, canonical_json_bytes
from runtime.resources import ResourceResolver, WritableRoots


class ProjectionDisposition(StrEnum):
    SOURCE_CONTRACT_UNAVAILABLE = "SOURCE_CONTRACT_UNAVAILABLE"
    SOURCE_IDENTITY_UNAVAILABLE = "SOURCE_IDENTITY_UNAVAILABLE"
    SOURCE_RECEIPT_UNAVAILABLE = "SOURCE_RECEIPT_UNAVAILABLE"


class ProjectionSourceError(ValueError):
    """The caller's run/artifact identity does not authenticate to a D4 source."""


@dataclass(frozen=True)
class ProjectionSourceResolution:
    disposition: ProjectionDisposition
    run_id: str
    artifact_id: str
    artifact_sha256: str | None
    artifact_byte_count: int | None
    request_sha256: str | None
    envelope_sha256: str | None
    release_id: str | None
    selected_leg_count: int | None
    selected_leg_fields_typed: bool
    materialized_rows: int
    coverage_disposition: str = "COVERAGE_UNAVAILABLE"
    dependency: str = "E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT"


_SHA = re.compile(r"[0-9a-f]{64}\Z")


def resolve_projection_source(
    resources: ResourceResolver,
    roots: WritableRoots,
    *,
    run_id: str,
    artifact_id: str,
) -> ProjectionSourceResolution:
    """Authenticate a same-run D4 terminal receipt without fabricating rows."""
    if type(run_id) is not str or not run_id or type(artifact_id) is not str or not artifact_id:
        raise ProjectionSourceError("exact non-empty run and artifact identities are required")
    if resources is None or roots is None:
        raise ProjectionSourceError("verified resources and writable roots are required")
    with app_root_lock(roots.data_root):
        try:
            snapshot = DurableRunRepository(resources, roots).run_snapshot(run_id)
        except Exception as exc:
            # Preserve D4's typed provenance failure rather than claiming an
            # authenticated source when the historical producer cannot verify.
            from database.run_repository import TerminalEvidenceUnavailable

            if isinstance(exc, TerminalEvidenceUnavailable):
                raise ProjectionSourceError("terminal receipt lineage is unavailable") from exc
            raise
        if snapshot is None:
            return ProjectionSourceResolution(
                ProjectionDisposition.SOURCE_IDENTITY_UNAVAILABLE, run_id,
                artifact_id, None, None, None, None, None, None, False, 0,
            )
        if snapshot["state"] != "TERMINAL" or not snapshot.get("receipt_artifact_id"):
            return ProjectionSourceResolution(
                ProjectionDisposition.SOURCE_RECEIPT_UNAVAILABLE, run_id,
                artifact_id, None, None, snapshot["request_sha256"],
                snapshot["envelope_sha256"], snapshot["release_id"], None,
                False, 0,
            )
        if snapshot["receipt_artifact_id"] != artifact_id:
            raise ProjectionSourceError("artifact identity is not the run's terminal receipt")

        with app_store_connection(resources, roots) as conn:
            row = conn.execute(
                "SELECT a.byte_sha256,a.byte_count,a.artifact_kind,a.logical_path,"
                "r.role,r.retained_root "
                "FROM app_artifacts a JOIN app_run_artifacts r USING(artifact_id) "
                "WHERE a.artifact_id=? AND r.run_id=? ORDER BY r.role",
                (artifact_id, run_id),
            ).fetchall()
            if len(row) != 1 or row[0][4:] != ("RUN_RECEIPT", 1):
                raise ProjectionSourceError("receipt artifact lacks its exact authorized D4 role")
            byte_sha, byte_count, kind, locator, _role, _retained = row[0]
            if (kind != "RUN_RECEIPT" or type(byte_sha) is not str
                    or _SHA.fullmatch(byte_sha) is None or type(byte_count) is not int
                    or locator != "run-receipts/" + byte_sha + ".json"):
                raise ProjectionSourceError("receipt artifact metadata is outside the D4 locator contract")
            try:
                raw = contained(roots.data_root, locator).read_bytes()
            except (OSError, ValueError) as exc:
                raise ProjectionSourceError("receipt artifact bytes are missing or unsafe") from exc
            if len(raw) != byte_count or hashlib.sha256(raw).hexdigest() != byte_sha:
                raise ProjectionSourceError("receipt artifact byte identity mismatch")
            try:
                value = json.loads(raw)
                if (type(value) is not dict or canonical_json_bytes(value) != raw
                        or value.get("policy_id") != "ATHENA_D4_OFFLINE_TERMINAL_PROJECTION_V1"
                        or value.get("run_id") != run_id
                        or value.get("request_sha256") != snapshot["request_sha256"]
                        or value.get("envelope_sha256") != snapshot["envelope_sha256"]
                        or value.get("release_id") != snapshot["release_id"]):
                    raise ValueError("receipt framing or run binding mismatch")
                receipt = RunReceipt.from_dict(value["receipt"])
            except Exception as exc:
                raise ProjectionSourceError("receipt canonical framing or domain contract is invalid") from exc
            if receipt.request.canonical_sha256 != snapshot["request_sha256"]:
                raise ProjectionSourceError("receipt request identity differs from the verified run")
            return ProjectionSourceResolution(
                ProjectionDisposition.SOURCE_CONTRACT_UNAVAILABLE,
                run_id=run_id,
                artifact_id=artifact_id,
                artifact_sha256=byte_sha,
                artifact_byte_count=byte_count,
                request_sha256=snapshot["request_sha256"],
                envelope_sha256=snapshot["envelope_sha256"],
                release_id=snapshot["release_id"],
                selected_leg_count=len(receipt.selected_legs),
                selected_leg_fields_typed=False,
                materialized_rows=0,
            )


def verify_projection_tables_empty(resources: ResourceResolver, roots: WritableRoots) -> bool:
    """Return true only while all three decision read models remain empty."""
    with app_store_connection(resources, roots) as conn:
        return all(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is None
                   for table in ("app_fixture_projections", "app_opportunity_projections",
                                 "app_portfolio_members"))


__all__ = [
    "ProjectionDisposition", "ProjectionSourceError", "ProjectionSourceResolution",
    "resolve_projection_source", "verify_projection_tables_empty",
]
