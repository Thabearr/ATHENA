from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import urllib.request

import pytest

from domain import sportybet_live_event_quote_evidence as live_quote
from runtime import source_identity
from scripts import audit_port_01_source_identity_parity as audit
from scripts import audit_runtime_reachability as reachability
from scripts import validate_main_shadow_authority_parity as parity


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "config/architecture/main-shadow-authority-parity-v1.json"
INVENTORY = ROOT / "artifacts/architecture/repository-architecture-inventory-v1.json"
P44R_FIXTURE_PREFIX = "tests/fixtures/p4_4r_run_36285099805_quote_evidence/initial"
P44R_CAPTURE_ID = "1aec7fa77430c1f7ab99b957"
P44R_BLOCKER_MANIFEST_SHA256 = (
    "f2515e5f02682a05b6d3e1cd48f03b08085f0567baf56dfce38244a63e99892e"
)
P44R_BLOCKER_MANIFEST_SHA1 = "120443830d12f2d77c6917d2e8396fab8d25c181"


def _git(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return completed.stdout


def _init_text_repository(repository: Path, relative_path: str = "data/fixture.json") -> Path:
    repository.mkdir(parents=True)
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "portability-test@example.invalid")
    _git(repository, "config", "user.name", "PORT-01B Test")
    _git(repository, "config", "core.autocrlf", "true")
    _git(repository, "config", "core.safecrlf", "false")
    (repository / ".gitattributes").write_bytes(b"*.json text\n")
    source = repository.joinpath(*relative_path.split("/"))
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"value":1}\n')
    _git(repository, "add", ".gitattributes", relative_path)
    _git(repository, "commit", "--quiet", "-m", "fixture")
    return source


def _runtime_fixture_directory(tmp_path: Path) -> tuple[Path, bytes]:
    directory = (
        tmp_path
        / Path(live_quote.ALLOWED_OUTPUT_RELATIVE)
        / P44R_CAPTURE_ID
    )
    directory.mkdir(parents=True)
    manifest_bytes = b""
    for source_name, runtime_name in (
        ("event.raw.json", live_quote.RAW_FILENAME),
        ("manifest.json", live_quote.MANIFEST_FILENAME),
    ):
        relative = f"{P44R_FIXTURE_PREFIX}/{source_name}"
        payload, _identity = source_identity.read_tracked_head_blob(ROOT, relative)
        destination = directory / runtime_name
        destination.write_bytes(payload)
        assert destination.read_bytes() == payload
        if source_name == "manifest.json":
            manifest_bytes = payload
    return directory, manifest_bytes


def test_b2_receipt_canonical_self_hash_and_b1_predecessor() -> None:
    raw = (ROOT / audit.ARTIFACT_RELATIVE_PATH).read_bytes()
    document = audit._read_json_bytes(raw, "test receipt")
    summary = audit.validate_receipt(document)
    assert document["predecessor"]["policy_id"] == audit.B1_POLICY_ID
    assert document["predecessor"]["canonical_sha256"] == audit.B1_CANONICAL_SHA256
    assert document["predecessor"]["git_blob_sha1"] == audit.B1_GIT_BLOB_SHA1
    assert document["predecessor"]["fixed_blocker_ids"] == list(audit.B1_FAILURE_IDS)
    assert summary["fixed_blocker_count"] == 10


def test_raw_canonical_git_blob_sha1_and_payload_domains_are_distinct() -> None:
    raw = b'{"value":1}\r\n'
    canonical = b'{"value":1}\n'
    git_blob = b"blob " + str(len(canonical)).encode("ascii") + b"\0" + canonical
    assert hashlib.sha256(raw).hexdigest() != source_identity.canonical_payload_sha256(canonical)
    assert source_identity.canonical_payload_sha256(canonical) == hashlib.sha256(canonical).hexdigest()
    assert hashlib.sha1(git_blob).hexdigest() != hashlib.sha256(canonical).hexdigest()


