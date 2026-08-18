from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)


def _raw() -> bytes:
    return b'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>Example Country - Example League</h1>
<div class="date">18/08 Tuesday</div><div class="time">20:00</div>
<div class="home">Example Home FC</div><div class="away">Example Away FC</div>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Away</a>
</body></html>'''


def _build(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = _raw()
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    value = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    return value


def test_current_sportradar_id_must_preserve_exact_numeric_payload(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="preserve",
    ):
        dataclasses.replace(
            value,
            sportradar_current_sport_event_id="sr:sport_event:124",
        )


def test_numeric_event_id_must_equal_legacy_payload(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="numeric Sportradar event ID",
    ):
        dataclasses.replace(value, sportradar_numeric_event_id=124)


def test_legacy_id_must_equal_exact_sportybet_event_id(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="legacy Sportradar",
    ):
        dataclasses.replace(
            value,
            sportradar_legacy_sport_event_id="sr:match:124",
        )


def test_source_url_cannot_drift_from_emitted_event_identity(tmp_path) -> None:
    value = _build(tmp_path)
    changed = value.source_url.replace("%3A123", "%3A124")
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="source URL",
    ):
        dataclasses.replace(value, source_url=changed)


def test_documentation_contract_hash_is_exact_not_merely_hash_shaped(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="documentation_contract_sha256",
    ):
        dataclasses.replace(value, documentation_contract_sha256="0" * 64)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("migration_guide_url", "https://developer.sportradar.com/other"),
        ("id_handling_url", "https://developer.sportradar.com/other"),
        ("identifier_authority", "UNREVIEWED"),
    ],
)
def test_documentation_semantics_metadata_is_frozen(
    tmp_path,
    field: str,
    replacement: str,
) -> None:
    value = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: replacement})


@pytest.mark.parametrize(
    "field",
    [
        "numeric_identifier_preserved",
        "soccer_match_identifier_uniqueness_documented",
        "sportradar_namespace_qualified",
    ],
)
def test_documented_true_invariants_cannot_be_demoted(tmp_path, field: str) -> None:
    value = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: False})


@pytest.mark.parametrize(
    "field",
    ["event_metadata_resolved", "fixture_identity_proven"],
)
def test_unresolved_authority_cannot_be_promoted(tmp_path, field: str) -> None:
    value = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: True})


def test_year_and_utc_cannot_be_smuggled_into_namespace_bridge(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="year/UTC",
    ):
        dataclasses.replace(value, sportybet_kickoff_year=2026)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="year/UTC",
    ):
        dataclasses.replace(value, sportybet_kickoff_utc="2026-08-18T20:00:00Z")


def test_every_safety_authority_remains_exact_false(tmp_path) -> None:
    value = _build(tmp_path)
    for key in value.safety:
        promoted = dict(value.safety)
        promoted[key] = True
        with pytest.raises(
            bridge.SportyBetSportradarEventIdentityError,
            match="must be exact bool False",
        ):
            dataclasses.replace(value, safety=promoted)


def test_bridge_rejects_noncanonical_current_prefix(tmp_path) -> None:
    value = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(
            value,
            sportradar_current_sport_event_id="SR:SPORT_EVENT:123",
        )
