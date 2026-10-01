"""PORT-02C qualifier safety tests (offline, dev-only installed-mode logic)."""
from __future__ import annotations

import os
import socket
import urllib.request
from pathlib import Path

import pytest

from scripts import qualify_port_02_native_runtime as qualifier

ROOT = Path(__file__).resolve().parents[2]


def test_network_sentinel_denies_and_counts():
    sentinel = qualifier._NetworkSentinel()
    sentinel.install()
    try:
        with pytest.raises(RuntimeError):
            socket.socket().connect(("127.0.0.1", 9))
        with pytest.raises(RuntimeError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        with pytest.raises(RuntimeError):
            urllib.request.urlopen("http://127.0.0.1:9/")
        assert sentinel.attempts == 3
    finally:
        sentinel.restore()
    sentinel_after = qualifier._NetworkSentinel()
    assert sentinel_after.attempts == 0


def test_qualifier_rejects_unsafe_arguments(tmp_path: Path):
    with pytest.raises(qualifier.QualificationError):
        qualifier._absolute_dir("relative/path", "release-root")
    with pytest.raises(qualifier.QualificationError):
        qualifier._absolute_dir("/tmp/../etc", "release-root")
    with pytest.raises(qualifier.QualificationError):
        qualifier._sha256_text("not-a-hash", "trusted-manifest-sha256")
    with pytest.raises(qualifier.QualificationError):
        qualifier.qualify(
            release_root=tmp_path,
            trusted_manifest_sha256="a" * 64,
            worker_executable=tmp_path,
            worker_sha256="b" * 64,
            output_dir=tmp_path / "out",
            variant="arbitrary-module",
        )


def test_qualifier_rejects_output_inside_install_tree(tmp_path: Path):
    release_root = tmp_path / "release"
    release_root.mkdir()
    with pytest.raises(qualifier.QualificationError):
        qualifier.qualify(
            release_root=release_root,
            trusted_manifest_sha256="a" * 64,
            worker_executable=release_root,
            worker_sha256="b" * 64,
            output_dir=release_root / "out",
            variant="standard",
        )


def test_shell_smoke_switch_parses_without_side_effects():
    import run_desktop

    assert run_desktop.parse_args([]).port02c_smoke is False
    assert run_desktop.parse_args(["--port02c-smoke"]).port02c_smoke is True


def test_qualifier_fails_closed_with_non_worker_executable(tmp_path: Path, monkeypatch):
    from scripts import build_dev_bundle

    bundle = tmp_path / "bundle"
    metadata = build_dev_bundle.build(repo=ROOT, platform_tag="linux", output=bundle, freeze=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    fake_worker = bundle / "bin" / "athena-worker"
    fake_worker.parent.mkdir(parents=True, exist_ok=True)
    fake_worker.write_bytes(b"#!/bin/sh\nexit 3\n")
    os.chmod(fake_worker, 0o755)
    import hashlib

    with pytest.raises(qualifier.QualificationError):
        qualifier.qualify(
            release_root=bundle,
            trusted_manifest_sha256=metadata["trusted_manifest_sha256"],
            worker_executable=fake_worker,
            worker_sha256=hashlib.sha256(fake_worker.read_bytes()).hexdigest(),
            output_dir=tmp_path / "out",
            variant="standard",
        )
