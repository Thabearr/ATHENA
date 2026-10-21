"""Small reviewed entry point for ATHENA's allowlisted worker operations."""
from __future__ import annotations

import argparse
from datetime import date
from enum import Enum
import os
from pathlib import Path
import sys
from typing import Any

from domain.run_contracts import canonical_json_bytes
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
    ReleaseIdentityError,
    ReleaseManifestError,
    verify_development_checkout,
    verify_installed_release,
)
from runtime.resources import ResourceResolver, default_writable_roots
from runtime.worker_launcher import (
    WORKER_COMMAND_FILENAME,
    WORKER_OFFLINE_PROBE_FILENAME,
    WORKER_PROVENANCE_FILENAME,
    WorkerCommand,
    WorkerLaunchError,
    _regular_file,
    _publish_or_match,
    _is_link_or_junction,
    _is_contained,
    _resolved_directory,
    build_offline_probe_documents,
    read_bound_request,
)


class WorkerEntryError(ValueError):
    """The worker could not authenticate its command and source identity."""


class WorkerInvocationIntent(Enum):
    """Reviewed invocation seams; product authority still requires DB proof."""

    PRODUCT_ADMITTED = "PRODUCT_ADMITTED"
    PORT_02C_INSTALLED_QUALIFICATION = "PORT_02C_INSTALLED_QUALIFICATION"


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(os.fspath(left))) == os.path.normcase(
        os.path.normpath(os.fspath(right))
    )


def _port_02c_probe_request(request: Any) -> bool:
    return (
        request.dates == (date(2026, 9, 23),)
        and request.target_legs == 2
        and request.target_total_odds is None
        and request.bookie == "sportybet"
        and request.mode == "offline_identity_probe"
        and request.authority_profile == "SHADOW"
        and request.create_share_code is False
        and request.place_wager is False
    )


def _invocation_intent(
    command: WorkerCommand,
    request: Any,
    identity: DevelopmentCheckoutIdentity | InstalledReleaseIdentity,
) -> WorkerInvocationIntent:
    """Derive the standalone qualifier seam from authenticated installed context."""
    if command.run_directory.parent.name != "port02c-runs":
        return WorkerInvocationIntent.PRODUCT_ADMITTED
    if (
        type(identity) is not InstalledReleaseIdentity
        or command.operation != "OFFLINE_IDENTITY_PROBE"
        or command.mode != "offline_identity_probe"
        or command.envelope_artifact_id is not None
        or not _port_02c_probe_request(request)
    ):
        raise WorkerEntryError("standalone PORT-02C invocation is outside its fixed probe contract")
    try:
        roots = default_writable_roots(installed_release_root=identity.release_root)
        expected_root = _resolved_directory(roots.data_root, "PORT-02C data root")
        expected_run = expected_root / "port02c-runs" / command.request_artifact_id
        actual_run = _resolved_directory(command.run_directory, "PORT-02C run directory")
    except (OSError, WorkerLaunchError, ValueError) as exc:
        raise WorkerEntryError("standalone PORT-02C output root is invalid") from exc
    if not _same_path(actual_run, expected_run) or not _is_contained(expected_root, actual_run):
        raise WorkerEntryError("standalone PORT-02C output is outside its fixed installed root")
    return WorkerInvocationIntent.PORT_02C_INSTALLED_QUALIFICATION


def _read_command_file(path_value: Any) -> tuple[WorkerCommand, Path]:
    if not isinstance(path_value, Path) or not path_value.is_absolute():
        raise WorkerEntryError("command file must be an explicit absolute path")
    try:
        path = _regular_file(path_value, label="worker command file")
        raw = path.read_bytes()
        command = WorkerCommand.from_json_bytes(raw)
    except (OSError, WorkerLaunchError) as exc:
        raise WorkerEntryError("worker command file is invalid") from exc
    expected = command.run_directory / WORKER_COMMAND_FILENAME
    if not _same_path(path, expected):
        raise WorkerEntryError("worker command file must be fixed inside its exact run directory")
    return command, path


