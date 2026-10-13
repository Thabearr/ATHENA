"""Small reviewed entry point for ATHENA's allowlisted worker operations."""
from __future__ import annotations

import argparse
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
from runtime.resources import ResourceResolver
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


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(os.fspath(left))) == os.path.normcase(
        os.path.normpath(os.fspath(right))
    )


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


def _run_current_shadow(command: WorkerCommand, request: Any) -> int:
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
    args = [
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
    # This lazy import preserves the offline identity-probe boundary. The
    # existing request supervisor remains the sole owner of its 75-minute
    # timeout and finalization behavior.
    from scripts import execute_current_shadow_request

    worker_env = execute_current_shadow_request.WORKER_ENV
    inherited = os.environ.pop(worker_env, None)
    try:
        return execute_current_shadow_request.main(args)
    finally:
        if inherited is not None:
            os.environ[worker_env] = inherited


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
    try:
        request = read_bound_request(command)
    except WorkerLaunchError as exc:
        raise WorkerEntryError("worker request artifact failed identity validation") from exc
    if command.operation == "OFFLINE_IDENTITY_PROBE":
        return _run_offline_probe(command, identity)
    if command.operation == "CURRENT_SHADOW_REQUEST":
        return _run_current_shadow(command, request)
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
