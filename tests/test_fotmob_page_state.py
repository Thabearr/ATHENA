from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
import socket
from typing import Any

import pytest

from domain import fotmob_page_state as state_domain
from domain.fotmob_page_capture import (
    DATASET_NAME as SOURCE_DATASET_NAME,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    CapturedFotMobPageResponse,
    build_page_capture_manifest,
    canonical_page_capture_manifest_bytes,
    capture_identifier,
    sha256_page_capture_manifest,
)
from domain.fotmob_page_state import (
    DATASET_NAME,
    FALLBACK_KEY,
    NEXT_DATA_ID,
    NEXT_DATA_TYPE,
    SCHEMA_VERSION,
    FotMobFixtureAvailability,
    FotMobPageStateAssessment,
    FotMobPageStateError,
    assess_fotmob_page_state,
    canonical_page_state_assessment_bytes,
    page_state_assessment_to_dict,
    sha256_page_state_assessment,
)
from scripts import assess_fotmob_page_state as state_script


DATE = "20260815"
OBSERVED = datetime.datetime(
    2026, 8, 9, 1, 26, 31, 150491, tzinfo=datetime.timezone.utc
)
SAFETY_KEYS = {
    "network_authorized",
    "external_asset_retrieval_authorized",
    "script_execution_authorized",
    "dom_fixture_fallback_authorized",
    "fixture_extraction_authorized",
    "source_qualified",
    "fixture_promotion_authorized",
    "intelligence_authorized",
    "model_feature_authorized",
    "probability_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
}


def payload(*, date: Any = DATE, matches: Any = None) -> dict[str, Any]:
    return {
        "query": {"date": date},
        "props": {
            "pageProps": {
                "fallback": {
                    FALLBACK_KEY: {"matches": [] if matches is None else matches}
                }
            }
        },
    }


def page(
    value: Any = None,
    *,
    json_text: str | None = None,
    attributes: str = 'id="__NEXT_DATA__" type="application/json"',
    before: str = "",
    after: str = "",
) -> bytes:
    serialized = json.dumps(payload() if value is None else value)
    content = serialized if json_text is None else json_text
    return (
        "<!doctype html><html><head>"
        + before
        + "</head><body><script "
        + attributes
        + ">"
        + content
        + "</script>"
        + after
        + "</body></html>"
    ).encode("utf-8")


def source_manifest(raw: bytes, *, network: bool = True):
    return build_page_capture_manifest(
        CapturedFotMobPageResponse(
            status=200,
            content_type="text/html; charset=utf-8",
            content_length=len(raw),
            body=raw,
            observed_at=OBSERVED,
            network_acquisition_performed=network,
        ),
        request_date=DATE,
    )


def assessment(raw: bytes | None = None) -> FotMobPageStateAssessment:
    content = page() if raw is None else raw
    return assess_fotmob_page_state(content, source_manifest(content))


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    return root


def write_capture(
    tmp_path: Path,
    *,
    raw: bytes | None = None,
    network: bool = True,
) -> tuple[Path, Path, Any]:
    content = page() if raw is None else raw
    manifest = source_manifest(content, network=network)
    repo = repository(tmp_path)
    allowed = repo / "evidence" / "fotmob-date-page"
    directory = allowed / DATE / capture_identifier(
        request_date=DATE,
        observed_at=manifest.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    directory.mkdir(parents=True)
    (directory / RAW_FILENAME).write_bytes(content)
    (directory / MANIFEST_FILENAME).write_bytes(
        canonical_page_capture_manifest_bytes(manifest)
    )
    return repo, directory, manifest


def test_exact_contract_and_field_order():
    built = assessment()
    assert DATASET_NAME == "athena-fotmob-page-state-assessment-v1"
    assert SCHEMA_VERSION == 1
    assert [item.value for item in FotMobFixtureAvailability] == [
        "NO_FIXTURE_DATA"
    ]
    assert [field.name for field in dataclasses.fields(FotMobPageStateAssessment)] == [
        "schema_version",
        "dataset_name",
        "source_capture_dataset_name",
        "source_capture_schema_version",
        "source_capture_manifest_sha256",
        "source_raw_sha256",
        "source_raw_size",
        "source_observed_at",
        "request_date",
        "next_data_element_count",
        "next_data_id",
        "next_data_type",
        "next_data_query_date",
        "fallback_key",
        "match_count",
        "fixture_availability",
        "safety",
    ]
    assert built.dataset_name == DATASET_NAME


@pytest.mark.parametrize("bad", [True, 1.0, "1", 0, 2])
def test_schema_version_is_exact_integer_one(bad: Any):
    with pytest.raises(FotMobPageStateError):
        dataclasses.replace(assessment(), schema_version=bad)


def test_assessment_and_safety_are_immutable_and_detached():
    original = dict(assessment().safety)
    built = dataclasses.replace(assessment(), safety=original)
    original["source_qualified"] = True
    assert built.safety["source_qualified"] is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.match_count = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        built.safety["source_qualified"] = True  # type: ignore[index]


@pytest.mark.parametrize("bad", [True, 0, 1, None, "false"])
def test_safety_requires_exact_false(bad: Any):
    changed = dict(assessment().safety)
    changed["source_qualified"] = bad
    with pytest.raises(FotMobPageStateError):
        dataclasses.replace(assessment(), safety=changed)


def test_safety_has_exact_keys():
    assert set(assessment().safety) == SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in assessment().safety.values())