def _verify_source_identity(
    command: WorkerCommand,
    *,
    development_root: Path | None,
    release_root: Path | None,
    trusted_manifest_sha256: str | None,
) -> DevelopmentCheckoutIdentity | InstalledReleaseIdentity:
    if development_root is not None:
        if release_root is not None or trusted_manifest_sha256 is not None:
            raise WorkerEntryError("development and installed source modes cannot be combined")
        try:
            identity = verify_development_checkout(development_root)
            ResourceResolver.for_development(identity)
        except (ReleaseIdentityError, ValueError) as exc:
            raise WorkerEntryError("DevelopmentCheckout identity could not be verified") from exc
        if (
            command.release_identity_kind != "DEVELOPMENT_CHECKOUT"
            or command.release_identity_id != identity.head_commit_sha
        ):
            raise WorkerEntryError("worker command does not bind the exact DevelopmentCheckout HEAD")
        return identity

    if release_root is None or trusted_manifest_sha256 is None:
        raise WorkerEntryError("installed mode requires release root and trusted manifest SHA-256")
    try:
        identity = verify_installed_release(release_root, trusted_manifest_sha256)
        ResourceResolver.for_installed(identity)
    except (ReleaseIdentityError, ReleaseManifestError, ValueError) as exc:
        raise WorkerEntryError("InstalledRelease identity could not be verified") from exc
    if (
        command.release_identity_kind != "INSTALLED_RELEASE"
        or command.release_identity_id != identity.manifest_sha256
    ):
        raise WorkerEntryError("worker command does not bind the exact InstalledRelease manifest")
    return identity


def _run_offline_probe(command: WorkerCommand, identity: Any) -> int:
    semantic, provenance = build_offline_probe_documents(command)
    # Independently ensure the source-mode identity selected at entry is the
    # same one captured by the command before publishing local evidence.
    if (
        identity.identity_kind != command.release_identity_kind
        or (
            identity.head_commit_sha
            if type(identity) is DevelopmentCheckoutIdentity
            else identity.manifest_sha256
        )
        != command.release_identity_id
    ):
        raise WorkerEntryError("offline probe source identity changed after admission")
    _publish_or_match(
        command.run_directory / WORKER_OFFLINE_PROBE_FILENAME,
        canonical_json_bytes(semantic),
    )
    _publish_or_match(
        command.run_directory / WORKER_PROVENANCE_FILENAME,
        canonical_json_bytes(provenance),
    )
    return 0


def _current_shadow_arguments(command: WorkerCommand, request: Any) -> list[str]:
    """Project the already-bound request into the fixed supervisor argv.

    This helper is deliberately pure: it performs no parsing, process start,
    provider access, or evidence write.  Product execution still goes through
    ``_run_current_shadow`` and its authenticated owner gate below.
    """
    if request.create_share_code is True:
        raise WorkerEntryError("product delivery requires reviewed durable transport context")
    if command.operation != "CURRENT_SHADOW_REQUEST":
        raise WorkerEntryError("Current Shadow dispatcher received another operation")
    if (
        request.authority_profile != "SHADOW"
        or request.mode != "research_shadow"
        or request.bookie != "sportybet"
        or request.place_wager is not False
        or type(request.create_share_code) is not bool
    ):
        raise WorkerEntryError("Current Shadow operation requires an exact no-wager RunRequest")
    dates = ",".join(day.strftime("%Y%m%d") for day in request.dates)
    output_directory = command.run_directory / "current-shadow"
    if output_directory.exists() or output_directory.is_symlink():
        if _is_link_or_junction(output_directory):
            raise WorkerEntryError("Current Shadow output directory must not be a symlink or junction")
        try:
            resolved_output = _resolved_directory(output_directory, "Current Shadow output directory")
        except WorkerLaunchError as exc:
            raise WorkerEntryError("Current Shadow output directory is not a safe directory") from exc
        if not _is_contained(command.run_directory, resolved_output):
            raise WorkerEntryError("Current Shadow output directory escaped its exact run directory")
    return [
        "--target-size",
        str(request.target_legs),
        "--fixture-scope",
        "today",
        "--fixture-dates",
        dates,
        "--output-dir",
        os.fspath(output_directory),
        "--create-share-code",
        "true" if request.create_share_code else "false",
    ]


