from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import re
from types import SimpleNamespace

from scripts import current_shadow_history_github_persistent_cache as cache


RUN_ID = 99
WORKFLOW_ID = 1234
WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
HEAD_SHA = "a" * 40
ZIP_BYTES = b"exact-actions-artifact-zip"
ARCHIVE_BYTES = b"exact-durable-history-archive"
ARCHIVE_SHA256 = hashlib.sha256(ARCHIVE_BYTES).hexdigest()
ARTIFACT_NAME = f"success-20260905T000700Z-run-{RUN_ID}.tar.gz"
RUN = {
    "id": RUN_ID,
    "status": "completed",
    "conclusion": "success",
    "workflow_id": WORKFLOW_ID,
    "event": "schedule",
    "head_branch": "main",
    "head_sha": HEAD_SHA,
    "path": WORKFLOW_PATH,
    "run_attempt": 1,
}


def test_exact_completed_run_is_prewarmed_only_once_per_worker(capsys) -> None:
    calls = {"artifact": 0, "download": 0, "extract": 0}
    artifact = {
        "id": 777,
        "name": ARTIFACT_NAME,
        "digest": "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest(),
    }

    def gh_json(_endpoint):
        calls["artifact"] += 1
        return {"artifacts": [artifact]}

    def download(_endpoint):
        calls["download"] += 1
        return ZIP_BYTES

    def extract(archive_bytes, expected_sha256, *, require_control):
        calls["extract"] += 1
        assert hashlib.sha256(archive_bytes).hexdigest() == expected_sha256
        assert require_control is True
        return ({"event": "TICK_COMMITTED"},)

    lineage = SimpleNamespace(
        _gh_json=gh_json,
        _candidate_artifact=lambda payload, _run_id: payload["artifacts"][0],
        _is_exact_zero_artifact_payload=lambda payload: not payload["artifacts"],
        _extract_control_rows=extract,
        ARTIFACT_RE=re.compile(r"(success|failure)-.*"),
    )
    projection = SimpleNamespace(
        continuity=SimpleNamespace(
            PRIMARY_WORKFLOW_ID=WORKFLOW_ID,
            PRIMARY_WORKFLOW_PATH=WORKFLOW_PATH,
        ),
        _prefetch_workflow_run_universe=lambda _reader: SimpleNamespace(runs=(RUN,)),
    )
    latest = SimpleNamespace(
        REPOSITORY="Thabearr/ATHENA",
        lineage_audit=lineage,
        recovery_projection=projection,
        pr175_projection=SimpleNamespace(_gh_download_compatible=download),
        mirror=SimpleNamespace(
            verify_actions_artifact_zip_digest=lambda payload, _digest: hashlib.sha256(
                payload
            ).hexdigest(),
            verify_actions_artifact_bundle=lambda **_kwargs: {
                "archive_bytes": ARCHIVE_BYTES,
                "archive_sha256": ARCHIVE_SHA256,
            },
        ),
    )

    hooks = cache._install_control_row_reuse(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
        latest.recovery_projection._prefetch_workflow_run_universe(
            lambda _page, _per_page: {}
        )
    finally:
        cache._restore_control_row_reuse(latest, hooks)

    assert calls == {"artifact": 1, "download": 1, "extract": 1}
    output = capsys.readouterr().out
    assert "prewarmed 1 new exact control archives" in output
    assert "prewarmed 0 new exact control archives" in output
    assert "reused 1 exact completed-run identities" in output


def test_run_metadata_drift_forces_a_fresh_speculative_prewarm() -> None:
    calls = 0
    artifact = {
        "id": 777,
        "name": ARTIFACT_NAME,
        "digest": "sha256:" + hashlib.sha256(ZIP_BYTES).hexdigest(),
    }

    def extract(_archive_bytes, _expected_sha256, *, require_control):
        nonlocal calls
        calls += 1
        return ({"require_control": require_control},)

    runs = [RUN]
    latest = SimpleNamespace(
        REPOSITORY="Thabearr/ATHENA",
        lineage_audit=SimpleNamespace(
            _gh_json=lambda _endpoint: {"artifacts": [artifact]},
            _candidate_artifact=lambda payload, _run_id: payload["artifacts"][0],
            _is_exact_zero_artifact_payload=lambda payload: not payload["artifacts"],
            _extract_control_rows=extract,
            ARTIFACT_RE=re.compile(r"(success|failure)-.*"),
        ),
        recovery_projection=SimpleNamespace(
            continuity=SimpleNamespace(
                PRIMARY_WORKFLOW_ID=WORKFLOW_ID,
                PRIMARY_WORKFLOW_PATH=WORKFLOW_PATH,
            ),
            _prefetch_workflow_run_universe=lambda _reader: SimpleNamespace(
                runs=tuple(runs)
            ),
        ),
        pr175_projection=SimpleNamespace(_gh_download_compatible=lambda _endpoint: ZIP_BYTES),
        mirror=SimpleNamespace(
            verify_actions_artifact_zip_digest=lambda *_args: None,
            verify_actions_artifact_bundle=lambda **_kwargs: {
                "archive_bytes": ARCHIVE_BYTES,
                "archive_sha256": ARCHIVE_SHA256,
            },
        ),
    )

    hooks = cache._install_control_row_reuse(latest)
    try:
        latest.recovery_projection._prefetch_workflow_run_universe(lambda *_args: {})
        runs[0] = dict(RUN, updated_at="2026-09-05T18:20:00Z")
        latest.recovery_projection._prefetch_workflow_run_universe(lambda *_args: {})
    finally:
        cache._restore_control_row_reuse(latest, hooks)

    assert calls == 2


@dataclasses.dataclass(frozen=True)
class _Derived:
    artifact_zip_sha256: str
    archive_sha256: str
    archive_size_bytes: int
    receipt_sha256: str
    nominal_scheduled_for_utc: dt.datetime
    committed_at_utc: dt.datetime
    checkpoint_sha256: str
    settlement_journal_sha256: str
    settlement_journal_row_count: int
    reviewed_fresh_settlements: tuple[object, ...]
    reviewed_legacy_update_count: int
    shadow_handoff: object


class _PrefixSource:
    def __init__(self, marker: str, *, payload: bytes = ZIP_BYTES):
        self.current_bootstrap = f"bootstrap:{marker}"
        self.source_raw_json = f"raw:{marker}".encode()
        self.source_manifest = f"manifest:{marker}"
        self.legacy_bootstrap_projection_raw = b"legacy"
        self.workflow_run_id = RUN_ID
        self.artifact_name = ARTIFACT_NAME
        self.artifact_zip_bytes = payload
        self.artifact_zip_metadata_digest = (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )
        self.marker = marker

    @property
    def source_observed_at(self) -> dt.datetime:
        return dt.datetime(2026, 9, 5, 18, 0, tzinfo=dt.timezone.utc)


def _fake_prefix_latest(*, fail_receipt_for: set[str] | None = None):
    full_calls: list[str] = []
    shadow_calls: list[str] = []
    verify_bundle_calls = 0
    nominal = dt.datetime(2026, 9, 5, 17, 7, tzinfo=dt.timezone.utc)
    committed = dt.datetime(2026, 9, 5, 17, 8, tzinfo=dt.timezone.utc)
    receipt_bytes = b"receipt"
    archive_sha = hashlib.sha256(ARCHIVE_BYTES).hexdigest()
    fail_receipt_for = fail_receipt_for or set()

    def original_derive(source):
        full_calls.append(source.marker)
        return _Derived(
            artifact_zip_sha256=hashlib.sha256(source.artifact_zip_bytes).hexdigest(),
            archive_sha256=archive_sha,
            archive_size_bytes=len(ARCHIVE_BYTES),
            receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
            nominal_scheduled_for_utc=nominal,
            committed_at_utc=committed,
            checkpoint_sha256="c" * 64,
            settlement_journal_sha256="d" * 64,
            settlement_journal_row_count=3,
            reviewed_fresh_settlements=("settlement-1", "settlement-2"),
            reviewed_legacy_update_count=1,
            shadow_handoff=f"full-shadow:{source.marker}",
        )

    def verify_bundle(**_kwargs):
        nonlocal verify_bundle_calls
        verify_bundle_calls += 1
        return {
            "archive_bytes": ARCHIVE_BYTES,
            "archive_sha256": archive_sha,
            "archive_size_bytes": len(ARCHIVE_BYTES),
            "receipt_bytes": receipt_bytes,
        }

    def exact_receipt(_raw, *, run_id, artifact_name, source_observed_at):
        marker = getattr(source_observed_at, "marker", None)
        if marker in fail_receipt_for:
            raise ValueError("receipt/source observation mismatch")
        return (
            {"workflow_run_id": run_id, "durable_asset_name": artifact_name},
            nominal,
            committed,
        )

    def shadow_builder(**kwargs):
        marker = str(kwargs["current_bootstrap"]).split(":", 1)[1]
        shadow_calls.append(marker)
        assert kwargs["reviewed_fresh_settlements"] == (
            "settlement-1",
            "settlement-2",
        )
        return f"reused-shadow:{marker}"

    prefix = SimpleNamespace(
        CurrentDurableFreshHistoryPrefixSourceBundle=_PrefixSource,
        _DerivedPrefix=_Derived,
        _derive=original_derive,
        _sha=lambda raw: hashlib.sha256(raw).hexdigest(),
        _exact_receipt=exact_receipt,
        mirror=SimpleNamespace(
            verify_actions_artifact_zip_digest=lambda payload, _digest: hashlib.sha256(
                payload
            ).hexdigest(),
            verify_actions_artifact_bundle=verify_bundle,
        ),
        shadow=SimpleNamespace(
            build_current_fotmob_utc_native_shadow_prediction_handoff=shadow_builder
        ),
    )
    latest = SimpleNamespace(prefix=prefix)
    return latest, full_calls, shadow_calls, lambda: verify_bundle_calls


def test_same_exact_durable_archive_reuses_invariant_replay_across_current_sources() -> None:
    latest, full_calls, shadow_calls, bundle_calls = _fake_prefix_latest()
    hooks = cache._install_durable_prefix_reuse(latest)
    try:
        first = latest.prefix._derive(_PrefixSource("day-1"))
        second = latest.prefix._derive(_PrefixSource("day-2"))
    finally:
        cache._restore_durable_prefix_reuse(latest, hooks)

    assert first.shadow_handoff == "full-shadow:day-1"
    assert second.shadow_handoff == "reused-shadow:day-2"
    assert second.reviewed_fresh_settlements == first.reviewed_fresh_settlements
    assert second.archive_sha256 == first.archive_sha256
    assert full_calls == ["day-1"]
    assert shadow_calls == ["day-2"]
    assert bundle_calls() == 1


def test_changed_artifact_bytes_never_share_durable_prefix_replay() -> None:
    latest, full_calls, shadow_calls, _bundle_calls = _fake_prefix_latest()
    hooks = cache._install_durable_prefix_reuse(latest)
    try:
        latest.prefix._derive(_PrefixSource("day-1"))
        changed = latest.prefix._derive(
            _PrefixSource("day-2", payload=ZIP_BYTES + b"-changed")
        )
    finally:
        cache._restore_durable_prefix_reuse(latest, hooks)

    assert changed.shadow_handoff == "full-shadow:day-2"
    assert full_calls == ["day-1", "day-2"]
    assert shadow_calls == []
