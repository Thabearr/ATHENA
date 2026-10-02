from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from scripts import restore_fotmob_pr119_bootstrap_release as bootstrap


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
FIXTURE = ROOT / "tests/fixtures/core_01b_artifact_roles/pr119-bootstrap.ndjson.gz"
RELEASE_METADATA_FIXTURE = ROOT / (
    "tests/fixtures/core_01b_artifact_roles/pr119-bootstrap-release-metadata.json"
)
HISTORICAL_PR119_EXECUTOR = (
    "scripts/qualify_fotmob_historical_source_history_completeness_materialization.py"
)
HISTORICAL_PR119_EXECUTOR_BLOB = "2409676b4993a25024e2e8554e84e3525e7c5e6e"
HISTORICAL_ARTIFACT_ID = "9249856559"
HISTORICAL_ARTIFACT_SHA256 = (
    "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
)
HISTORICAL_ARTIFACT_SIZE = 61_886_753


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _payload() -> bytes:
    return gzip.decompress(FIXTURE.read_bytes())


def _release(*, assets: list[dict] | None = None, **overrides) -> dict:
    value = {
        "id": bootstrap.RELEASE_ID,
        "tag_name": bootstrap.RELEASE_TAG,
        "name": bootstrap.RELEASE_NAME,
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "id": bootstrap.ASSET_ID,
                "name": bootstrap.ASSET_NAME,
                "state": "uploaded",
                "size": bootstrap.ASSET_SIZE,
                "digest": bootstrap.ASSET_DIGEST,
            }
        ] if assets is None else assets,
    }
    return {**value, **overrides}


def _asset(**overrides) -> dict:
    return {
        "id": bootstrap.ASSET_ID,
        "name": bootstrap.ASSET_NAME,
        "state": "uploaded",
        "size": bootstrap.ASSET_SIZE,
        "digest": bootstrap.ASSET_DIGEST,
        **overrides,
    }


def test_offline_fixture_is_the_exact_fixed_release_payload() -> None:
    raw = _payload()
    assert len(raw) == bootstrap.ASSET_SIZE == fresh.BOOTSTRAP_PROJECTION_SIZE
    assert hashlib.sha256(raw).hexdigest() == bootstrap.PAYLOAD_SHA256
    assert raw.count(b"\n") == bootstrap.ROW_COUNT == fresh.BOOTSTRAP_PROJECTION_ROWS
    assert len(fresh.parse_reviewed_legacy_bootstrap_projection(raw)) == bootstrap.ROW_COUNT


def test_source_controlled_release_metadata_fixture_binds_exact_fixed_identity() -> None:
    raw = RELEASE_METADATA_FIXTURE.read_bytes()
    metadata = json.loads(raw)
    assert raw == (json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assets = bootstrap.validate_release_metadata(bootstrap.REPOSITORY, metadata)
    assert bootstrap.validate_asset_metadata(assets) == bootstrap.ASSET_ID


def test_historical_pr119_materializer_remains_pinned_but_is_not_live_bootstrap() -> None:
    assert subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{HISTORICAL_PR119_EXECUTOR}"],
        cwd=ROOT,
        text=True,
    ).strip() == HISTORICAL_PR119_EXECUTOR_BLOB
    assert HISTORICAL_ARTIFACT_ID == "9249856559"
    assert HISTORICAL_ARTIFACT_SIZE == 61_886_753
    assert HISTORICAL_ARTIFACT_SHA256 == (
        "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
    )


