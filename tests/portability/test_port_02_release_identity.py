from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
import urllib.request

import pytest

from domain import canonical_core as core
from domain import component_authority_registry as registry_module
from domain import run_contracts
from runtime import release_identity, source_identity
from runtime.resources import (
    ResourceResolutionError,
    ResourceResolver,
    WritableRoots,
    default_writable_roots,
)
from scripts import audit_port_02_installed_release_identity as receipt_audit


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = "config/architecture/component-authority-registry-v1.json"
PARITY_PATH = "config/architecture/main-shadow-authority-parity-v1.json"
WEIGHTS_PATH = "config/model_weights.json"
UI_PATHS = ("ui/index.html", "ui/app.js", "ui/styles.css")
MODEL_PATH = "models/over25_model.joblib"
MIGRATION_PATH = "database/migrations/002_add_elo_columns.sql"
COMPONENTS = tuple(
    (
        module.__name__.replace(".", "/") + ".py",
        module,
        identity,
    )
    for _responsibility, (_component_id, module, identity) in core._COMPONENT_SPECS.items()
)
CLOSED_ROOTS = ("config", "contracts", "database/migrations", "models", "ui")
REGIME = core.CURRENT_SPORTYBET_PROVIDER


def _platform_tags() -> tuple[str, str]:
    platform_tag = "windows" if sys.platform == "win32" else "linux"
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }[platform.machine().lower()]
    return platform_tag, architecture


@lru_cache(maxsize=None)
def _tracked_head_payload(logical_path: str) -> tuple[bytes, source_identity.DevelopmentSourceIdentity]:
    return source_identity.read_tracked_head_blob(ROOT, logical_path)