def test_source_manifest_type_size_sha_and_ancestry_are_required():
    raw = page()
    manifest = source_manifest(raw)
    with pytest.raises(FotMobPageStateError, match="source_manifest"):
        assess_fotmob_page_state(raw, object())  # type: ignore[arg-type]
    with pytest.raises(FotMobPageStateError, match="size"):
        assess_fotmob_page_state(raw + b" ", manifest)
    changed = bytearray(raw)
    changed[-10] = changed[-10] ^ 1
    with pytest.raises(FotMobPageStateError, match="SHA-256"):
        assess_fotmob_page_state(bytes(changed), manifest)

    built = assess_fotmob_page_state(raw, manifest)
    assert built.source_capture_dataset_name == SOURCE_DATASET_NAME
    assert built.source_capture_schema_version == 1
    assert built.source_capture_manifest_sha256 == sha256_page_capture_manifest(manifest)
    assert built.source_raw_sha256 == manifest.raw_sha256
    assert built.source_raw_size == manifest.raw_size
    assert built.source_observed_at == manifest.observed_at
    assert built.request_date == manifest.request_date


@pytest.mark.parametrize("raw", ["html", bytearray(b"html"), None, [], {}])
def test_raw_html_requires_exact_bytes(raw: Any):
    with pytest.raises(FotMobPageStateError):
        assess_fotmob_page_state(raw, source_manifest(page()))


def test_empty_and_oversized_raw_html_fail_closed():
    with pytest.raises(FotMobPageStateError, match="empty"):
        assess_fotmob_page_state(b"", source_manifest(page()))
    oversized = b"x" * (MAX_RESPONSE_BYTES + 1)
    with pytest.raises(FotMobPageStateError, match="8 MiB"):
        assess_fotmob_page_state(oversized, source_manifest(page()))


def test_exact_utf8_and_attribute_order_are_accepted():
    raw = page(attributes='type="application/json" id="__NEXT_DATA__"')
    assert assessment(raw).fixture_availability is FotMobFixtureAvailability.NO_FIXTURE_DATA


def test_invalid_utf8_is_rejected_after_valid_ancestry():
    raw = page() + b"\xff"
    with pytest.raises(FotMobPageStateError, match="strict UTF-8"):
        assess_fotmob_page_state(raw, source_manifest(raw))


def test_missing_or_multiple_next_data_elements_are_rejected():
    missing = b"<!doctype html><html><script>ordinary()</script></html>"
    with pytest.raises(FotMobPageStateError, match="exactly one"):
        assess_fotmob_page_state(missing, source_manifest(missing))
    duplicate = page(after='<script id="__NEXT_DATA__" type="application/json">{}</script>')
    with pytest.raises(FotMobPageStateError, match="exactly one"):
        assess_fotmob_page_state(duplicate, source_manifest(duplicate))