def test_live_workflow_is_fixed_release_only_before_the_single_collection_surface() -> None:
    text = _workflow_text()
    bootstrap_start = text.index(
        "- name: Restore or materialize PR119 bootstrap projection"
    )
    collect_start = text.index("- name: Execute reviewed fresh-holdout collection tick")
    bootstrap_section = text[bootstrap_start:collect_start]
    assert "restore_fotmob_pr119_bootstrap_release.py" in bootstrap_section
    assert "9249856559" not in bootstrap_section
    assert "/actions/artifacts/9249856559/zip" not in bootstrap_section
    assert HISTORICAL_ARTIFACT_SHA256 not in bootstrap_section
    assert str(HISTORICAL_ARTIFACT_SIZE) not in bootstrap_section
    assert HISTORICAL_PR119_EXECUTOR not in bootstrap_section
    assert "replay receipt" not in bootstrap_section.lower()
    assert "gh release create" not in bootstrap_section
    assert "gh release upload" not in bootstrap_section
    assert "--clobber" not in bootstrap_section
    assert "--execute-live-network" not in bootstrap_section
    assert "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py" not in bootstrap_section
    assert bootstrap_section.index("restore_fotmob_pr119_bootstrap_release.py") < len(
        bootstrap_section
    )

    helper = (ROOT / "scripts/restore_fotmob_pr119_bootstrap_release.py").read_text(
        encoding="utf-8"
    )
    for value in (
        "RELEASE_ID = 373205103",
        'RELEASE_TAG = "athena-fresh-holdout-bootstrap-v1"',
        "ASSET_ID = 521090702",
        'ASSET_NAME = "pr119-materialized.ndjson"',
        "ASSET_SIZE = 10_545_099",
        bootstrap.PAYLOAD_SHA256,
        "ROW_COUNT = 21_326",
        "Accept: application/octet-stream",
    ):
        assert value in helper
    assert text.count("--execute-live-network") == 1
    assert text.index("--execute-live-network") > collect_start


def test_schedule_continuity_and_no_backfill_contract_remains_unchanged() -> None:
    text = _workflow_text()
    assert "- cron: '7 * * * *'" in text
    assert "- cron: '37 * * * *'" in text
    assert "workflow_dispatch:" in text
    for required_input in (
        "continuity_source_watchdog_run_id:",
        "continuity_target_slot:",
        "continuity_target_cron:",
        "continuity_confirmation:",
    ):
        assert required_input in text
        assert text.index(required_input) < text.index("concurrency:")
    assert '"PROSPECTIVE_ONLY_NO_BACKFILL_V1"' in text
    assert "continuity.validate_watchdog_source_run(" in text
    assert "continuity.validate_watchdog_source_jobs(" in text
    assert "continuity.validate_continuity_dispatch(" in text
    assert "checkout_head != current_main" in text
    assert "refusing to fabricate a nominal slot or backfill evidence" in text
    assert "CONTINUITY_ALREADY_ATTEMPTED_NO_ACQUISITION" in text
    assert "SCHEDULE_ALREADY_ATTEMPTED_NO_ACQUISITION" in text
    assert "AMBIGUOUS_NO_ACQUISITION" in text
    assert "backfill_authorized: true" not in text
    assert "backfill_authorized = True" not in text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", bootstrap.RELEASE_ID + 1),
        ("tag_name", "another-release"),
        ("name", "another-name"),
        ("draft", True),
        ("prerelease", True),
        ("draft", 0),
    ],
)
def test_wrong_release_identity_fails_closed(field: str, value) -> None:
    release = _release(**{field: value})
    with pytest.raises(bootstrap.ReleaseMetadataError):
        bootstrap.validate_release_metadata(bootstrap.REPOSITORY, release)


def test_wrong_repository_and_missing_release_metadata_fail_closed() -> None:
    with pytest.raises(bootstrap.ReleaseMetadataError):
        bootstrap.validate_release_metadata("other/repository", _release())
    with pytest.raises(bootstrap.ReleaseMetadataError):
        bootstrap.validate_release_metadata(bootstrap.REPOSITORY, None)


@pytest.mark.parametrize(
    "asset",
    [
        _asset(id=bootstrap.ASSET_ID + 1),
        _asset(name="different.ndjson"),
        _asset(size=bootstrap.ASSET_SIZE - 1),
        _asset(digest="sha256:" + "0" * 64),
        _asset(state="starter"),
    ],
)
def test_wrong_asset_identity_fails_closed(asset: dict) -> None:
    with pytest.raises(bootstrap.AssetMetadataError):
        bootstrap.validate_asset_metadata([asset])


def test_missing_duplicate_or_malformed_matching_asset_fails_closed() -> None:
    with pytest.raises(bootstrap.AssetMetadataError, match="found 0"):
        bootstrap.validate_asset_metadata([])
    with pytest.raises(bootstrap.AssetMetadataError, match="found 2"):
        bootstrap.validate_asset_metadata(
            [_asset(), _asset(id=bootstrap.ASSET_ID + 1)]
        )
    with pytest.raises(bootstrap.AssetMetadataError):
        bootstrap.validate_asset_metadata([None, _asset(id=True)])