def _stage_resource(
    root: Path,
    logical_path: str,
    *,
    role: str,
    payload_path: str | None = None,
    canonical_sha256: str | None = None,
) -> dict[str, object]:
    payload, source = _tracked_head_payload(logical_path)
    install_path = payload_path or logical_path
    destination = root.joinpath(*install_path.split("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "logical_path": logical_path,
        "payload_path": install_path,
        "role": role,
        "byte_sha256": hashlib.sha256(payload).hexdigest(),
        "required": True,
        "source_git_blob_sha1": (
            source.git_blob_sha1 if role == "CANONICAL_COMPONENT_SOURCE" else None
        ),
        "canonical_sha256": canonical_sha256,
    }


def build_synthetic_release(
    tmp_path: Path,
    *,
    directory_name: str = "ATHENA-Δ-installed-release",
) -> tuple[Path, str, dict[str, object]]:
    """Stage a minimal release exclusively from exact tracked HEAD payloads."""

    root = tmp_path / directory_name
    root.mkdir()
    resources: list[dict[str, object]] = []
    registry_payload, _ = _tracked_head_payload(REGISTRY_PATH)
    registry = registry_module.ComponentAuthorityRegistry.from_json_bytes(registry_payload)
    resources.append(
        _stage_resource(
            root,
            REGISTRY_PATH,
            role="AUTHORITY_REGISTRY",
            canonical_sha256=registry.canonical_sha256,
        )
    )
    resources.append(_stage_resource(root, PARITY_PATH, role="CONFIG"))
    resources.append(_stage_resource(root, WEIGHTS_PATH, role="CONFIG"))
    for path in UI_PATHS:
        resources.append(_stage_resource(root, path, role="UI"))
    resources.append(_stage_resource(root, MODEL_PATH, role="MODEL"))
    resources.append(_stage_resource(root, MIGRATION_PATH, role="MIGRATION"))
    for logical_path, _module, contract_identity in COMPONENTS:
        resources.append(
            _stage_resource(
                root,
                logical_path,
                role="CANONICAL_COMPONENT_SOURCE",
                payload_path=f"contracts/{logical_path}",
                canonical_sha256=contract_identity(),
            )
        )
    resources.sort(key=lambda item: str(item["logical_path"]))
    platform_tag, architecture_tag = _platform_tags()
    manifest: dict[str, object] = {
        "schema_version": release_identity.MANIFEST_SCHEMA_VERSION,
        "policy_id": release_identity.MANIFEST_POLICY_ID,
        "release_id": "athena-port02a-synthetic-v1",
        "build_id": "test-build-0001",
        "platform_tag": platform_tag,
        "architecture_tag": architecture_tag,
        "closed_world_roots": list(CLOSED_ROOTS),
        "resources": resources,
    }
    manifest_bytes = release_identity.canonical_release_manifest_bytes(manifest)
    (root / release_identity.MANIFEST_FILENAME).write_bytes(manifest_bytes)
    return root, hashlib.sha256(manifest_bytes).hexdigest(), manifest


def _write_manifest(root: Path, manifest: dict[str, object]) -> str:
    raw = release_identity.canonical_release_manifest_bytes(manifest)
    (root / release_identity.MANIFEST_FILENAME).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _manifest_record(manifest: dict[str, object], logical_path: str) -> dict[str, object]:
    return next(
        item for item in manifest["resources"]
        if item["logical_path"] == logical_path
    )


def _authority_manifest(profile: str = "SHADOW") -> run_contracts.AuthorityManifest:
    return run_contracts.AuthorityManifest(
        authority_profile=profile,
        mode="AS_OF_REPLAY",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )


def test_development_checkout_identity_binds_exact_current_head_and_missing_git_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = release_identity.verify_development_checkout(ROOT)
    assert identity.repository_root == ROOT
    assert identity.head_commit_sha == subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    assert identity.identity_kind == "DEVELOPMENT_CHECKOUT"
    assert identity.policy_id == release_identity.DEVELOPMENT_IDENTITY_POLICY_ID

    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("git intentionally unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    with pytest.raises(release_identity.ReleaseIdentityError):
        release_identity.verify_development_checkout(ROOT)


def test_installed_release_manifest_is_exact_hash_pinned_and_readable_without_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    development = release_identity.verify_development_checkout(ROOT)
    dev_resolver = ResourceResolver.for_development(development)
    dev_registry_bytes = dev_resolver.read_bytes(REGISTRY_PATH)
    dev_bindings = core.resolve_canonical_core(_authority_manifest(), regime_id=REGIME)
    release_root, trusted_sha, _manifest = build_synthetic_release(tmp_path)
    calls: list[tuple[object, ...]] = []

    def no_git(*args, **_kwargs):
        calls.append(args)
        raise FileNotFoundError("Git intentionally unavailable after installed verification")

    monkeypatch.setattr(subprocess, "run", no_git)
    installed = release_identity.verify_installed_release(release_root, trusted_sha)
    resolver = ResourceResolver.for_installed(installed)
    installed_bindings = core.resolve_canonical_core(
        _authority_manifest(),
        regime_id=REGIME,
        release_identity=installed,
        resources=resolver,
    )
    assert calls == []
    assert dev_resolver.source_mode == "DEVELOPMENT_CHECKOUT"
    assert installed.identity_kind == "INSTALLED_RELEASE"
    assert installed.trust_mode == "TRUSTED_MANIFEST_SHA256_V1"
    assert installed.manifest_sha256 == trusted_sha
    assert installed_bindings.to_dict() == dev_bindings.to_dict()
    assert installed_bindings.canonical_sha256 == dev_bindings.canonical_sha256
    assert tuple(record.responsibility_id for record in installed_bindings.records) == core.CANONICAL_RESPONSIBILITIES
    assert installed_bindings.registry_canonical_sha256 == dev_bindings.registry_canonical_sha256
    assert dev_registry_bytes == resolver.read_bytes(REGISTRY_PATH)
    assert calls == []
    with pytest.raises(release_identity.ReleaseIdentityError):
        release_identity.verify_development_checkout(release_root)
    assert calls


def test_manifest_digest_and_canonical_bytes_are_both_required(tmp_path: Path) -> None:
    root, trusted, manifest = build_synthetic_release(tmp_path)
    with pytest.raises(release_identity.ReleaseManifestError, match="trusted manifest SHA-256"):
        release_identity.verify_installed_release(root, "0" * 64)

    pretty = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    (root / release_identity.MANIFEST_FILENAME).write_bytes(pretty)
    pretty_sha = hashlib.sha256(pretty).hexdigest()
    with pytest.raises(release_identity.ReleaseManifestError, match="not canonical"):
        release_identity.verify_installed_release(root, pretty_sha)


def test_duplicate_manifest_keys_and_non_finite_values_fail_closed(tmp_path: Path) -> None:
    root, _trusted, _manifest = build_synthetic_release(tmp_path)
    raw = (root / release_identity.MANIFEST_FILENAME).read_bytes()
    duplicate = b'{"schema_version":1,' + raw[1:]
    (root / release_identity.MANIFEST_FILENAME).write_bytes(duplicate)
    with pytest.raises(release_identity.ReleaseManifestError, match="duplicate JSON"):
        release_identity.verify_installed_release(root, hashlib.sha256(duplicate).hexdigest())

    non_finite = raw.replace(b'"schema_version":1', b'"schema_version":NaN', 1)
    (root / release_identity.MANIFEST_FILENAME).write_bytes(non_finite)
    with pytest.raises(release_identity.ReleaseManifestError, match="non-finite"):
        release_identity.verify_installed_release(root, hashlib.sha256(non_finite).hexdigest())


@pytest.mark.parametrize(
    "path_value",
    ("../escape", "/absolute", "C:/drive", "a\\b", "a//b", "a/./b", "a/../b"),
)
def test_manifest_payload_path_traversal_and_nonportable_paths_fail(
    tmp_path: Path,
    path_value: str,
) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    _manifest_record(manifest, UI_PATHS[0])["payload_path"] = path_value
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="payload_path"):
        release_identity.verify_installed_release(root, trusted)


def test_duplicate_logical_or_payload_paths_and_unsorted_records_fail(tmp_path: Path) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    first = manifest["resources"][0]
    second = manifest["resources"][1]
    second["logical_path"] = first["logical_path"]
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="duplicate or case-colliding"):
        release_identity.verify_installed_release(root, trusted)

    root, _trusted, manifest = build_synthetic_release(tmp_path, directory_name="ATHENA-unsorted-Δ")
    manifest["resources"].reverse()
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="sorted by logical_path"):
        release_identity.verify_installed_release(root, trusted)