@pytest.mark.parametrize(
    ("attributes", "message"),
    [
        ('id="__NEXT_DATA__" type="text/javascript"', "type"),
        ('id="__NEXT_DATA__" type="application/ld+json"', "type"),
        ('id="__NEXT_DATA__" type="application/json" src="payload.json"', "inline"),
        ('id="__NEXT_DATA__" id="other" type="application/json"', "duplicate id"),
        ('id="__NEXT_DATA__" type="application/json" type="text/plain"', "duplicate type"),
    ],
)
def test_next_data_identity_fails_closed(attributes: str, message: str):
    raw = page(attributes=attributes)
    with pytest.raises(FotMobPageStateError, match=message):
        assess_fotmob_page_state(raw, source_manifest(raw))


def test_unrelated_inline_and_external_scripts_are_ignored_without_retrieval(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("network used"))
    raw = page(
        before='<script src="https://example.invalid/chunk.js"></script><script>window.x=1</script>'
    )
    assert assessment(raw).match_count == 0


@pytest.mark.parametrize(
    "json_text",
    [
        "{",
        '{"query":{"date":"20260815"},"query":{}}',
        '{"query":{"date":NaN}}',
        '{"query":{"date":Infinity}}',
        '{"query":{"date":-Infinity}}',
        "[]",
        '"value"',
    ],
)
def test_strict_json_rejections(json_text: str):
    raw = page(json_text=json_text)
    with pytest.raises(FotMobPageStateError):
        assess_fotmob_page_state(raw, source_manifest(raw))


@pytest.mark.parametrize(
    "changed",
    [
        {"__remove_query__": True},
        {"query": []},
        {"query": {}},
        {"query": {"date": 20260815}},
        {"query": {"date": "20260816"}},
    ],
)
def test_query_and_date_contract(changed: dict[str, Any]):
    base = payload()
    if "__remove_query__" in changed:
        del base["query"]
    else:
        base.update(changed)
    raw = page(base)
    with pytest.raises(FotMobPageStateError):
        assess_fotmob_page_state(raw, source_manifest(raw))


def _path_payload(case: str) -> dict[str, Any]:
    base = payload()
    if case == "props_missing":
        del base["props"]
    elif case == "props_type":
        base["props"] = []
    elif case == "page_props_missing":
        del base["props"]["pageProps"]
    elif case == "page_props_type":
        base["props"]["pageProps"] = []
    elif case == "fallback_missing":
        del base["props"]["pageProps"]["fallback"]
    elif case == "fallback_type":
        base["props"]["pageProps"]["fallback"] = []
    elif case == "notable_missing":
        del base["props"]["pageProps"]["fallback"][FALLBACK_KEY]
    elif case == "alternative_locale":
        fallback = base["props"]["pageProps"]["fallback"]
        fallback["notableMatches:en:GB"] = fallback.pop(FALLBACK_KEY)
    elif case == "container_type":
        base["props"]["pageProps"]["fallback"][FALLBACK_KEY] = []
    elif case == "matches_missing":
        del base["props"]["pageProps"]["fallback"][FALLBACK_KEY]["matches"]
    elif case == "matches_type":
        base["props"]["pageProps"]["fallback"][FALLBACK_KEY]["matches"] = {}
    return base


@pytest.mark.parametrize(
    "case",
    [
        "props_missing",
        "props_type",
        "page_props_missing",
        "page_props_type",
        "fallback_missing",
        "fallback_type",
        "notable_missing",
        "alternative_locale",
        "container_type",
        "matches_missing",
        "matches_type",
    ],
)
def test_exact_reviewed_path_is_mandatory(case: str):
    raw = page(_path_payload(case))
    with pytest.raises(FotMobPageStateError):
        assess_fotmob_page_state(raw, source_manifest(raw))


def test_exact_empty_matches_returns_only_no_fixture_data():
    built = assessment()
    assert built.next_data_element_count == 1
    assert built.next_data_id == NEXT_DATA_ID
    assert built.next_data_type == NEXT_DATA_TYPE
    assert built.next_data_query_date == DATE
    assert built.fallback_key == FALLBACK_KEY
    assert built.match_count == 0
    assert built.fixture_availability is FotMobFixtureAvailability.NO_FIXTURE_DATA


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"id": 1},
        {"home": "A", "away": "B"},
        {"utcTime": "2026-08-15T12:00:00Z"},
    ],
)
def test_non_empty_matches_fail_without_fixture_output(record: Any):
    raw = page(payload(matches=[record]))
    with pytest.raises(FotMobPageStateError, match="schema is unreviewed"):
        assess_fotmob_page_state(raw, source_manifest(raw))


