from __future__ import annotations

import dataclasses
import datetime as dt
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
OTHER_DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A999&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)


def _event_raw() -> bytes:
    return b'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>Example Country - Example League</h1>
<div>18/08 Tuesday</div><div>20:00</div>
<div>Example Home FC</div><div>Example Away FC</div>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Away</a>
</body></html>'''


def _terms_raw() -> bytes:
    return (
        "<!doctype html><html><body><p>"
        + terms.EXPECTED_STATEMENT
        + "</p></body></html>"
    ).encode("utf-8")


def _result(tmp_path: Path) -> local.SportyBetEventLocalTimeBasis:
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = _event_raw()
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        raw,
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
    terms_raw = _terms_raw()
    qualification = terms.build_qualification(
        terms_raw,
        source_url=terms.SOURCE_URL,
        observed_at_user_attested=TERMS_OBSERVED,
        imported_at_utc=TERMS_IMPORTED,
        attestation=terms.ATTESTATION,
    )
    return local.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )


def test_embedded_event_source_url_cannot_drift_to_another_valid_event(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="event source URL does not match provider event/sport identity",
    ):
        dataclasses.replace(result, event_source_url=OTHER_DETAIL_URL)


def test_embedded_event_id_cannot_drift_from_exact_source_url(tmp_path: Path) -> None:
    result = _result(tmp_path)
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="event source URL does not match provider event/sport identity",
    ):
        dataclasses.replace(result, event_id="sr:match:999")


def test_embedded_terms_source_url_cannot_drift(tmp_path: Path) -> None:
    result = _result(tmp_path)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(
            result,
            terms_source_url="https://www.sportybet.com/ng/help?nav=sports",
        )


def test_embedded_terms_rule_hash_is_exact_not_merely_hash_shaped(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    with pytest.raises(
        local.SportyBetEventLocalTimeBasisError,
        match="terms_rule_sha256 mismatch",
    ):
        dataclasses.replace(result, terms_rule_sha256="0" * 64)


def test_embedded_header_display_and_scalar_components_must_reconcile(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, kickoff_minute=1)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, home_display=result.away_display)


def test_embedded_kickoff_display_cannot_be_forged_independently(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    with pytest.raises(local.SportyBetEventLocalTimeBasisError):
        dataclasses.replace(result, kickoff_display="18/08 Tuesday 20:01")