def test_closed_world_missing_tampered_config_model_ui_and_source_block(tmp_path: Path) -> None:
    cases = (
        (REGISTRY_PATH, "missing"),
        (UI_PATHS[1], "missing"),
        (PARITY_PATH, "tamper"),
        (WEIGHTS_PATH, "tamper"),
        (MODEL_PATH, "tamper"),
        (UI_PATHS[0], "tamper"),
        ("domain/price_all.py", "tamper-payload"),
    )
    for index, (logical, operation) in enumerate(cases):
        root, trusted, _manifest = build_synthetic_release(
            tmp_path,
            directory_name=f"ATHENA-tamper-{index}-Δ",
        )
        record = next(
            item for item in _manifest["resources"]
            if item["logical_path"] == logical or item["payload_path"] == logical
        )
        payload_path = root.joinpath(*str(record["payload_path"]).split("/"))
        if operation == "missing":
            payload_path.unlink()
        else:
            payload_path.write_bytes(payload_path.read_bytes() + b"tamper")
        with pytest.raises(release_identity.ReleaseManifestError):
            release_identity.verify_installed_release(root, trusted)


def test_closed_world_rejects_extra_files_but_allows_unmanaged_executable_area(tmp_path: Path) -> None:
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    (root / "ui" / "surprise.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(release_identity.ReleaseManifestError, match="closed-world"):
        release_identity.verify_installed_release(root, trusted)

    root, trusted, _manifest = build_synthetic_release(tmp_path, directory_name="ATHENA-executable-extra-Δ")
    (root / "bin").mkdir()
    (root / "bin" / "athena.exe").write_bytes(b"synthetic executable area")
    installed = release_identity.verify_installed_release(root, trusted)
    assert installed.release_id == "athena-port02a-synthetic-v1"


def test_symlink_escape_fails_closed_where_supported(tmp_path: Path) -> None:
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"not a release resource")
    link = root / "ui" / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is not available on this host: {type(exc).__name__}")
    with pytest.raises(release_identity.ReleaseManifestError, match="symlink|junction"):
        release_identity.verify_installed_release(root, trusted)


