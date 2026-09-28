from __future__ import annotations

import ast
import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import urllib.request

import pytest

from domain import execution_envelope as envelope_contract
from domain.run_contracts import AuthorityManifest, RunRequest, canonical_json_bytes


UTC = timezone.utc
NOW = datetime(2026, 9, 22, 12, 30, 0, 123456, tzinfo=UTC)
EXPIRY = NOW + timedelta(minutes=30)
GIT_SHA = "a" * 40


def _request(*, profile="SHADOW", create_share_code=True, target_legs=20):
    mode = "main_application" if profile == "MAIN" else "research_shadow"
    return RunRequest(
        dates=(date(2026, 9, 23), date(2026, 9, 24)),
        target_legs=target_legs,
        target_total_odds=None,
        bookie="sportybet",
        mode=mode,
        authority_profile=profile,
        create_share_code=create_share_code,
        place_wager=False,
    )


def _manifest(
    *, profile="SHADOW", provider_acquisition=True, share_code_generation=True
):
    mode = "main_application" if profile == "MAIN" else "research_shadow"
    return AuthorityManifest(
        authority_profile=profile,
        mode=mode,
        provider_acquisition=provider_acquisition,
        share_code_generation=share_code_generation,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )


def _intent(*, acquire_sources=True, create_share_code=True, place_wager=False):
    return envelope_contract.RequestedOperationIntent(
        acquire_sources=acquire_sources,
        create_share_code=create_share_code,
        place_wager=place_wager,
    )


