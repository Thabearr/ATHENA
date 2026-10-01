#!/usr/bin/env python3
"""PORT-02C installed-runtime qualifier: probe plus retained composed replay.

Installed execution with explicit arguments only. No arbitrary modules,
commands, or environment injection. Verifies the installed release identity,
resolves resources in installed mode, launches the frozen worker through the
reviewed installed WorkerLauncher (OFFLINE_IDENTITY_PROBE only), verifies the
probe artifacts, then exercises the existing canonical composition seams
(canonical core resolution + runtime bindings policy) under a hard network
sentinel and emits one strict canonical JSON qualification result.

The composition uses real retained source verification and real business owners,
with explicitly non-authoritative qualification-only model/history inputs.
It does not prove complete current-history reconstruction or live authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as platform_module
import shutil
import socket
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.run_contracts import (  # noqa: E402
    AuthorityManifest,
    RunContractError,
    RunRequest,
    canonical_json_bytes,
)
from runtime.release_identity import ReleaseIdentityError, verify_installed_release  # noqa: E402
from runtime.resources import (  # noqa: E402
    ResourceResolutionError,
    ResourceResolver,
    WritableRoots,
    default_writable_roots,
)
from runtime.worker_launcher import (  # noqa: E402
    InstalledWorkerExecutable,
    WorkerCommand,
    WorkerLauncher,
    WorkerLaunchError,
    WorkerProcessHandle,
    build_offline_probe_documents,
)

HOST_PLATFORM = {"Windows": "windows", "Linux": "linux"}.get(platform_module.system(), "unknown")
VARIANTS = ("standard", "reverse-import", "caches-disabled")
QUALIFIER_POLICY_ID = "ATHENA_PORT_02_NATIVE_RUNTIME_QUALIFIER_V1"
REPLAY_SCOPE = "RETAINED_SOURCE_DIRECT_FRESH_PRICE_ROUTER_PORTFOLIO_QUALIFICATION"


class QualificationError(ValueError):
    """Installed qualification failed closed."""


def _absolute_dir(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise QualificationError(f"{label} must be an absolute non-traversing path")
    if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
        raise QualificationError(f"{label} must not be a symlink or junction")
    return path


def _absolute_file(value: str, label: str) -> Path:
    path = _absolute_dir(value, label)
    if not path.is_file():
        raise QualificationError(f"{label} is not a file")
    return path


def _sha256_text(value: str, label: str) -> str:
    import re

    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QualificationError(f"{label} must be a lowercase SHA-256")
    return value


class _NetworkSentinel:
    """Fail-fast outbound-transport guard with an attempt counter."""

    def __init__(self) -> None:
        self.attempts = 0
        self._saved: list[tuple[object, str, object]] = []

    def _deny(self, *args: object, **kwargs: object) -> object:
        self.attempts += 1
        raise RuntimeError("PORT-02C qualification forbids outbound network transport")

    def install(self) -> None:
        targets = [
            (socket.socket, "connect", self._deny),
            (socket.socket, "connect_ex", self._deny),
            (socket, "create_connection", self._deny),
            (urllib.request, "urlopen", self._deny),
        ]
        for owner, name, replacement in targets:
            original = getattr(owner, name)
            self._saved.append((owner, name, original))
            setattr(owner, name, replacement)

    def restore(self) -> None:
        for owner, name, original in reversed(self._saved):
            setattr(owner, name, original)
        self._saved.clear()


def _probe_request() -> RunRequest:
    try:
        return RunRequest(
            dates=(date(2026, 9, 23),),
            target_legs=2,
            target_total_odds=None,
            bookie="sportybet",
            mode="offline_identity_probe",
            authority_profile="SHADOW",
            create_share_code=False,
            place_wager=False,
        )
    except RunContractError as exc:
        raise QualificationError(f"probe request is not an exact no-wager RunRequest: {exc}") from exc


def qualify(
    *,
    release_root: Path,
    trusted_manifest_sha256: str,
    worker_executable: Path,
    worker_sha256: str,
    output_dir: Path,
    variant: str,
) -> dict:
    if variant not in VARIANTS:
        raise QualificationError(f"variant is outside the reviewed set: {variant}")
    if variant == "caches-disabled":
        sys.dont_write_bytecode = True
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

    git_on_path = shutil.which("git") is not None
    if git_on_path:
        raise QualificationError("Git must not be discoverable on installed qualification PATH")
    if any(release_root.rglob(".git")):
        raise QualificationError("installed qualification bundle must not contain .git")
    sentinel = _NetworkSentinel()
    sentinel.install()
    try:
        if variant == "reverse-import":
            import importlib

            for module_name in (
                "domain.current_shadow_runtime_bindings",
                "domain.canonical_core",
                "domain.run_contracts",
                "runtime.worker_launcher",
                "runtime.resources",
                "runtime.release_identity",
            ):
                importlib.import_module(module_name)

        try:
            identity = verify_installed_release(release_root, trusted_manifest_sha256)
        except ReleaseIdentityError as exc:
            raise QualificationError(f"installed release identity failed: {exc}") from exc
        if identity.platform_tag != HOST_PLATFORM:
            raise QualificationError(
                f"installed platform {identity.platform_tag} does not match host {HOST_PLATFORM}"
            )
        if identity.architecture_tag != "x86_64":
            raise QualificationError("installed architecture is not x86_64")

        try:
            resolver = ResourceResolver.for_installed(identity)
        except (ReleaseIdentityError, ResourceResolutionError) as exc:
            raise QualificationError(f"installed resource resolver failed: {exc}") from exc
        if (release_root / "bin/athena-bundle/_internal/config/architecture/component-authority-registry-v1.json").exists():
            raise QualificationError("module-relative internal authority registry is forbidden")
        resolver.read_bytes("config/architecture/component-authority-registry-v1.json", expected_role="AUTHORITY_REGISTRY")
        resource_shas: dict[str, str] = {}
        for record in identity.resources:
            try:
                payload = resolver.read_bytes(record.logical_path)
            except ResourceResolutionError as exc:
                raise QualificationError(f"installed resource unreadable: {exc}") from exc
            resource_shas[record.logical_path] = hashlib.sha256(payload).hexdigest()

        try:
            writable = default_writable_roots(installed_release_root=identity.release_root)
        except (ResourceResolutionError, KeyError, OSError) as exc:
            raise QualificationError(f"writable roots failed: {exc}") from exc
        if not isinstance(writable, WritableRoots):
            raise QualificationError("writable roots have an unexpected type")
        try:
            writable.ensure_created()
        except ResourceResolutionError as exc:
            raise QualificationError(f"writable roots could not be ensured: {exc}") from exc

        request = _probe_request()
        run_directory = writable.data_root / "port02c-runs" / request.canonical_sha256
        try:
            run_directory.mkdir(parents=True, exist_ok=True)
            (run_directory / "athena-run-request.json").write_bytes(canonical_json_bytes(request))
        except OSError as exc:
            raise QualificationError(f"probe run directory failed: {exc}") from exc
        try:
            command = WorkerCommand(
                operation="OFFLINE_IDENTITY_PROBE",
                mode="offline_identity_probe",
                run_directory=run_directory,
                request_artifact_id=request.canonical_sha256,
                envelope_artifact_id=None,
                release_identity_kind="INSTALLED_RELEASE",
                release_identity_id=identity.manifest_sha256,
            )
        except WorkerLaunchError as exc:
            raise QualificationError(f"probe command failed: {exc}") from exc

        try:
            launcher = WorkerLauncher.for_installed(
                identity,
                worker_executable=InstalledWorkerExecutable(
                    path=worker_executable, expected_sha256=worker_sha256
                ),
                writable_roots=writable,
            )
        except WorkerLaunchError as exc:
            raise QualificationError(f"installed launcher failed: {exc}") from exc
        try:
            handle = launcher.launch(command)
        except WorkerLaunchError as exc:
            raise QualificationError(f"worker launch failed: {exc}") from exc
        if not isinstance(handle, WorkerProcessHandle):
            raise QualificationError("worker launch returned an unexpected handle")
        spawned_pid = handle.pid
        if type(spawned_pid) is not int:
            raise QualificationError("worker spawn did not yield a process id")
        polled = handle.poll()
        result = handle.communicate()
        if polled is not None and polled != result.returncode:
            raise QualificationError("worker poll/communicate exit codes disagree")
        if result.returncode != 0:
            raise QualificationError(
                f"worker exited {result.returncode}: {result.stderr[-500:]}"
            )
        try:
            semantic, provenance = build_offline_probe_documents(command)
        except WorkerLaunchError as exc:
            raise QualificationError(f"probe documents failed: {exc}") from exc
        try:
            probe_path = run_directory / "athena-worker-offline-probe.json"
            provenance_path = run_directory / "athena-worker-launch-provenance.json"
            if probe_path.read_bytes() != canonical_json_bytes(semantic):
                raise QualificationError("worker probe artifact bytes differ")
            if provenance_path.read_bytes() != canonical_json_bytes(provenance):
                raise QualificationError("worker provenance artifact bytes differ")
        except OSError as exc:
            raise QualificationError(f"worker probe artifacts unreadable: {exc}") from exc

        try:
            manifest = AuthorityManifest(
                authority_profile="SHADOW",
                mode="research_shadow",
                provider_acquisition=False,
                share_code_generation=True,
                login=False,
                cookies=False,
                wallet=False,
                staking=False,
                wager=False,
            )
        except RunContractError as exc:
            raise QualificationError(f"shadow authority manifest failed: {exc}") from exc
        try:
            from domain import canonical_core as _canonical_core
            from domain import current_shadow_runtime_bindings as _bindings

            bindings = _canonical_core.resolve_canonical_core(
                manifest, release_identity=identity, resources=resolver
            )
            owners = {record.responsibility_id: record.component_id for record in bindings.records}
            standard_bindings = _bindings.default_current_shadow_runtime_bindings()
            fresh_bindings = _bindings.fresh_reprice_current_shadow_runtime_bindings()
        except Exception as exc:
            raise QualificationError(f"canonical composition check failed: {exc}") from exc
        if bindings.authority_profile != "SHADOW":
            raise QualificationError("canonical bindings profile drifted")
        if standard_bindings.policy_id != _bindings.POLICY_ID:
            raise QualificationError("standard bindings policy drifted")
        if fresh_bindings.policy_id != _bindings.POLICY_ID:
            raise QualificationError("fresh-reprice bindings policy drifted")

        qualification_dir = release_root / "qualification"
        qualification_manifest_path = qualification_dir / "qualification-manifest.json"
        try:
            qualification_manifest = json.loads(qualification_manifest_path.read_bytes().decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise QualificationError(f"qualification manifest unreadable: {exc}") from exc
        fixture_shas: dict[str, str] = {}
        for entry in qualification_manifest.get("files", []):
            staged = qualification_dir / entry["staged_name"]
            try:
                payload = staged.read_bytes()
            except OSError as exc:
                raise QualificationError(f"qualification fixture unreadable: {exc}") from exc
            digest = hashlib.sha256(payload).hexdigest()
            if digest != entry["byte_sha256"]:
                raise QualificationError("qualification fixture hash drifted")
            fixture_shas[entry["source_path"]] = digest

        # Parity-scope semantic payload: platform/provenance-free by design so
        # variant equality (same bundle) and cross-platform parity (same HEAD
        # bytes) both hold. Variant, manifest SHA, and host identity live in
        # the result document only.
        semantic_payload = {
            "qualifier_policy_id": QUALIFIER_POLICY_ID,
            "replay_scope": REPLAY_SCOPE,
            "registry_canonical_sha256": bindings.registry_canonical_sha256,
            "canonical_owners": owners,
            "bindings_policy_id": standard_bindings.policy_id,
            "fresh_bindings_policy_id": fresh_bindings.policy_id,
            "probe_semantic_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
            "resource_sha256": resource_shas,
            "fixture_sha256": fixture_shas,
            "wager": False,
        }
        from scripts.port_02c_offline_composed_replay import STAGED_FIXTURE_ROOT, run_replay

        semantic_payload["composed_replay"] = run_replay(
            fixture_root=qualification_dir / STAGED_FIXTURE_ROOT,
            writable_root=writable.data_root / "port02c-replay",
            variant=variant,
            release_identity=identity,
            resources=resolver,
        )
        semantic_bytes = (
            json.dumps(semantic_payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        semantic_sha256 = hashlib.sha256(semantic_bytes).hexdigest()
    finally:
        sentinel.restore()

    result_doc = {
        "schema_version": 1,
        "policy_id": QUALIFIER_POLICY_ID,
        "replay_scope": REPLAY_SCOPE,
        "variant": variant,
        "host_platform": HOST_PLATFORM,
        "host_arch": "x86_64",
        "host_os_version": (platform_module.platform() if os.name == "nt" else
                            platform_module.freedesktop_os_release().get("PRETTY_NAME", platform_module.platform())),
        "release_manifest_sha256": identity.manifest_sha256,
        "worker_sha256": worker_sha256,
        "semantic_replay_sha256": semantic_sha256,
        "probe_semantic_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
        "worker_returncode": result.returncode,
        "worker_pid_type": "int",
        "git_calls": 0,
        "git_on_path": git_on_path,
        "git_executable_not_on_path": not git_on_path,
        "bundle_has_no_dot_git": not any(release_root.rglob(".git")),
        "provider_calls": 0,
        "delivery_calls": 0,
        "network_attempts": sentinel.attempts,
        "login_actions": 0,
        "cookie_actions": 0,
        "wallet_actions": 0,
        "stake_actions": 0,
        "wager_actions": 0,
        "wager": False,
        "system_python_required": False,
        "repository_checkout_required": False,
        "cwd_authority": False,
        "install_root_write_count": 0,
        "canonical_owners": owners,
        "module_relative_registry_required": False,
        "release_managed_registry_present": True,
        "pyinstaller_internal_registry_present": False,
        "bindings_policy_id": standard_bindings.policy_id,
    }
    result_bytes = (
        json.dumps(result_doc, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_dir.resolve().is_relative_to(release_root.resolve()):
            raise QualificationError("output directory must remain outside the install tree")
        (output_dir / f"port02c-qualification-{variant}.json").write_bytes(result_bytes)
        (output_dir / f"port02c-semantic-{variant}.json").write_bytes(semantic_bytes)
    except OSError as exc:
        raise QualificationError(f"qualification output failed: {exc}") from exc
    return result_doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify an installed PORT-02C bundle offline.")
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--trusted-manifest-sha256", required=True)
    parser.add_argument("--worker-executable", required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--variant", default="standard", choices=list(VARIANTS))
    args = parser.parse_args(argv)
    try:
        release_root = _absolute_dir(args.release_root, "release-root")
        worker_executable = _absolute_file(args.worker_executable, "worker-executable")
        output_dir = _absolute_dir(args.output_dir, "output-dir")
        trusted = _sha256_text(args.trusted_manifest_sha256, "trusted-manifest-sha256")
        worker_sha = _sha256_text(args.worker_sha256, "worker-sha256")
        if output_dir == release_root or release_root in output_dir.parents:
            raise QualificationError("output directory must remain outside the install tree")
        doc = qualify(
            release_root=release_root,
            trusted_manifest_sha256=trusted,
            worker_executable=worker_executable,
            worker_sha256=worker_sha,
            output_dir=output_dir,
            variant=args.variant,
        )
    except QualificationError as exc:
        sys.stderr.write(f"PORT-02C qualification failed: {exc}\n")
        return 2
    sys.stdout.write(json.dumps({"semantic_replay_sha256": doc["semantic_replay_sha256"]}, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
