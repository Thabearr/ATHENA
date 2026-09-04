"""Focused proof tests for the one reviewed historical same-slot collision.

These tests use an in-memory, exact-shape durable archive.  The archive values
are synthetic, but the run/artifact identities and all receipt/state invariants
are the reviewed 2026-09-04 evidence-bound constants.  No provider or GitHub
network is contacted.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import tarfile
from typing import Any
import zipfile

import pytest

from domain import fotmob_fresh_holdout_continuity as continuity
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as activation
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


HEAD_SHA = "92da60c93e03c0c958a6d3143b43bb43fa8a2f42"
SLOT = "2026-09-04T00:07:00.000000Z"
SCHEDULED = "2026-09-04T00:07:00Z"
ROOT = ".cache/athena-research/fotmob-utc-native-xg-fresh-holdout/"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _watchdog() -> dict[str, Any]:
    return {
        "id": 33819767003,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "created_at": "2026-09-03T23:57:11Z",
        "status": "completed",
        "conclusion": "success",
    }


def _watchdog_jobs() -> dict[str, Any]:
    return {
        "jobs": [
            {
                "run_id": 33819767003,
                "workflow_name": continuity.WATCHDOG_WORKFLOW_NAME,
                "name": continuity.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": HEAD_SHA,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-09-03T23:57:12Z",
                "steps": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in continuity.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }


def _run(run_id: int, *, event: str, created_at: str, name: str) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": name,
        "display_title": name,
        "event": event,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "created_at": created_at,
        "status": "completed",
        "conclusion": "failure",
    }


def _capture_row(request_date: str, *, archive_name: str, suffix: str) -> dict[str, Any]:
    raw_sha = (suffix * 64)[:64]
    manifest_sha = ((suffix[::-1] or "a") * 64)[:64]
    return {
        "ccode3": "NGA",
        "durable_asset_name": archive_name,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W36",
        "manifest_sha256": manifest_sha,
        "network_acquisition_performed": True,
        "observed_at": f"2026-09-04T00:59:{request_date[-2:]}.000000Z",
        "preserved_from_uncommitted_tick": True,
        "raw_sha256": raw_sha,
        "raw_size": 100,
        "request_date": request_date,
        "schema_version": 1,
        "timezone": "UTC",
        "working_capture_relative": f"working-captures/{request_date}/capture-{suffix}",
    }


def _gap() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event": "SCHEDULER_GAP_RANGE",
        "detected_at_scheduled_for_utc": SLOT,
        "previous_committed_tick_utc": "2026-09-03T22:07:00.000000Z",
        "first_missing_tick_utc": "2026-09-03T22:37:00.000000Z",
        "last_missing_tick_utc": "2026-09-03T23:37:00.000000Z",
        "missing_tick_count": 3,
        "backfill_authorized": False,
    }


def _qualification(capture: dict[str, Any]) -> dict[str, Any]:
    return {
        "backfill_authorized": False,
        "capture_manifest_sha256": capture["manifest_sha256"],
        "capture_raw_sha256": capture["raw_sha256"],
        "detail": projection._HISTORICAL_DETAIL,
        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
        "observed_at": capture["observed_at"],
        "schema_version": 1,
        "tick_committed": False,
    }


def _state_bytes(
    *,
    natural: bool,
    mutate_prefix: bool = False,
    mutation: str | None = None,
) -> dict[str, bytes]:
    canonical_name = projection._HISTORICAL_CONTINUITY_ARTIFACT
    natural_name = projection._HISTORICAL_NATURAL_ARTIFACT
    canonical_captures = [
        {"request_date": f"base-{index:03d}", "durable_asset_name": "other.tar.gz"}
        for index in range(660)
    ] + [
        _capture_row(day, archive_name=canonical_name, suffix=letter)
        for day, letter in zip(("20260903", "20260904", "20260905"), "abc")
    ]
    natural_captures = list(canonical_captures) + [
        _capture_row(day, archive_name=natural_name, suffix=letter)
        for day, letter in zip(("20260903", "20260904", "20260905"), "def")
    ]
    if mutate_prefix or mutation == "capture_prefix":
        natural_captures[0] = {**natural_captures[0], "request_date": "mutated"}

    # The raw validator is exercised separately by the existing projection
    # suite; this synthetic journal is intentionally only the exact byte/prefix
    # shape needed by the complete preflight proof.
    base_control = [
        {
            "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
            "schema_version": 1,
            "tick_committed": False,
            "backfill_authorized": False,
        }
        for _ in range(715)
    ]
    canonical_control = base_control
    natural_control = list(canonical_control) + [_gap()]
    natural_control.extend(_qualification(capture) for capture in natural_captures[-3:])

    if natural and mutation == "capture_acquisition":
        natural_captures[-1] = {
            **natural_captures[-1],
            "network_acquisition_performed": False,
        }
        natural_control[-1] = _qualification(natural_captures[-1])
    elif natural and mutation == "control_prefix":
        natural_control[0] = {**natural_control[0], "tick_committed": True}
    elif natural and mutation == "control_gap":
        natural_control[-4] = {**natural_control[-4], "missing_tick_count": 2}
    elif natural and mutation == "control_extra":
        natural_control.append(_qualification(natural_captures[-1]))

    def ndjson(rows: list[dict[str, Any]]) -> bytes:
        return b"".join(_canonical(row) for row in rows)

    common = {
        "prediction": b"{}\n" * 3136,
        "identity": b"{}\n" * 6071,
        "settlement": b"{}\n" * 166,
        "checkpoint": _canonical({"schema_version": 1}),
    }
    if natural and mutation in {"prediction", "identity", "settlement"}:
        key = mutation
        common[key] = common[key].replace(b"{}\n", b'{"changed":true}\n', 1)
    if natural and mutation == "checkpoint":
        common["checkpoint"] = _canonical({"schema_version": 1, "changed": True})
    return {
        "capture": ndjson(natural_captures if natural else canonical_captures),
        "control": ndjson(natural_control if natural else canonical_control),
        **common,
    }


def _archive(state: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    members = {
        "capture": "capture-index.ndjson",
        "control": "control-journal.ndjson",
        "prediction": "prediction-journal.ndjson",
        "identity": "post-seal-identity-journal.ndjson",
        "settlement": "settlement-journal.ndjson",
        "checkpoint": "checkpoint.json",
    }
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            for key, name in members.items():
                member = tarfile.TarInfo(ROOT + name)
                member.mode = 0o600
                member.size = len(state[key])
                tar.addfile(member, io.BytesIO(state[key]))
    return out.getvalue()


def _bundle(
    run_id: int,
    *,
    natural: bool,
    mutate_prefix: bool = False,
    mutation: str | None = None,
) -> dict[str, Any]:
    name = (
        projection._HISTORICAL_NATURAL_ARTIFACT
        if natural
        else projection._HISTORICAL_CONTINUITY_ARTIFACT
    )
    archive = _archive(
        _state_bytes(
            natural=natural,
            mutate_prefix=mutate_prefix,
            mutation=mutation,
        )
    )
    receipt = {
        "backfill_or_retrofill_authorized": False,
        "disposition": projection._HISTORICAL_FAILURE_DISPOSITION,
        "durable_asset_name": name,
        "durable_asset_sha256": hashlib.sha256(archive).hexdigest(),
        "durable_asset_size_bytes": len(archive),
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W36",
        "failure_lineage_reconcile_outcome": "success",
        "network_replay_authorized": False,
        "nominal_scheduled_for_utc": SLOT,
        "runner_id": activation.RUNNER_ID,
        "safety": {key: False for key in activation.SAFETY_KEYS},
        "scheduled_for_utc": SCHEDULED,
        "schema_version": 1,
        "tick_committed": False,
        "tick_exit_code": 1,
        "workflow_event_schedule": "7 * * * *",
        "workflow_run_id": run_id,
    }
    receipt_raw = _canonical(receipt)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive_zip:
        for member_name, payload in ((name, archive), (mirror.RECEIPT_MEMBER, receipt_raw)):
            info = zipfile.ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive_zip.writestr(info, payload)
    zip_bytes = out.getvalue()
    return {
        "archive": archive,
        "receipt": receipt_raw,
        "zip": zip_bytes,
        "zip_digest": "sha256:" + hashlib.sha256(zip_bytes).hexdigest(),
    }


def _fixture(
    monkeypatch,
    *,
    natural_first: bool = False,
    mutate_prefix: bool = False,
    mutation: str | None = None,
):
    continuity_run = _run(
        projection._HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
        event="workflow_dispatch",
        created_at=projection._HISTORICAL_SAME_SLOT_CONTINUITY_CREATED_AT,
        name=projection._HISTORICAL_SAME_SLOT_CONTINUITY_NAME,
    )
    natural_run = _run(
        projection._HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
        event="schedule",
        created_at=projection._HISTORICAL_SAME_SLOT_NATURAL_CREATED_AT,
        name=projection._HISTORICAL_SAME_SLOT_NATURAL_NAME,
    )
    canonical_bundle = _bundle(continuity_run["id"], natural=False)
    natural_bundle = _bundle(
        natural_run["id"],
        natural=True,
        mutate_prefix=mutate_prefix,
        mutation=mutation,
    )
    monkeypatch.setattr(
        projection, "_HISTORICAL_CONTINUITY_ARCHIVE_SHA256", hashlib.sha256(canonical_bundle["archive"]).hexdigest()
    )
    monkeypatch.setattr(projection, "_HISTORICAL_CONTINUITY_ARCHIVE_SIZE", len(canonical_bundle["archive"]))
    monkeypatch.setattr(
        projection, "_HISTORICAL_NATURAL_ARCHIVE_SHA256", hashlib.sha256(natural_bundle["archive"]).hexdigest()
    )
    monkeypatch.setattr(projection, "_HISTORICAL_NATURAL_ARCHIVE_SIZE", len(natural_bundle["archive"]))
    monkeypatch.setattr(projection, "_HISTORICAL_CONTINUITY_ZIP_DIGEST", canonical_bundle["zip_digest"])
    monkeypatch.setattr(projection, "_HISTORICAL_NATURAL_ZIP_DIGEST", natural_bundle["zip_digest"])
    monkeypatch.setattr(projection, "_ORIGINAL_VALIDATE_CONTROL_LINEAGE", lambda _rows: (set(), set()))

    ordered = [natural_run, continuity_run] if natural_first else [continuity_run, natural_run]
    pages = [{"workflow_runs": ordered}]
    artifacts = {
        continuity_run["id"]: {
            "artifacts": [{
                "id": projection._HISTORICAL_CONTINUITY_ARTIFACT_ID,
                "name": projection._HISTORICAL_CONTINUITY_ARTIFACT,
                "expired": False,
                "digest": canonical_bundle["zip_digest"],
            }]
        },
        natural_run["id"]: {
            "artifacts": [{
                "id": projection._HISTORICAL_NATURAL_ARTIFACT_ID,
                "name": projection._HISTORICAL_NATURAL_ARTIFACT,
                "expired": False,
                "digest": natural_bundle["zip_digest"],
            }]
        },
    }
    zips = {
        projection._HISTORICAL_CONTINUITY_ARTIFACT_ID: canonical_bundle["zip"],
        projection._HISTORICAL_NATURAL_ARTIFACT_ID: natural_bundle["zip"],
    }
    by_id = {
        continuity_run["id"]: continuity_run,
        natural_run["id"]: natural_run,
        33819767003: _watchdog(),
    }
    readers = {
        "get_run_by_id": lambda run_id: by_id[run_id],
        "get_run_artifacts": lambda run_id: artifacts[run_id],
        "download_artifact_zip": lambda artifact_id: zips[artifact_id],
        "get_run_jobs": lambda run_id: _watchdog_jobs() if run_id == 33819767003 else {"jobs": []},
    }
    return continuity_run, natural_run, pages, readers, canonical_bundle, natural_bundle


def _proof(monkeypatch, *, natural_first: bool = False):
    continuity_run, natural_run, pages, readers, _canonical, _natural = _fixture(
        monkeypatch, natural_first=natural_first
    )
    universe = projection._prefetch_workflow_run_universe(
        lambda page, _per_page: pages[page - 1]
    )
    proof = projection._prove_exact_historical_same_slot_provider_duplicate(
        run_universe=universe,
        **readers,
    )
    return continuity_run, natural_run, universe, proof, readers


def test_historical_pair_proof_is_order_independent(monkeypatch):
    first = _proof(monkeypatch, natural_first=False)[3]
    second = _proof(monkeypatch, natural_first=True)[3]
    assert first == second
    assert first.canonical_run_id == 33820556400
    assert first.auxiliary_run_id == 33823663641
    assert first.provider_acquisition_count_canonical == 3
    assert first.provider_acquisition_count_auxiliary == 3


def test_historical_pair_split_across_prefetched_pages(monkeypatch):
    continuity_run, natural_run, pages, readers, *_ = _fixture(monkeypatch)
    filler = [
        {
            "id": 70000000000 + index,
            "name": "unrelated run",
            "event": "schedule",
            "created_at": "2026-09-04T01:00:00Z",
        }
        for index in range(100)
    ]
    pages = [{"workflow_runs": filler}, {"workflow_runs": [natural_run, continuity_run]}]
    universe = projection._prefetch_workflow_run_universe(
        lambda page, _per_page: pages[page - 1]
    )
    proof = projection._prove_exact_historical_same_slot_provider_duplicate(
        run_universe=universe,
        **readers,
    )
    assert proof is not None
    assert universe.reader(1, 100)["workflow_runs"] == filler
    assert universe.reader(2, 100)["workflow_runs"][0]["id"] == natural_run["id"]


def test_historical_pair_split_pages_is_order_independent(monkeypatch):
    continuity_run, natural_run, pages, readers, *_ = _fixture(monkeypatch)
    filler_a = [
        {
            "id": 71000000000 + index,
            "name": "newer unrelated run",
            "event": "schedule",
            "created_at": "2026-09-04T02:00:00Z",
        }
        for index in range(100)
    ]
    filler_b = [
        {
            "id": 72000000000 + index,
            "name": "older unrelated run",
            "event": "schedule",
            "created_at": "2026-09-04T01:00:00Z",
        }
        for index in range(99)
    ]
    outcomes = []
    for ordered_pages in (
        [
            {"workflow_runs": filler_a},
            {"workflow_runs": [natural_run, continuity_run] + filler_b[:98]},
            {"workflow_runs": []},
        ],
        [
            {"workflow_runs": [natural_run, continuity_run] + filler_b[:98]},
            {"workflow_runs": filler_a},
            {"workflow_runs": []},
        ],
    ):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page, values=ordered_pages: values[page - 1]
        )
        proof = projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )
        outcomes.append(proof.to_dict() if proof is not None else None)
    assert outcomes[0] == outcomes[1]
    assert outcomes[0]["canonical_run_id"] == continuity_run["id"]


def test_prefetched_reader_preserves_pages_and_projection_uses_proof(monkeypatch):
    continuity_run, natural_run, universe, proof, readers = _proof(
        monkeypatch, natural_first=True
    )
    assert universe.reader(1, 100)["workflow_runs"][0]["id"] == natural_run["id"]
    observed: dict[str, bool] = {}

    def fake_engine(**kwargs):
        observed["natural"] = audit._run_is_collection_candidate(natural_run)
        assert kwargs["get_runs_page"](1, 100)["workflow_runs"][0]["id"] == natural_run["id"]
        return {"runs": [], "audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)
    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="a" * 40,
        get_main_ref=lambda: {"sha": "a" * 40},
        get_runs_page=lambda page, per_page: universe.reader(page, per_page),
        **readers,
        get_release=lambda _tag: {},
        download_release_asset=lambda _asset_id: b"unused",
        verify_dependencies=False,
    )
    assert observed == {"natural": False}
    assert result["verified_same_slot_provider_duplicate_count"] == 1
    auxiliary = result["projected_same_slot_provider_duplicate_runs"][0]
    assert auxiliary["run_id"] == 33823663641
    assert auxiliary["canonical_run_id"] == 33820556400
    assert auxiliary["provider_acquisition_performed"] is True
    assert auxiliary["archive_sha256"] == proof.auxiliary_archive_sha256


@pytest.mark.parametrize(
    "mutation",
    [
        "capture_prefix",
        "capture_acquisition",
        "control_prefix",
        "control_gap",
        "control_extra",
        "prediction",
        "identity",
        "settlement",
        "checkpoint",
        "receipt",
        "archive_bytes",
    ],
)
def test_historical_pair_mutations_fail_closed(monkeypatch, mutation):
    continuity_run, natural_run, pages, readers, canonical_bundle, natural_bundle = _fixture(
        monkeypatch,
        mutate_prefix=mutation == "natural_prefix",
        mutation=mutation,
    )
    if mutation == "receipt":
        raw = json.loads(natural_bundle["receipt"])
        raw["network_replay_authorized"] = True
        receipt = _canonical(raw)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive_zip:
            archive_zip.writestr(projection._HISTORICAL_NATURAL_ARTIFACT, natural_bundle["archive"])
            archive_zip.writestr(mirror.RECEIPT_MEMBER, receipt)
        readers["download_artifact_zip"] = lambda artifact_id: (
            out.getvalue() if artifact_id == projection._HISTORICAL_NATURAL_ARTIFACT_ID else canonical_bundle["zip"]
        )
        readers["get_run_artifacts"] = lambda run_id: {
            "artifacts": [{
                "id": projection._HISTORICAL_NATURAL_ARTIFACT_ID,
                "name": projection._HISTORICAL_NATURAL_ARTIFACT,
                "expired": False,
                "digest": "sha256:" + hashlib.sha256(out.getvalue()).hexdigest(),
            }]
        } if run_id == natural_run["id"] else {
            "artifacts": [{
                "id": projection._HISTORICAL_CONTINUITY_ARTIFACT_ID,
                "name": projection._HISTORICAL_CONTINUITY_ARTIFACT,
                "expired": False,
                "digest": canonical_bundle["zip_digest"],
            }]
        }
    elif mutation == "archive_bytes":
        changed = natural_bundle["zip"][:-1] + bytes([natural_bundle["zip"][-1] ^ 1])
        readers["download_artifact_zip"] = lambda artifact_id: (
            changed if artifact_id == projection._HISTORICAL_NATURAL_ARTIFACT_ID else canonical_bundle["zip"]
        )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


@pytest.mark.parametrize(
    ("run_kind", "field", "value"),
    [
        ("continuity", "event", "schedule"),
        ("continuity", "head_sha", "a" * 40),
        ("continuity", "created_at", "2026-09-04T00:54:24Z"),
        ("continuity", "name", "changed"),
        ("natural", "event", "workflow_dispatch"),
        ("natural", "workflow_id", 999),
        ("natural", "path", "other.yml"),
        ("natural", "head_branch", "release"),
        ("natural", "conclusion", "success"),
        ("natural", "created_at", "2026-09-04T00:08:32Z"),
    ],
)
def test_historical_pair_run_metadata_cross_check_fails_closed(
    monkeypatch, run_kind, field, value
):
    continuity_run, natural_run, pages, readers, *_ = _fixture(monkeypatch)
    target = continuity_run if run_kind == "continuity" else natural_run
    target[field] = value
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head_sha", "a" * 40),
        ("created_at", "2026-09-04T23:57:11Z"),
        ("conclusion", "failure"),
        ("event", "workflow_dispatch"),
    ],
)
def test_historical_pair_watchdog_provenance_fails_closed(monkeypatch, field, value):
    _continuity, _natural, pages, readers, *_ = _fixture(monkeypatch)
    original = readers["get_run_by_id"]

    def get_run(run_id):
        run = original(run_id)
        if run_id == projection._HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID:
            run = {**run, field: value}
        return run

    readers["get_run_by_id"] = get_run
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


def test_historical_pair_proof_requires_complete_prefetched_universe(monkeypatch):
    _continuity, _natural, _pages, readers, *_ = _fixture(monkeypatch)
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=[{"id": projection._HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID}],
            **readers,
        )


def test_cached_page_reader_returns_detached_exact_snapshots(monkeypatch):
    _continuity, _natural, pages, _readers, *_ = _fixture(monkeypatch)
    universe = projection._prefetch_workflow_run_universe(
        lambda page, _per_page: pages[page - 1]
    )
    first = universe.reader(1, 100)
    first["workflow_runs"][0]["id"] = 1
    second = universe.reader(1, 100)
    assert second["workflow_runs"][0]["id"] != 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 123),
        ("name", "wrong.tar.gz"),
        ("digest", "sha256:" + "0" * 64),
        ("expired", True),
    ],
)
def test_historical_pair_artifact_identity_mutation_fails_closed(
    monkeypatch, field, value
):
    _continuity, natural, pages, readers, *_ = _fixture(monkeypatch)
    original = readers["get_run_artifacts"]

    def get_artifacts(run_id):
        payload = copy.deepcopy(original(run_id))
        if run_id == natural["id"]:
            payload["artifacts"][0][field] = value
        return payload

    readers["get_run_artifacts"] = get_artifacts
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


def test_historical_pair_missing_artifact_fails_closed(monkeypatch):
    _continuity, natural, pages, readers, *_ = _fixture(monkeypatch)
    original = readers["get_run_artifacts"]

    def get_artifacts(run_id):
        if run_id == natural["id"]:
            return {"total_count": 0, "artifacts": []}
        return original(run_id)

    readers["get_run_artifacts"] = get_artifacts
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


def test_historical_pair_third_matching_artifact_fails_closed(monkeypatch):
    continuity_run, natural_run, pages, readers, *_ = _fixture(monkeypatch)
    third = {**natural_run, "id": 99999999999}
    pages[0]["workflow_runs"].append(third)
    original = readers["get_run_artifacts"]

    def get_artifacts(run_id):
        if run_id == third["id"]:
            return {
                "total_count": 1,
                "artifacts": [
                    {
                        "id": 900,
                        "name": "failure-20260904T000700Z-run-99999999999.tar.gz",
                        "expired": False,
                        "digest": "sha256:" + "0" * 64,
                    }
                ],
            }
        return original(run_id)

    readers["get_run_artifacts"] = get_artifacts
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_run_id", 1),
        ("nominal_scheduled_for_utc", "2026-09-04T00:37:00.000000Z"),
        ("durable_asset_size_bytes", 1),
        ("durable_release_tag", "athena-fresh-holdout-evidence-2026-W35"),
        ("tick_committed", True),
    ],
)
def test_historical_pair_receipt_identity_mutation_fails_closed(
    monkeypatch, field, value
):
    _continuity, natural, pages, readers, _canonical_bundle, natural_bundle = _fixture(monkeypatch)
    receipt = json.loads(natural_bundle["receipt"])
    receipt[field] = value
    receipt_raw = _canonical(receipt)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive_zip:
        archive_zip.writestr(projection._HISTORICAL_NATURAL_ARTIFACT, natural_bundle["archive"])
        archive_zip.writestr(mirror.RECEIPT_MEMBER, receipt_raw)
    changed_zip = out.getvalue()
    monkeypatch.setattr(
        projection,
        "_HISTORICAL_NATURAL_ZIP_DIGEST",
        "sha256:" + hashlib.sha256(changed_zip).hexdigest(),
    )
    original = readers["get_run_artifacts"]

    def get_artifacts(run_id):
        payload = original(run_id)
        if run_id == natural["id"]:
            payload = copy.deepcopy(payload)
            payload["artifacts"][0]["digest"] = projection._HISTORICAL_NATURAL_ZIP_DIGEST
        return payload

    readers["get_run_artifacts"] = get_artifacts
    original_zip = readers["download_artifact_zip"]
    readers["download_artifact_zip"] = lambda artifact_id: (
        changed_zip
        if artifact_id == projection._HISTORICAL_NATURAL_ARTIFACT_ID
        else original_zip(artifact_id)
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )


def test_third_same_slot_execution_and_arbitrary_pair_remain_fail_closed(monkeypatch):
    continuity_run, natural_run, pages, readers, *_ = _fixture(monkeypatch)
    third = {**natural_run, "id": 99999999999, "nominal_slot_utc": SLOT}
    pages[0]["workflow_runs"].append(third)
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        universe = projection._prefetch_workflow_run_universe(
            lambda page, _per_page: pages[page - 1]
        )
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=universe,
            **readers,
        )

    # The frozen engine's arbitrary same-slot behavior is still covered by the
    # existing integration regression; this assertion documents that this
    # current-only proof does not manufacture a proof for unrelated IDs.
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._prove_exact_historical_same_slot_provider_duplicate(
            run_universe=[{"id": 1}],
            **readers,
        )


def test_proof_object_cannot_be_fabricated_without_preflight_token():
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection.HistoricalSameSlotProviderDuplicateProof(
            canonical_run_id=33820556400,
            auxiliary_run_id=33823663641,
            nominal_slot_utc=SLOT,
            canonical_archive_name=projection._HISTORICAL_CONTINUITY_ARTIFACT,
            canonical_archive_sha256="a" * 64,
            canonical_archive_size_bytes=1,
            auxiliary_archive_name=projection._HISTORICAL_NATURAL_ARTIFACT,
            auxiliary_archive_sha256="b" * 64,
            auxiliary_archive_size_bytes=1,
            canonical_actions_artifact_id=9918215386,
            canonical_actions_digest="sha256:" + "a" * 64,
            auxiliary_actions_artifact_id=9919255715,
            auxiliary_actions_digest="sha256:" + "b" * 64,
            provider_acquisition_count_canonical=3,
            provider_acquisition_count_auxiliary=3,
        )


def test_proof_object_rejects_mutated_identity_even_with_internal_token():
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection.HistoricalSameSlotProviderDuplicateProof(
            canonical_run_id=33820556400,
            auxiliary_run_id=33823663641,
            nominal_slot_utc=SLOT,
            canonical_archive_name=projection._HISTORICAL_CONTINUITY_ARTIFACT,
            canonical_archive_sha256="a" * 64,
            canonical_archive_size_bytes=projection._HISTORICAL_CONTINUITY_ARCHIVE_SIZE,
            auxiliary_archive_name=projection._HISTORICAL_NATURAL_ARTIFACT,
            auxiliary_archive_sha256=projection._HISTORICAL_NATURAL_ARCHIVE_SHA256,
            auxiliary_archive_size_bytes=projection._HISTORICAL_NATURAL_ARCHIVE_SIZE,
            canonical_actions_artifact_id=projection._HISTORICAL_CONTINUITY_ARTIFACT_ID,
            canonical_actions_digest=projection._HISTORICAL_CONTINUITY_ZIP_DIGEST,
            auxiliary_actions_artifact_id=projection._HISTORICAL_NATURAL_ARTIFACT_ID,
            auxiliary_actions_digest=projection._HISTORICAL_NATURAL_ZIP_DIGEST,
            provider_acquisition_count_canonical=3,
            provider_acquisition_count_auxiliary=3,
            _token=projection._HISTORICAL_PROOF_TOKEN,
        )