def _envelope(
    *,
    request=None,
    intent=None,
    manifest=None,
    source_identity=None,
    issued_at=NOW,
    expires_at=EXPIRY,
    timezone_id=envelope_contract.DATE_RESOLUTION_TIMEZONE_ID,
):
    selected_request = request or _request()
    selected_intent = intent or _intent(create_share_code=selected_request.create_share_code)
    selected_manifest = manifest or _manifest(
        profile=selected_request.authority_profile,
        provider_acquisition=True,
        share_code_generation=True,
    )
    return envelope_contract.ExecutionEnvelope.from_request_bytes(
        request_bytes=canonical_json_bytes(selected_request),
        requested_operations=selected_intent,
        authority_manifest=selected_manifest,
        source_identity=source_identity or envelope_contract.SourceReleaseIdentity("GIT_COMMIT", GIT_SHA),
        date_resolution_policy_id=envelope_contract.DATE_RESOLUTION_POLICY_ID,
        date_resolution_timezone_id=timezone_id,
        clock_policy_id=envelope_contract.PREVIEW_CLOCK_POLICY_ID,
        clock_observed_at=issued_at,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def test_execution_envelope_has_pinned_v2_identity_and_exact_canonical_round_trip():
    envelope = _envelope()
    first = envelope.canonical_bytes
    second = _envelope().canonical_bytes
    assert envelope_contract.EXECUTION_ENVELOPE_SCHEMA_VERSION == 2
    assert envelope_contract.EXECUTION_ENVELOPE_POLICY_ID == "ATHENA_EXECUTION_ENVELOPE_V2"
    assert envelope_contract.EXECUTION_ENVELOPE_CONTRACT == "ExecutionEnvelope"
    assert first == second
    assert first.endswith(b"\n")
    rebuilt = envelope_contract.ExecutionEnvelope.from_json_bytes(first)
    assert rebuilt == envelope
    assert envelope.canonical_sha256 == "fab7404d686945300f0292430cb96c886c2c703d2c7ff926c5e4327656ad6f59"
    preview = envelope_contract.evaluate_execution_envelope(envelope)
    assert preview.canonical_sha256 == "d33aa2d7f427639bc2e70b78b6e0c07b5e5b6cdfdf8403bebdb5e7783ae5ed86"
    assert rebuilt.request_bytes == canonical_json_bytes(rebuilt.request)
    assert rebuilt.request_sha256 == rebuilt.request.canonical_sha256
    assert rebuilt.resolved_request_dates == ("2026-09-23", "2026-09-24")
    assert rebuilt.date_resolution_timezone_id == "Africa/Lagos"
    assert rebuilt.clock_observed_at == rebuilt.issued_at == NOW


def test_envelope_identity_changes_only_when_bound_identity_changes():
    base_request = _request()
    base = _envelope(request=base_request)
    acquisition_changed = _envelope(
        request=base_request,
        intent=_intent(acquire_sources=False, create_share_code=True),
    )
    assert acquisition_changed.request_bytes == base.request_bytes
    assert acquisition_changed.canonical_sha256 != base.canonical_sha256

    delivery_request = _request(create_share_code=False)
    delivery_changed = _envelope(
        request=delivery_request,
        intent=_intent(acquire_sources=True, create_share_code=False),
    )
    assert delivery_changed.canonical_sha256 != base.canonical_sha256

    assert _envelope(request=_request(target_legs=21)).canonical_sha256 != base.canonical_sha256
    assert _envelope(
        request=base_request,
        manifest=_manifest(provider_acquisition=False, share_code_generation=True),
    ).canonical_sha256 != base.canonical_sha256
    assert _envelope(
        request=base_request,
        source_identity=envelope_contract.SourceReleaseIdentity("SIGNED_RELEASE", "athena-2.0.0+signed"),
    ).canonical_sha256 != base.canonical_sha256
    assert _envelope(request=base_request, expires_at=EXPIRY + timedelta(seconds=1)).canonical_sha256 != base.canonical_sha256


@pytest.mark.parametrize(
    ("requested", "capability", "operation", "expected_allowed", "expected_denied"),
    [
        (False, True, "ACQUIRE_SOURCES", (), ()),
        (True, False, "ACQUIRE_SOURCES", (), ("ACQUIRE_SOURCES",)),
        (True, True, "ACQUIRE_SOURCES", ("ACQUIRE_SOURCES",), ()),
        (False, True, "CREATE_SHARE_CODE", (), ()),
        (True, False, "CREATE_SHARE_CODE", (), ("CREATE_SHARE_CODE",)),
        (True, True, "CREATE_SHARE_CODE", ("CREATE_SHARE_CODE",), ()),
    ],
)
def test_preview_intersects_operation_intent_with_capability_without_widening(
    requested, capability, operation, expected_allowed, expected_denied
):
    acquire = operation == "ACQUIRE_SOURCES"
    acquisition_requested = requested if acquire else False
    delivery_requested = requested if not acquire else False
    request = _request(create_share_code=delivery_requested)
    intent = _intent(
        acquire_sources=acquisition_requested,
        create_share_code=request.create_share_code,
    )
    manifest = _manifest(
        provider_acquisition=capability if acquire else True,
        share_code_generation=capability if not acquire else True,
    )
    preview = envelope_contract.evaluate_execution_envelope(
        _envelope(request=request, intent=intent, manifest=manifest)
    )
    assert preview.allowed_operations == expected_allowed
    assert preview.denied_operations == expected_denied
    if expected_denied:
        assert len(preview.blockers) == 1
        blocker = preview.blockers[0]
        assert blocker.code == "REQUEST_AUTHORITY_MISMATCH"
        assert blocker.operation == operation
        assert blocker.capability == (
            "provider_acquisition" if acquire else "share_code_generation"
        )
        assert blocker.reason
    else:
        assert preview.blockers == ()


def test_main_delivery_intent_is_representable_but_preview_denies_without_capability():
    request = _request(profile="MAIN", create_share_code=True)
    preview = envelope_contract.evaluate_execution_envelope(
        _envelope(
            request=request,
            intent=_intent(acquire_sources=False, create_share_code=True),
            manifest=_manifest(profile="MAIN", provider_acquisition=False, share_code_generation=False),
        )
    )
    assert preview.denied_operations == ("CREATE_SHARE_CODE",)
    assert [blocker.code for blocker in preview.blockers] == ["REQUEST_AUTHORITY_MISMATCH"]


def test_preview_canonical_round_trip_and_decisions_are_derived_from_bound_manifest():
    preview = envelope_contract.evaluate_execution_envelope(
        _envelope(
            request=_request(create_share_code=False),
            intent=_intent(acquire_sources=True, create_share_code=False),
            manifest=_manifest(provider_acquisition=True, share_code_generation=True),
        )
    )
    assert preview.allowed_operations == ("ACQUIRE_SOURCES",)
    assert preview.denied_operations == ()
    assert preview.blockers == ()
    raw = preview.canonical_bytes
    assert envelope_contract.ExecutionPreview.from_json_bytes(raw) == preview
    assert raw == envelope_contract.ExecutionPreview.from_json_bytes(raw).canonical_bytes


@pytest.mark.parametrize("intent", [
    {"acquire_sources": "false", "create_share_code": False, "place_wager": False},
    {"acquire_sources": False, "create_share_code": 0, "place_wager": False},
    {"acquire_sources": False, "create_share_code": False, "place_wager": True},
])
def test_operation_intent_rejects_nonbool_and_wager_true(intent):
    with pytest.raises(envelope_contract.ExecutionEnvelopeError):
        envelope_contract.RequestedOperationIntent(**intent)


def test_envelope_rejects_operation_intent_that_conflicts_with_v1_delivery_field():
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="conflicts"):
        _envelope(request=_request(create_share_code=False), intent=_intent(create_share_code=True))


def test_envelope_rejects_naive_clock_and_nonincreasing_expiry():
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="timezone-aware"):
        _envelope(issued_at=datetime(2026, 9, 22, 12, 30), expires_at=EXPIRY)
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="later than"):
        _envelope(issued_at=NOW, expires_at=NOW)


def test_envelope_rejects_unreviewed_date_zone_and_mismatched_resolved_dates():
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="timezone identity"):
        _envelope(timezone_id="UTC")
    envelope = _envelope()
    payload = envelope.to_dict()
    payload["resolved_request_dates"] = ["2026-09-22", "2026-09-24"]
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="resolved dates"):
        envelope_contract.ExecutionEnvelope.from_dict(payload)