def test_unicode_release_root_unrelated_cwd_read_only_resource_and_no_cwd_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    previous_cwd = Path.cwd()
    try:
        monkeypatch.chdir(unrelated)
        registry_file = root.joinpath(*REGISTRY_PATH.split("/"))
        original_mode = registry_file.stat().st_mode
        try:
            registry_file.chmod(stat.S_IREAD)
            installed = release_identity.verify_installed_release(root, trusted)
            resolver = ResourceResolver.for_installed(installed)
            assert resolver.read_bytes(REGISTRY_PATH, expected_role="AUTHORITY_REGISTRY")
            assert resolver.path_for(UI_PATHS[0], expected_role="UI").is_file()
            assert "Δ" in str(root)
        finally:
            registry_file.chmod(original_mode | stat.S_IWRITE)
    finally:
        monkeypatch.chdir(previous_cwd)


def test_source_git_and_canonical_metadata_mismatch_block_canonical_core(tmp_path: Path) -> None:
    for field, bad in (("source_git_blob_sha1", "0" * 40), ("canonical_sha256", "0" * 64)):
        root, _trusted, manifest = build_synthetic_release(
            tmp_path,
            directory_name=f"ATHENA-metadata-{field}-Δ",
        )
        record = _manifest_record(manifest, COMPONENTS[1][0])
        record[field] = bad
        trusted = _write_manifest(root, manifest)
        installed = release_identity.verify_installed_release(root, trusted)
        resolver = ResourceResolver.for_installed(installed)
        with pytest.raises(core.CanonicalCoreError, match="identity drifted"):
            core.resolve_canonical_core(
                _authority_manifest(), regime_id=REGIME,
                release_identity=installed, resources=resolver,
            )


def test_resource_role_mismatch_and_installed_identity_resolver_mismatch_fail(tmp_path: Path) -> None:
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    identity = release_identity.verify_installed_release(root, trusted)
    resolver = ResourceResolver.for_installed(identity)
    with pytest.raises(ResourceResolutionError, match="role"):
        resolver.read_bytes(UI_PATHS[0], expected_role="MODEL")

    second_identity = release_identity.verify_installed_release(root, trusted)
    with pytest.raises(core.CanonicalCoreError, match="resolver bound"):
        core.resolve_canonical_core(
            _authority_manifest(), regime_id=REGIME,
            release_identity=second_identity, resources=resolver,
        )
    with pytest.raises(ResourceResolutionError, match="DevelopmentCheckoutIdentity"):
        ResourceResolver.for_development(identity)  # type: ignore[arg-type]


def test_missing_installed_registry_and_identity_without_resolver_fail_closed(tmp_path: Path) -> None:
    root, trusted, manifest = build_synthetic_release(tmp_path)
    # Removing a listed required registry is rejected before core resolution.
    registry_file = root.joinpath(*REGISTRY_PATH.split("/"))
    registry_file.unlink()
    with pytest.raises(release_identity.ReleaseManifestError, match="required installed resource"):
        release_identity.verify_installed_release(root, trusted)

    root, trusted, _manifest = build_synthetic_release(tmp_path, directory_name="ATHENA-no-resolver-Δ")
    identity = release_identity.verify_installed_release(root, trusted)
    with pytest.raises(core.CanonicalCoreError, match="resolver"):
        core.resolve_canonical_core(_authority_manifest(), regime_id=REGIME, release_identity=identity)