def test_no_fixture_candidate_or_fixture_fields_exist():
    assert not hasattr(state_domain, "FotMobFixtureCandidate")
    serialized = assessment().to_dict()
    forbidden = {
        "fixture_identifier",
        "match_id",
        "home_team",
        "away_team",
        "competition",
        "kickoff",
        "status",
        "fixture_url",
    }
    assert forbidden.isdisjoint(serialized)


def test_serialization_and_hash_are_canonical_and_contain_no_source_payload():
    built = assessment()
    assert page_state_assessment_to_dict(built) == built.to_dict()
    canonical = canonical_page_state_assessment_bytes(built)
    assert canonical.endswith(b"\n")
    assert canonical == canonical_page_state_assessment_bytes(dataclasses.replace(built))
    assert sha256_page_state_assessment(built) == hashlib.sha256(canonical).hexdigest()
    assert json.loads(canonical) == built.to_dict()
    for forbidden in (b"<!doctype", b"pageProps", b"translations", b"localization"):
        assert forbidden not in canonical


def test_serialization_rejects_nan(monkeypatch):
    monkeypatch.setattr(
        FotMobPageStateAssessment,
        "to_dict",
        lambda self: {"invalid": float("nan")},
    )
    with pytest.raises(FotMobPageStateError, match="serialization"):
        canonical_page_state_assessment_bytes(assessment())


def test_direct_assessment_invariants_fail_closed():
    built = assessment()
    mutations = [
        {"dataset_name": "other"},
        {"source_capture_dataset_name": "other"},
        {"source_capture_schema_version": True},
        {"source_capture_manifest_sha256": "A" * 64},
        {"source_raw_sha256": "0" * 63},
        {"source_raw_size": True},
        {"next_data_element_count": True},
        {"next_data_id": "other"},
        {"next_data_type": "application/ld+json"},
        {"next_data_query_date": "20260816"},
        {"fallback_key": "notableMatches:en:GB"},
        {"match_count": True},
        {"fixture_availability": "NO_FIXTURE_DATA"},
    ]
    for mutation in mutations:
        with pytest.raises(FotMobPageStateError):
            dataclasses.replace(built, **mutation)


def test_cli_assesses_verified_capture_and_prints_only_canonical_json(tmp_path, capsys):
    repo, directory, _ = write_capture(tmp_path)
    allowed = directory.parents[1]
    before = {path.relative_to(directory): path.read_bytes() for path in directory.iterdir()}
    socket_original = socket.socket
    socket.socket = lambda *_a, **_k: pytest.fail("network used")  # type: ignore[assignment]
    try:
        assert state_script.main(
            [
                "--allowed-root",
                str(allowed.relative_to(repo)),
                "--capture-directory",
                str(directory.relative_to(repo)),
            ],
            repository_root=repo,
        ) == 0
    finally:
        socket.socket = socket_original
    stdout = capsys.readouterr().out.encode("utf-8")
    built = assessment()
    assert stdout == canonical_page_state_assessment_bytes(built)
    after = {path.relative_to(directory): path.read_bytes() for path in directory.iterdir()}
    assert after == before


def test_cli_verifies_capture_before_second_read_or_assessment(tmp_path, monkeypatch):
    repo, directory, _ = write_capture(tmp_path)
    allowed = directory.parents[1]
    monkeypatch.setattr(
        state_script,
        "verify_page_capture_directory",
        lambda *_a, **_k: (_ for _ in ()).throw(
            state_script.FotMobPageCaptureError("bad manifest")
        ),
    )
    monkeypatch.setattr(
        state_script,
        "_read_bounded_raw_page",
        lambda *_a, **_k: pytest.fail("read occurred before verification"),
    )
    monkeypatch.setattr(
        state_script,
        "assess_fotmob_page_state",
        lambda *_a, **_k: pytest.fail("assessment occurred after bad verification"),
    )
    with pytest.raises(FotMobPageStateError, match="verification failed"):
        state_script.assess_capture_directory(
            directory,
            allowed_root=allowed,
            repository_root=repo,
        )