def test_git_blob_sha1_and_exact_payload_sha256_are_correct(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_text_repository(repository)
    payload, identity = source_identity.read_tracked_head_blob(
        repository, "data/fixture.json"
    )
    expected_object = _git(repository, "rev-parse", "HEAD:data/fixture.json").decode().strip()
    assert identity.git_blob_sha1 == expected_object
    assert identity.git_blob_sha1 == hashlib.sha1(
        b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    ).hexdigest()
    assert identity.git_blob_payload_sha256 == hashlib.sha256(payload).hexdigest()


def test_tracked_crlf_materialization_proves_filtered_head_equivalence(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    source = _init_text_repository(repository)
    source.write_bytes(b'{"value":1}\r\n')
    payload, identity = source_identity.read_tracked_head_blob(
        repository, "data/fixture.json"
    )
    assert payload == b'{"value":1}\n'
    assert source.read_bytes() == b'{"value":1}\r\n'
    assert identity.git_blob_sha1 == identity.filtered_worktree_git_blob_sha1
    assert identity.raw_worktree_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert identity.git_blob_payload_sha256 != identity.raw_worktree_sha256


def test_semantic_tracked_worktree_mutation_fails_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    source = _init_text_repository(repository)
    source.write_bytes(b'{"value":2}\r\n')
    with pytest.raises(source_identity.SourceIdentityError, match="filtered worktree"):
        source_identity.read_tracked_head_blob(repository, "data/fixture.json")


def test_untracked_path_cannot_borrow_head_identity(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_text_repository(repository)
    (repository / "untracked.json").write_bytes(b'{"value":1}\n')
    with pytest.raises(source_identity.SourceIdentityError, match="tracked HEAD"):
        source_identity.read_tracked_head_blob(repository, "untracked.json")


def test_untracked_crlf_canonical_candidate_is_rejected_without_head_substitution(
    tmp_path: Path,
) -> None:
    payload = json.loads(CONTRACT.read_bytes())
    candidate = tmp_path / "candidate.json"
    canonical = parity.canonical_json_bytes(payload)
    candidate.write_bytes(canonical.replace(b"\n", b"\r\n"))
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(_git(ROOT, "show", "HEAD:artifacts/architecture/repository-architecture-inventory-v1.json"))
    with pytest.raises(parity.ValidationError, match="not canonical"):
        parity.validate_contract(candidate, inventory)


def test_tracked_canonical_contract_uses_head_bytes_after_checkout_proof() -> None:
    result = parity.validate_contract(CONTRACT, INVENTORY)
    payload, identity = source_identity.read_tracked_head_blob(
        ROOT,
        "config/architecture/main-shadow-authority-parity-v1.json",
    )
    assert payload == parity.canonical_json_bytes(json.loads(payload))
    assert result["contract_sha256"] == hashlib.sha256(payload).hexdigest()
    assert identity.filtered_worktree_git_blob_sha1 == identity.git_blob_sha1


@pytest.mark.parametrize("filename", ["event.raw.json", "manifest.json"])
def test_retained_fixture_materializes_exact_tracked_head_bytes(
    filename: str, tmp_path: Path
) -> None:
    relative = f"{P44R_FIXTURE_PREFIX}/{filename}"
    destination = tmp_path / filename
    identity = reachability._materialize_tracked_fixture(relative, destination)
    expected, expected_identity = source_identity.read_tracked_head_blob(ROOT, relative)
    assert destination.read_bytes() == expected
    assert identity == expected_identity
    if filename == "manifest.json":
        assert identity.git_blob_sha1 == P44R_BLOCKER_MANIFEST_SHA1
        assert identity.git_blob_payload_sha256 == P44R_BLOCKER_MANIFEST_SHA256


def test_runtime_raw_quote_manifest_accepts_exact_bytes_and_rejects_crlf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, manifest = _runtime_fixture_directory(tmp_path)
    monkeypatch.setattr(
        live_quote,
        "_network_fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    verified = live_quote.verify_live_event_quote_evidence(
        directory, repository_root=tmp_path
    )
    assert verified.event_id == "sr:match:66299604"

    manifest_path = directory / live_quote.MANIFEST_FILENAME
    manifest_path.write_bytes(manifest.replace(b"\n", b"\r\n"))
    with pytest.raises(live_quote.SportyBetLiveEventQuoteEvidenceError, match="manifest bytes are not canonical"):
        live_quote.verify_live_event_quote_evidence(directory, repository_root=tmp_path)


def test_runtime_raw_quote_manifest_rejects_whitespace_and_semantic_mutation(
    tmp_path: Path,
) -> None:
    directory, manifest = _runtime_fixture_directory(tmp_path)
    manifest_path = directory / live_quote.MANIFEST_FILENAME
    manifest_path.write_bytes(manifest[:-1] + b" \n")
    with pytest.raises(live_quote.SportyBetLiveEventQuoteEvidenceError, match="manifest bytes are not canonical"):
        live_quote.verify_live_event_quote_evidence(directory, repository_root=tmp_path)

    value = json.loads(manifest)
    value["raw_size"] += 1
    canonical_semantic_mutation = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(canonical_semantic_mutation)
    with pytest.raises(live_quote.SportyBetLiveEventQuoteEvidenceError, match="raw response identity mismatch"):
        live_quote.verify_live_event_quote_evidence(directory, repository_root=tmp_path)


def test_unicode_path_and_unrelated_cwd_use_explicit_repository_root(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "athena-λ-漢字"
    relative = "資料/試合.json"
    _init_text_repository(repository, relative)
    monkeypatch.chdir(tmp_path)
    payload, identity = source_identity.read_tracked_head_blob(repository, relative)
    assert payload == b'{"value":1}\n'
    assert identity.repository_relative_path == relative


def test_read_only_source_can_be_verified_without_writing(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    source = _init_text_repository(repository)
    before = source.read_bytes()
    original_mode = source.stat().st_mode
    try:
        source.chmod(stat.S_IREAD)
        payload, identity = source_identity.read_tracked_head_blob(
            repository, "data/fixture.json"
        )
        assert payload == before
        assert identity.raw_worktree_sha256 == hashlib.sha256(before).hexdigest()
        assert source.read_bytes() == before
    finally:
        source.chmod(stat.S_IREAD | stat.S_IWRITE)
        source.chmod(original_mode | stat.S_IWRITE)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.json",
        "folder/../file.json",
        "C:/absolute.json",
        "/absolute.json",
        "folder\\file.json",
        "folder//file.json",
        "folder/./file.json",
        "folder\x00file.json",
    ],
)
def test_traversal_absolute_and_nonportable_git_paths_are_rejected(path: str) -> None:
    with pytest.raises(source_identity.SourceIdentityError):
        source_identity.validate_repository_relative_path(path)


def test_outside_repository_tracked_path_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_text_repository(repository)
    with pytest.raises(source_identity.SourceIdentityError):
        source_identity.read_tracked_head_blob(repository, str(tmp_path / "outside.json"))


def test_tracked_symlink_path_fails_closed_when_supported(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    source = _init_text_repository(repository)
    link = repository / "data" / "alias.json"
    try:
        link.symlink_to(source.name)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this Windows environment")
    _git(repository, "add", "data/alias.json")
    _git(repository, "commit", "--quiet", "-m", "tracked symlink")
    with pytest.raises(source_identity.SourceIdentityError, match="symlink"):
        source_identity.read_tracked_head_blob(repository, "data/alias.json")


def test_missing_git_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_text_repository(repository)

    def missing_git(*_args, **_kwargs):
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(source_identity.subprocess, "run", missing_git)
    with pytest.raises(source_identity.SourceIdentityError, match="local Git"):
        source_identity.read_tracked_head_blob(repository, "data/fixture.json")


def test_historical_portability_and_baseline_anchors_remain_exact() -> None:
    document = audit.load_receipt()
    for anchor in document["immutable_anchors"]:
        current = audit.current_anchor_identity(anchor)
        payload, identity = source_identity.read_tracked_head_blob(ROOT, anchor["path"])
        assert identity.git_blob_sha1 == current["git_blob_sha1"]
        assert identity.git_blob_payload_sha256 == current["git_blob_payload_sha256"]
        if anchor["canonical_sha256"] is not None:
            value = audit._read_json_bytes(payload, anchor["anchor_id"])
            if "canonical_sha256" in value:
                assert value["canonical_sha256"] == anchor["canonical_sha256"]
            else:
                assert hashlib.sha256(parity.canonical_json_bytes(value)).hexdigest() == anchor[
                    "canonical_sha256"
                ]


def test_current_audit_executes_immutable_canonical_anchor_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = {
        "anchor_id": "SYNTHETIC_CANONICAL_ANCHOR",
        "path": "synthetic/anchor.json",
        "git_blob_sha1": "a" * 40,
        "git_blob_payload_sha256": "b" * 64,
        "canonical_sha256": "1" * 64,
    }
    payload = b'{"canonical_sha256":"' + b"0" * 64 + b'"}\n'
    identity = source_identity.DevelopmentSourceIdentity(
        repository_relative_path=anchor["path"],
        git_blob_sha1=anchor["git_blob_sha1"],
        git_blob_payload_sha256=anchor["git_blob_payload_sha256"],
        filtered_worktree_git_blob_sha1=anchor["git_blob_sha1"],
        raw_worktree_sha256=hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(audit, "load_receipt", lambda: {"current_source_evolution": []})
    monkeypatch.setattr(audit, "validate_receipt", lambda _document: {})
    monkeypatch.setattr(audit, "EXPECTED_ANCHORS", (anchor,))
    monkeypatch.setattr(
        audit,
        "read_tracked_head_blob",
        lambda *_args, **_kwargs: (payload, identity),
    )

    with pytest.raises(audit.PortabilityAuditError, match="historical canonical identity changed"):
        audit.validate_current_state()


def test_current_platform_audit_is_offline_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network or provider operation is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    result = audit.validate_current_state()
    assert result["result"] == "PORT_01B_SOURCE_IDENTITY_PARITY_SKIP_SOURCE_MOVED"
    assert result["moved_paths"] == ["domain/canonical_core.py"]
    assert result["fixed_blocker_count"] == 10
    assert result["network_provider_delivery_calls"] == 0


def test_b2_current_source_drift_outside_b3_authorized_path_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {
        "path": "scripts/validate_main_shadow_authority_parity.py",
        "after_git_blob_sha1": "a" * 40,
        "after_git_blob_payload_sha256": "b" * 64,
    }
    identity = source_identity.DevelopmentSourceIdentity(
        repository_relative_path=row["path"],
        git_blob_sha1="c" * 40,
        git_blob_payload_sha256="d" * 64,
        filtered_worktree_git_blob_sha1="c" * 40,
        raw_worktree_sha256="e" * 64,
    )
    monkeypatch.setattr(audit, "load_receipt", lambda: {"current_source_evolution": [row]})
    monkeypatch.setattr(audit, "validate_receipt", lambda _document: {})
    monkeypatch.setattr(audit, "EXPECTED_ANCHORS", ())
    monkeypatch.setattr(audit, "read_tracked_head_blob", lambda *_args, **_kwargs: (b"", identity))
    with pytest.raises(audit.PortabilityAuditError, match="current source identity changed"):
        audit.validate_current_state()


def test_canonical_core_uses_same_tracked_identity_for_unchanged_component() -> None:
    from domain import provider_market_semantics
    from domain import canonical_core

    _payload, identity = source_identity.read_tracked_head_blob(
        ROOT, Path(provider_market_semantics.__file__).resolve().relative_to(ROOT).as_posix()
    )
    assert canonical_core._git_blob_sha(provider_market_semantics) == identity.git_blob_sha1


def test_no_b2_test_probes_provider_or_delivery_transports(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external transport must remain unused")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(live_quote, "_network_fetch", forbidden)
    assert audit.validate_receipt(audit.load_receipt())["fixed_blocker_count"] == 10