def _run_current_shadow(
    command: WorkerCommand, request: Any, *, repository=None, gate=None,
    gate_bytes: bytes | None = None,
) -> int:
    args = _current_shadow_arguments(command, request)
    # This lazy import preserves the offline identity-probe boundary. The
    # existing request supervisor remains the sole owner of its 75-minute
    # timeout and finalization behavior.
    from scripts import execute_current_shadow_request

    if (repository is None or type(gate) is not dict or type(gate_bytes) is not bytes):
        raise WorkerEntryError("Current Shadow supervisor requires the exact product startup owner")
    try:
        return execute_current_shadow_request.run_authenticated_product_worker(
            args,
            repository=repository,
            command=command,
            gate=gate,
            gate_bytes=gate_bytes,
        )
    except Exception as exc:
        raise WorkerEntryError("Current Shadow nested supervisor start was not authorized") from exc


def execute_worker_command(
    *,
    command_file: Path,
    development_root: Path | None = None,
    release_root: Path | None = None,
    trusted_manifest_sha256: str | None = None,
) -> int:
    command, _resolved_command_path = _read_command_file(command_file)
    identity = _verify_source_identity(
        command,
        development_root=development_root,
        release_root=release_root,
        trusted_manifest_sha256=trusted_manifest_sha256,
    )
    resources = (
        ResourceResolver.for_development(identity)
        if type(identity) is DevelopmentCheckoutIdentity
        else ResourceResolver.for_installed(identity)
    )
    try:
        request = read_bound_request(command)
    except WorkerLaunchError as exc:
        raise WorkerEntryError("worker request artifact failed identity validation") from exc
    invocation_intent = _invocation_intent(command, request, identity)
    repository = None
    gate = None
    if invocation_intent is WorkerInvocationIntent.PRODUCT_ADMITTED:
        from runtime.worker_startup_gate import StartupGateError, _data_root_from_path, wait_for_gate
        from database.run_repository import DurableRunRepository

        try:
            gate = wait_for_gate(command, resources=resources)
            repository = DurableRunRepository.for_worker_data_root(
                resources, _data_root_from_path(command.run_directory),
            )
        except (StartupGateError, ValueError, OSError) as exc:
            raise WorkerEntryError("worker process ownership gate failed") from exc
    elif invocation_intent is not WorkerInvocationIntent.PORT_02C_INSTALLED_QUALIFICATION:
        raise WorkerEntryError("worker invocation intent is outside the reviewed contract")
    if command.operation == "OFFLINE_IDENTITY_PROBE":
        if repository is not None and gate is not None:
            try:
                repository.authorize_worker_start(
                    command=command, gate=gate, gate_bytes=canonical_json_bytes(gate),
                    effect=lambda: _run_offline_probe(command, identity),
                )
            except Exception as exc:
                raise WorkerEntryError("worker startup effect was not authorized") from exc
            return 0
        return _run_offline_probe(command, identity)
    if command.operation == "CURRENT_SHADOW_REQUEST":
        if repository is None or gate is None:
            raise WorkerEntryError("Current Shadow requires product admission")
        try:
            repository.authorize_worker_start(
                command=command, gate=gate, gate_bytes=canonical_json_bytes(gate),
            )
        except Exception as exc:
            raise WorkerEntryError("worker startup effect was not authorized") from exc
        return _run_current_shadow(
            command, request, repository=repository, gate=gate,
            gate_bytes=canonical_json_bytes(gate),
        )
    raise WorkerEntryError("worker operation is outside the allowlist")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--command-file", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--development-root", type=Path)
    source.add_argument("--release-root", type=Path)
    parser.add_argument("--trusted-manifest-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return execute_worker_command(
            command_file=args.command_file,
            development_root=args.development_root,
            release_root=args.release_root,
            trusted_manifest_sha256=args.trusted_manifest_sha256,
        )
    except WorkerEntryError as exc:
        print(f"ATHENA worker admission failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["WorkerEntryError", "build_parser", "execute_worker_command", "main"]
