from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from domain import run_contracts as contracts


UTC = timezone.utc
NOW = datetime(2026, 9, 10, 13, 0, 1, 123456, tzinfo=UTC)
SHA = "a" * 40


def _request(**overrides):
    values = {
        "dates": (date(2026, 9, 11), date(2026, 9, 10)),
        "target_legs": 25,
        "target_total_odds": None,
        "bookie": "sportybet",
        "mode": "research_shadow",
        "authority_profile": "SHADOW",
        "create_share_code": True,
        "place_wager": False,
    }
    values.update(overrides)
    return contracts.RunRequest(**values)


def _manifest(**overrides):
    values = {
        "authority_profile": "SHADOW",
        "mode": "research_shadow",
        "provider_acquisition": True,
        "share_code_generation": True,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
        "additional_capabilities": {"production_selection": False},
    }
    values.update(overrides)
    return contracts.AuthorityManifest(**values)


def _receipt(**overrides):
    request = overrides.pop("request", _request(target_legs=2))
    values = {
        "status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
        "observed_at": NOW,
        "exact_commit_sha": SHA,
        "request": request,
        "stages": (
            contracts.RunStage(
                stage="PRICE_ALL_ROUTER",
                status="COMPLETED",
                observed_at=NOW,
                counts={"priced_fixture_count": 3},
                evidence={"source": {"sha256": "b" * 64}},
            ),
        ),
        "counts": {"selected_leg_count": 1, "priced_fixture_count": 3},
        "selected_legs": ({"leg_id": "L1", "market": {"id": "MATCH_RESULT"}},),
        "shortfall": 1,
        "share_code_result": {
            "verified": True,
            "share_code": "ABC123",
            "share_url": "https://example.test/ABC123",
        },
        "authority_manifest": _manifest(),
        "evidence": {"source_artifacts": [{"sha256": "c" * 64}]},
        "wager_placed": False,
    }
    values.update(overrides)
    return contracts.RunReceipt(**values)


def test_run_request_uses_concrete_sorted_dates_and_exact_target_semantics():
    request = _request()
    assert request.dates == (date(2026, 9, 10), date(2026, 9, 11))
    assert request.target_legs == 25
    assert request.target_total_odds is None
    assert request.to_dict()["dates"] == ["2026-09-10", "2026-09-11"]
    assert request.to_dict()["place_wager"] is False


def test_target_total_odds_is_separate_decimal_objective_not_target_legs():
    request = _request(target_legs=25, target_total_odds=Decimal("125.5000"))
    payload = request.to_dict()
    assert payload["target_legs"] == 25
    assert payload["target_total_odds"] == "125.5"
    rebuilt = contracts.RunRequest.from_json_bytes(contracts.canonical_json_bytes(request))
    assert rebuilt.target_legs == 25
    assert rebuilt.target_total_odds == Decimal("125.5")


@pytest.mark.parametrize("target", [0, 51, True, 2.5, "25"])
def test_run_request_rejects_invalid_target_legs(target):
    with pytest.raises(contracts.RunContractError):
        _request(target_legs=target)


def test_run_request_rejects_duplicate_or_more_than_seven_dates():
    with pytest.raises(contracts.RunContractError):
        _request(dates=(date(2026, 9, 10), date(2026, 9, 10)))
    with pytest.raises(contracts.RunContractError):
        _request(dates=tuple(date(2026, 9, day) for day in range(10, 18)))


def test_run_request_rejects_datetime_in_date_contract():
    with pytest.raises(contracts.RunContractError):
        _request(dates=(datetime(2026, 9, 10, tzinfo=UTC),))


@pytest.mark.parametrize("bookie", ["SportyBet", " sportybet", "sporty bet", ""])
def test_run_request_rejects_noncanonical_delivery_adapter_id(bookie):
    with pytest.raises(contracts.RunContractError):
        _request(bookie=bookie)


def test_run_request_rejects_wager_request():
    with pytest.raises(contracts.RunContractError, match="wager"):
        _request(place_wager=True)


