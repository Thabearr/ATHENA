from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import current_shadow_history_github_persistent_cache as cache


ACTIONS_ENDPOINT = "/repos/Thabearr/ATHENA/actions/artifacts/123/zip"
RELEASE_ENDPOINT = "/repos/Thabearr/ATHENA/releases/assets/456"
MUTABLE_ENDPOINT = "/repos/Thabearr/ATHENA/releases/tags/test"


def _latest(download):
    projection = SimpleNamespace(_gh_download_compatible=download)
    # The in-process prefetch layer only needs these surfaces at install/restore
    # for this direct persistent-cache test; no universe prefetch is executed.
    latest = SimpleNamespace(
        pr175_projection=projection,
        lineage_audit=SimpleNamespace(_gh_json=lambda endpoint: {"endpoint": endpoint}),
        recovery_projection=SimpleNamespace(
            _prefetch_workflow_run_universe=lambda reader: SimpleNamespace(runs=())
        ),
    )
    return latest


def test_immutable_binary_payload_survives_a_new_install(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cache.CACHE_ENV, str(tmp_path / "history-cache"))
    calls: list[str] = []

    def live(endpoint: str) -> bytes:
        calls.append(endpoint)
        return ("live:" + endpoint).encode()

    first = _latest(live)
    hooks = cache.install(first)
    try:
        expected = first.pr175_projection._gh_download_compatible(ACTIONS_ENDPOINT)
    finally:
        cache.restore(first, hooks)
    assert calls == [ACTIONS_ENDPOINT]

    def must_not_run(endpoint: str) -> bytes:
        raise AssertionError(f"unexpected live read: {endpoint}")

    second = _latest(must_not_run)
    hooks = cache.install(second)
    try:
        assert second.pr175_projection._gh_download_compatible(ACTIONS_ENDPOINT) == expected
    finally:
        cache.restore(second, hooks)


def test_release_asset_is_cached_but_mutable_release_json_is_not(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cache.CACHE_ENV, str(tmp_path / "history-cache"))
    root = cache._cache_root()
    cache._persist(root, RELEASE_ENDPOINT, b"release-bytes")
    assert cache._load(root, RELEASE_ENDPOINT) == b"release-bytes"
    cache._persist(root, MUTABLE_ENDPOINT, b"must-not-persist")
    assert cache._load(root, MUTABLE_ENDPOINT) is None


def test_corrupt_cache_entry_falls_back_to_live_transport(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cache.CACHE_ENV, str(tmp_path / "history-cache"))
    root = cache._cache_root()
    cache._persist(root, ACTIONS_ENDPOINT, b"good")
    payload_path, _metadata_path = cache._paths(root, ACTIONS_ENDPOINT)
    payload_path.write_bytes(b"corrupt")

    calls: list[str] = []

    def live(endpoint: str) -> bytes:
        calls.append(endpoint)
        return b"fresh"

    latest = _latest(live)
    hooks = cache.install(latest)
    try:
        assert latest.pr175_projection._gh_download_compatible(ACTIONS_ENDPOINT) == b"fresh"
    finally:
        cache.restore(latest, hooks)
    assert calls == [ACTIONS_ENDPOINT]
    assert cache._load(root, ACTIONS_ENDPOINT) == b"fresh"


def test_cache_never_claims_non_binary_or_cross_repo_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cache.CACHE_ENV, str(tmp_path / "history-cache"))
    root = cache._cache_root()
    for endpoint in (
        MUTABLE_ENDPOINT,
        "/repos/Other/Repo/actions/artifacts/123/zip",
        "/repos/Thabearr/ATHENA/actions/runs/123/artifacts",
    ):
        cache._persist(root, endpoint, b"value")
        assert cache._load(root, endpoint) is None


def test_persisted_prefix_never_redownloads_when_only_one_immutable_tail_appears(tmp_path, monkeypatch) -> None:
    """Transport cost becomes O(new immutable binaries), never O(prefix + tail)."""
    monkeypatch.setenv(cache.CACHE_ENV, str(tmp_path / "history-cache"))
    prefix = [
        f"/repos/Thabearr/ATHENA/actions/artifacts/{number}/zip"
        for number in range(1000, 1100)
    ]
    tail = "/repos/Thabearr/ATHENA/actions/artifacts/1100/zip"
    first_calls: list[str] = []

    def first_live(endpoint: str) -> bytes:
        first_calls.append(endpoint)
        return endpoint.encode("ascii")

    first = _latest(first_live)
    hooks = cache.install(first)
    try:
        for endpoint in prefix:
            assert first.pr175_projection._gh_download_compatible(endpoint) == endpoint.encode("ascii")
    finally:
        cache.restore(first, hooks)
    assert first_calls == prefix

    second_calls: list[str] = []

    def second_live(endpoint: str) -> bytes:
        second_calls.append(endpoint)
        return endpoint.encode("ascii")

    second = _latest(second_live)
    hooks = cache.install(second)
    try:
        for endpoint in prefix:
            assert second.pr175_projection._gh_download_compatible(endpoint) == endpoint.encode("ascii")
        assert second.pr175_projection._gh_download_compatible(tail) == tail.encode("ascii")
        assert hooks.stats.to_dict() == {
            "cache_hits": len(prefix),
            "cache_misses": 1,
            "cache_hit_bytes": sum(len(endpoint) for endpoint in prefix),
            "cache_miss_bytes": len(tail),
        }
    finally:
        cache.restore(second, hooks)
    assert second_calls == [tail]


def test_current_shadow_and_prime_workflows_restore_and_save_only_transport_cache() -> None:
    for workflow_name in (
        ".github/workflows/current-shadow-all-market.yml",
        ".github/workflows/current-shadow-history-cache-prime.yml",
    ):
        workflow = Path(workflow_name).read_text(encoding="utf-8")
        assert "actions/cache/restore@v4" in workflow
        assert "actions/cache/save@v4" in workflow
        assert cache.DEFAULT_CACHE_DIR.as_posix() in workflow
        assert "athena-current-shadow-history-binary-v1-" in workflow
        assert "permissions:\n  contents: read\n  actions: write\n" in workflow
        assert "github.event.comment.user.login == github.repository_owner" in workflow
        assert "wager" not in workflow.lower()