def test_cli_rejects_allowed_root_outside_repository(tmp_path):
    repo, directory, _ = write_capture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(FotMobPageStateError, match="repository root"):
        state_script.assess_capture_directory(
            directory,
            allowed_root=outside,
            repository_root=repo,
        )


@pytest.mark.parametrize("which", ["root", "capture", "raw"])
def test_cli_rejects_symlink_boundaries_when_supported(tmp_path, which):
    repo, directory, _ = write_capture(tmp_path)
    allowed = directory.parents[1]
    target = tmp_path / f"{which}-link"
    try:
        if which == "root":
            target.symlink_to(allowed, target_is_directory=True)
            args = (directory, target)
        elif which == "capture":
            target.symlink_to(directory, target_is_directory=True)
            args = (target, allowed)
        else:
            raw = directory / RAW_FILENAME
            replacement = directory / "raw-real"
            raw.rename(replacement)
            raw.symlink_to(replacement)
            args = (directory, allowed)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FotMobPageStateError):
        state_script.assess_capture_directory(
            args[0],
            allowed_root=args[1],
            repository_root=repo,
        )


def test_second_read_is_bounded_and_rejects_oversize_without_read_bytes(
    tmp_path, monkeypatch
):
    candidate = tmp_path / RAW_FILENAME
    candidate.write_bytes(b"x" * (MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: pytest.fail("unrestricted Path.read_bytes used"),
    )
    with pytest.raises(FotMobPageStateError, match="8 MiB"):
        state_script._read_bounded_raw_page(candidate)


class _GrowingReader:
    def __init__(self, requested: list[int]) -> None:
        self.requested = requested

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, amount: int) -> bytes:
        self.requested.append(amount)
        return b"x" * amount


def test_second_read_detects_stat_read_growth_at_maximum_plus_one(
    tmp_path, monkeypatch
):
    candidate = tmp_path / RAW_FILENAME
    candidate.write_bytes(b"safe")
    requested: list[int] = []
    original_open = Path.open

    def raced_open(path, *args, **kwargs):
        if path == candidate and args and args[0] == "rb":
            return _GrowingReader(requested)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: pytest.fail("unrestricted Path.read_bytes used"),
    )
    with pytest.raises(FotMobPageStateError, match="8 MiB"):
        state_script._read_bounded_raw_page(candidate)
    assert requested == [MAX_RESPONSE_BYTES + 1]


def test_cli_has_only_offline_read_arguments():
    options = {
        option
        for action in state_script.build_parser()._actions
        for option in action.option_strings
    }
    assert options == {"-h", "--help", "--capture-directory", "--allowed-root"}


def test_source_capability_remains_unknown():
    from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

    fotmob = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]
    assert all(
        getattr(fotmob, field) is CapabilityAvailability.UNKNOWN
        for field in (
            "full_time_score",
            "half_time_score",
            "event_timestamps",
            "reliable_fixture_identity",
            "historical_coverage",
            "freshness_metadata",
        )
    )


def test_production_modules_have_no_network_parser_or_downstream_imports():
    imports: set[str] = set()
    for module in (state_domain, state_script):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
    forbidden = {
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "curl_cffi",
        "playwright",
        "selenium",
        "urllib.request",
        "bs4",
        "lxml",
        "domain.fixture_catalog",
        "domain.fixture_intelligence",
        "domain.fixture_model_features",
        "intelligence.prediction_engine",
        "intelligence.match_analyst",
    }
    assert imports.isdisjoint(forbidden)


def test_no_network_fixture_model_pricing_or_betting_fields_are_emitted():
    result = assessment().to_dict()
    forbidden_fragments = {
        "home_team",
        "away_team",
        "kickoff",
        "match_id",
        "fixture_identifier",
        "probability",
        "odds",
        "price",
        "expected_value",
        "kelly",
        "stake",
        "bet",
    }
    assert forbidden_fragments.isdisjoint(result)
    assert result["fixture_availability"] == "NO_FIXTURE_DATA"
    assert all(value is False for value in result["safety"].values())
