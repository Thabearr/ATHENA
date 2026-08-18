from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)


def _raw(
    *,
    competition: str = "Example Country - Example League",
    date_text: str = "18/08 Tuesday",
    time_text: str = "20:00",
    home: str = "Example Home FC",
    away: str = "Example Away FC",
    combined_datetime: bool = False,
) -> bytes:
    when = (
        f"<div class='when'>{date_text} {time_text}</div>"
        if combined_datetime
        else (
            f"<div class='date'>{date_text}</div>"
            f"<div class='time'>{time_text}</div>"
        )
    )
    return f'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>{competition}</h1>
{when}
<div class="home">{home}</div>
<div class="away">{away}</div>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Away</a>
</body></html>'''.encode("utf-8")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _source(repo: Path, *, raw: bytes | None = None):
    raw = _raw() if raw is None else raw
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
    return evidence_dir, manifest, inventory, raw


def _candidate(tmp_path: Path):
    repo = _repo(tmp_path)
    _, manifest, inventory, raw = _source(repo)
    candidate = header.build_machine_event_header_candidate(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    return candidate, manifest, inventory, raw


def test_extracts_machine_visible_header_without_inventing_utc(
    tmp_path: Path,
) -> None:
    candidate, _, _, _ = _candidate(tmp_path)
    assert candidate.event_id == "sr:match:123"
    assert candidate.sport_id == "sr:sport:1"
    assert candidate.competition_display == "Example Country - Example League"
    assert candidate.home_display == "Example Home FC"
    assert candidate.away_display == "Example Away FC"
    assert candidate.kickoff_display == "18/08 Tuesday 20:00"
    assert (
        candidate.kickoff_day,
        candidate.kickoff_month,
        candidate.kickoff_weekday,
        candidate.kickoff_hour,
        candidate.kickoff_minute,
    ) == (18, 8, "Tuesday", 20, 0)
    assert candidate.kickoff_year is None
    assert candidate.kickoff_timezone is None
    assert candidate.kickoff_utc is None
    assert candidate.display_time_basis == header.DISPLAY_TIME_BASIS
    assert candidate.provider_quote_at is None
    assert candidate.provider_snapshot_id is None
    assert all(value is False for value in candidate.safety.values())
    assert candidate.safety["network_acquisition_authorized"] is False
    assert candidate.safety["booking_code_authorized"] is False


def test_combined_datetime_text_is_supported() -> None:
    extracted = header.extract_visible_event_header(
        _raw(combined_datetime=True)
    )
    assert extracted.kickoff_display == "18/08 Tuesday 20:00"
    assert extracted.home_display == "Example Home FC"
    assert extracted.away_display == "Example Away FC"


def test_script_and_style_decoys_are_ignored() -> None:
    raw = _raw().replace(
        b"<h1>",
        b"<script>19/08 Wednesday 21:00 Fake Home Fake Away</script>"
        b"<style>.x:after{content:'20/08 Thursday 22:00';}</style><h1>",
    )
    extracted = header.extract_visible_event_header(raw)
    assert extracted.kickoff_display == "18/08 Tuesday 20:00"


def test_repeated_identical_header_is_semantically_deduplicated() -> None:
    block = (
        b"<h2>Example Country - Example League</h2>"
        b"<div>18/08 Tuesday</div><div>20:00</div>"
        b"<div>Example Home FC</div><div>Example Away FC</div>"
    )
    raw = _raw().replace(b"</body>", block + b"</body>")
    extracted = header.extract_visible_event_header(raw)
    assert extracted.home_display == "Example Home FC"
    assert extracted.away_display == "Example Away FC"


def test_multiple_distinct_headers_fail_closed() -> None:
    raw = _raw().replace(
        b"</body>",
        b"<h2>Other League</h2><div>19/08 Wednesday</div><div>21:00</div>"
        b"<div>Other Home</div><div>Other Away</div></body>",
    )
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="multiple",
    ):
        header.extract_visible_event_header(raw)


def test_missing_header_fails_closed() -> None:
    raw = _raw().replace(b"18/08 Tuesday", b"Tuesday 18 August")
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="no unique",
    ):
        header.extract_visible_event_header(raw)


@pytest.mark.parametrize(
    ("date_text", "time_text"),
    [
        ("00/08 Tuesday", "20:00"),
        ("18/13 Tuesday", "20:00"),
        ("31/02 Tuesday", "20:00"),
        ("31/04 Tuesday", "20:00"),
        ("18/08 Tuesday", "24:00"),
        ("18/08 Tue", "20:00"),
    ],
)
def test_invalid_or_impossible_display_clock_fails_closed(
    date_text: str,
    time_text: str,
) -> None:
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        header.extract_visible_event_header(
            _raw(date_text=date_text, time_text=time_text)
        )


def test_february_29_is_not_rejected_without_a_proven_year() -> None:
    extracted = header.extract_visible_event_header(
        _raw(date_text="29/02 Thursday")
    )
    assert extracted.kickoff_day == 29
    assert extracted.kickoff_month == 2
    assert extracted.kickoff_year if hasattr(extracted, "kickoff_year") else True


def test_home_and_away_must_be_distinct() -> None:
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="no unique",
    ):
        header.extract_visible_event_header(
            _raw(home="Same FC", away="Same FC")
        )


def test_machine_extractor_does_not_case_fold_or_alias_names() -> None:
    extracted = header.extract_visible_event_header(
        _raw(home="Newcastle", away="Liverpool FC")
    )
    assert extracted.home_display == "Newcastle"
    assert extracted.away_display == "Liverpool FC"
    assert extracted.home_display != "Newcastle United"
    assert extracted.away_display != "Liverpool"


def test_visible_html_whitespace_is_render_collapsed_only() -> None:
    raw = _raw(
        competition="Example   League",
        home="Example   Home FC",
        away="Example Away   FC",
    )
    extracted = header.extract_visible_event_header(raw)
    assert extracted.competition_display == "Example League"
    assert extracted.home_display == "Example Home FC"
    assert extracted.away_display == "Example Away FC"


@pytest.mark.parametrize("raw", [b"", "not-bytes", b"\xff"])
def test_raw_html_must_be_bounded_utf8_bytes(raw: object) -> None:
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        header.visible_text_tokens(raw)


def test_event_detail_lineage_is_bound_to_exact_manifest_and_inventory(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _, manifest, inventory, raw = _source(repo)
    tampered = dataclasses.replace(
        inventory,
        source_raw_sha256="0" * 64,
    )
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="lineage",
    ):
        header.build_machine_event_header_candidate(
            manifest=manifest,
            inventory=tampered,
            raw_html=raw,
        )


def test_raw_byte_tampering_fails_before_header_extraction(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _, manifest, inventory, raw = _source(repo)
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="raw HTML",
    ):
        header.build_machine_event_header_candidate(
            manifest=manifest,
            inventory=inventory,
            raw_html=raw + b" ",
        )


def test_index_evidence_cannot_create_event_header_candidate(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    raw = _raw()
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        raw,
        source_url="https://www.sportybet.com/ng/lite",
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    with pytest.raises(
        header.SportyBetMachineEventHeaderError,
        match="event-detail",
    ):
        header.build_machine_event_header_candidate(
            manifest=manifest,
            inventory=inventory,
            raw_html=raw,
        )


def test_candidate_canonical_bytes_and_hash_are_deterministic(
    tmp_path: Path,
) -> None:
    candidate, manifest, inventory, raw = _candidate(tmp_path)
    second = header.build_machine_event_header_candidate(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    payload = header.canonical_candidate_bytes(candidate)
    assert payload == header.canonical_candidate_bytes(second)
    assert header.candidate_sha256(candidate) == header.candidate_sha256(second)
    assert payload.endswith(b"\n")
    parsed = json.loads(payload)
    assert parsed["kickoff_year"] is None
    assert parsed["kickoff_timezone"] is None
    assert parsed["kickoff_utc"] is None
    assert all(value is False for value in parsed["safety"].values())


def test_candidate_identity_fields_revalidate_source_url(
    tmp_path: Path,
) -> None:
    candidate, _, _, _ = _candidate(tmp_path)
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(candidate, source_evidence_id="not-an-evidence-id")
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(candidate, event_id="sr:match:999")
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(candidate, sport_id="sr:sport:2")
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(
            candidate,
            source_url="https://www.sportybet.com/ng/lite",
        )
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(candidate, event_id="bad")


def test_coordinated_candidate_tampering_is_rejected(
    tmp_path: Path,
) -> None:
    candidate, _, _, _ = _candidate(tmp_path)
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(
            candidate,
            kickoff_utc="2026-08-18T20:00:00Z",
        )
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(candidate, display_time_basis="GMT")
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(
            candidate,
            safety={
                **candidate.safety,
                "fixture_reconciliation_authorized": True,
            },
        )
    with pytest.raises(header.SportyBetMachineEventHeaderError):
        dataclasses.replace(
            candidate,
            safety={
                key: value
                for key, value in candidate.safety.items()
                if key != "network_acquisition_authorized"
            },
        )
