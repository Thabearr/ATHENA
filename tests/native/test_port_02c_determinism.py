"""PORT-02C installed-mode determinism tests (offline, dev-only logic proof).

The worker executable here is an interpreter wrapper, not a frozen binary:
this proves installed-mode LOGIC (identity binding, probe documents,
canonical bindings, variant equality). Native frozen proof runs in
port-02c-native-runtime.yml on Windows + Ubuntu.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from scripts import build_dev_bundle
from scripts import qualify_port_02_native_runtime as qualifier

ROOT = Path(__file__).resolve().parents[2]


def _stage_bundle_with_wrapper_worker(tmp_path: Path) -> tuple[Path, dict, Path, str]:
    bundle = tmp_path / "bundle"
    metadata = build_dev_bundle.build(repo=ROOT, platform_tag="linux", output=bundle, freeze=False)
    wrapper = bundle / "bin" / "athena-worker"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from runtime.worker_entry import main\n"
        "raise SystemExit(main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o755)
    return bundle, metadata, wrapper, hashlib.sha256(wrapper.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name == "nt", reason="interpreter-wrapper worker probe is POSIX-only")
def test_variant_equality_and_canonical_output(tmp_path: Path, monkeypatch):
    bundle, metadata, wrapper, wrapper_sha = _stage_bundle_with_wrapper_worker(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    from scripts.port_02c_git_free_launch import sanitized_git_free_path

    monkeypatch.setenv("PATH", sanitized_git_free_path(os.environ.get("PATH", "")))

    digests: dict[str, str] = {}
    for variant in ("standard", "reverse-import", "caches-disabled"):
        out = tmp_path / f"out-{variant}"
        doc = qualifier.qualify(
            release_root=bundle,
            trusted_manifest_sha256=metadata["trusted_manifest_sha256"],
            worker_executable=wrapper,
            worker_sha256=wrapper_sha,
            output_dir=out,
            variant=variant,
        )
        assert doc["wager"] is False
        assert doc["provider_calls"] == 0
        assert doc["delivery_calls"] == 0
        assert doc["network_attempts"] == 0
        assert doc["git_calls"] == 0
        assert doc["worker_returncode"] == 0
        assert doc["replay_scope"] == qualifier.REPLAY_SCOPE
        result_path = out / f"port02c-qualification-{variant}.json"
        raw = result_path.read_bytes()
        assert raw == (
            json.dumps(
                json.loads(raw.decode("utf-8")),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        digests[variant] = doc["semantic_replay_sha256"]

    assert digests["standard"] == digests["reverse-import"] == digests["caches-disabled"]
