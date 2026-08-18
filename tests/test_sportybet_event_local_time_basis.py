from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_event_local_time_basis as local
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


UTC = dt.timezone.utc
EVENT_OBSERVED = dt.datetime(2026, 8, 18, 17, 0, tzinfo=UTC)
EVENT_IMPORTED = dt.datetime(2026, 8, 18, 17, 1, tzinfo=UTC)
TERMS_OBSERVED = dt.datetime(2026, 8, 18, 16, 55, tzinfo=UTC)
TERMS_IMPORTED = dt.datetime(2026, 8, 18, 16, 56, tzinfo=UTC)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
PROTOCOL = Path(
    "artifacts/research-protocols/sportybet-event-local-time-basis-v1.json"
)


def _event_raw(*, extra_visible: str = "", extra_hidden: str = "") -> bytes:
    return f'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>Example Country - Example League</h1>
<div class="date">18/08 Tuesday</div><div class="time">20:00</div>
<div class="home">Example Home FC</div><div class="away">Example Away FC</div>
{extra_visible}
<script>{extra_hidden}</script>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Away</a>
</body></html>'''.encode("utf-8")


def _terms_raw() -> bytes:
    return (
        "<!doctype html><html><body><h1>Terms &amp; Conditions</h1><p>"
        + terms.EXPECTED_STATEMENT
        + "</p></body></html>"
    ).encode("utf-8")


def _event_source(tmp_path: Path, *, raw: bytes | None = None):
    repo = tmp_path / "repo"
    repo.mkdir()
    event_raw = _event_raw() if raw is None else raw
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        event_raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=EVENT_OBSERVED,
        imported_at_utc=EVENT_IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    return repo, manifest, inventory, event_raw


def _terms_qualification(
    *,
    observed: dt.datetime = TERMS_OBSERVED,
    imported: dt.datetime = TERMS_IMPORTED,
    raw: bytes | None = None,
):
    terms_raw = _terms_raw() if raw is None else raw
    qualification = terms.build_qualification(
        terms_raw,
        source_url=terms.SOURCE_URL,
        observed_at_user_attested=observed,
        imported_at_utc=imported,
        attestation=terms.ATTESTATION,
    )
    return qualification, terms_raw


def _build(tmp_path: Path, *, event_raw: bytes | None = None):
    _, manifest, inventory, raw = _event_source(tmp_path, raw=event_raw)
    qualification, terms_raw = _terms_qualification()
    result = local.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    return result, manifest, inventory, raw, qualification, terms_raw


def test_protocol_is_canonical_and_keeps_downstream_authority_false() -> None:
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
    assert payload["qualified_time_zone_label"] == "GMT"
    assert payload["utc_offset_seconds"] == 0
    assert payload["max_terms_age_microseconds"] == 3_600_000_000
    assert payload["terms_must_not_postdate_event_observation"] is True
    assert payload["requires_exact_pr156_event_rederivation"] is True
    assert payload["requires_exact_pr157_terms_rederivation"] is True
    assert payload["event_year_capability"] == "UNPROVEN"
    assert payload["kickoff_utc_capability"] == "UNPROVEN_UNTIL_YEAR"
    assert payload["network_acquisition_authorized"] is False
    assert all(value is False for value in payload["safety"].values())


def test_compatible_exact_evidence_qualifies_event_display_clock_as_gmt(
    tmp_path: Path,
) -> None:
    result, _, _, _, _, _ = _build(tmp_path)
    assert result.status == local.STATUS
    assert result.event_id == "sr:match:123"
    assert result.sport_id == "sr:sport:1"
    assert result.kickoff_display == "18/08 Tuesday 20:00"
    assert result.kickoff_timezone == "GMT"
    assert result.utc_offset_seconds == 0
    assert result.kickoff_year is None
    assert result.kickoff_utc is None
    assert result.specific_event_time_basis_qualified is True
    assert result.event_local_override_marker_count == 0
    assert result.event_local_override_scan_status == local.OVERRIDE_SCAN_STATUS
    assert result.terms_age_microseconds == 300_000_000
    assert result.provider_quote_at is None
    assert result.provider_snapshot_id is None
    assert all(value is False for value in result.safety.values())


def test_terms_observation_must_not_postdate_event_observation(tmp_path: Path) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    observed = EVENT_OBSERVED + dt.timedelta(seconds=1)
    qualification, terms_raw = _terms_qualification(
        observed=observed,
        imported=observed + dt.timedelta(seconds=1),
    )
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="must not postdate",
    ):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
        )


def test_terms_observation_older_than_one_hour_fails_closed(tmp_path: Path) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    observed = EVENT_OBSERVED - dt.timedelta(hours=1, microseconds=1)
    qualification, terms_raw = _terms_qualification(
        observed=observed,
        imported=observed + dt.timedelta(seconds=1),
    )
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="older than the frozen compatibility window",
    ):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
        )


def test_exact_one_hour_terms_age_is_allowed(tmp_path: Path) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    observed = EVENT_OBSERVED - dt.timedelta(hours=1)
    qualification, terms_raw = _terms_qualification(
        observed=observed,
        imported=observed + dt.timedelta(seconds=1),
    )
    result = local.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    assert result.terms_age_microseconds == local.MAX_TERMS_AGE_MICROSECONDS


@pytest.mark.parametrize(
    "marker",
    [
        "<div>WAT</div>",
        "<div>GMT</div>",
        "<div>UTC+01:00</div>",
        "<div>Africa/Lagos</div>",
        "<div>Local Time</div>",
        "<div>Times shown are local</div>",
    ],
)
def test_any_reviewed_visible_event_time_basis_marker_fails_closed(
    tmp_path: Path,
    marker: str,
) -> None:
    raw = _event_raw(extra_visible=marker)
    _, manifest, inventory, event_raw = _event_source(tmp_path, raw=raw)
    qualification, terms_raw = _terms_qualification()
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="separate review required",
    ):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
        )


def test_script_only_time_basis_decoy_is_not_visible_override_evidence(
    tmp_path: Path,
) -> None:
    raw = _event_raw(extra_hidden="WAT UTC+01:00 Africa/Lagos Local Time")
    result, _, _, _, _, _ = _build(tmp_path, event_raw=raw)
    assert result.specific_event_time_basis_qualified is True
    assert result.event_local_override_marker_count == 0


def test_forged_terms_qualification_is_rejected_by_exact_rederivation(
    tmp_path: Path,
) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    qualification, terms_raw = _terms_qualification()
    forged = dataclasses.replace(qualification, raw_sha256="0" * 64)
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="exact deterministic derivative",
    ):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=forged,
            terms_raw_html=terms_raw,
        )


def test_tampered_terms_raw_html_is_rejected(tmp_path: Path) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    qualification, terms_raw = _terms_qualification()
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw + b" ",
        )


def test_event_inventory_lineage_is_revalidated_by_pr156_boundary(
    tmp_path: Path,
) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    qualification, terms_raw = _terms_qualification()
    forged = dataclasses.replace(inventory, source_raw_sha256="0" * 64)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=forged,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
        )


def test_event_raw_tampering_is_rejected_before_time_basis_application(
    tmp_path: Path,
) -> None:
    _, manifest, inventory, event_raw = _event_source(tmp_path)
    qualification, terms_raw = _terms_qualification()
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        local.build_event_local_time_basis(
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw + b" ",
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
        )


def test_canonical_artifact_and_hash_are_deterministic(tmp_path: Path) -> None:
    result, manifest, inventory, event_raw, qualification, terms_raw = _build(tmp_path)
    second = local.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    first_bytes = local.canonical_time_basis_bytes(result)
    assert first_bytes == local.canonical_time_basis_bytes(second)
    assert local.time_basis_sha256(result) == local.time_basis_sha256(second)
    assert first_bytes.endswith(b"\n")
    payload = json.loads(first_bytes)
    assert payload["kickoff_timezone"] == "GMT"
    assert payload["kickoff_year"] is None
    assert payload["kickoff_utc"] is None
    assert payload["specific_event_time_basis_qualified"] is True
    assert all(value is False for value in payload["safety"].values())


def test_bool_cannot_impersonate_exact_numeric_fields(tmp_path: Path) -> None:
    result, _, _, _, _, _ = _build(tmp_path)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, terms_age_microseconds=True)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, event_local_override_marker_count=False)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, utc_offset_seconds=False)


def test_year_and_utc_cannot_be_forged_after_qualification(tmp_path: Path) -> None:
    result, _, _, _, _, _ = _build(tmp_path)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, kickoff_year=2026)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, kickoff_utc="2026-08-18T20:00:00Z")


def test_betting_authority_cannot_be_forged_after_qualification(tmp_path: Path) -> None:
    result, _, _, _, _, _ = _build(tmp_path)
    safety = dict(result.safety)
    safety["fixture_reconciliation_authorized"] = True
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, safety=safety)
    safety = dict(result.safety)
    safety["bet_authorized"] = True
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, safety=safety)
