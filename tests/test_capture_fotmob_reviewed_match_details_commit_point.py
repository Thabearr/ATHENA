from __future__ import annotations

import datetime
from pathlib import Path

from domain.reviewed_fixture_intelligence_bootstrap_artifact import (
    canonical_verified_bootstrap_artifact_receipt_bytes,
)
import scripts.capture_fotmob_reviewed_match_details as module
from tests.support.module_loader import load_test_module

UTC = datetime.timezone.utc
REQUEST_AT = datetime.datetime(2026, 8, 10, 6, 0, tzinfo=UTC)
SEND_AT = REQUEST_AT + datetime.timedelta(milliseconds=100)
OBSERVED_AT = REQUEST_AT + datetime.timedelta(seconds=1)


def _upstream(tmp_path: Path):
    loaded = load_test_module("test_reviewed_fixture_intelligence_bootstrap_artifact")
    _, _, verified = loaded._verified(tmp_path)
    return verified, canonical_verified_bootstrap_artifact_receipt_bytes(verified)


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class _Response:
    status = 200

    def __init__(self):
        self.body = b"{opaque-raw-evidence"
        self.offset = 0

    def getheader(self, name):
        if name == "Content-Type":
            return "application/json"
        if name == "Content-Length":
            return str(len(self.body))
        return None

    def read(self, amount):
        if self.offset >= len(self.body):
            return b""
        chunk = self.body[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk


class _Connection:
    def __init__(self):
        self.response = _Response()

    def putrequest(self, *args, **kwargs):
        return None

    def putheader(self, *args, **kwargs):
        return None

    def endheaders(self):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        return None


def test_no_state_dependent_revalidation_occurs_after_durable_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    verified, receipt_bytes = _upstream(tmp_path / "upstream")
    repo = tmp_path / "repo"
    repo.mkdir()

    real_revalidate = module.revalidate_reviewed_match_details_capture_artifact
    calls = 0

    def fail_if_called_after_writer(value):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("state-dependent validation occurred after commit point")
        return real_revalidate(value)

    monkeypatch.setattr(
        module,
        "revalidate_reviewed_match_details_capture_artifact",
        fail_if_called_after_writer,
    )

    execution = module.capture_fotmob_reviewed_match_details(
        verified_bootstrap_artifact=verified,
        verification_receipt_bytes=receipt_bytes,
        fixture_identifier="FOTMOB:1001",
        execute_live_network=True,
        repository_root=repo,
        connection_factory=lambda *args, **kwargs: _Connection(),
        clock=_Clock(REQUEST_AT, SEND_AT, OBSERVED_AT),
    )

    assert calls == 1
    assert execution.capture_directory.exists()
    assert (execution.capture_directory / "response.json").exists()
    assert (execution.capture_directory / "manifest.json").exists()
