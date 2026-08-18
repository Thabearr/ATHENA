from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_user_controlled_evidence as manual
from scripts import import_sportybet_user_controlled_evidence as command


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
RAW = b'''<!doctype html><html><body>
<a href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=18&outcomeId=12&odds=1.85&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main&specifier=total%3D2.5">Over 2.5</a>
</body></html>'''


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_build_manifest_preserves_manual_provenance_without_quote_authority() -> None:
    manifest = manual.build_manifest(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
    )
    data = manifest.to_dict()
    assert data["acquisition_mode"] == "USER_CONTROLLED_BROWSER_EXPORT"
    assert data["observation_authority"] == "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
    assert data["athena_network_acquisition_performed"] is False
    assert data["provider_quote_at"] is None
    assert data["provider_snapshot_id"] is None
    assert all(value is False for value in data["safety"].values())
    assert data["request_target"] == (
        "/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&"
        "marketGroupsName=Main&sportId=sr%3Asport%3A1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sportybet.com/ng/lite",
        "https://sportybet.com/ng/lite",
        "https://www.sportybet.com:443/ng/lite",
        "https://user@www.sportybet.com/ng/lite",
        "https://www.sportybet.com/ng/lite#frag",
        "https://www.sportybet.com/ng/lite?x=1",
        "https://www.sportybet.com/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketGroupsName=Main",
        "https://www.sportybet.com/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1&sportId=sr%3Asport%3A1",
        "https://www.sportybet.com/ng/lite/preMatch/detail?marketGroupsName=Main&eventId=sr%3Amatch%3A123&sportId=sr%3Asport%3A1",
        "https://www.sportybet.com/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketGroupsName=Other&sportId=sr%3Asport%3A1",
        "https://www.sportybet.com/ng/not-reviewed",
    ],
)
def test_source_url_fails_closed_outside_exact_reviewed_identity(url: str) -> None:
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.validate_source_url(url)


def test_import_time_cannot_precede_user_observation() -> None:
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.build_manifest(
            RAW,
            source_url=DETAIL_URL,
            observed_at_user_attested=IMPORTED,
            imported_at_utc=OBSERVED,
            attestation=manual.ATTESTATION,
        )


def test_attestation_is_exact() -> None:
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.build_manifest(
            RAW,
            source_url=DETAIL_URL,
            observed_at_user_attested=OBSERVED,
            imported_at_utc=IMPORTED,
            attestation="yes I saw it",
        )


def test_store_verify_and_idempotent_replay(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    directory, first = manual.store_user_controlled_evidence(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    assert directory.parent == repo / manual.ALLOWED_OUTPUT_RELATIVE
    verified = manual.verify_evidence_directory(directory, allowed_root=directory.parent)
    assert verified.to_dict() == first.to_dict()
    same_directory, second = manual.store_user_controlled_evidence(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    assert same_directory == directory
    assert second.to_dict() == first.to_dict()


def test_tampered_raw_bytes_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    directory, _ = manual.store_user_controlled_evidence(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    (directory / manual.RAW_FILENAME).write_bytes(RAW + b" ")
    with pytest.raises(manual.SportyBetUserEvidenceError, match="identity mismatch"):
        manual.verify_evidence_directory(directory, allowed_root=directory.parent)


def test_noncanonical_or_extra_manifest_state_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    directory, _ = manual.store_user_controlled_evidence(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    manifest_path = directory / manual.MANIFEST_FILENAME
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    parsed["unexpected"] = True
    manifest_path.write_text(json.dumps(parsed), encoding="utf-8")
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.verify_evidence_directory(directory, allowed_root=directory.parent)


def test_output_root_traversal_and_wrong_root_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    kwargs = dict(
        raw_html=RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.store_user_controlled_evidence(
            **kwargs,
            output_root=Path("../escape"),
        )
    with pytest.raises(manual.SportyBetUserEvidenceError):
        manual.store_user_controlled_evidence(
            **kwargs,
            output_root=Path(".cache/athena-research/sportybet-live-source-captures"),
        )


def test_symlink_html_input_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_bytes(RAW)
    link = tmp_path / "link.html"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(manual.SportyBetUserEvidenceError, match="symlink"):
        manual.read_user_html(link)


def test_command_imports_offline_and_receipt_keeps_all_authority_false(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    html = tmp_path / "page.html"
    html.write_bytes(RAW)
    receipt = command.import_evidence(
        html_file=html,
        source_url=DETAIL_URL,
        observed_at="2026-08-18T12:00:00Z",
        attestation=manual.ATTESTATION,
        repository_root=repo,
        imported_at_utc=IMPORTED,
    )
    assert receipt["status"] == "USER_CONTROLLED_EVIDENCE_PRESERVED"
    assert receipt["athena_network_acquisition_performed"] is False
    assert receipt["network_acquisition_authorized"] is False
    assert receipt["provider_quote_at"] is None
    assert receipt["provider_snapshot_id"] is None
    for key in (
        "fresh_price_authorized",
        "pricing_authorized",
        "selection_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    ):
        assert receipt[key] is False


def test_command_rejects_wrong_attestation_before_storage(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    html = tmp_path / "page.html"
    html.write_bytes(RAW)
    with pytest.raises(manual.SportyBetUserEvidenceError):
        command.import_evidence(
            html_file=html,
            source_url=DETAIL_URL,
            observed_at="2026-08-18T12:00:00Z",
            attestation="wrong",
            repository_root=repo,
            imported_at_utc=IMPORTED,
        )
    assert not (repo / manual.ALLOWED_OUTPUT_RELATIVE).exists()


def test_module_contains_no_network_client_imports() -> None:
    source = Path(manual.__file__).read_text(encoding="utf-8")
    script = Path(command.__file__).read_text(encoding="utf-8")
    forbidden = (
        "urllib.request",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "socket.create_connection",
    )
    for token in forbidden:
        assert token not in source
        assert token not in script
