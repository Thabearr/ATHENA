#!/usr/bin/env python3
"""Build a deterministic PORT-02C native installed-runtime bundle (staging).

Runs only from a verified DevelopmentCheckout. Stages allowlisted resource
bytes from exact tracked HEAD identities, writes the reviewed
`release-manifest.json`, stages qualification-only replay fixtures with their
own strict qualification manifest, and optionally invokes PyInstaller
(`--freeze`) to produce native onedir executables.

Build output is disposable and must not be committed. No secrets, no provider
evidence, no network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform as platform_module
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.port_02c_build_config import (  # noqa: E402
    ARCHITECTURE_TAG,
    BANNED_FROZEN_MODULES,
    PLATFORM_TAGS,
    PYINSTALLER_REVIEWED_DATA_RESOURCES,
    QUALIFICATION_FIXTURE_PREFIXES,
    QUALIFY_EXE,
    SHELL_EXE,
    SLICE_CLOSED_WORLD_ROOTS,
    SLICE_RESOURCES,
    WORKER_EXE,
)
from runtime.release_identity import (  # noqa: E402
    MANIFEST_POLICY_ID,
    MANIFEST_SCHEMA_VERSION,
    ReleaseIdentityError,
    canonical_release_manifest_bytes,
    verify_development_checkout,
)

HOST_PLATFORM = {"Windows": "windows", "Linux": "linux"}.get(platform_module.system(), "unknown")


def _fail(message: str) -> "NoReturn":
    from typing import NoReturn  # local import keeps module import-light

    raise SystemExit(f"build_dev_bundle: {message}")


def _run_git(args: list[str], *, cwd: Path) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        _fail(f"git could not be executed: {exc}")
    if completed.returncode != 0:
        _fail(f"git {' '.join(args)} failed: {completed.stderr.decode('utf-8', 'replace')[:300]}")
    return completed.stdout


def _require_clean_tracked(repo: Path, rel: str) -> tuple[bytes, str]:
    """Return (blob_bytes, blob_sha1) for an exact tracked, unmodified HEAD file."""
    if ".." in PurePosixPath(rel).parts or not rel or rel.startswith("/"):
        _fail(f"resource escapes the repository: {rel}")
    worktree_path = repo / PurePosixPath(rel)
    try:
        resolved = worktree_path.resolve(strict=False)
    except OSError as exc:
        _fail(f"resource path could not be resolved: {rel}: {exc}")
    if resolved.is_symlink() or bool(getattr(resolved, "is_junction", lambda: False)()):
        _fail(f"resource is a symlink or junction: {rel}")
    mode_out = _run_git(["ls-files", "-s", "--", rel], cwd=repo).decode("utf-8").strip()
    if not mode_out:
        _fail(f"resource is untracked: {rel}")
    mode = mode_out.split()[0]
    if mode not in ("100644", "100755"):
        _fail(f"resource has unsupported git mode {mode}: {rel}")
    status = _run_git(["status", "--porcelain", "--", rel], cwd=repo).decode("utf-8").strip()
    if status:
        _fail(f"resource is dirty: {rel}: {status[:120]}")
    blob_sha1 = _run_git(["rev-parse", "--verify", f"HEAD:{rel}"], cwd=repo).decode("utf-8").strip()
    blob = _run_git(["show", f"HEAD:{rel}"], cwd=repo)
    return blob, blob_sha1


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def validate_reviewed_data_resources(repo: Path) -> list[dict]:
    """Bind the exact static frozen data closure to clean tracked HEAD bytes."""
    records = []
    for rel, destination, expected_size, expected_sha in PYINSTALLER_REVIEWED_DATA_RESOURCES:
        path = repo / PurePosixPath(rel)
        for parent in (path, *path.parents):
            if parent == repo:
                break
            if parent.is_symlink() or bool(getattr(parent, "is_junction", lambda: False)()):
                _fail(f"reviewed data path is a symlink or junction: {rel}")
        if not path.is_file():
            _fail(f"reviewed data is not a normal file: {rel}")
        blob, blob_sha1 = _require_clean_tracked(repo, rel)
        if path.read_bytes() != blob:
            _fail(f"reviewed data checkout bytes differ from HEAD: {rel}")
        digest = hashlib.sha256(blob).hexdigest()
        if len(blob) != expected_size or digest != expected_sha:
            _fail(f"reviewed data byte size/SHA mismatch: {rel}")
        records.append({"source_path": rel, "destination": destination,
                        "byte_size": len(blob), "byte_sha256": digest,
                        "source_git_blob_sha1": blob_sha1})
    return records


def _discover_qualification_files(repo: Path) -> list[str]:
    discovered: list[str] = []
    for prefix in QUALIFICATION_FIXTURE_PREFIXES:
        if prefix.endswith(".py"):
            _require_clean_tracked(repo, prefix)
            discovered.append(prefix)
            continue
        out = _run_git(["ls-tree", "-r", "--name-only", "-z", f"HEAD:{prefix}"], cwd=repo)
        for raw in out.split(b"\0"):
            if raw:
                discovered.append(f"{prefix}/{raw.decode('utf-8')}")
    if not discovered:
        _fail("no qualification fixture files discovered")
    return sorted(set(discovered))


def build(*, repo: Path, platform_tag: str, output: Path, freeze: bool) -> dict:
    if platform_tag not in PLATFORM_TAGS:
        _fail(f"platform is outside the reviewed vocabulary: {platform_tag}")
    try:
        identity = verify_development_checkout(repo)
    except ReleaseIdentityError as exc:
        _fail(f"development checkout is not verified: {exc}")
    head_sha = identity.head_commit_sha
    reviewed_data = validate_reviewed_data_resources(repo)

    if output.exists() and any(output.iterdir()):
        _fail(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    if freeze and platform_tag != HOST_PLATFORM:
        _fail(f"cross-build is forbidden: host={HOST_PLATFORM} requested={platform_tag}")

    records: list[dict] = []
    for rel, role in sorted(SLICE_RESOURCES, key=lambda item: item[0]):
        blob, blob_sha1 = _require_clean_tracked(repo, rel)
        payload_path = output / PurePosixPath(rel)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(blob)
        records.append(
            {
                "logical_path": rel,
                "payload_path": rel,
                "role": role,
                "byte_sha256": hashlib.sha256(blob).hexdigest(),
                "required": True,
                "source_git_blob_sha1": blob_sha1,
                "canonical_sha256": None,
            }
        )

    from domain import canonical_core as _canonical_core
    from domain import component_authority_registry as _authority

    registry_rel = "config/architecture/component-authority-registry-v1.json"
    try:
        registry = _authority.ComponentAuthorityRegistry.from_json_bytes(
            (output / PurePosixPath(registry_rel)).read_bytes()
        )
    except (_authority.ComponentAuthorityRegistryError, OSError) as exc:
        _fail(f"reviewed authority registry could not be parsed: {exc}")
    for record in records:
        if record["logical_path"] == registry_rel:
            record["canonical_sha256"] = registry.canonical_sha256
    if not any(
        record["logical_path"] == registry_rel and record["canonical_sha256"] for record in records
    ):
        _fail("reviewed authority registry record was not staged")
    for responsibility in _canonical_core.CANONICAL_RESPONSIBILITIES:
        try:
            _component_id, module, _identity_fn = _canonical_core._COMPONENT_SPECS[responsibility]
        except KeyError as exc:
            _fail(f"canonical responsibility has no reviewed component spec: {exc}")
        logical = f"{module.__name__.replace('.', '/')}.py"
        try:
            champion = registry.resolve_champion(
                responsibility,
                _canonical_core.CURRENT_SPORTYBET_PROVIDER,
                profile="SHADOW",
                required_schema_version=_canonical_core.SCHEMA_VERSION,
            )
        except _authority.ComponentAuthorityRegistryError as exc:
            _fail(f"canonical champion could not be resolved: {exc}")
        blob, blob_sha1 = _require_clean_tracked(repo, logical)
        if blob_sha1 != champion.artifact_git_blob_sha:
            _fail(f"canonical source Git identity drifted: {logical}")
        contract = _canonical_core._installed_contract_identity(responsibility)
        if contract != champion.contract_sha256:
            _fail(f"canonical source contract identity drifted: {logical}")
        payload_path = output / PurePosixPath(logical)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(blob)
        records.append(
            {
                "logical_path": logical,
                "payload_path": logical,
                "role": "CANONICAL_COMPONENT_SOURCE",
                "byte_sha256": hashlib.sha256(blob).hexdigest(),
                "required": True,
                "source_git_blob_sha1": blob_sha1,
                "canonical_sha256": contract,
            }
        )
    records.sort(key=lambda item: item["logical_path"])

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "policy_id": MANIFEST_POLICY_ID,
        "release_id": "ATHENA-PORT02C-SLICE",
        "build_id": f"port02c-{head_sha[:12]}-{platform_tag}",
        "platform_tag": platform_tag,
        "architecture_tag": ARCHITECTURE_TAG,
        "closed_world_roots": list(SLICE_CLOSED_WORLD_ROOTS),
        "resources": records,
    }
    manifest_bytes = canonical_release_manifest_bytes(manifest)
    (output / "release-manifest.json").write_bytes(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    qualification_dir = output / "qualification"
    qualification_dir.mkdir(parents=True, exist_ok=True)
    from scripts.port_02c_offline_composed_replay import FIXTURE_PREFIX, STAGED_FIXTURE_ROOT, verify_fixture_manifest

    qualification_records: list[dict] = []
    for rel in _discover_qualification_files(repo):
        blob, blob_sha1 = _require_clean_tracked(repo, rel)
        if not rel.startswith(FIXTURE_PREFIX + "/"):
            _fail(f"qualification member is outside the exact retained corpus: {rel}")
        staged = qualification_dir / STAGED_FIXTURE_ROOT / PurePosixPath(rel[len(FIXTURE_PREFIX) + 1:])
        if staged.exists():
            _fail(f"qualification fixture collision: {rel}")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(blob)
        qualification_records.append(
            {
                "source_path": rel,
                "staged_name": staged.relative_to(qualification_dir).as_posix(),
                "byte_sha256": hashlib.sha256(blob).hexdigest(),
                "source_git_blob_sha1": blob_sha1,
            }
        )
    qualification_manifest = {
        "policy_id": "ATHENA_PORT_02_NATIVE_RUNTIME_QUALIFICATION_MANIFEST_V1",
        "implementation_base_main_sha": head_sha,
        "files": sorted(qualification_records, key=lambda item: item["source_path"]),
    }
    qualification_manifest_bytes = _canonical_json_bytes(qualification_manifest)
    (qualification_dir / "qualification-manifest.json").write_bytes(qualification_manifest_bytes)
    verify_fixture_manifest(qualification_dir / STAGED_FIXTURE_ROOT)

    pyinstaller_version = None
    executables: dict[str, str] = {}
    if freeze:
        try:
            import PyInstaller  # type: ignore[import-not-found]  # noqa: E402
        except ImportError:
            _fail("PyInstaller is not installed; install packaging/build-requirements.txt first")
        pyinstaller_version = getattr(PyInstaller, "__version__", "unknown")
        spec = repo / "packaging" / platform_tag / "athena-port02c.spec"
        if not spec.is_file():
            _fail(f"missing PyInstaller spec: {spec}")
        bin_dir = output / "bin"
        work_dir = output / ".pyinstaller-work"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--distpath",
                str(bin_dir),
                "--workpath",
                str(work_dir),
                str(spec),
            ],
            cwd=str(repo),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode != 0:
            _fail(f"PyInstaller failed: {completed.stdout.decode('utf-8', 'replace')[-2000:]}")
        collected = bin_dir / "athena-bundle"
        for record in reviewed_data:
            installed = collected / "_internal" / record["destination"] / PurePosixPath(record["source_path"]).name
            if not installed.is_file():
                _fail(f"reviewed frozen data is missing: {installed}")
            raw = installed.read_bytes()
            if len(raw) != record["byte_size"] or hashlib.sha256(raw).hexdigest() != record["byte_sha256"]:
                _fail(f"reviewed frozen data identity mismatch: {installed}")
        for key, names in (("shell", SHELL_EXE), ("worker", WORKER_EXE), ("qualifier", QUALIFY_EXE)):
            exe_path = collected / names[platform_tag]
            if not exe_path.is_file():
                _fail(f"expected frozen executable is missing: {exe_path}")
            executables[key] = hashlib.sha256(exe_path.read_bytes()).hexdigest()

    metadata = {
        "builder_policy_id": "ATHENA_PORT_02_NATIVE_RUNTIME_BUILD_V1",
        "implementation_base_main_sha": head_sha,
        "platform_tag": platform_tag,
        "architecture_tag": ARCHITECTURE_TAG,
        "host_platform": HOST_PLATFORM,
        "host_os_version": platform_module.platform(),
        "python_version": platform_module.python_version(),
        "pyinstaller_version": pyinstaller_version,
        "frozen": freeze,
        "trusted_manifest_sha256": manifest_sha256,
        "resource_count": len(records),
        "qualification_file_count": len(qualification_records),
        "qualification_manifest_sha256": hashlib.sha256(qualification_manifest_bytes).hexdigest(),
        "executable_sha256": executables,
        "pyinstaller_reviewed_data_resources": reviewed_data,
        "banned_frozen_modules": list(BANNED_FROZEN_MODULES),
        "entire_repo_bundled": False,
        "entire_venv_bundled": False,
        "first_launch_pip_install": False,
    }
    (output / "build-metadata.json").write_bytes(_canonical_json_bytes(metadata))
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a deterministic PORT-02C bundle.")
    parser.add_argument("--platform", required=True, choices=list(PLATFORM_TAGS))
    parser.add_argument("--output", required=True, help="Empty/disposable output directory.")
    parser.add_argument("--freeze", action="store_true", help="Invoke PyInstaller (native host only).")
    args = parser.parse_args(argv)

    output = Path(args.output)
    if not output.is_absolute():
        _fail("--output must be an absolute path")
    if any(part == ".." for part in output.parts):
        _fail("--output must not traverse")
    metadata = build(repo=ROOT, platform_tag=args.platform, output=output, freeze=args.freeze)
    sys.stdout.write(
        json.dumps(
            {
                "platform": metadata["platform_tag"],
                "frozen": metadata["frozen"],
                "trusted_manifest_sha256": metadata["trusted_manifest_sha256"],
                "resources": metadata["resource_count"],
                "qualification_files": metadata["qualification_file_count"],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
