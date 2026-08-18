from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_event_identity_verification as verify
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
PROTOCOL = Path(
    "artifacts/research-protocols/sportybet-sportradar-event-identity-v1.json"
)


def _detail_url(*, event_id: int = 123, sport_id: int = 1) -> str:
    return (
        "https://www.sportybet.com/ng/lite/preMatch/detail?"
        f"eventId=sr%3Amatch%3A{event_id}&marketGroupsName=Main&"
        f"sportId=sr%3Asport%3A{sport_id}"
    )


def _raw(*, event_id: int = 123, sport_id: int = 1) -> bytes:
    return f'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>Example Country - Example League</h1>
<div class="date">18/08 Tuesday</div><div class="time">20:00</div>
<div class="home">Example Home FC</div><div class="away">Example Away FC</div>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A{event_id}&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A{sport_id}&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A{event_id}&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A{sport_id}&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A{event_id}&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A{sport_id}&marketGroupsName=Main">Away</a>
</body></html>'''.encode("utf-8")


def _source(tmp_path: Path, *, event_id: int = 123, sport_id: int = 1):
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = _raw(event_id=event_id, sport_id=sport_id)
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        raw,
        source_url=_detail_url(event_id=event_id, sport_id=sport_id),
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    return manifest, inventory, raw


def _build(tmp_path: Path):
    manifest, inventory, raw = _source(tmp_path)
    value = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    return value, manifest, inventory, raw


def test_protocol_is_canonical_and_keeps_all_downstream_authority_false() -> None:
    raw = PROTOCOL.read_bytes()
    payload = json.loads(raw)
    canonical = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert raw == canonical
    assert payload["schema_version"] == 1
    assert payload["status"] == bridge.STATUS
    assert payload["legacy_sport_event_prefix"] == "sr:match:"
    assert payload["current_sport_event_prefix"] == "sr:sport_event:"
    assert payload["soccer_sport_id"] == "sr:sport:1"
    assert payload["numeric_identifier_preserved_across_prefix_migration"] is True
    assert payload["soccer_match_sport_event_identifier_uniqueness_documented"] is True
    assert payload["requires_exact_pr156_event_rederivation"] is True
    assert payload["requires_exact_bridge_rederivation_at_consumption"] is True
    assert payload["event_metadata_resolved"] is False
    assert payload["sportybet_year_capability"] == "UNPROVEN"
    assert payload["sportybet_kickoff_utc_capability"] == "UNPROVEN"
    assert payload["sportradar_network_resolution_authorized"] is False
    assert all(value is False for value in payload["safety"].values())


def test_documentation_contract_is_frozen_and_canonical() -> None:
    assert bridge.documentation_contract_sha256() == bridge.DOCUMENTATION_CONTRACT_SHA256
    payload = json.loads(bridge.documentation_contract_bytes())
    assert payload == bridge.documentation_contract()
    assert payload["legacy_sport_event_prefix"] == "sr:match:"
    assert payload["current_sport_event_prefix"] == "sr:sport_event:"
    assert payload["numeric_identifier_preserved_across_prefix_migration"] is True
    assert payload["soccer_match_sport_event_identifier_uniqueness_documented"] is True


def test_exact_sportybet_event_id_becomes_documented_sportradar_resolver_key(
    tmp_path: Path,
) -> None:
    value, manifest, inventory, raw = _build(tmp_path)
    source_candidate = header.build_machine_event_header_candidate(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    assert value.source_event_candidate_sha256 == header.candidate_sha256(source_candidate)
    assert value.sportybet_event_id == "sr:match:123"
    assert value.sportybet_sport_id == "sr:sport:1"
    assert value.sportradar_numeric_event_id == 123
    assert value.sportradar_legacy_sport_event_id == "sr:match:123"
    assert value.sportradar_current_sport_event_id == "sr:sport_event:123"
    assert value.sportradar_namespace_qualified is True
    assert value.numeric_identifier_preserved is True
    assert value.soccer_match_identifier_uniqueness_documented is True
    assert value.event_metadata_resolved is False
    assert value.fixture_identity_proven is False
    assert value.sportybet_kickoff_year is None
    assert value.sportybet_kickoff_utc is None
    assert value.safety["sportradar_metadata_resolution_authorized"] is False
    assert all(item is False for item in value.safety.values())


def test_bridge_is_deterministic(tmp_path: Path) -> None:
    value, manifest, inventory, raw = _build(tmp_path)
    again = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    assert bridge.canonical_bridge_bytes(value) == bridge.canonical_bridge_bytes(again)
    assert bridge.bridge_sha256(value) == bridge.bridge_sha256(again)


def test_consumption_verifier_rebuilds_exact_bridge(tmp_path: Path) -> None:
    value, manifest, inventory, raw = _build(tmp_path)
    rebuilt = verify.revalidate_sportradar_event_identity_bridge(
        value,
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    assert bridge.canonical_bridge_bytes(rebuilt) == bridge.canonical_bridge_bytes(value)


def test_non_soccer_sport_id_fails_closed(tmp_path: Path) -> None:
    manifest, inventory, raw = _source(tmp_path, sport_id=2)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="soccer",
    ):
        bridge.build_sportradar_event_identity_bridge(
            manifest=manifest,
            inventory=inventory,
            raw_html=raw,
        )


def test_tampered_raw_html_cannot_reuse_verified_inventory(tmp_path: Path) -> None:
    manifest, inventory, raw = _source(tmp_path)
    tampered = raw.replace(b"Example Home FC", b"Forged Home FC", 1)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        bridge.build_sportradar_event_identity_bridge(
            manifest=manifest,
            inventory=inventory,
            raw_html=tampered,
        )