@pytest.mark.parametrize("digest", [None, "missing"])
def test_github_omitted_asset_digest_is_allowed_but_download_hash_is_still_required(
    digest,
) -> None:
    asset = _asset()
    if digest == "missing":
        asset.pop("digest")
    else:
        asset["digest"] = None
    assert bootstrap.validate_asset_metadata([asset]) == bootstrap.ASSET_ID


def test_release_and_asset_are_authenticated_before_exact_asset_download_and_write(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, int]] = []
    target = tmp_path / bootstrap.ASSET_NAME
    raw = bootstrap.restore_pr119_bootstrap(
        repository=bootstrap.REPOSITORY,
        get_release_metadata=lambda release_id: calls.append(("release", release_id))
        or json.loads(RELEASE_METADATA_FIXTURE.read_bytes()),
        download_asset=lambda asset_id: calls.append(("asset", asset_id)) or _payload(),
        target=target,
    )
    assert calls == [("release", bootstrap.RELEASE_ID), ("asset", bootstrap.ASSET_ID)]
    assert raw == _payload()
    assert target.is_file() and not target.is_symlink()
    assert target.read_bytes() == raw


def test_bad_release_or_asset_metadata_never_downloads(tmp_path: Path) -> None:
    calls: list[int] = []
    with pytest.raises(bootstrap.ReleaseMetadataError):
        bootstrap.restore_pr119_bootstrap(
            repository=bootstrap.REPOSITORY,
            get_release_metadata=lambda _release_id: _release(id=1),
            download_asset=lambda asset_id: calls.append(asset_id) or b"unused",
            target=tmp_path / bootstrap.ASSET_NAME,
        )
    with pytest.raises(bootstrap.AssetMetadataError):
        bootstrap.restore_pr119_bootstrap(
            repository=bootstrap.REPOSITORY,
            get_release_metadata=lambda _release_id: _release(assets=[]),
            download_asset=lambda asset_id: calls.append(asset_id) or b"unused",
            target=tmp_path / bootstrap.ASSET_NAME,
        )
    assert calls == []
    assert not (tmp_path / bootstrap.ASSET_NAME).exists()


@pytest.mark.parametrize(
    "raw",
    [pytest.param(b"short", id="wrong-size"),
     pytest.param(b"x" * bootstrap.ASSET_SIZE, id="same-size-wrong-sha")],
)
def test_downloaded_wrong_size_or_sha_fails_closed(raw: bytes) -> None:
    with pytest.raises(bootstrap.ProjectionPayloadError):
        bootstrap.validate_projection_payload(raw)


def test_wrong_row_count_and_malformed_projection_fail_closed(monkeypatch) -> None:
    raw = _payload()
    monkeypatch.setattr(
        fresh, "parse_reviewed_legacy_bootstrap_projection", lambda _raw: (object(),)
    )
    with pytest.raises(bootstrap.ProjectionPayloadError, match="row count"):
        bootstrap.validate_projection_payload(raw)

    def malformed(_raw):
        raise ValueError("malformed test projection")

    monkeypatch.setattr(fresh, "parse_reviewed_legacy_bootstrap_projection", malformed)
    with pytest.raises(bootstrap.ProjectionPayloadError, match="reviewed projection parser"):
        bootstrap.validate_projection_payload(raw)


def test_symlink_and_non_regular_bootstrap_targets_are_rejected(tmp_path: Path) -> None:
    raw = _payload()
    directory = tmp_path / "directory-target"
    directory.mkdir()
    with pytest.raises(bootstrap.BootstrapTargetError, match="regular file"):
        bootstrap._write_exact_target(directory, raw)

    referent = tmp_path / "referent.ndjson"
    referent.write_bytes(b"untouched")
    link = tmp_path / bootstrap.ASSET_NAME
    try:
        os.symlink(referent, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    with pytest.raises(bootstrap.BootstrapTargetError, match="symlink"):
        bootstrap._write_exact_target(link, raw)
    assert referent.read_bytes() == b"untouched"