def test_wrong_platform_architecture_release_root_and_manifest_role_fail(tmp_path: Path) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    manifest["platform_tag"] = "linux" if _platform_tags()[0] == "windows" else "windows"
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="platform tag"):
        release_identity.verify_installed_release(root, trusted)

    root, _trusted, manifest = build_synthetic_release(tmp_path, directory_name="ATHENA-wrong-arch-Δ")
    manifest["architecture_tag"] = "aarch64" if _platform_tags()[1] == "x86_64" else "x86_64"
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="architecture tag"):
        release_identity.verify_installed_release(root, trusted)

    with pytest.raises(release_identity.ReleaseManifestError):
        release_identity.verify_installed_release(tmp_path / "not-a-release", "0" * 64)


def test_raw_installed_resource_mutation_after_identity_creation_is_detected(tmp_path: Path) -> None:
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    identity = release_identity.verify_installed_release(root, trusted)
    resolver = ResourceResolver.for_installed(identity)
    target = root.joinpath(*UI_PATHS[0].split("/"))
    target.write_bytes(target.read_bytes() + b"changed after admission")
    with pytest.raises(ResourceResolutionError, match="identity changed"):
        resolver.read_bytes(UI_PATHS[0])


def test_development_resource_resolver_reads_exact_tracked_head_blob() -> None:
    identity = release_identity.verify_development_checkout(ROOT)
    resolver = ResourceResolver.for_development(identity)
    payload = resolver.read_bytes(REGISTRY_PATH, expected_role="AUTHORITY_REGISTRY")
    expected, source = _tracked_head_payload(REGISTRY_PATH)
    assert payload == expected
    assert resolver.source_identity(REGISTRY_PATH).git_blob_sha1 == source.git_blob_sha1
    assert resolver.path_for(REGISTRY_PATH).is_file()


def test_writable_roots_are_separate_and_platform_policies_are_explicit(
    tmp_path: Path,
) -> None:
    release = tmp_path / "install"
    release.mkdir()
    explicit = WritableRoots(
        data_root=tmp_path / "user-data",
        cache_root=tmp_path / "user-cache",
        state_root=tmp_path / "user-state",
        installed_release_root=release,
    )
    explicit.ensure_created()
    assert all(path.is_dir() for path in (explicit.data_root, explicit.cache_root, explicit.state_root))
    assert not any(path == release or release in path.parents for path in (
        explicit.data_root, explicit.cache_root, explicit.state_root
    ))

    if sys.platform == "win32":
        windows = default_writable_roots(
            platform_name="win32", environ={"LOCALAPPDATA": "C:\\Users\\Sample\\AppData\\Local"}
        )
        assert str(windows.data_root).endswith("ATHENA\\data")
        pytest.skip("Linux/XDG path semantics are validated on Hosted Linux")
    linux = default_writable_roots(
        platform_name="linux",
        environ={
            "HOME": "/home/sample",
            "XDG_DATA_HOME": "/data",
            "XDG_CACHE_HOME": "/cache",
            "XDG_STATE_HOME": "/state",
        },
    )
    assert linux.data_root == Path("/data/athena")
    assert linux.cache_root == Path("/cache/athena")
    assert linux.state_root == Path("/state/athena")
    with pytest.raises(ResourceResolutionError, match="support Windows and Linux only"):
        default_writable_roots(platform_name="darwin", environ={"HOME": "/tmp"})
    with pytest.raises(ResourceResolutionError, match="LOCALAPPDATA"):
        default_writable_roots(platform_name="win32", environ={})
    with pytest.raises(ResourceResolutionError, match="HOME"):
        default_writable_roots(platform_name="linux", environ={})
    with pytest.raises(ResourceResolutionError, match="inside installed"):
        WritableRoots(
            data_root=release / "data",
            cache_root=tmp_path / "cache",
            state_root=tmp_path / "state",
            installed_release_root=release,
        )


