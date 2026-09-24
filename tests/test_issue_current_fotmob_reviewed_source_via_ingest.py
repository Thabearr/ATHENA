from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import issue_current_fotmob_reviewed_source_via_ingest as cli
from services.current_fotmob_ingest_issuer import CurrentFotMobIngestIssuerError


COMMIT = "a" * 40
SUMMARY = {
    "schema_version": 1,
    "dataset_name": "athena-current-fotmob-reviewed-source-execution-v1",
    "status": "REVIEWED_CURRENT_FOTMOB_FIXTURE_BOOTSTRAP_VERIFIED",
    "source_capture_directory": "artifacts/athena-ingest-workflow/sources/fotmob/20260924/cap-1",
    "source_capture_manifest_sha256": "b" * 64,
    "source_raw_sha256": "c" * 64,
    "minimum_lead_seconds": 3600,
    "max_source_age_seconds": 900,
    "authority": {"model_feature": False, "selection": False, "bet": False},
    "wager_placed": False,
}


def _result():
    return SimpleNamespace(execution=SimpleNamespace(summary=lambda: SUMMARY))


def _invoke(monkeypatch, tmp_path: Path, *, extra=()):
    output = tmp_path / "execution.json"
    code = cli.main(
        ["--date", "20260924", "--execute-live-network", "--output", str(output), *extra]
    )
    return code, output


def test_success_binds_exact_github_lineage_calls_issuer_once_and_writes_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    calls = []

    def issue(*args, **kwargs):
        calls.append((args, kwargs))
        return _result()

    monkeypatch.setattr(cli, "issue_current_reviewed_fotmob_via_canonical_ingest", issue)
    code, output = _invoke(monkeypatch, tmp_path)

    assert code == 0
    assert len(calls) == 1
    assert calls[0][0] == ("20260924",)
    assert calls[0][1]["expected_git_sha"] == COMMIT
    assert calls[0][1]["expected_git_ref"] == "refs/heads/main"
    assert calls[0][1]["execute_live_network"] is True
    assert "timezone" not in calls[0][1]
    assert "ccode3" not in calls[0][1]
    assert json.loads(output.read_text(encoding="utf-8")) == SUMMARY
    assert json.loads(output.read_text(encoding="utf-8"))["wager_placed"] is False


@pytest.mark.parametrize(
    ("ref", "sha", "expected_failure"),
    [
        ("refs/heads/feature", COMMIT, "MAIN_REF_REQUIRED"),
        (None, COMMIT, "MAIN_REF_REQUIRED"),
        ("refs/heads/main", None, "CANONICAL_GITHUB_SHA_REQUIRED"),
        ("refs/heads/main", "A" * 40, "CANONICAL_GITHUB_SHA_REQUIRED"),
        ("refs/heads/main", "f" * 39, "CANONICAL_GITHUB_SHA_REQUIRED"),
        ("refs/heads/main", "g" * 40, "CANONICAL_GITHUB_SHA_REQUIRED"),
    ],
)
def test_bad_github_lineage_fails_before_issuer_and_leaves_failure_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ref: str | None,
    sha: str | None,
    expected_failure: str,
) -> None:
    if ref is None:
        monkeypatch.delenv("GITHUB_REF", raising=False)
    else:
        monkeypatch.setenv("GITHUB_REF", ref)
    if sha is None:
        monkeypatch.delenv("GITHUB_SHA", raising=False)
    else:
        monkeypatch.setenv("GITHUB_SHA", sha)
    monkeypatch.setattr(
        cli,
        "issue_current_reviewed_fotmob_via_canonical_ingest",
        lambda *args, **kwargs: pytest.fail("lineage failed before issuer invocation"),
    )

    code, output = _invoke(monkeypatch, tmp_path)

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert code != 0
    assert receipt["failure_code"] == expected_failure
    assert receipt["minimum_lead_seconds"] == 3600
    assert receipt["max_source_age_seconds"] == 900
    assert receipt["wager_placed"] is False


def test_missing_live_network_flag_fails_before_issuer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setattr(
        cli,
        "issue_current_reviewed_fotmob_via_canonical_ingest",
        lambda *args, **kwargs: pytest.fail("missing live flag must stop before issuer"),
    )
    output = tmp_path / "execution.json"

    code = cli.main(["--date", "20260924", "--output", str(output)])

    assert code != 0
    assert json.loads(output.read_text(encoding="utf-8"))["failure_code"] == "LIVE_NETWORK_FLAG_REQUIRED"


def test_issuer_failure_writes_fail_closed_summary_without_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise CurrentFotMobIngestIssuerError("synthetic offline failure")

    monkeypatch.setattr(cli, "issue_current_reviewed_fotmob_via_canonical_ingest", fail)
    code, output = _invoke(monkeypatch, tmp_path)

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert code != 0
    assert len(calls) == 1
    assert receipt["status"] == "CANONICAL_CURRENT_FOTMOB_INGEST_ISSUER_FAILED"
    assert receipt["failure_code"] == "CANONICAL_ISSUER_FAILED"
    assert receipt["wager_placed"] is False
    assert receipt["minimum_lead_seconds"] == 3600
    assert receipt["max_source_age_seconds"] == 900
    assert not hasattr(cli, "issue_current_fotmob_reviewed_source")


def test_cli_owns_no_provider_transport_or_legacy_live_issuer() -> None:
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    imports: set[str] = set()
    references: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.update(alias.name for alias in node.names)
            references.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
            references.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            references.add(node.id)
        elif isinstance(node, ast.Attribute):
            references.add(node.attr)
    assert not ({"fetch_fotmob_data_matches", "write_data_matches_capture_directory"} & references)
    assert "issue_current_fotmob_reviewed_source" not in references
    assert "issue_current_reviewed_fotmob_via_canonical_ingest" in imports


def test_cli_exposes_no_policy_or_request_scope_overrides() -> None:
    options = {
        option
        for action in cli.build_parser()._actions
        for option in action.option_strings
    }
    assert options == {"-h", "--help", "--date", "--execute-live-network", "--output"}