def test_envelope_tamper_suite_rejects_stale_digests_and_malformed_contracts():
    envelope = _envelope()
    payload = envelope.to_dict()

    changed_request = _request(target_legs=21)
    tampered_request = dict(payload)
    tampered_request["request_bytes_base64"] = base64.b64encode(canonical_json_bytes(changed_request)).decode("ascii")
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="request SHA-256"):
        envelope_contract.ExecutionEnvelope.from_dict(tampered_request)

    tampered_request_sha = dict(payload, request_sha256="0" * 64)
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="request SHA-256"):
        envelope_contract.ExecutionEnvelope.from_dict(tampered_request_sha)

    changed_manifest = json.loads(json.dumps(payload))
    changed_manifest["authority_manifest"]["capabilities"]["share_code_generation"] = False
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="capability SHA-256"):
        envelope_contract.ExecutionEnvelope.from_dict(changed_manifest)

    changed_intent = json.loads(json.dumps(payload))
    changed_intent["requested_operations"]["acquire_sources"] = False
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="requested-operation SHA-256"):
        envelope_contract.ExecutionEnvelope.from_dict(changed_intent)

    bad_base64 = dict(payload, request_bytes_base64="%%%not-base64%%")
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="base64"):
        envelope_contract.ExecutionEnvelope.from_dict(bad_base64)

    bad_request_contract = json.loads(json.dumps(payload))
    altered_request = _request().to_dict()
    altered_request["contract"] = "NotRunRequest"
    bad_request_contract["request_bytes_base64"] = base64.b64encode(canonical_json_bytes(altered_request)).decode("ascii")
    bad_request_contract["request_sha256"] = hashlib.sha256(
        base64.b64decode(bad_request_contract["request_bytes_base64"])
    ).hexdigest()
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="embedded RunRequest"):
        envelope_contract.ExecutionEnvelope.from_dict(bad_request_contract)

    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="fields drifted"):
        envelope_contract.ExecutionEnvelope.from_dict(dict(payload, unexpected=True))
    missing = dict(payload)
    del missing["expires_at"]
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="fields drifted"):
        envelope_contract.ExecutionEnvelope.from_dict(missing)


def test_envelope_json_decoder_rejects_duplicate_keys_and_noncanonical_json():
    envelope = _envelope()
    raw = envelope.canonical_bytes
    duplicate = raw[:-2] + b',"policy_id":"ATHENA_EXECUTION_ENVELOPE_V2"}\n'
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="duplicate"):
        envelope_contract.ExecutionEnvelope.from_json_bytes(duplicate)
    pretty = json.dumps(envelope.to_dict(), sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="not canonical"):
        envelope_contract.ExecutionEnvelope.from_json_bytes(pretty)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", True, "schema version"),
        ("schema_version", 3, "schema version"),
        ("policy_id", "ATHENA_EXECUTION_ENVELOPE_V1", "identity drifted"),
        ("issued_at", "2026-09-22T12:30:00Z", "canonical microsecond"),
        ("expires_at", "2026-09-22T12:30:00.123456Z", "later than"),
    ],
)
def test_envelope_rejects_unknown_version_policy_and_noncanonical_timestamps(field, value, message):
    payload = _envelope().to_dict()
    payload[field] = value
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match=message):
        envelope_contract.ExecutionEnvelope.from_dict(payload)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("GIT_COMMIT", "A" * 40),
        ("GIT_COMMIT", "abc"),
        ("GIT_TREE", "a" * 40),
        ("SIGNED_RELEASE", "bad\nrelease"),
    ],
)
def test_source_identity_rejects_unknown_or_malformed_values(kind, value):
    with pytest.raises(envelope_contract.ExecutionEnvelopeError):
        envelope_contract.SourceReleaseIdentity(kind, value)


def test_manifest_rejects_smuggled_sensitive_capability_payload():
    payload = _envelope().to_dict()
    payload["authority_manifest"]["additional_capabilities"] = {"production_authority": True}
    with pytest.raises(envelope_contract.ExecutionEnvelopeError, match="authority_manifest is invalid"):
        envelope_contract.ExecutionEnvelope.from_dict(payload)


def test_envelope_and_preview_are_pure_offline_values_with_zero_side_effects(monkeypatch):
    calls = []

    def denied(*_args, **_kwargs):
        calls.append("network-or-subprocess")
        raise AssertionError("offline preview touched an external boundary")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(subprocess, "run", denied)

    envelope = _envelope(
        request=_request(create_share_code=False),
        intent=_intent(acquire_sources=True, create_share_code=False),
        manifest=_manifest(provider_acquisition=False, share_code_generation=True),
    )
    preview = envelope_contract.evaluate_execution_envelope(envelope)
    assert preview.denied_operations == ("ACQUIRE_SOURCES",)
    assert preview.blockers[0].code == "REQUEST_AUTHORITY_MISMATCH"
    assert calls == []

    tree = ast.parse(Path(envelope_contract.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported
        for prefix in ("providers", "workers", "services", "subprocess", "socket", "urllib", "requests")
    )