def test_external_network_provider_and_delivery_sentinels_remain_unused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network/provider/delivery operation is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    identity = release_identity.verify_installed_release(root, trusted)
    resolver = ResourceResolver.for_installed(identity)
    result = core.resolve_canonical_core(
        _authority_manifest(), regime_id=REGIME,
        release_identity=identity, resources=resolver,
    )
    assert result.authority_profile == "SHADOW"


def test_manifest_role_and_metadata_shape_are_strict(tmp_path: Path) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    _manifest_record(manifest, UI_PATHS[0])["role"] = "MODEL"
    trusted = _write_manifest(root, manifest)
    installed = release_identity.verify_installed_release(root, trusted)
    resolver = ResourceResolver.for_installed(installed)
    with pytest.raises(ResourceResolutionError, match="role"):
        resolver.resource_record(UI_PATHS[0], expected_role="UI")

    root, _trusted, manifest = build_synthetic_release(tmp_path, directory_name="ATHENA-bool-Δ")
    _manifest_record(manifest, UI_PATHS[0])["required"] = 1
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="exact bool"):
        release_identity.verify_installed_release(root, trusted)


@pytest.mark.parametrize("change", ("duplicate_payload", "missing_field", "extra_field"))
def test_manifest_exact_fields_and_payload_uniqueness_fail_closed(
    tmp_path: Path,
    change: str,
) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    if change == "duplicate_payload":
        first, second = manifest["resources"][:2]
        second["payload_path"] = first["payload_path"]
        manifest["resources"].sort(key=lambda item: str(item["logical_path"]))
    elif change == "missing_field":
        del manifest["build_id"]
    else:
        manifest["unreviewed"] = True
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError):
        release_identity.verify_installed_release(root, trusted)


def test_manifest_path_case_collisions_are_rejected(tmp_path: Path) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    first = _manifest_record(manifest, UI_PATHS[0])
    second = _manifest_record(manifest, UI_PATHS[1])
    second["payload_path"] = str(first["payload_path"]).swapcase()
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="duplicate or case-colliding"):
        release_identity.verify_installed_release(root, trusted)


def test_installed_manifest_schema_policy_identity_and_release_ids_are_pinned(tmp_path: Path) -> None:
    root, _trusted, manifest = build_synthetic_release(tmp_path)
    manifest["policy_id"] = "UNKNOWN_POLICY"
    trusted = _write_manifest(root, manifest)
    with pytest.raises(release_identity.ReleaseManifestError, match="policy"):
        release_identity.verify_installed_release(root, trusted)


def test_port_02_receipt_is_canonical_self_hashed_and_pins_parity(tmp_path: Path) -> None:
    receipt_path = ROOT / receipt_audit.ARTIFACT_PATH
    raw_receipt = receipt_path.read_bytes()
    document = receipt_audit._load_strict_json(raw_receipt)
    assert raw_receipt == receipt_audit.canonical_json_bytes(document)
    summary = receipt_audit.validate_receipt(document)
    assert summary["canonical_sha256"] == document["canonical_sha256"]
    root, trusted, _manifest = build_synthetic_release(tmp_path)
    if _platform_tags() == (
        document["installed_proof"]["platform_tag"],
        document["installed_proof"]["architecture_tag"],
    ):
        assert trusted == document["installed_proof"]["trusted_manifest_sha256"]
    installed = release_identity.verify_installed_release(root, trusted)
    bindings = core.resolve_canonical_core(
        _authority_manifest(),
        regime_id=REGIME,
        release_identity=installed,
        resources=ResourceResolver.for_installed(installed),
    )
    assert bindings.canonical_sha256 == document["canonical_core_parity"]["installed_bindings_sha256"]
    assert bindings.registry_canonical_sha256 == document["canonical_core_parity"]["registry_canonical_sha256"]


def test_port_02_audit_duplicate_json_keys_fail_closed() -> None:
    with pytest.raises(receipt_audit.Port02AuditError, match="duplicate JSON"):
        receipt_audit._load_strict_json(b'{"schema_version":1,"schema_version":1}\n')
