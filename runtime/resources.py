"""Explicit read-only resource resolution for source and installed releases."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Mapping

from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
    RESOURCE_ROLES,
    ReleaseIdentityError,
    ReleaseManifestError,
    ResourceRecord,
    _safe_child_path,
    verify_development_checkout,
)
from runtime.source_identity import (
    DevelopmentSourceIdentity,
    SourceIdentityError,
    read_tracked_head_blob,
    validate_repository_relative_path,
)


class ResourceResolutionError(ValueError):
    """A logical resource is missing, outside the trusted release, or changed."""


def _logical_path(value: str) -> str:
    try:
        return validate_repository_relative_path(value)
    except SourceIdentityError as exc:
        raise ResourceResolutionError("resource logical path is not normalized POSIX text") from exc


@dataclass(frozen=True, init=False)
class ResourceResolver:
    """Resolver permanently bound to one verified source-mode identity."""

    identity: DevelopmentCheckoutIdentity | InstalledReleaseIdentity

    def __init__(self, *_args, **_kwargs) -> None:
        raise ResourceResolutionError("construct ResourceResolver with an explicit verified identity")

    @classmethod
    def _create(cls, identity: DevelopmentCheckoutIdentity | InstalledReleaseIdentity) -> "ResourceResolver":
        instance = object.__new__(cls)
        object.__setattr__(instance, "identity", identity)
        return instance

    @classmethod
    def for_development(cls, identity: DevelopmentCheckoutIdentity) -> "ResourceResolver":
        if type(identity) is not DevelopmentCheckoutIdentity:
            raise ResourceResolutionError("exact DevelopmentCheckoutIdentity is required")
        try:
            current = verify_development_checkout(identity.repository_root)
        except ReleaseIdentityError as exc:
            raise ResourceResolutionError("DevelopmentCheckout identity is no longer valid") from exc
        if current.head_commit_sha != identity.head_commit_sha:
            raise ResourceResolutionError("DevelopmentCheckout HEAD changed after identity creation")
        return cls._create(identity)

    @classmethod
    def for_installed(cls, identity: InstalledReleaseIdentity) -> "ResourceResolver":
        if type(identity) is not InstalledReleaseIdentity:
            raise ResourceResolutionError("exact verified InstalledReleaseIdentity is required")
        return cls._create(identity)

    @property
    def source_mode(self) -> str:
        return self.identity.identity_kind

    def resource_record(
        self,
        logical_path: str,
        *,
        expected_role: str | None = None,
    ) -> ResourceRecord:
        path = _logical_path(logical_path)
        if type(self.identity) is not InstalledReleaseIdentity:
            raise ResourceResolutionError("resource records exist only for installed releases")
        try:
            record = self.identity.resource_record(path)
        except ReleaseManifestError as exc:
            raise ResourceResolutionError("resource is not in the installed release manifest") from exc
        if expected_role is not None:
            if type(expected_role) is not str or expected_role not in RESOURCE_ROLES:
                raise ResourceResolutionError("expected role is outside the reviewed vocabulary")
            if record.role != expected_role:
                raise ResourceResolutionError("installed resource role does not match requested role")
        return record

    def source_identity(self, logical_path: str) -> DevelopmentSourceIdentity | ResourceRecord:
        path = _logical_path(logical_path)
        if type(self.identity) is DevelopmentCheckoutIdentity:
            try:
                _payload, identity = read_tracked_head_blob(self.identity.repository_root, path)
            except SourceIdentityError as exc:
                raise ResourceResolutionError("development resource identity could not be proven") from exc
            self._require_same_development_head()
            return identity
        return self.resource_record(path)

    def read_bytes(
        self,
        logical_path: str,
        *,
        expected_role: str | None = None,
    ) -> bytes:
        path = _logical_path(logical_path)
        if type(self.identity) is DevelopmentCheckoutIdentity:
            if expected_role is not None and expected_role not in RESOURCE_ROLES:
                raise ResourceResolutionError("expected role is outside the reviewed vocabulary")
            try:
                payload, source = read_tracked_head_blob(self.identity.repository_root, path)
            except SourceIdentityError as exc:
                raise ResourceResolutionError("development resource could not be read from exact HEAD") from exc
            self._require_same_development_head()
            return payload

        record = self.resource_record(path, expected_role=expected_role)
        try:
            payload_path = _safe_child_path(self.identity.release_root, record.payload_path)
            payload = payload_path.read_bytes()
        except (OSError, ReleaseManifestError) as exc:
            raise ResourceResolutionError("installed resource could not be read safely") from exc
        if hashlib.sha256(payload).hexdigest() != record.byte_sha256:
            raise ResourceResolutionError("installed resource byte identity changed after verification")
        return payload

    def path_for(
        self,
        logical_path: str,
        *,
        expected_role: str | None = None,
    ) -> Path:
        """Return a verified filesystem path for libraries requiring paths."""

        path = _logical_path(logical_path)
        if type(self.identity) is DevelopmentCheckoutIdentity:
            # Verify before returning a path; callers remain responsible for not
            # treating it as a stable byte snapshot after return.
            self.read_bytes(path, expected_role=expected_role)
            candidate = self.identity.repository_root.joinpath(*PurePosixPath(path).parts)
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(self.identity.repository_root)
            except (OSError, ValueError) as exc:
                raise ResourceResolutionError("development resource path escaped its repository") from exc
            return resolved
        record = self.resource_record(path, expected_role=expected_role)
        self.read_bytes(path, expected_role=expected_role)
        try:
            return _safe_child_path(self.identity.release_root, record.payload_path)
        except ReleaseManifestError as exc:
            raise ResourceResolutionError("installed resource path is not safe") from exc

    def _require_same_development_head(self) -> None:
        if type(self.identity) is not DevelopmentCheckoutIdentity:
            return
        try:
            current = verify_development_checkout(self.identity.repository_root)
        except ReleaseIdentityError as exc:
            raise ResourceResolutionError("DevelopmentCheckout identity could not be revalidated") from exc
        if current.head_commit_sha != self.identity.head_commit_sha:
            raise ResourceResolutionError("DevelopmentCheckout HEAD changed after identity creation")


def _resolved_absolute(path: Path, label: str) -> Path:
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ResourceResolutionError(f"{label} must be absolute and contain no traversal alias")
    try:
        if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
            raise ResourceResolutionError(f"{label} must not be a symlink or junction")
        return path.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise ResourceResolutionError(f"{label} could not be resolved") from exc


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class WritableRoots:
    """Distinct application-writable roots, separate from release resources."""

    data_root: Path
    cache_root: Path
    state_root: Path
    installed_release_root: Path | None = None

    def __post_init__(self) -> None:
        roots = tuple(
            _resolved_absolute(Path(item), name)
            for item, name in (
                (self.data_root, "data_root"),
                (self.cache_root, "cache_root"),
                (self.state_root, "state_root"),
            )
        )
        folded = [str(item).casefold() for item in roots]
        if len(set(folded)) != len(roots):
            raise ResourceResolutionError("writable roots must be distinct")
        for left_index, left in enumerate(roots):
            for right in roots[left_index + 1 :]:
                if _contains(left, right) or _contains(right, left):
                    raise ResourceResolutionError("writable roots must not contain one another")
        release = None
        if self.installed_release_root is not None:
            release = _resolved_absolute(Path(self.installed_release_root), "installed_release_root")
            if any(_contains(release, item) for item in roots):
                raise ResourceResolutionError("writable roots must remain outside installed release root")
        object.__setattr__(self, "data_root", roots[0])
        object.__setattr__(self, "cache_root", roots[1])
        object.__setattr__(self, "state_root", roots[2])
        object.__setattr__(self, "installed_release_root", release)

    def ensure_created(self) -> "WritableRoots":
        """Create only these three explicitly configured writable directories."""

        for path in (self.data_root, self.cache_root, self.state_root):
            try:
                path.mkdir(parents=True, exist_ok=True)
                if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
                    raise ResourceResolutionError("writable root resolved through a link")
                resolved = path.resolve(strict=True)
                if self.installed_release_root is not None and _contains(self.installed_release_root, resolved):
                    raise ResourceResolutionError("writable root resolved inside installed release")
            except ResourceResolutionError:
                raise
            except OSError as exc:
                raise ResourceResolutionError("writable root could not be created") from exc
        return self


def default_writable_roots(
    *,
    installed_release_root: str | os.PathLike[str] | None = None,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
) -> WritableRoots:
    """Resolve standard Windows or Linux data/cache/state roots without cwd."""

    selected_platform = sys.platform if platform_name is None else platform_name
    env = os.environ if environ is None else environ
    if selected_platform == "win32":
        base_value = env.get("LOCALAPPDATA")
        if type(base_value) is not str or not base_value:
            raise ResourceResolutionError("LOCALAPPDATA is required for Windows writable roots")
        base = Path(base_value)
        if not base.is_absolute():
            raise ResourceResolutionError("LOCALAPPDATA must be absolute")
        root = base / "ATHENA"
        roots = (root / "data", root / "cache", root / "state")
    elif selected_platform.startswith("linux"):
        home_value = Path(home) if home is not None else Path(env["HOME"]) if env.get("HOME") else None
        if home_value is None or not home_value.is_absolute():
            raise ResourceResolutionError("absolute HOME is required for Linux writable roots")

        def xdg(name: str, fallback: Path) -> Path:
            value = env.get(name)
            if not value:
                return fallback
            candidate = Path(value)
            if not candidate.is_absolute():
                raise ResourceResolutionError(f"{name} must be absolute")
            return candidate

        roots = (
            xdg("XDG_DATA_HOME", home_value / ".local" / "share") / "athena",
            xdg("XDG_CACHE_HOME", home_value / ".cache") / "athena",
            xdg("XDG_STATE_HOME", home_value / ".local" / "state") / "athena",
        )
    else:
        raise ResourceResolutionError("writable-root defaults support Windows and Linux only")
    return WritableRoots(
        data_root=roots[0],
        cache_root=roots[1],
        state_root=roots[2],
        installed_release_root=Path(installed_release_root) if installed_release_root is not None else None,
    )


__all__ = [
    "ResourceResolutionError",
    "ResourceResolver",
    "WritableRoots",
    "default_writable_roots",
]