def test_run_request_canonical_round_trip_is_byte_exact_and_deterministic():
    request = _request(target_total_odds=Decimal("20.250"))
    first = contracts.canonical_json_bytes(request)
    second = contracts.canonical_json_bytes(request)
    assert first == second
    assert first.endswith(b"\n")
    assert contracts.RunRequest.from_json_bytes(first) == request
    assert contracts.canonical_sha256(request) == request.canonical_sha256


def test_run_request_strict_parser_rejects_extra_duplicate_nonfinite_and_noncanonical_bytes():
    payload = _request().to_dict()
    payload["extra"] = True
    with pytest.raises(contracts.RunContractError):
        contracts.RunRequest.from_dict(payload)

    raw = contracts.canonical_json_bytes(_request())
    duplicate = raw[:-2] + b',"target_legs":25}\n'
    with pytest.raises(contracts.RunContractError, match="duplicate"):
        contracts.RunRequest.from_json_bytes(duplicate)

    nonfinite = raw.replace(b'"target_legs":25', b'"target_legs":NaN')
    with pytest.raises(contracts.RunContractError, match="non-finite"):
        contracts.RunRequest.from_json_bytes(nonfinite)

    pretty = json.dumps(_request().to_dict(), indent=2, sort_keys=True).encode() + b"\n"
    with pytest.raises(contracts.RunContractError, match="not canonical"):
        contracts.RunRequest.from_json_bytes(pretty)


def test_run_request_parser_rejects_boolean_schema_version():
    payload = _request().to_dict()
    payload["schema_version"] = True
    with pytest.raises(contracts.RunContractError, match="schema"):
        contracts.RunRequest.from_dict(payload)


def test_run_request_from_dict_rejects_noncanonical_date_order_and_decimal_text():
    payload = _request().to_dict()
    payload["dates"] = list(reversed(payload["dates"]))
    with pytest.raises(contracts.RunContractError, match="canonical normalized"):
        contracts.RunRequest.from_dict(payload)

    payload = _request(target_total_odds=Decimal("2.5")).to_dict()
    payload["target_total_odds"] = "2.500"
    with pytest.raises(contracts.RunContractError, match="canonical decimal"):
        contracts.RunRequest.from_dict(payload)


def test_authority_manifest_is_immutable_and_all_profiles_deny_sensitive_capabilities_in_p1_1():
    source = {"production_selection": False}
    manifest = _manifest(additional_capabilities=source)
    source["production_selection"] = True
    assert manifest.additional_capabilities["production_selection"] is False
    with pytest.raises(TypeError):
        manifest.additional_capabilities["x"] = True
    for profile in ("SHADOW", "MAIN"):
        for field in ("login", "cookies", "wallet", "staking", "wager"):
            with pytest.raises(contracts.RunContractError):
                _manifest(authority_profile=profile, **{field: True})


def test_authority_manifest_preserves_safe_research_capabilities_but_rejects_smuggled_authority():
    manifest = _manifest(
        additional_capabilities={
            "research_shadow_price_all": True,
            "provider_create_reload_verification": True,
            "production_selection": False,
            "bet": False,
        }
    )
    assert manifest.additional_capabilities["research_shadow_price_all"] is True
    assert manifest.additional_capabilities["provider_create_reload_verification"] is True

    for capability in (
        "production_selection",
        "phase6",
        "bet",
        "place_wager",
        "stake_submitted",
        "wallet_read",
        "login_session",
    ):
        with pytest.raises(contracts.RunContractError, match="production/sensitive"):
            _manifest(additional_capabilities={capability: True})


def test_authority_manifest_rejects_conflicting_duplicate_canonical_capability():
    with pytest.raises(contracts.RunContractError, match="contradicts canonical"):
        _manifest(
            share_code_generation=True,
            additional_capabilities={"share_code_generation": False},
        )
    manifest = _manifest(
        share_code_generation=True,
        additional_capabilities={"share_code_generation": True},
    )
    assert manifest.additional_capabilities["share_code_generation"] is True


