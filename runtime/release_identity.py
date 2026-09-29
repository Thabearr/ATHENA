"""Reviewed DevelopmentCheckout and hash-pinned installed release identities.

Installed releases use an out-of-band trusted SHA-256 of an exact canonical
manifest.  This is a hash-pinned trust mode, not a digital signature.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
from typing import Any, Sequence
import unicodedata

from runtime.source_identity import (
    SourceIdentityError,
    read_tracked_head_blob,
    validate_repository_relative_path,
)


DEVELOPMENT_IDENTITY_POLICY_ID = "ATHENA_DEVELOPMENT_CHECKOUT_IDENTITY_V1"
INSTALLED_IDENTITY_POLICY_ID = "ATHENA_INSTALLED_RELEASE_IDENTITY_V1"
TRUST_MODE = "TRUSTED_MANIFEST_SHA256_V1"
MANIFEST_FILENAME = "release-manifest.json"
MANIFEST_SCHEMA_VERSION = 1
MANIFEST_POLICY_ID = "ATHENA_INSTALLED_RELEASE_MANIFEST_V1"
RESOURCE_ROLES = (
    "CANONICAL_COMPONENT_SOURCE",
    "AUTHORITY_REGISTRY",
    "CONFIG",
    "MODEL",
    "UI",
    "MIGRATION",
    "TIMEZONE",
    "LOCK",
    "SCHEMA",
)

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$", re.ASCII)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "release_id",
        "build_id",
        "platform_tag",
        "architecture_tag",
        "closed_world_roots",
        "resources",
    }
)
_RESOURCE_FIELDS = frozenset(
    {
        "logical_path",
        "payload_path",
        "role",
        "byte_sha256",
        "required",
        "source_git_blob_sha1",
        "canonical_sha256",
    }
)


class ReleaseIdentityError(ValueError):
    """A development or installed release identity cannot be proven."""


class ReleaseManifestError(ReleaseIdentityError):
    """An installed release manifest or managed payload is invalid."""


@dataclass(frozen=True)
class ResourceRecord:
    logical_path: str
    payload_path: str
    role: str
    byte_sha256: str
    required: bool
    source_git_blob_sha1: str | None
    canonical_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "payload_path": self.payload_path,
            "role": self.role,
            "byte_sha256": self.byte_sha256,
            "required": self.required,
            "source_git_blob_sha1": self.source_git_blob_sha1,
            "canonical_sha256": self.canonical_sha256,
        }


def _reject_constant(value: str) -> None:
    raise ReleaseManifestError(f"non-finite JSON value is forbidden: {value}")


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseManifestError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def canonical_release_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Serialize a release manifest as UTF-8 compact sorted JSON plus one LF."""

    if type(manifest) is not dict:
        raise ReleaseManifestError("release manifest must be an exact object")
    try:
        return (
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReleaseManifestError("release manifest cannot be serialized canonically") from exc


def _validate_relative_path(value: Any, label: str) -> str:
    if type(value) is str and any(unicodedata.category(character) == "Cc" for character in value):
        raise ReleaseManifestError(f"{label} contains a control character")
    try:
        return validate_repository_relative_path(value)
    except SourceIdentityError as exc:
        raise ReleaseManifestError(f"{label} is not a safe normalized POSIX path") from exc


def _check_hash(value: Any, label: str, *, sha1: bool = False) -> str:
    pattern = _SHA1_RE if sha1 else _SHA256_RE
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ReleaseManifestError(f"{label} must be lowercase {'SHA-1' if sha1 else 'SHA-256'}")
    return value


def _manifest_identifier(value: Any, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ReleaseManifestError(f"{label} must be exact bounded ASCII identity text")
    return value


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    try:
        return bool(checker()) if callable(checker) else False
    except OSError as exc:
        raise ReleaseManifestError("release path junction state could not be checked") from exc


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or _is_junction(path)
    except OSError as exc:
        raise ReleaseManifestError("release path link state could not be checked") from exc


def _resolve_release_root(release_root: str | os.PathLike[str]) -> Path:
    try:
        requested = Path(release_root)
        if not requested.is_absolute() or any(part == ".." for part in requested.parts):
            raise ReleaseManifestError("release_root must be an explicit absolute non-traversing path")
        if _is_link(requested):
            raise ReleaseManifestError("release_root must not be a symlink or junction")
        root = requested.resolve(strict=True)
    except ReleaseManifestError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ReleaseManifestError("release_root must resolve to an existing directory") from exc
    if not root.is_dir():
        raise ReleaseManifestError("release_root must be a directory")
    return root


def _safe_child_path(
    root: Path,
    relative: str,
    *,
    must_exist: bool = True,
    regular_file: bool = True,
) -> Path:
    relative = _validate_relative_path(relative, "payload_path")
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link(current):
                raise ReleaseManifestError("installed payload path contains a symlink or junction")
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ReleaseManifestError("installed payload path is missing or escapes release_root") from exc
    if must_exist and regular_file:
        try:
            mode = resolved.stat().st_mode
        except OSError as exc:
            raise ReleaseManifestError("installed payload cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise ReleaseManifestError("installed payload must be a regular file")
    return resolved


def _current_platform_tags() -> tuple[str, str]:
    if sys.platform == "win32":
        platform_tag = "windows"
    elif sys.platform.startswith("linux"):
        platform_tag = "linux"
    else:
        raise ReleaseManifestError("installed release verification supports Windows and Linux only")
    machine = platform.machine().lower()
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    if architecture is None:
        raise ReleaseManifestError("installed release architecture is unsupported")
    return platform_tag, architecture


def _parse_manifest(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise ReleaseManifestError("release manifest input must be exact bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseManifestError("release manifest must be UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except ReleaseManifestError:
        raise
    except json.JSONDecodeError as exc:
        raise ReleaseManifestError("release manifest JSON is invalid") from exc
    if type(value) is not dict:
        raise ReleaseManifestError("release manifest root must be an object")
    if raw != canonical_release_manifest_bytes(value):
        raise ReleaseManifestError("release manifest bytes are not canonical")
    return value


def _parse_records(value: Any) -> tuple[ResourceRecord, ...]:
    if type(value) is not list or not value:
        raise ReleaseManifestError("resources must be a non-empty list")
    records: list[ResourceRecord] = []
    logical_seen: set[str] = set()
    payload_seen: set[str] = set()
    for item in value:
        if type(item) is not dict or set(item) != _RESOURCE_FIELDS:
            raise ReleaseManifestError("resource record fields are not exact")
        logical = _validate_relative_path(item["logical_path"], "logical_path")
        payload = _validate_relative_path(item["payload_path"], "payload_path")
        if logical.casefold() in logical_seen or payload.casefold() in payload_seen:
            raise ReleaseManifestError("duplicate or case-colliding resource path")
        logical_seen.add(logical.casefold())
        payload_seen.add(payload.casefold())
        role = item["role"]
        if type(role) is not str or role not in RESOURCE_ROLES:
            raise ReleaseManifestError("resource role is outside the reviewed vocabulary")
        byte_sha256 = _check_hash(item["byte_sha256"], "resource byte_sha256")
        if type(item["required"]) is not bool:
            raise ReleaseManifestError("resource required must be exact bool")
        source_sha = item["source_git_blob_sha1"]
        canonical_sha = item["canonical_sha256"]
        if source_sha is not None:
            _check_hash(source_sha, "source_git_blob_sha1", sha1=True)
        if canonical_sha is not None:
            _check_hash(canonical_sha, "canonical_sha256")
        if role == "CANONICAL_COMPONENT_SOURCE" and (source_sha is None or canonical_sha is None):
            raise ReleaseManifestError("canonical component source requires both source identities")
        records.append(
            ResourceRecord(
                logical_path=logical,
                payload_path=payload,
                role=role,
                byte_sha256=byte_sha256,
                required=item["required"],
                source_git_blob_sha1=source_sha,
                canonical_sha256=canonical_sha,
            )
        )
    if [record.logical_path for record in records] != sorted(record.logical_path for record in records):
        raise ReleaseManifestError("resources must be sorted by logical_path")
    return tuple(records)


def _validate_manifest_shape(value: dict[str, Any]) -> tuple[str, str, str, str, tuple[str, ...], tuple[ResourceRecord, ...]]:
    if set(value) != _MANIFEST_FIELDS:
        raise ReleaseManifestError("release manifest fields are not exact")
    if type(value["schema_version"]) is not int or value["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ReleaseManifestError("release manifest schema version is unsupported")
    if value["policy_id"] != MANIFEST_POLICY_ID:
        raise ReleaseManifestError("release manifest policy is unsupported")
    release_id = _manifest_identifier(value["release_id"], "release_id")
    build_id = _manifest_identifier(value["build_id"], "build_id")
    platform_tag = value["platform_tag"]
    architecture_tag = value["architecture_tag"]
    if type(platform_tag) is not str or platform_tag not in {"windows", "linux"}:
        raise ReleaseManifestError("platform_tag is outside the reviewed vocabulary")
    if type(architecture_tag) is not str or architecture_tag not in {"x86_64", "aarch64"}:
        raise ReleaseManifestError("architecture_tag is outside the reviewed vocabulary")
    roots_value = value["closed_world_roots"]
    if type(roots_value) is not list or not roots_value:
        raise ReleaseManifestError("closed_world_roots must be a non-empty list")
    roots = tuple(_validate_relative_path(item, "closed_world_root") for item in roots_value)
    if (
        tuple(sorted(set(roots))) != roots
        or len({item.casefold() for item in roots}) != len(roots)
    ):
        raise ReleaseManifestError("closed_world_roots must be sorted and unique")
    for left_index, left in enumerate(roots):
        for right in roots[left_index + 1 :]:
            if right.startswith(left + "/"):
                raise ReleaseManifestError("closed-world roots must not overlap")
    records = _parse_records(value["resources"])
    return release_id, build_id, platform_tag, architecture_tag, roots, records


def _enumerate_closed_root(root: Path, relative_root: str) -> set[str]:
    directory = _safe_child_path(root, relative_root, regular_file=False)
    if not directory.is_dir():
        raise ReleaseManifestError("closed-world root must be a directory")
    found: set[str] = set()

    def walk(current: Path, logical_prefix: str) -> None:
        try:
            children = sorted(os.scandir(current), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise ReleaseManifestError("closed-world resource tree cannot be enumerated") from exc
        names: set[str] = set()
        for entry in children:
            if entry.name.casefold() in names:
                raise ReleaseManifestError("closed-world tree contains case-colliding names")
            names.add(entry.name.casefold())
            child = current / entry.name
            if _is_link(child):
                raise ReleaseManifestError("closed-world tree contains symlink or junction")
            logical = f"{logical_prefix}/{entry.name}"
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise ReleaseManifestError("closed-world resource cannot be inspected") from exc
            if stat.S_ISDIR(mode):
                walk(child, logical)
            elif stat.S_ISREG(mode):
                found.add(logical)
            else:
                raise ReleaseManifestError("closed-world tree contains a non-regular resource")

    walk(directory, relative_root)
    return found


def _verify_closed_world(root: Path, roots: tuple[str, ...], records: tuple[ResourceRecord, ...]) -> None:
    for closed_root in roots:
        actual = _enumerate_closed_root(root, closed_root)
        declared = {
            record.payload_path
            for record in records
            if record.payload_path == closed_root or record.payload_path.startswith(closed_root + "/")
        }
        existing_declared = {
            path for path in declared if (root.joinpath(*PurePosixPath(path).parts)).exists()
        }
        if actual != existing_declared:
            missing = sorted(existing_declared - actual)
            extra = sorted(actual - existing_declared)
            raise ReleaseManifestError(
                f"closed-world resource set differs (missing={missing}, extra={extra})"
            )


@dataclass(frozen=True, init=False)
class DevelopmentCheckoutIdentity:
    repository_root: Path
    head_commit_sha: str
    policy_id: str
    identity_kind: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ReleaseIdentityError("DevelopmentCheckoutIdentity is verifier-created")

    @classmethod
    def _create(cls, repository_root: Path, head_commit_sha: str) -> "DevelopmentCheckoutIdentity":
        value = object.__new__(cls)
        for name, item in {
            "repository_root": repository_root,
            "head_commit_sha": head_commit_sha,
            "policy_id": DEVELOPMENT_IDENTITY_POLICY_ID,
            "identity_kind": "DEVELOPMENT_CHECKOUT",
        }.items():
            object.__setattr__(value, name, item)
        return value


@dataclass(frozen=True, init=False)
class InstalledReleaseIdentity:
    release_root: Path
    release_id: str
    build_id: str
    platform_tag: str
    architecture_tag: str
    manifest_sha256: str
    manifest_policy_id: str
    manifest_schema_version: int
    closed_world_roots: tuple[str, ...]
    resources: tuple[ResourceRecord, ...]
    identity_kind: str
    trust_mode: str
    _manifest_bytes: bytes

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ReleaseIdentityError("InstalledReleaseIdentity is verifier-created")

    @classmethod
    def _create(
        cls,
        *,
        release_root: Path,
        release_id: str,
        build_id: str,
        platform_tag: str,
        architecture_tag: str,
        manifest_sha256: str,
        closed_world_roots: tuple[str, ...],
        resources: tuple[ResourceRecord, ...],
        manifest_bytes: bytes,
    ) -> "InstalledReleaseIdentity":
        value = object.__new__(cls)
        for name, item in {
            "release_root": release_root,
            "release_id": release_id,
            "build_id": build_id,
            "platform_tag": platform_tag,
            "architecture_tag": architecture_tag,
            "manifest_sha256": manifest_sha256,
            "manifest_policy_id": MANIFEST_POLICY_ID,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "closed_world_roots": closed_world_roots,
            "resources": resources,
            "identity_kind": "INSTALLED_RELEASE",
            "trust_mode": TRUST_MODE,
            "_manifest_bytes": manifest_bytes,
        }.items():
            object.__setattr__(value, name, item)
        return value

    def resource_record(self, logical_path: str) -> ResourceRecord:
        path = _validate_relative_path(logical_path, "logical_path")
        for record in self.resources:
            if record.logical_path == path:
                return record
        raise ReleaseManifestError("resource is not declared by the trusted release manifest")

    @property
    def manifest_bytes(self) -> bytes:
        return self._manifest_bytes


def verify_development_checkout(
    repository_root: str | os.PathLike[str],
) -> DevelopmentCheckoutIdentity:
    """Bind an explicit local repository root to its exact current Git HEAD."""

    try:
        requested_root = Path(repository_root)
        if not requested_root.is_absolute():
            raise ReleaseIdentityError("DevelopmentCheckout repository_root must be absolute")
        root = requested_root.resolve(strict=True)
        # This exact tracked read proves the explicit root is the repository's
        # top level, has a commit, and has an unchanged filtered checkout.
        read_tracked_head_blob(root, "runtime/source_identity.py")
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, SourceIdentityError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        raise ReleaseIdentityError("explicit DevelopmentCheckout Git identity could not be proven") from exc
    if completed.returncode != 0:
        raise ReleaseIdentityError("explicit DevelopmentCheckout has no exact Git HEAD")
    try:
        head = completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ReleaseIdentityError("DevelopmentCheckout HEAD is malformed") from exc
    if _SHA1_RE.fullmatch(head) is None:
        raise ReleaseIdentityError("DevelopmentCheckout HEAD is not an exact commit SHA-1")
    return DevelopmentCheckoutIdentity._create(root, head)


def verify_installed_release(
    release_root: str | os.PathLike[str],
    trusted_manifest_sha256: str,
) -> InstalledReleaseIdentity:
    """Verify an installed release without invoking Git or consulting cwd."""

    trusted = _check_hash(trusted_manifest_sha256, "trusted_manifest_sha256")
    root = _resolve_release_root(release_root)
    manifest_path = _safe_child_path(root, MANIFEST_FILENAME)
    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        raise ReleaseManifestError("installed release manifest cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != trusted:
        raise ReleaseManifestError("trusted manifest SHA-256 mismatch")
    manifest = _parse_manifest(raw)
    (
        release_id,
        build_id,
        manifest_platform,
        manifest_architecture,
        closed_roots,
        records,
    ) = _validate_manifest_shape(manifest)
    actual_platform, actual_architecture = _current_platform_tags()
    if manifest_platform != actual_platform:
        raise ReleaseManifestError("installed release platform tag does not match this host")
    if manifest_architecture != actual_architecture:
        raise ReleaseManifestError("installed release architecture tag does not match this host")
    _verify_closed_world(root, closed_roots, records)
    for record in records:
        payload_path = _safe_child_path(root, record.payload_path, must_exist=False)
        if not payload_path.exists():
            if record.required:
                raise ReleaseManifestError("required installed resource is missing")
            continue
        verified_path = _safe_child_path(root, record.payload_path)
        try:
            payload = verified_path.read_bytes()
        except OSError as exc:
            raise ReleaseManifestError("installed resource cannot be read") from exc
        if hashlib.sha256(payload).hexdigest() != record.byte_sha256:
            raise ReleaseManifestError(f"installed resource byte SHA-256 mismatch: {record.logical_path}")
    return InstalledReleaseIdentity._create(
        release_root=root,
        release_id=release_id,
        build_id=build_id,
        platform_tag=manifest_platform,
        architecture_tag=manifest_architecture,
        manifest_sha256=trusted,
        closed_world_roots=closed_roots,
        resources=records,
        manifest_bytes=raw,
    )


__all__ = [
    "DEVELOPMENT_IDENTITY_POLICY_ID",
    "INSTALLED_IDENTITY_POLICY_ID",
    "MANIFEST_FILENAME",
    "MANIFEST_POLICY_ID",
    "MANIFEST_SCHEMA_VERSION",
    "RESOURCE_ROLES",
    "TRUST_MODE",
    "DevelopmentCheckoutIdentity",
    "InstalledReleaseIdentity",
    "ReleaseIdentityError",
    "ReleaseManifestError",
    "ResourceRecord",
    "canonical_release_manifest_bytes",
    "verify_development_checkout",
    "verify_installed_release",
]
