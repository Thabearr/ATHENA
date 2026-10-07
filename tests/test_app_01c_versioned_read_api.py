"""D2 HTTP semantics against test-only read/cancel/export ports."""
from __future__ import annotations

import ast
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from api.app_factory import create_app
from domain.run_contracts import (
    AuthorityManifest,
    RunReceipt,
    RunRequest,
    canonical_json_bytes,
)
from runtime.local_session import LocalSession
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver, WritableRoots
from services.athena_capability_service import AthenaCapabilityService
from services.athena_preview_service import AthenaPreviewAdmissionService
from services.athena_read_service import (
    AthenaReadService,
    CancelIntentResult,
    ExportRecord,
    ReadBackendError,
    ReceiptObservation,
    RetainedFixturePage,
    RetainedFixtureRecord,
    RunEventPage,
    RunEventPayload,
    RunEventRecord,
    RunHistoryEntry,
    RunHistoryPage,
    RunSnapshotRecord,
)


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:12345"
HOST = "127.0.0.1:12345"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def resources(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    records = []
    for path, role in (("ui/index.html", "UI"), ("ui/app.js", "UI"), ("ui/styles.css", "UI"),
                       ("config/architecture/component-authority-registry-v1.json", "AUTHORITY_REGISTRY")):
        payload = (ROOT / path).read_bytes()
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append({"logical_path": path, "payload_path": path, "role": role,
                        "byte_sha256": hashlib.sha256(payload).hexdigest(), "required": True,
                        "source_git_blob_sha1": None, "canonical_sha256": None})
    raw = canonical_release_manifest_bytes({
        "schema_version": 1,
        "policy_id": "ATHENA_INSTALLED_RELEASE_MANIFEST_V1",
        "release_id": "test-release",
        "build_id": "test-build",
        "platform_tag": "windows" if sys.platform == "win32" else "linux",
        "architecture_tag": {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "aarch64",
                              "arm64": "aarch64"}[platform.machine().lower()],
        "closed_world_roots": ["config", "ui"],
        "resources": sorted(records, key=lambda item: item["logical_path"]),
    })
    (root / "release-manifest.json").write_bytes(raw)
    return ResourceResolver.for_installed(verify_installed_release(root, hashlib.sha256(raw).hexdigest()))


def _receipt_bytes(status: str, selected_count: int) -> bytes:
    request = RunRequest(
        dates=(date(2026, 10, 2),),
        target_legs=3,
        target_total_odds=None,
        bookie="sportybet",
        mode="main_application",
        authority_profile="MAIN",
        create_share_code=False,
        place_wager=False,
    )
    manifest = AuthorityManifest(
        authority_profile="MAIN",
        mode="main_application",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
        additional_capabilities={},
    )
    receipt = RunReceipt(
        status=status,
        observed_at=NOW,
        exact_commit_sha="a" * 40,
        request=request,
        stages=(),
        counts={"selected_leg_count": selected_count},
        selected_legs=tuple({"leg_id": f"leg-{index + 1}"} for index in range(selected_count)),
        shortfall=request.target_legs - selected_count,
        share_code_result=None,
        authority_manifest=manifest,
        evidence={},
        wager_placed=False,
    )
    return canonical_json_bytes(receipt)


class FakeRunRepository:
    def __init__(self):
        self.calls = {"snapshot": 0, "events": 0, "receipt": 0, "history": 0}
        self.snapshots = {
            "run-1": RunSnapshotRecord(
                run_id="run-1", state="RUNNING", state_version=4, created_at=NOW,
                updated_at=NOW, last_proven_stage="PRICE_ALL_ROUTER",
                counts={"selected_leg_count": 2, "unknown_count": None},
                target_legs=3, selected_leg_count=2, shortfall=1,
                execution_state="RUNNING", business_result="SHORTFALL", delivery_state=None,
                receipt_state="UNKNOWN", request_identity_ref="request-abc",
            ),
        }
        self.events = {
            "run-1": tuple(
                RunEventRecord(
                    sequence=sequence,
                    kind="STAGE_COMPLETED" if sequence < 4 else "STATE_CHANGED",
                    observed_at=NOW,
                    state_version=sequence,
                    payload=RunEventPayload(stage="PRICE_ALL_ROUTER" if sequence < 4 else None,
                                            state="RUNNING" if sequence == 4 else None),
                )
                for sequence in range(1, 5)
            ),
        }
        self.receipts = {
            "run-no-bet": ReceiptObservation("run-no-bet", "TERMINAL", _receipt_bytes("NO_BET", 0)),
            "run-shortfall": ReceiptObservation("run-shortfall", "TERMINAL", _receipt_bytes("SHORTFALL", 1)),
            "run-pending": ReceiptObservation("run-pending", "RUNNING", None),
            "run-corrupt": ReceiptObservation("run-corrupt", "TERMINAL", b"not canonical", "diag-123"),
        }
        self.history = (
            RunHistoryEntry("run-1", "RUNNING", state_version=4, created_at=NOW, updated_at=NOW, profile="MAIN"),
            RunHistoryEntry("run-no-bet", "TERMINAL", state_version=1, created_at=NOW, updated_at=NOW, profile="MAIN"),
            RunHistoryEntry("run-shortfall", "TERMINAL", state_version=1, created_at=NOW, updated_at=NOW, profile="SHADOW"),
        )

    def get_run_snapshot(self, run_id):
        self.calls["snapshot"] += 1
        return self.snapshots.get(run_id)

    def list_run_events(self, run_id, *, after_sequence, limit):
        self.calls["events"] += 1
        if run_id not in self.snapshots:
            return None
        items = tuple(event for event in self.events.get(run_id, ()) if event.sequence > after_sequence)
        return RunEventPage(items[:limit])

    def get_receipt_observation(self, run_id):
        self.calls["receipt"] += 1
        if run_id in self.receipts:
            return self.receipts[run_id]
        return None

    def list_runs(self, *, cursor, limit, state, profile):
        self.calls["history"] += 1
        items = [item for item in self.history
                 if (state is None or item.state == state) and (profile is None or item.profile == profile)]
        offset = int(cursor or "0")
        page = tuple(items[offset:offset + limit])
        end = offset + len(page)
        return RunHistoryPage(page, str(end) if end < len(items) else None)


class FakeCancelRepository:
    def __init__(self):
        self.calls = []
        self.states = {"queued": ["QUEUED", 1], "running": ["RUNNING", 2],
                       "terminal": ["TERMINAL", 8]}

    def request_cancel(self, run_id):
        self.calls.append(run_id)
        current = self.states.get(run_id)
        if current is None:
            return None
        state, version = current
        if state in {"TERMINAL", "CANCELLED", "INTERRUPTED"}:
            return CancelIntentResult(run_id, "already_terminal", state, version)
        if state == "CANCEL_REQUESTED":
            return CancelIntentResult(run_id, "already_requested", state, version)
        self.states[run_id] = ["CANCEL_REQUESTED", version + 1]
        return CancelIntentResult(run_id, "requested", "CANCEL_REQUESTED", version + 1)


class FakeFixtureIndex:
    def __init__(self):
        self.calls = []
        self.items = (
            RetainedFixtureRecord("fix-1", NOW, "comp-1", "League One", "North", "South", "club"),
            RetainedFixtureRecord("fix-2", NOW.replace(day=2), "comp-1", "League One", "East", "West", "club"),
            RetainedFixtureRecord("fix-3", NOW.replace(day=3), "intl-1", "Nations Cup", "Alpha", "Beta", "international"),
        )

    def list_retained_fixtures(self, *, cursor, limit, scope, date_from, date_to):
        self.calls.append((cursor, limit, scope, date_from, date_to))
        items = [item for item in self.items
                 if (scope is None or item.scope == scope)
                 and (date_from is None or date_from <= item.kickoff_at.date() <= date_to)]
        offset = int(cursor or "0")
        page = tuple(items[offset:offset + limit])
        end = offset + len(page)
        return RetainedFixturePage(page, str(end) if end < len(items) else None)


class FakeExportRepository:
    def __init__(self, run_repository):
        self.run_repository = run_repository
        self.calls = []
        self.records = {}

    def create_export(self, request):
        self.calls.append(request)
        if request.run_id is not None and request.run_id not in self.run_repository.snapshots:
            raise ReadBackendError("RUN_NOT_FOUND")
        if request.receipt_sha256 is not None:
            verified_digests = {
                hashlib.sha256(item.receipt_bytes).hexdigest()
                for item in self.run_repository.receipts.values()
                if item.receipt_bytes is not None and item.run_state in {"TERMINAL", "CANCELLED", "INTERRUPTED"}
            }
            if request.receipt_sha256 not in verified_digests:
                raise ReadBackendError("RUN_NOT_FOUND")
        export_id = "exp_" + ("a" if not self.records else "b") * 32
        filename = "run-summary.json" if request.kind == "run_summary_json" else "verified-receipt.json"
        record = ExportRecord(
            export_id=export_id,
            kind=request.kind,
            redaction_mode=request.redaction_mode,
            run_id=request.run_id,
            receipt_sha256=request.receipt_sha256,
            logical_path=f"exports/{export_id}/{filename}",
            created_at=NOW,
            sha256="e" * 64,
            byte_count=321,
        )
        self.records[export_id] = record
        return record

    def get_export(self, export_id):
        return self.records.get(export_id)


@pytest.fixture
def harness(resources, tmp_path):
    session = LocalSession()
    runs = FakeRunRepository()
    cancels = FakeCancelRepository()
    fixtures = FakeFixtureIndex()
    exports = FakeExportRepository(runs)
    read_service = AthenaReadService(
        run_repository=runs,
        cancel_repository=cancels,
        fixture_index=fixtures,
        export_repository=exports,
    )
    preview_service = AthenaPreviewAdmissionService(resources)
    roots = WritableRoots(
        data_root=tmp_path / "app-data", cache_root=tmp_path / "app-cache",
        state_root=tmp_path / "app-state", installed_release_root=resources.identity.release_root,
    )
    app = create_app(
        release_identity=resources.identity,
        resource_resolver=resources,
        writable_roots=roots,
        local_session=session,
        capability_service=AthenaCapabilityService(resources, preview_admission_service=preview_service),
        preview_admission_service=preview_service,
        read_service=read_service,
        origin=ORIGIN,
    )
    return TestClient(app), read_service, runs, cancels, fixtures, exports, session


def auth(session, *, origin=ORIGIN):
    result = {"X-Athena-Session": session.credential(), "Host": HOST}
    if origin is not None:
        result["Origin"] = origin
    return result


def test_security_rejects_before_any_read_cancel_or_export_service_call(harness, monkeypatch):
    client, service, _, _, _, _, session = harness
    calls = []
    methods = ("get_run_snapshot", "list_run_events", "get_verified_receipt", "list_runs",
               "list_retained_fixtures", "request_cancel", "create_export", "get_export")
    for name in methods:
        original = getattr(service, name)
        def counted(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(service, name, counted)

    read_paths = (
        "/api/v1/runs/run-1", "/api/v1/runs/run-1/events", "/api/v1/runs/run-no-bet/receipt",
        "/api/v1/runs", "/api/v1/fixtures", "/api/v1/exports/exp_" + "a" * 32,
    )
    for path in read_paths:
        assert client.get(path, headers={"Host": HOST}).status_code == 401
        assert client.get(path, headers={"X-Athena-Session": "0" * 64, "Host": HOST}).status_code == 401
        assert client.get(path, headers={**auth(session), "Host": "attacker.example"}).status_code == 403

    export_body = {"run_id": "run-1", "kind": "run_summary_json"}
    for method, path, body in (("post", "/api/v1/runs/queued/cancel", None),
                               ("post", "/api/v1/exports", export_body)):
        call = getattr(client, method)
        assert call(path, headers=auth(session, origin=None), json=body).status_code == 403
        assert call(path, headers=auth(session, origin="http://evil.example"), json=body).status_code == 403
        assert call(path, headers={**auth(session), "Host": "attacker.example"}, json=body).status_code == 403
        assert call(path, headers={"Host": HOST, "Origin": ORIGIN}, json=body).status_code == 401
        assert call(path, headers={"Host": HOST, "Origin": ORIGIN, "X-Athena-Session": "0" * 64},
                    json=body).status_code == 401
    assert calls == []


def test_run_snapshot_truth_unknowns_and_not_found(harness):
    client, _, _, _, _, _, session = harness
    response = client.get("/api/v1/runs/run-1", headers=auth(session, origin=None))
    assert response.status_code == 200
    body = response.json()
    assert (body["run_id"], body["state"], body["state_version"]) == ("run-1", "RUNNING", 4)
    assert body["last_proven_stage"] == "PRICE_ALL_ROUTER"
    assert body["counts"] == {"selected_leg_count": 2, "unknown_count": None}
    assert body["target_legs"] == 3 and body["selected_leg_count"] == 2 and body["shortfall"] == 1
    assert body["delivery_state"] is None and body["release_identity_ref"] is None
    missing = client.get("/api/v1/runs/missing", headers=auth(session, origin=None))
    assert missing.status_code == 404 and missing.json()["code"] == "RUN_NOT_FOUND"
    invalid = client.get("/api/v1/runs/..%2Fsecret", headers=auth(session, origin=None))
    assert invalid.status_code in {404, 422}


def test_event_pages_are_ordered_bounded_and_continue_from_last_proven_sequence(harness):
    client, _, runs, _, _, _, session = harness
    first = client.get("/api/v1/runs/run-1/events?limit=2", headers=auth(session, origin=None))
    assert first.status_code == 200
    assert [item["sequence"] for item in first.json()["events"]] == [1, 2]
    assert first.json()["next_cursor"] == 2
    second = client.get("/api/v1/runs/run-1/events?after_sequence=2&limit=2", headers=auth(session, origin=None))
    assert [item["sequence"] for item in second.json()["events"]] == [3, 4]
    assert second.json()["next_cursor"] == 4
    assert all(item["state_version"] == item["sequence"] for item in first.json()["events"])
    calls = runs.calls["events"]
    runs.events["run-1"] = (runs.events["run-1"][0], runs.events["run-1"][2])
    sparse = client.get("/api/v1/runs/run-1/events?limit=10", headers=auth(session, origin=None))
    assert [item["sequence"] for item in sparse.json()["events"]] == [1, 3]
    assert sparse.json()["next_cursor"] == 3
    calls += 1
    for query in ("after_sequence=-1", "after_sequence=1.0", "limit=0", "limit=201", "limit=01", "limit=2&limit=3"):
        response = client.get("/api/v1/runs/run-1/events?" + query, headers=auth(session, origin=None))
        assert response.status_code == 422
    assert runs.calls["events"] == calls
    missing = client.get("/api/v1/runs/no-run/events", headers=auth(session, origin=None))
    assert missing.status_code == 404


def test_verified_receipts_keep_no_bet_shortfall_and_canonical_counts(harness):
    client, _, _, _, _, _, session = harness
    for run_id, status, selected, shortfall in (
        ("run-no-bet", "NO_BET", 0, 3), ("run-shortfall", "SHORTFALL", 1, 2),
    ):
        response = client.get(f"/api/v1/runs/{run_id}/receipt", headers=auth(session, origin=None))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == status
        assert body["selected_leg_count"] == selected and body["shortfall"] == shortfall
        assert body["wager_placed"] is False
        assert body["delivery_state"] == "NOT_REQUESTED"
        assert "selected_legs" not in body and "share_code_result" not in body and "evidence" not in body
    pending = client.get("/api/v1/runs/run-pending/receipt", headers=auth(session, origin=None))
    assert pending.status_code == 409 and pending.json()["code"] == "RECEIPT_NOT_PRODUCED"
    corrupt = client.get("/api/v1/runs/run-corrupt/receipt", headers=auth(session, origin=None))
    assert corrupt.status_code == 409 and corrupt.json()["code"] == "RECEIPT_INTEGRITY_BLOCKED"
    assert corrupt.json()["diagnostic_id"] == "diag-123"
    missing = client.get("/api/v1/runs/missing/receipt", headers=auth(session, origin=None))
    assert missing.status_code == 404 and missing.json()["code"] == "RUN_NOT_FOUND"


def test_history_and_fixture_pages_are_stable_bounded_and_filtered(harness):
    client, _, runs, _, fixtures, _, session = harness
    first = client.get("/api/v1/runs?limit=2", headers=auth(session, origin=None))
    assert first.status_code == 200
    assert [item["run_id"] for item in first.json()["items"]] == ["run-1", "run-no-bet"]
    assert first.json()["next_cursor"] == "2"
    second = client.get("/api/v1/runs?cursor=2&limit=2", headers=auth(session, origin=None))
    assert [item["run_id"] for item in second.json()["items"]] == ["run-shortfall"]
    assert second.json()["next_cursor"] is None
    filtered = client.get("/api/v1/runs?limit=1&state=TERMINAL", headers=auth(session, origin=None))
    assert [item["run_id"] for item in filtered.json()["items"]] == ["run-no-bet"]
    filtered_next = client.get("/api/v1/runs?cursor=1&limit=1&state=TERMINAL",
                               headers=auth(session, origin=None))
    assert [item["run_id"] for item in filtered_next.json()["items"]] == ["run-shortfall"]
    assert filtered_next.json()["next_cursor"] is None
    fixture_page = client.get("/api/v1/fixtures?limit=1&scope=club&date_from=2026-10-01&date_to=2026-10-31",
                              headers=auth(session, origin=None))
    assert fixture_page.status_code == 200
    assert [item["fixture_id"] for item in fixture_page.json()["items"]] == ["fix-1"]
    assert fixture_page.json()["next_cursor"] == "1"
    fixture_page2 = client.get("/api/v1/fixtures?cursor=1&limit=1&scope=club&date_from=2026-10-01&date_to=2026-10-31",
                               headers=auth(session, origin=None))
    assert fixture_page2.json()["items"][0]["fixture_id"] == "fix-2"
    assert all(call[2] == "club" for call in fixtures.calls)
    assert runs.calls["history"] == 4
    bad = client.get("/api/v1/fixtures?date_from=2026-10-01&date_to=2026-11-15",
                     headers=auth(session, origin=None))
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_FILTER"


def test_cancel_records_only_idempotent_cooperative_intent(harness):
    client, _, _, cancels, _, _, session = harness
    headers = auth(session)
    first = client.post("/api/v1/runs/queued/cancel", headers=headers)
    assert first.status_code == 200 and first.json()["disposition"] == "requested"
    replay = client.post("/api/v1/runs/queued/cancel", headers=headers)
    assert replay.status_code == 200 and replay.json()["disposition"] == "already_requested"
    assert first.json()["run_id"] == replay.json()["run_id"] == "queued"
    running = client.post("/api/v1/runs/running/cancel", headers=headers)
    assert running.json()["state"] == "CANCEL_REQUESTED"
    terminal = client.post("/api/v1/runs/terminal/cancel", headers=headers)
    assert terminal.json()["disposition"] == "already_terminal"
    assert cancels.calls == ["queued", "queued", "running", "terminal"]
    missing = client.post("/api/v1/runs/missing/cancel", headers=headers)
    assert missing.status_code == 404


def test_exports_use_opaque_ids_and_fixed_logical_paths_and_reject_paths(harness):
    client, _, _, _, _, exports, session = harness
    response = client.post("/api/v1/exports", headers=auth(session),
                           json={"run_id": "run-1", "kind": "run_summary_json", "redaction_mode": "strict"})
    assert response.status_code == 201
    record = response.json()
    assert record["export_id"] == "exp_" + "a" * 32
    assert record["logical_path"] == f"exports/{record['export_id']}/run-summary.json"
    assert record["run_id"] == "run-1" and record["receipt_sha256"] is None
    retrieved = client.get("/api/v1/exports/" + record["export_id"], headers=auth(session, origin=None))
    assert retrieved.status_code == 200 and retrieved.json() == record
    verified_receipt_sha = hashlib.sha256(_receipt_bytes("NO_BET", 0)).hexdigest()
    receipt_export = client.post("/api/v1/exports", headers=auth(session), json={
        "receipt_sha256": verified_receipt_sha,
        "kind": "verified_receipt_json",
    })
    assert receipt_export.status_code == 201
    assert receipt_export.json()["logical_path"] == (
        f"exports/{receipt_export.json()['export_id']}/verified-receipt.json"
    )
    bad_kind = client.post("/api/v1/exports", headers=auth(session),
                           json={"run_id": "run-1", "kind": "arbitrary"})
    assert bad_kind.status_code == 422 and bad_kind.json()["code"] == "INVALID_EXPORT_KIND"
    for path in ("../outside", "C:\\outside\\file", "C:relative", "/etc/passwd",
                 "..%2foutside", "exports/link/../target", "\\\\server\\share"):
        bad = client.post("/api/v1/exports", headers=auth(session), json={
            "run_id": "run-1", "kind": "run_summary_json", "path": path,
        })
        assert bad.status_code == 422 and bad.json()["code"] == "INVALID_EXPORT_REQUEST"
        assert path not in bad.text
    assert len(exports.calls) == 2


def test_supported_unavailable_ports_are_503_instead_of_empty_or_fake_success(resources, tmp_path):
    session = LocalSession()
    preview_service = AthenaPreviewAdmissionService(resources)
    app = create_app(
        release_identity=resources.identity,
        resource_resolver=resources,
        writable_roots=WritableRoots(data_root=tmp_path / "data", cache_root=tmp_path / "cache",
                                     state_root=tmp_path / "state",
                                     installed_release_root=resources.identity.release_root),
        local_session=session,
        capability_service=AthenaCapabilityService(resources, preview_admission_service=preview_service),
        preview_admission_service=preview_service,
        read_service=AthenaReadService.unavailable(),
        origin=ORIGIN,
    )
    client = TestClient(app)
    headers = auth(session)
    for path, code in (
        ("/api/v1/runs/run-1", "RUN_STORE_UNAVAILABLE"),
        ("/api/v1/runs/run-1/events", "RUN_STORE_UNAVAILABLE"),
        ("/api/v1/runs/run-1/receipt", "RUN_STORE_UNAVAILABLE"),
        ("/api/v1/runs", "RUN_STORE_UNAVAILABLE"),
        ("/api/v1/fixtures", "RETAINED_FIXTURE_INDEX_UNAVAILABLE"),
        ("/api/v1/exports/exp_" + "a" * 32, "EXPORT_STORE_UNAVAILABLE"),
    ):
        response = client.get(path, headers=auth(session, origin=None))
        assert response.status_code == 503 and response.json()["code"] == code
    cancel = client.post("/api/v1/runs/run-1/cancel", headers=headers)
    assert cancel.status_code == 503 and cancel.json()["code"] == "CANCEL_STORE_UNAVAILABLE"
    export = client.post("/api/v1/exports", headers=headers,
                         json={"run_id": "run-1", "kind": "run_summary_json"})
    assert export.status_code == 503 and export.json()["code"] == "EXPORT_STORE_UNAVAILABLE"
    assert "items" not in client.get("/api/v1/runs", headers=auth(session, origin=None)).json()
    assert "export_id" not in export.json()


def test_legacy_generate_historical_execution_is_pinned_but_current_compatibility_is_blocked(resources, tmp_path):
    from scripts import audit_app_01a_local_shell as audit
    historical = audit.historical_runtime_payload("api/server.py")
    if isinstance(historical, bytes):
        historical = historical.decode("utf-8")
    assert "from services.legacy_acca_builder_compat import AccaBuilder" in historical
    assert "builder.build(" in historical

    source = (ROOT / "api/server.py").read_text(encoding="utf-8")
    assert "AccaBuilder" not in source and "legacy_acca_builder_compat" not in source
    assert "AthenaRunService" not in source and "WorkerLauncher" not in source
    from api.server import create_compatibility_app
    client = TestClient(create_compatibility_app(development_compatibility=True))
    response = client.post("/api/generate", json={"days": 2})
    assert response.status_code == 410
    assert response.json()["code"] == "LEGACY_GENERATE_BLOCKED"
    session = LocalSession()
    preview_service = AthenaPreviewAdmissionService(resources)
    supported_app = create_app(
        release_identity=resources.identity,
        resource_resolver=resources,
        writable_roots=WritableRoots(data_root=tmp_path / "data", cache_root=tmp_path / "cache",
                                     state_root=tmp_path / "state",
                                     installed_release_root=resources.identity.release_root),
        local_session=session,
        capability_service=AthenaCapabilityService(resources, preview_admission_service=preview_service),
        preview_admission_service=preview_service,
        read_service=AthenaReadService.unavailable(),
        origin=ORIGIN,
    )
    supported = TestClient(supported_app)
    assert supported.get("/api/generate", headers=auth(session, origin=None)).status_code == 404


def test_versioned_routers_are_import_pure_and_error_payloads_are_confidential(harness, monkeypatch):
    client, service, runs, _, _, _, session = harness
    router_paths = (ROOT / "api/v1/runs.py", ROOT / "api/v1/fixtures.py", ROOT / "api/v1/exports.py",
                    ROOT / "api/v1/common.py")
    forbidden = ("workers", "legacy_acca_builder", "BookieAutomator", "api.export", "betting_service",
                 "pricing", "portfolio", "FotMobAdvancedScraper", "_get_cached_fixtures")
    for path in router_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not any(any(blocked in module for blocked in forbidden) for module in imported)

    credential = session.credential()
    secret_path = "C:\\Users\\secret\\athena.sqlite"
    runs.get_run_snapshot = lambda run_id: (_ for _ in ()).throw(RuntimeError(
        f"{secret_path} {credential} traceback DB_PASSWORD=hidden"))
    response = client.get("/api/v1/runs/run-1", headers=auth(session, origin=None))
    assert response.status_code == 503
    for secret in (secret_path, credential, "traceback", "DB_PASSWORD", "RuntimeError"):
        assert secret not in response.text


def test_v1_fixture_browse_never_imports_or_calls_provider_or_legacy_cache(harness, monkeypatch):
    client, _, _, _, fixture_index, _, session = harness
    external = []
    original = socket.socket.connect

    def deny_external(self, address):
        if self.family == getattr(socket, "AF_UNIX", -1) or address[0] in {"127.0.0.1", "::1"}:
            return original(self, address)
        external.append(address)
        raise AssertionError("provider transport is forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny_external)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("worker launch forbidden"))
    from api import server as legacy_server
    monkeypatch.setattr(legacy_server, "FotMobAdvancedScraper", lambda: pytest.fail("provider scraper called"))
    monkeypatch.setattr(legacy_server, "_get_cached_fixtures", lambda *args, **kwargs: pytest.fail("legacy cache called"))
    response = client.get("/api/v1/fixtures", headers=auth(session, origin=None))
    assert response.status_code == 200
    assert len(fixture_index.calls) == 1
    assert external == []