def test_run_stage_normalizes_utc_and_freezes_nested_evidence():
    source = {"nested": {"items": [1, 2]}}
    stage = contracts.RunStage(
        stage="PORTFOLIO",
        status="COMPLETED",
        observed_at=datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc),
        counts={"selected": 1},
        evidence=source,
    )
    source["nested"]["items"].append(3)
    assert stage.to_dict()["evidence"] == {"nested": {"items": [1, 2]}}
    assert len(stage.canonical_sha256) == 64
    with pytest.raises(TypeError):
        stage.evidence["x"] = 1


def test_run_stage_and_receipt_require_mapping_evidence_surfaces():
    with pytest.raises(contracts.RunContractError, match="mapping"):
        contracts.RunStage(stage="PORTFOLIO", status="COMPLETED", evidence=[])
    with pytest.raises(contracts.RunContractError, match="share_code_result"):
        _receipt(share_code_result="ABC123")
    with pytest.raises(contracts.RunContractError, match="receipt evidence"):
        _receipt(evidence=[])


def test_run_receipt_round_trip_carries_stage_counts_legs_shortfall_delivery_and_authority():
    receipt = _receipt()
    raw = contracts.canonical_json_bytes(receipt)
    rebuilt = contracts.RunReceipt.from_json_bytes(raw)
    assert rebuilt.to_dict() == receipt.to_dict()
    assert rebuilt.counts["selected_leg_count"] == 1
    assert rebuilt.shortfall == 1
    assert rebuilt.share_code_result["verified"] is True
    assert rebuilt.authority_manifest.authority_profile == "SHADOW"
    assert rebuilt.to_dict()["stage_digests"] == [receipt.stages[0].canonical_sha256]
    assert rebuilt.wager_placed is False


def test_run_receipt_rejects_tampered_stage_digest():
    payload = _receipt().to_dict()
    payload["stage_digests"][0] = "0" * 64
    with pytest.raises(contracts.RunContractError, match="stage digests"):
        contracts.RunReceipt.from_dict(payload)


def test_run_receipt_parser_rejects_boolean_schema_version():
    payload = _receipt().to_dict()
    payload["schema_version"] = True
    with pytest.raises(contracts.RunContractError, match="schema"):
        contracts.RunReceipt.from_dict(payload)


def test_run_receipt_deep_freezes_selected_legs_share_result_and_evidence():
    leg = {"leg_id": "L1", "nested": {"values": [1]}}
    delivery = {"verified": True, "nested": {"values": [2]}}
    evidence = {"nested": {"values": [3]}}
    receipt = _receipt(selected_legs=(leg,), share_code_result=delivery, evidence=evidence)
    leg["nested"]["values"].append(9)
    delivery["nested"]["values"].append(9)
    evidence["nested"]["values"].append(9)
    payload = receipt.to_dict()
    assert payload["selected_legs"][0]["nested"]["values"] == [1]
    assert payload["share_code_result"]["nested"]["values"] == [2]
    assert payload["evidence"]["nested"]["values"] == [3]


def test_run_receipt_rejects_fabricated_shortfall_or_selected_count():
    with pytest.raises(contracts.RunContractError, match="shortfall"):
        _receipt(shortfall=0)
    with pytest.raises(contracts.RunContractError, match="selected_leg_count"):
        _receipt(counts={"selected_leg_count": 2})


def test_run_receipt_rejects_profile_mode_mismatch_and_wager_result():
    with pytest.raises(contracts.RunContractError, match="profile/mode"):
        _receipt(authority_manifest=_manifest(mode="backtest"))
    with pytest.raises(contracts.RunContractError, match="wager"):
        _receipt(wager_placed=True)


def test_run_receipt_share_code_result_requires_request_intent_and_manifest_authority():
    disabled_request = _request(target_legs=2, create_share_code=False)
    with pytest.raises(contracts.RunContractError, match="disabled request delivery flag"):
        _receipt(request=disabled_request)

    with pytest.raises(contracts.RunContractError, match="share-code generation authority"):
        _receipt(authority_manifest=_manifest(share_code_generation=False))


def test_canonical_contract_module_has_no_legacy_or_current_shadow_import_dependency():
    path = Path(contracts.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("current_shadow" in name for name in imported)
    assert not any(name.startswith(("providers", "engine", "services", "intelligence")) for name in imported)
