from tests._p3_0_comparison_evidence_support import *  # noqa: F401,F403
from scripts import _p3_0_paired_capture_part1 as capture_part1


def _failure_receipt(tmp_path, exc):
    dest = tmp_path if not tmp_path.exists() else tmp_path / "receipt_child"
    capture_part1._safe_failure(
        dest, exact_commit_sha="a" * 40, capture_id="failure-test",
        started_at="2026-09-12T00:00:00.000000Z", exc=exc,
    )
    return json.loads((dest / "p3-0-capture-failure.json").read_text(encoding="utf-8"))



def test_failure_receipt_preserves_bounded_explicit_cause_chain(tmp_path):
    try:
        try:
            try:
                raise ValueError("leaf")
            except ValueError as exc:
                raise RuntimeError("middle") from exc
        except RuntimeError as exc:
            raise LookupError("outer") from exc
    except LookupError as outer:
        receipt = _failure_receipt(tmp_path, outer)
    assert receipt["schema_version"] == 2
    assert receipt["failure_type"] == "LookupError"
    assert receipt["failure_message"] == "outer"
    assert receipt["failure_chain"] == [
        {"exception_type": "LookupError", "message": "outer"},
        {"exception_type": "RuntimeError", "message": "middle"},
        {"exception_type": "ValueError", "message": "leaf"},
    ]
    assert receipt["failure_chain_truncated"] is False
    assert all(set(row) == {"exception_type", "message"} for row in receipt["failure_chain"])
    assert receipt["share_code_operation"] is False
    assert receipt["login"] is False and receipt["cookies"] is False
    assert receipt["wallet"] is False and receipt["stake"] is False and receipt["wager_placed"] is False


def test_failure_receipt_bounds_depth_messages_and_suppressed_context(tmp_path):
    exc = RuntimeError("x" * 900)
    for index in range(capture_part1.FAILURE_CHAIN_MAX_DEPTH + 2):
        try:
            raise exc
        except RuntimeError as cause:
            exc = RuntimeError(f"level-{index}")
            exc.__cause__ = cause
    receipt = _failure_receipt(tmp_path, exc)
    assert len(receipt["failure_chain"]) == capture_part1.FAILURE_CHAIN_MAX_DEPTH
    assert receipt["failure_chain_truncated"] is True
    assert all(len(row["message"]) <= capture_part1.FAILURE_MESSAGE_MAX_CHARS for row in receipt["failure_chain"])
    try:
        try:
            raise ValueError("hidden")
        except ValueError:
            raise RuntimeError("outer") from None
    except RuntimeError as suppressed:
        suppressed_receipt = _failure_receipt(tmp_path / "suppressed", suppressed)
    assert suppressed_receipt["failure_chain"] == [{"exception_type": "RuntimeError", "message": "outer"}]
    assert not ({"traceback", "stack", "locals", "globals", "environment", "headers"} & set(receipt))


def test_failure_receipt_bounds_each_stored_message(tmp_path):
    message = "x" * (capture_part1.FAILURE_MESSAGE_MAX_CHARS + 100)
    receipt = _failure_receipt(tmp_path, RuntimeError(message))

    assert receipt["failure_message"] == "x" * capture_part1.FAILURE_MESSAGE_MAX_CHARS
    assert receipt["failure_chain"] == [{
        "exception_type": "RuntimeError",
        "message": "x" * capture_part1.FAILURE_MESSAGE_MAX_CHARS,
    }]
    assert receipt["failure_chain_truncated"] is False
    assert len(receipt["failure_message"]) == 800
    assert len(receipt["failure_chain"][0]["message"]) == 800

def test_artifact_manifest_rejects_tamper_extra_missing_and_path_escape(tmp_path):
    bundle = _bundle()
    output = tmp_path / "capture"
    evidence.write_capture_artifact(bundle, output)
    assert evidence.verify_capture_artifact(output)["canonical_sha256"] == bundle["canonical_sha256"]

    (output / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)
    (output / "unexpected.txt").unlink()

    victim = output / "bundle.json"
    saved = victim.read_bytes(); victim.unlink()
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)
    victim.write_bytes(saved)

    manifest = json.loads((output / "manifest.json").read_text())
    manifest["files"][0]["path"] = "../outside"
    (output / "manifest.json").write_bytes(evidence.canonical_json_bytes(manifest))
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)


def test_manifest_rejects_duplicate_absolute_and_symlink(tmp_path):
    bundle = _bundle()
    output = tmp_path / "capture"
    evidence.write_capture_artifact(bundle, output)
    original = json.loads((output / "manifest.json").read_text())

    duplicate = copy.deepcopy(original)
    duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
    (output / "manifest.json").write_bytes(evidence.canonical_json_bytes(duplicate))
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)

    (output / "manifest.json").write_bytes(evidence.canonical_json_bytes(original))
    absolute = copy.deepcopy(original)
    absolute["files"][0]["path"] = "/tmp/outside"
    (output / "manifest.json").write_bytes(evidence.canonical_json_bytes(absolute))
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)

    (output / "manifest.json").write_bytes(evidence.canonical_json_bytes(original))
    target_rel = original["files"][0]["path"]
    target = output / target_rel
    saved = target.read_bytes(); target.unlink()
    outside = tmp_path / "outside.json"; outside.write_bytes(saved)
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(evidence.P30ComparisonEvidenceError):
        evidence.verify_capture_artifact(output)


def test_pipeline_observer_default_off_return_ignored_and_failure_contained():
    fixture = {
        "fixture_id": FIXTURE,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "league": "Test League",
        "match_date": KICKOFF,
    }

    def analyst_result(_context):
        return {
            "decision_status": DecisionStatus.BET.value,
            "recommended_analytical_verdict": "HOME_WIN",
            "viable_markets": [],
            "accumulator_eligible_selection": None,
            "no_bet_reasons": [],
            "evidence_report": {"final_decision": "BET"},
        }

    def pipeline():
        value = object.__new__(AnalysisPipeline)
        value.analyst = SimpleNamespace(compile_master_fixture_prediction=analyst_result)
        value._resolve_team_id = lambda _name: 1
        return value

    baseline = pipeline().run_pipeline_snapshot(override_fixtures=[copy.deepcopy(fixture)])
    received = []

    def observer(context, pre_gate, analysis, row):
        context["fixture_id"] = "mutated"
        pre_gate["decision_status"] = "NO_BET"
        analysis["decision_status"] = "BET"
        row["decision_status"] = "BET"
        received.append(True)
        return {"replacement": "forbidden"}

    observed = pipeline().run_pipeline_snapshot(
        override_fixtures=[copy.deepcopy(fixture)], evidence_observer=observer
    )
    assert observed == baseline
    assert received == [True]
    contained = pipeline().run_pipeline_snapshot(
        override_fixtures=[copy.deepcopy(fixture)],
        evidence_observer=lambda *_: (_ for _ in ()).throw(RuntimeError("capture failure")),
    )
    assert contained == baseline


def test_legacy_observer_holds_copies_and_quarantines_staking():
    observer = evidence.LegacyEvidenceObserver(
        clock=lambda: datetime(2026, 9, 30, 12, 3, tzinfo=timezone.utc)
    )
    source_context = _legacy_input()
    pre = _analysis("BET")
    authorized = _analysis("ANALYTICAL_CANDIDATE")
    exported = {"fixture_id": FIXTURE, "decision_status": "ANALYTICAL_CANDIDATE", "evidence_report": {"possession": 55}}
    observer(source_context, pre, authorized, exported)
    source_context["home_team"] = "mutated"
    pre["decision_status"] = "NO_BET"
    captured = observer.observations()[0]
    assert captured["legacy_input"]["home_team"] == "Alpha FC"
    assert captured["legacy_output"]["legacy_analysis_before_runtime_gate"]["decision_status"] == "BET"
    assert "kelly_stake_pct" not in evidence.canonical_json_bytes(captured).decode()


def test_legacy_seam_numpy_normalization_and_observer_retention():
    import numpy as np

    fixture = {
        "fixture_id": 4452140,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "league": "Premier League",
        "match_date": "2026-09-30",
        "data_source": "fotmob",
    }

    def analyst_result(*_args, **_kwargs):
        return {
            "decision_status": "BET",
            "recommended_analytical_verdict": "BET",
            "edge_differential": np.float64(0.08),
            "edge_is_bookmaker_value": True,
            "bookmaker_odds": np.float32(2.10),
            "bookmaker_probability": np.float64(0.45),
            "edge_pp": np.float64(8.0),
            "upset_alert": np.bool_(False),
            "risk_score": np.float64(12.5),
            "stale_data": False,
            "viable_markets": ["1X"],
            "accumulator_eligible_selection": "HOME",
            "reasoning_verdicts": ["VALUE"],
            "no_bet_reasons": [],
            "evidence_report": {
                "final_decision": "BET",
                "legacy_decision_status_before_runtime_gate": "BET",
                "risk_metric": np.float64(12.5),
                "array_metric": np.array([np.float64(1.0), np.float64(2.0)]),
            },
        }

    pipeline = object.__new__(AnalysisPipeline)
    pipeline.analyst = SimpleNamespace(compile_master_fixture_prediction=analyst_result)
    pipeline._resolve_team_id = lambda _name: 1

    observer = evidence.LegacyEvidenceObserver(
        clock=lambda: datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    )

    baseline = pipeline.run_pipeline_snapshot(override_fixtures=[copy.deepcopy(fixture)])
    observed = pipeline.run_pipeline_snapshot(
        override_fixtures=[copy.deepcopy(fixture)],
        evidence_observer=observer,
    )

    # 1. Output invariance: baseline and observed pipeline outputs are identical
    assert len(observed) == len(baseline) == 1
    row = observed[0]
    base_row = baseline[0]
    assert row["fixture_id"] == base_row["fixture_id"] == 4452140
    assert row["decision_status"] == base_row["decision_status"] == "ANALYTICAL_CANDIDATE"  # Runtime gate mapped BET to ANALYTICAL_CANDIDATE
    assert row["risk_score"] == base_row["risk_score"] == 12.5
    assert row["edge"] == base_row["edge"] == 0.08
    assert row["bookmaker_odds"] == base_row["bookmaker_odds"] == 2.10
    assert row["bookmaker_probability"] == base_row["bookmaker_probability"] == 0.45
    assert row["viable_markets"] == base_row["viable_markets"] == ["1X"]
    np.testing.assert_array_equal(
        row["evidence_report"]["array_metric"],
        base_row["evidence_report"]["array_metric"],
    )

    # 2. Observer retention: observer successfully captured and normalized numpy types
    observations = observer.observations()
    assert len(observations) == 1
    obs = observations[0]
    legacy_output = obs["legacy_output"]
    pre_gate = legacy_output["legacy_analysis_before_runtime_gate"]
    assert pre_gate["risk_score"] == 12.5
    assert type(pre_gate["risk_score"]) is float
    assert type(pre_gate["edge_differential"]) is float
    assert type(pre_gate["bookmaker_odds"]) is float
    assert type(pre_gate["upset_alert"]) is bool

    # 3. Canonical JSON serialization succeeds without non-JSON errors
    raw_bytes = evidence.canonical_json_bytes(obs)
    assert isinstance(raw_bytes, bytes)

    # 4. Zero authority leakage: runtime safety keys quarantined, no sensitive material
    assert "runtime_authorization_state" not in raw_bytes.decode()
    assert "runtime_authorization_reasons" not in raw_bytes.decode()
    assert "kelly_stake_pct" not in raw_bytes.decode()


def test_pair_capture_module_has_no_delivery_email_auth_wallet_or_wager_imports():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "scripts" / "capture_p3_0_paired_evidence.py",
        root / "scripts" / "_p3_0_paired_capture_part1.py",
        root / "scripts" / "_p3_0_paired_capture_part2.py",
    )
    module_names = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_names.append(node.module)
    forbidden = ("send_current_shadow_email", "sportybet_share_code", "wallet", "staking", "wager")
    assert not any(any(token in name for token in forbidden) for name in module_names)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "execute_current_shadow_all_market(" not in source
    assert "_acquire_router_inputs(" in source
    assert "resolve_shadow_canonical_core()" in source
    assert "_legacy_bookmaker_quotes" in source
    assert "build_current_shadow_exact_quotes" in source
    assert "P3_0_E1_EXACT_CURRENT_SHADOW_CAPTURE" in source


def test_capture_workflow_is_dispatch_only_and_never_calls_delivery():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github" / "workflows" / "p3-0-comparison-evidence-capture.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "issue_comment:" not in text
    assert "send_current_shadow_email" not in text
    assert "execute_current_shadow_request" not in text
    assert "capture_p3_0_paired_evidence" in text
    assert "upload-artifact@v4" in text


def test_capture_workflow_passes_read_only_github_token_to_paired_capture_step():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github" / "workflows" / "p3-0-comparison-evidence-capture.yml").read_text(encoding="utf-8")
    marker = "      - name: Capture paired P3.0 evidence through Router only\n"
    start = text.index(marker)
    end = text.index("      - name: Upload P3.0-E1 capture artifact\n", start)
    capture_step = text[start:end]

    assert "GH_TOKEN: ${{ github.token }}" in capture_step
    assert "contents: read" in text
    assert "actions: read" in text
    for forbidden in (
        "secrets.GH_TOKEN",
        "secrets.GITHUB_TOKEN",
        "contents: write",
        "actions: write",
        "send_current_shadow_email",
        "execute_current_shadow_request",
        "share-code",
        "login",
        "wallet",
        "staking",
        "wager",
    ):
        assert forbidden not in text


def test_bundle_and_artifact_are_deterministic(tmp_path):
    first = _bundle(); second = _bundle()
    assert first == second
    assert evidence.verify_capture_bundle(first) == first
    output = tmp_path / "capture"
    evidence.write_capture_artifact(first, output)
    assert evidence.verify_capture_artifact(output) == first


def test_fix_b_readiness_envelope_vs_immutable_capture_child_offline_proof(tmp_path):
    """Prove Fix B: readiness envelope and immutable capture child are distinct and safe."""
    # 1. readiness creates envelope
    envelope_dir = tmp_path / "artifacts" / "p3-0-comparison-evidence"
    envelope_dir.mkdir(parents=True, exist_ok=True)
    readiness_receipt = envelope_dir / "p3-0-e1-live-readiness.json"
    readiness_content = b'{"status":"P3_0_E1_LIVE_READINESS_VERIFIED"}\n'
    readiness_receipt.write_bytes(readiness_content)

    # 2. readiness receipt exists
    assert readiness_receipt.exists()

    # 3. capture child does not exist
    capture_child = envelope_dir / "capture"
    assert not capture_child.exists()

    # 4. deterministic valid capture publishes into child
    bundle = _bundle()
    published = evidence.write_capture_artifact(bundle, capture_child)
    assert published == capture_child
    assert capture_child.exists()

    # 5. capture verifies
    verified = evidence.verify_capture_artifact(capture_child)
    assert verified["canonical_sha256"] == bundle["canonical_sha256"]

    # 6. readiness receipt bytes unchanged
    assert readiness_receipt.read_bytes() == readiness_content

    # 7. preexisting child fails closed
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence.write_capture_artifact(bundle, capture_child)

    # 8. no overwrite occurs
    verified_after = evidence.verify_capture_artifact(capture_child)
    assert verified_after["canonical_sha256"] == bundle["canonical_sha256"]


def test_deterministic_post_router_failure_reproduction_not_retained_model_reexecution(tmp_path):
    """Prove structural fix for run 35467453094 without claiming model reexecution.

    Fixture: FOTMOB:5071367, provider event: sr:match:66299552 (DC United vs Charlotte FC).
    """
    from domain.p3_0_comparison_evidence import (
        LegacyEvidenceObserver,
        P30ComparisonEvidenceError,
    )
    from domain._p3_0_comparison_evidence_part1 import _reject_sensitive_key
    from services.analysis_pipeline import (
        LEGACY_RUNTIME_AUTHORIZATION_STATE,
        LEGACY_RUNTIME_BET_BLOCK_REASON,
        apply_runtime_authorization,
    )

    legacy_analysis = {
        "fixture_id": "5071367",
        "home_team": "DC United",
        "away_team": "Charlotte FC",
        "league": "Major League Soccer",
        "match_date": "2026-09-19T23:30:00Z",
        "decision_status": "BET",
        "evidence_report": {
            "final_decision": "BET",
            "decision_reasons": ["Cleared."],
            "runtime_authorization_state": LEGACY_RUNTIME_AUTHORIZATION_STATE,
            "runtime_authorization_reasons": [LEGACY_RUNTIME_BET_BLOCK_REASON],
        },
    }
    quarantined = apply_runtime_authorization(legacy_analysis)

    # Before fix: _reject_sensitive_key rejects "runtime_authorization_state"
    with pytest.raises(P30ComparisonEvidenceError, match="sensitive evidence key is forbidden"):
        _reject_sensitive_key(
            "runtime_authorization_state",
            "legacy_exported_row.evidence_report.runtime_authorization_state",
            LEGACY_RUNTIME_AUTHORIZATION_STATE,
        )

    # Before fix: output path collides with readiness envelope
    envelope = tmp_path / "artifacts" / "p3-0-comparison-evidence"
    envelope.mkdir(parents=True, exist_ok=True)
    readiness_file = envelope / "p3-0-e1-live-readiness.json"
    readiness_file.write_text('{"status":"P3_0_E1_LIVE_READINESS_VERIFIED"}')
    bundle = _bundle()
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence.write_capture_artifact(bundle, envelope)

    # After fix:
    # 1. Runtime metadata is quarantined from copied P3 evidence
    observer = LegacyEvidenceObserver()
    observer(
        fixture_context={
            "fixture_id": "5071367",
            "home_team": "DC United",
            "away_team": "Charlotte FC",
            "match_date": "2026-09-19",
        },
        pre_gate=quarantined,
        authorized=quarantined,
        exported={
            "fixture_id": "5071367",
            "fixture": "DC United vs Charlotte FC",
            "home_team": "DC United",
            "away_team": "Charlotte FC",
            "league": "Major League Soccer",
            "match_date": "2026-09-19",
            "decision_status": "ANALYTICAL_CANDIDATE",
            "evidence_report": quarantined["evidence_report"],
            "runtime_authorization_state": LEGACY_RUNTIME_AUTHORIZATION_STATE,
            "runtime_authorization_reasons": [LEGACY_RUNTIME_BET_BLOCK_REASON],
        },
    )
    obs = observer.observations()
    assert len(obs) == 1

    # 2. Immutable capture child publishes cleanly without colliding with envelope
    capture_child = envelope / "capture"
    published = evidence.write_capture_artifact(bundle, capture_child)
    assert published == capture_child
    assert readiness_file.exists()


def test_readiness_check_l_offline_publication_proof():
    """Verify Check L executes all 12 points of the offline publication/completion proof."""
    from scripts.verify_p3_0_e1_live_readiness import check_l_workflows_integrity

    repo_root = Path(__file__).resolve().parents[1]
    result = check_l_workflows_integrity(repo_root)
    assert result["status"] == "PASSED"
    assert result["workflow_step_order_verified"] is True
    assert result["envelope_child_separation_verified"] is True
    assert result["capture_child_path"] == "artifacts/p3-0-comparison-evidence/capture"
    assert result["offline_publication_verified"] is True
    assert result["preexisting_child_rejected"] is True
    assert result["complete_corpus_exit_zero_verified"] is True
    assert result["partial_corpus_nonzero_verified"] is True
    assert result["partial_artifact_immutability_verified"] is True


def test_post_router_capture_stage_failure_taxonomy(tmp_path):
    """Verify explicit machine-readable post-Router capture-stage failure taxonomy.

    Tests:
    1. LEGACY_EVIDENCE_OBSERVER_INCOMPLETE per-fixture observation/export evidence.
    2. PAIRED_CAPTURE_PARTIAL classification with exit 1 and preserved artifact bytes.
    3. CAPTURE_ARTIFACT_PUBLICATION_FAILED wrapping with preserved cause.
    4. Source acquisition failure is NOT mislabeled as publication failure.
    """
    from domain import p3_0_comparison_evidence as evidence
    from scripts import (
        _p3_0_paired_capture_part1 as capture_part1,
        _p3_0_paired_capture_part2 as capture_part2,
    )

    # 1. LEGACY_EVIDENCE_OBSERVER_INCOMPLETE: test per-fixture recording
    mock_source = SimpleNamespace(
        fixture_identity="FOTMOB:999999",
        provider_event_id="sr:match:999999",
    )

    class DummyEmptyPipeline:
        def run_pipeline_snapshot(self, **kwargs):
            return []

    orig_pipeline = capture_part2._legacy_pipeline
    orig_override = capture_part2._legacy_override_fixture
    capture_part2._legacy_pipeline = lambda: DummyEmptyPipeline()
    capture_part2._legacy_override_fixture = lambda s: {"fixture_id": 999999}
    try:
        by_fixture, incomplete = capture_part2._legacy_observations([mock_source])
        assert len(incomplete) == 1
        assert incomplete[0]["failure_code"] == evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE
        assert incomplete[0]["fixture_identity"] == "FOTMOB:999999"
        assert incomplete[0]["provider_event_id"] == "sr:match:999999"
        assert incomplete[0]["observation_count"] == 0
        assert incomplete[0]["exported_row_count"] == 0
    finally:
        capture_part2._legacy_pipeline = orig_pipeline
        capture_part2._legacy_override_fixture = orig_override


    # 2. PAIRED_CAPTURE_PARTIAL: test classification, exit code 1, and artifact immutability
    partial_bundle = capture_part1.build_offline_proof_bundle(partial=True)
    exit_code, payload = capture_part1.classify_published_capture_result(
        partial_bundle,
        capture_stage_causes=[evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE],
    )
    assert exit_code == 1
    assert payload["status"] == "P3_0_E1_CAPTURE_PARTIAL"
    assert payload["failure_code"] == evidence.PAIRED_CAPTURE_PARTIAL
    assert payload["incomplete_fixture_count"] > 0
    assert payload["complete_fixture_count"] < payload["fixture_count"]
    assert payload["capture_stage_causes"] == [evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE]


    # Verify partial artifact immutability
    partial_dir = tmp_path / "partial_output"
    evidence.write_capture_artifact(partial_bundle, partial_dir)
    manifest_bytes_before = (partial_dir / "manifest.json").read_bytes()
    bundle_bytes_before = (partial_dir / "bundle.json").read_bytes()

    # Call _safe_failure and verify it never mutates published child
    capture_part1._safe_failure(
        partial_dir,
        exact_commit_sha="a" * 40,
        capture_id="partial-test",
        started_at="2026-09-20T00:00:00.000000Z",
        exc=RuntimeError("partial run failed"),
    )
    assert not (partial_dir / "p3-0-capture-failure.json").exists()
    assert (partial_dir / "manifest.json").read_bytes() == manifest_bytes_before
    assert (partial_dir / "bundle.json").read_bytes() == bundle_bytes_before
    evidence.verify_capture_artifact(partial_dir)

    # 3. Production publication helper and failure taxonomy
    # Case A: Writer raises OSError
    def _exploding_writer(bundle, dest):
        raise OSError("disk full simulation")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(evidence, "write_capture_artifact", _exploding_writer)
    try:
        with pytest.raises(capture_part1.P30PairedCaptureError) as exc_info:
            capture_part1._publish_capture_artifact(_bundle(), tmp_path / "oserror_dest")
        pub_err = exc_info.value
        assert pub_err.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
        assert isinstance(pub_err.__cause__, OSError)
        assert str(pub_err.__cause__) == "disk full simulation"
        assert "CAPTURE_ARTIFACT_PUBLICATION_FAILED: OSError: disk full simulation" in str(pub_err)
    finally:
        monkeypatch.undo()

    # Case B: Destination already exists
    preexisting_dest = tmp_path / "preexisting_child"
    preexisting_dest.mkdir(parents=True, exist_ok=True)
    with pytest.raises(capture_part1.P30PairedCaptureError) as exc_info:
        capture_part1._publish_capture_artifact(_bundle(), preexisting_dest)
    existing_err = exc_info.value
    assert existing_err.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
    assert isinstance(existing_err.__cause__, evidence.P30ComparisonEvidenceError)
    assert "capture output directory already exists" in str(existing_err.__cause__)
    assert list(preexisting_dest.iterdir()) == []

    # Case C: Valid destination publishes and verifies
    valid_dest = tmp_path / "valid_child"
    published_res = capture_part1._publish_capture_artifact(_bundle(), valid_dest)
    assert published_res == valid_dest
    assert evidence.verify_capture_artifact(valid_dest)["canonical_sha256"] == _bundle()["canonical_sha256"]

    # Case D: Source failure is NOT mislabeled as publication failure
    source_err = capture_part1.P30PairedCaptureError(
        'P3.0-E1 source acquisition produced zero Router inputs: {"failure_code":"PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS"}'
    )
    source_failure_dir = tmp_path / "source_failure_dir"
    capture_part1._safe_failure(
        source_failure_dir,
        exact_commit_sha="c" * 40,
        capture_id="source-failure-test",
        started_at="2026-09-20T00:00:00.000000Z",
        exc=source_err,
    )
    source_receipt = json.loads((source_failure_dir / "p3-0-capture-failure.json").read_text(encoding="utf-8"))
    assert source_receipt.get("failure_code") != evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
    assert source_receipt.get("failure_code") != evidence.PAIRED_CAPTURE_PARTIAL

    # Case E: Invalid bundle fails contract validation before publication
    invalid_bundle = dict(_bundle())
    invalid_bundle["canonical_sha256"] = "0" * 64
    with pytest.raises(evidence.P30ComparisonEvidenceError) as exc_info:
        capture_part1._publish_capture_artifact(invalid_bundle, tmp_path / "invalid_bundle_dest")
    assert not isinstance(exc_info.value, capture_part1.P30PairedCaptureError)


def test_safe_failure_preexisting_destination_regression_matrix(tmp_path):
    """Verify _safe_failure never mutates any preexisting destination in any form.

    Required matrix:
    1. Preexisting published capture directory with manifest
    2. Preexisting empty capture directory with no manifest
    3. Preexisting nonempty capture directory with no manifest
    4. Preexisting regular file at capture path
    5. Preexisting symlink / broken symlink predicate handling
    6. Absent destination still permits creation of failure-only child
    7. Active failure receipt carries CAPTURE_ARTIFACT_PUBLICATION_FAILED when destination absent
    """
    def _snapshot_tree(root: Path) -> dict[str, tuple[int, str]]:
        if not root.exists():
            return {}
        if root.is_file():
            return {"__file__": (root.stat().st_size, hashlib.sha256(root.read_bytes()).hexdigest())}
        snapshot = {}
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                snapshot[rel] = (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
        return snapshot

    # 1. Preexisting published capture directory with manifest
    published_dir = tmp_path / "preexisting_published"
    evidence.write_capture_artifact(_bundle(), published_dir)
    before_published = _snapshot_tree(published_dir)
    capture_part1._safe_failure(
        published_dir, exact_commit_sha="a" * 40, capture_id="safe-test-1",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert _snapshot_tree(published_dir) == before_published
    assert not (published_dir / "p3-0-capture-failure.json").exists()

    # 2. Preexisting empty capture directory with no manifest
    empty_dir = tmp_path / "preexisting_empty"
    empty_dir.mkdir(parents=True, exist_ok=False)
    before_empty = _snapshot_tree(empty_dir)
    capture_part1._safe_failure(
        empty_dir, exact_commit_sha="a" * 40, capture_id="safe-test-2",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert _snapshot_tree(empty_dir) == before_empty
    assert list(empty_dir.iterdir()) == []
    assert not (empty_dir / "p3-0-capture-failure.json").exists()

    # 3. Preexisting nonempty capture directory with no manifest
    nonempty_dir = tmp_path / "preexisting_nonempty"
    nonempty_dir.mkdir(parents=True, exist_ok=False)
    (nonempty_dir / "unrelated.txt").write_text("preexisting content", encoding="utf-8")
    sub = nonempty_dir / "nested"
    sub.mkdir(parents=True, exist_ok=False)
    (sub / "blob.dat").write_bytes(b"\x00\x01\x02\x03")
    before_nonempty = _snapshot_tree(nonempty_dir)
    capture_part1._safe_failure(
        nonempty_dir, exact_commit_sha="a" * 40, capture_id="safe-test-3",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert _snapshot_tree(nonempty_dir) == before_nonempty
    assert not (nonempty_dir / "p3-0-capture-failure.json").exists()

    # 4. Preexisting regular file at capture path
    file_dest = tmp_path / "preexisting_file.txt"
    file_dest.write_bytes(b"untouchable file content")
    before_file_bytes = file_dest.read_bytes()
    capture_part1._safe_failure(
        file_dest, exact_commit_sha="a" * 40, capture_id="safe-test-4",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert file_dest.is_file()
    assert file_dest.read_bytes() == before_file_bytes

    # 5. Preexisting symlink / broken symlink predicate handling
    assert capture_part1._destination_preexists(file_dest) is True
    assert capture_part1._destination_preexists(empty_dir) is True
    assert capture_part1._destination_preexists(tmp_path / "definitely_absent_path") is False
    symlink_dest = tmp_path / "test_symlink"
    symlink_target = tmp_path / "symlink_target.txt"
    symlink_target.write_text("target", encoding="utf-8")
    try:
        symlink_dest.symlink_to(symlink_target)
        assert capture_part1._destination_preexists(symlink_dest) is True
        capture_part1._safe_failure(
            symlink_dest, exact_commit_sha="a" * 40, capture_id="safe-test-5",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
        )
        assert symlink_target.read_text(encoding="utf-8") == "target"
        symlink_target.unlink()
        # Broken symlink must still be detected as preexisting
        assert capture_part1._destination_preexists(symlink_dest) is True
        capture_part1._safe_failure(
            symlink_dest, exact_commit_sha="a" * 40, capture_id="safe-test-5b",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
        )
    except (OSError, NotImplementedError):
        pass  # Windows unprivileged symlinks

    # 6. Absent destination still permits creation of failure-only child
    absent_dest = tmp_path / "absent_failure_child"
    assert not absent_dest.exists()
    capture_part1._safe_failure(
        absent_dest, exact_commit_sha="d" * 40, capture_id="safe-test-6",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("absent test err"),
    )
    assert absent_dest.exists()
    assert (absent_dest / "p3-0-capture-failure.json").exists()
    receipt = json.loads((absent_dest / "p3-0-capture-failure.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "CAPTURE_FAILED"
    assert receipt["destination_policy_id"] == evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID

    # 7. Active failure receipt carries CAPTURE_ARTIFACT_PUBLICATION_FAILED when destination absent
    absent_pub_dest = tmp_path / "absent_pub_failure_child"
    pub_err = capture_part1.P30PairedCaptureError("CAPTURE_ARTIFACT_PUBLICATION_FAILED: OSError: disk full")
    pub_err.failure_code = evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
    capture_part1._safe_failure(
        absent_pub_dest, exact_commit_sha="e" * 40, capture_id="safe-test-7",
        started_at="2026-09-20T00:00:00.000000Z", exc=pub_err,
    )
    pub_receipt = json.loads((absent_pub_dest / "p3-0-capture-failure.json").read_text(encoding="utf-8"))
    assert pub_receipt["failure_code"] == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED


def test_atomic_child_claim_and_contract_ownership_regressions(tmp_path):
    """Prove all 24 required regression points for contract ownership, atomic claim, and receipts.

    A. Contract ownership (1-5)
    B. Atomic child claim (6-15)
    C. Receipt semantics (16-19)
    D. Readiness proofs (20-24)
    """
    from domain import p3_0_comparison_evidence as evidence
    from scripts import _p3_0_paired_capture_part1 as capture_part1
    from scripts.verify_p3_0_e1_live_readiness import check_l_workflows_integrity

    # A. Contract ownership
    # 1. evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID exists
    assert hasattr(evidence, "P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID")
    # 2. Exact value
    expected_policy = "P3_E1_FAILURE_RECEIPT_ONLY_WHEN_CAPTURE_DESTINATION_ABSENT_V1"
    assert evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID == expected_policy
    # 3. _contract_payload()["failure_receipt_destination_policy_id"] equals that exact constant
    payload = evidence._contract_payload()
    assert payload["failure_receipt_destination_policy_id"] == expected_policy
    # 4. Script receipt uses the canonical evidence constant
    envelope = tmp_path / "reg_envelope"
    envelope.mkdir(parents=True, exist_ok=True)
    child_receipt_test = envelope / "test_receipt_child"
    capture_part1._safe_failure(
        child_receipt_test, exact_commit_sha="f" * 40, capture_id="cap-test-reg",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("test-err"),
    )
    written_receipt = json.loads((child_receipt_test / "p3-0-capture-failure.json").read_text(encoding="utf-8"))
    assert written_receipt["destination_policy_id"] == evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID
    # 5. No duplicate literal semantic owner remains in the capture script
    assert not hasattr(capture_part1, "SAFE_FAILURE_DESTINATION_POLICY_ID")
    capture_script_text = Path(capture_part1.__file__).read_text(encoding="utf-8")
    assert "SAFE_FAILURE_DESTINATION_POLICY_ID =" not in capture_script_text

    # B. Atomic child claim
    # 6. Parent envelope exists + child absent: child creation succeeds exactly once
    atomic_child = envelope / "claim_test_child"
    assert not atomic_child.exists()
    assert capture_part1._claim_absent_failure_destination(atomic_child) is True
    assert atomic_child.is_dir()
    # 7. Second claim against same child fails closed
    assert capture_part1._claim_absent_failure_destination(atomic_child) is False

    # 8. Empty preexisting child remains untouched
    empty_child = envelope / "empty_child"
    empty_child.mkdir(parents=False, exist_ok=False)
    assert capture_part1._claim_absent_failure_destination(empty_child) is False
    capture_part1._safe_failure(
        empty_child, exact_commit_sha="a" * 40, capture_id="cap-empty",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert list(empty_child.iterdir()) == []

    # 9. Nonempty preexisting unmanifested child remains untouched
    nonempty_child = envelope / "nonempty_child"
    nonempty_child.mkdir(parents=False, exist_ok=False)
    file_in_nonempty = nonempty_child / "data.bin"
    file_in_nonempty.write_bytes(b"hello world")
    assert capture_part1._claim_absent_failure_destination(nonempty_child) is False
    capture_part1._safe_failure(
        nonempty_child, exact_commit_sha="a" * 40, capture_id="cap-nonempty",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert list(nonempty_child.iterdir()) == [file_in_nonempty]
    assert file_in_nonempty.read_bytes() == b"hello world"

    # 10. Published manifest child remains untouched
    published_child = envelope / "published_child"
    bundle = _bundle()
    evidence.write_capture_artifact(bundle, published_child)
    pub_manifest_before = (published_child / "manifest.json").read_bytes()
    assert capture_part1._claim_absent_failure_destination(published_child) is False
    capture_part1._safe_failure(
        published_child, exact_commit_sha="a" * 40, capture_id="cap-pub",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert not (published_child / "p3-0-capture-failure.json").exists()
    assert (published_child / "manifest.json").read_bytes() == pub_manifest_before

    # 11. Preexisting regular file remains untouched
    regular_file = envelope / "file_child"
    regular_file.write_bytes(b"untouchable")
    assert capture_part1._claim_absent_failure_destination(regular_file) is False
    capture_part1._safe_failure(
        regular_file, exact_commit_sha="a" * 40, capture_id="cap-file",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert regular_file.is_file()
    assert regular_file.read_bytes() == b"untouchable"

    # 12. Symlink/broken symlink remains untouched where platform permits
    sym_dest = envelope / "sym_child"
    sym_target = envelope / "sym_target.txt"
    sym_target.write_text("target", encoding="utf-8")
    try:
        sym_dest.symlink_to(sym_target)
        assert capture_part1._claim_absent_failure_destination(sym_dest) is False
        sym_target.unlink()
        assert capture_part1._claim_absent_failure_destination(sym_dest) is False
    except (OSError, NotImplementedError):
        pass

    # 13. Missing parent is NOT created
    missing_parent = envelope / "missing_parent_dir" / "child"
    assert not missing_parent.parent.exists()
    assert capture_part1._claim_absent_failure_destination(missing_parent) is False
    assert not missing_parent.parent.exists()
    assert not missing_parent.exists()

    # 14. Parent file is NOT modified
    parent_as_file = envelope / "parent_is_a_file"
    parent_as_file.write_bytes(b"parent content")
    child_under_file = parent_as_file / "child"
    assert capture_part1._claim_absent_failure_destination(child_under_file) is False
    assert parent_as_file.read_bytes() == b"parent content"

    # 15. Parent symlink is NOT traversed for failure-receipt creation
    parent_sym_target = envelope / "real_parent_target"
    parent_sym_target.mkdir(parents=False, exist_ok=False)
    parent_sym = envelope / "parent_symlink"
    try:
        parent_sym.symlink_to(parent_sym_target, target_is_directory=True)
        child_under_sym = parent_sym / "child"
        assert capture_part1._claim_absent_failure_destination(child_under_sym) is False
        assert not (parent_sym_target / "child").exists()
    except (OSError, NotImplementedError):
        pass

    # C. Receipt semantics
    # 16. Successful atomic claim writes exactly one p3-0-capture-failure.json
    atomic_receipt_child = envelope / "atomic_receipt_child"
    capture_part1._safe_failure(
        atomic_receipt_child, exact_commit_sha="a" * 40, capture_id="cap-receipt-test",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    files_in_child = list(atomic_receipt_child.iterdir())
    assert files_in_child == [atomic_receipt_child / "p3-0-capture-failure.json"]
    # 17. Receipt includes canonical destination_policy_id
    rcpt = json.loads(files_in_child[0].read_text(encoding="utf-8"))
    assert rcpt["destination_policy_id"] == evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID
    # 18. Existing child gets no failure receipt
    capture_part1._safe_failure(
        empty_child, exact_commit_sha="a" * 40, capture_id="cap-empty-2",
        started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("err"),
    )
    assert not (empty_child / "p3-0-capture-failure.json").exists()
    # 19. Original publication/source error remains process-visible even when failure receipt cannot be created
    with pytest.raises(capture_part1.P30PairedCaptureError) as exc_info:
        capture_part1._publish_capture_artifact(bundle, published_child)
    assert exc_info.value.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
    assert isinstance(exc_info.value.__cause__, evidence.P30ComparisonEvidenceError)

    # D. Readiness
    # 20-24. Check L proves canonical destination policy ID, atomic claim, preexisting child no mutation, no network, 14 checks passing
    repo_root = Path(__file__).resolve().parents[1]
    res_l = check_l_workflows_integrity(repo_root)
    assert res_l["status"] == "PASSED"
    assert res_l["atomic_child_claim_verified"] is True
    assert res_l["failure_receipt_destination_policy_verified"] is True
    assert res_l["preexisting_child_rejected"] is True
    assert res_l["writer_no_follow_preexistence_verified"] is True
    assert res_l["parent_symlink_rejected"] is True
    assert res_l["final_publication_recheck_verified"] is True


def test_canonical_writer_no_follow_and_race_window_regressions(tmp_path):
    """Prove canonical writer no-follow preexistence, parent validation, and race-window protections.

    Covers:
    1. _path_entry_preexists predicate (dir, file, live symlink, broken symlink, absent, error fail-closed).
    2. write_capture_artifact pre-checks (existing dir, nonempty dir, file, symlink, broken symlink).
    3. Parent envelope validation (missing parent, file parent, symlink parent, broken symlink parent).
    4. _publish_temporary_capture_directory race-window rejection (cases A-F).
    5. Temporary directory cleanup on publication failure.
    6. Production wrapper taxonomy and cause preservation.
    """
    import shutil
    import unittest.mock as mock
    from domain import p3_0_comparison_evidence as evidence
    from scripts import _p3_0_paired_capture_part1 as capture_part1

    bundle = _bundle()
    envelope = tmp_path / "writer_reg_envelope"
    envelope.mkdir(parents=True, exist_ok=False)

    # 1. _path_entry_preexists predicate
    # 1a. Absent path => False
    absent_p = envelope / "definitely_absent_123"
    assert evidence._path_entry_preexists(absent_p) is False

    # 1b. Directory => True
    test_d = envelope / "test_dir"
    test_d.mkdir(parents=False, exist_ok=False)
    assert evidence._path_entry_preexists(test_d) is True

    # 1c. Regular file => True
    test_f = envelope / "test_file.txt"
    test_f.write_text("content", encoding="utf-8")
    assert evidence._path_entry_preexists(test_f) is True

    # 1d. Live & broken symlink => True
    sym_dest = envelope / "test_sym"
    sym_tgt = envelope / "test_sym_target.txt"
    sym_tgt.write_text("tgt", encoding="utf-8")
    try:
        sym_dest.symlink_to(sym_tgt)
        assert evidence._path_entry_preexists(sym_dest) is True
        sym_tgt.unlink()
        assert evidence._path_entry_preexists(sym_dest) is True
        sym_dest.unlink()
    except (OSError, NotImplementedError):
        pass

    # 1e. Filesystem inspection error => fails closed as True
    with mock.patch("os.lstat", side_effect=OSError("disk read error")):
        assert evidence._path_entry_preexists(absent_p) is True

    # 2. write_capture_artifact pre-checks
    # 2a. Preexisting empty dir => raises exact error
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence.write_capture_artifact(bundle, test_d)

    # 2b. Preexisting nonempty dir => raises exact error, files unmutated
    (test_d / "keep.txt").write_text("keep this", encoding="utf-8")
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence.write_capture_artifact(bundle, test_d)
    assert (test_d / "keep.txt").read_text(encoding="utf-8") == "keep this"

    # 2c. Preexisting regular file => raises exact error, file unmutated
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence.write_capture_artifact(bundle, test_f)
    assert test_f.read_text(encoding="utf-8") == "content"

    # 2d. Preexisting broken symlink => raises exact error, symlink unmutated
    try:
        sym_dest.symlink_to(sym_tgt)  # sym_tgt does not exist -> broken symlink
        with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
            evidence.write_capture_artifact(bundle, sym_dest)
        assert sym_dest.is_symlink()
        sym_dest.unlink()
    except (OSError, NotImplementedError):
        pass

    # 3. Parent envelope validation
    # 3a. Missing parent => raises parent error
    missing_parent_dest = envelope / "missing_dir" / "capture"
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output parent must be an existing non-symlink directory"):
        evidence.write_capture_artifact(bundle, missing_parent_dest)
    assert not missing_parent_dest.parent.exists()

    # 3b. Parent is a regular file => raises parent error
    child_under_file = test_f / "capture"
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output parent must be an existing non-symlink directory"):
        evidence.write_capture_artifact(bundle, child_under_file)

    # 3c. Parent is a symlink to a directory => raises parent error
    parent_sym_target = envelope / "real_parent"
    parent_sym_target.mkdir(parents=False, exist_ok=False)
    parent_sym = envelope / "sym_parent"
    try:
        parent_sym.symlink_to(parent_sym_target, target_is_directory=True)
        child_under_sym_parent = parent_sym / "capture"
        with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output parent must be an existing non-symlink directory"):
            evidence.write_capture_artifact(bundle, child_under_sym_parent)
        assert not (parent_sym_target / "capture").exists()
    except (OSError, NotImplementedError):
        pass

    # 4. _publish_temporary_capture_directory race-window rejection (Cases A-F)
    # Case A: Destination absent => temporary artifact publishes successfully
    temp_a = envelope / "temp_a"
    temp_a.mkdir(parents=False, exist_ok=False)
    (temp_a / "file.txt").write_text("a", encoding="utf-8")
    dest_a = envelope / "dest_a"
    evidence._publish_temporary_capture_directory(temp_a, dest_a)
    assert dest_a.is_dir()
    assert (dest_a / "file.txt").read_text(encoding="utf-8") == "a"
    assert not temp_a.exists()

    # Case B: Destination is a broken symlink => fails closed, symlink unchanged
    temp_b = envelope / "temp_b"
    temp_b.mkdir(parents=False, exist_ok=False)
    (temp_b / "file.txt").write_text("b", encoding="utf-8")
    dest_b = envelope / "dest_b"
    try:
        dest_b.symlink_to(envelope / "nonexistent_b_target")
        with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
            evidence._publish_temporary_capture_directory(temp_b, dest_b)
        assert dest_b.is_symlink()
        dest_b.unlink()
    except (OSError, NotImplementedError):
        pass
    shutil.rmtree(temp_b, ignore_errors=True)

    # Case C: Destination is an empty directory => fails closed, 0 mutation
    temp_c = envelope / "temp_c"
    temp_c.mkdir(parents=False, exist_ok=False)
    (temp_c / "file.txt").write_text("c", encoding="utf-8")
    dest_c = envelope / "dest_c"
    dest_c.mkdir(parents=False, exist_ok=False)
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence._publish_temporary_capture_directory(temp_c, dest_c)
    assert list(dest_c.iterdir()) == []
    shutil.rmtree(temp_c, ignore_errors=True)

    # Case D: Destination is a nonempty directory => fails closed, full tree bytes unchanged
    temp_d = envelope / "temp_d"
    temp_d.mkdir(parents=False, exist_ok=False)
    (temp_d / "file.txt").write_text("d", encoding="utf-8")
    dest_d = envelope / "dest_d"
    dest_d.mkdir(parents=False, exist_ok=False)
    (dest_d / "existing.txt").write_text("original_d", encoding="utf-8")
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence._publish_temporary_capture_directory(temp_d, dest_d)
    assert (dest_d / "existing.txt").read_text(encoding="utf-8") == "original_d"
    shutil.rmtree(temp_d, ignore_errors=True)

    # Case E: Destination is a regular file => fails closed, bytes unchanged
    temp_e = envelope / "temp_e"
    temp_e.mkdir(parents=False, exist_ok=False)
    (temp_e / "file.txt").write_text("e", encoding="utf-8")
    dest_e = envelope / "dest_e.txt"
    dest_e.write_text("original_e", encoding="utf-8")
    with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
        evidence._publish_temporary_capture_directory(temp_e, dest_e)
    assert dest_e.read_text(encoding="utf-8") == "original_e"
    shutil.rmtree(temp_e, ignore_errors=True)

    # Case F: Destination appears after writer's initial check (deterministic TOCTOU race)
    # We simulate this by intercepting _publish_temporary_capture_directory:
    # right before _publish_temporary_capture_directory is called, destination is created.
    dest_f = envelope / "dest_f"
    assert not dest_f.exists()

    orig_pub = evidence._publish_temporary_capture_directory
    def racing_publish(temp_dir, destination):
        # Destination appears during temporary directory build window!
        destination.mkdir(parents=False, exist_ok=False)
        (destination / "raced_marker.txt").write_text("raced", encoding="utf-8")
        return orig_pub(temp_dir, destination)

    with mock.patch("domain._p3_0_comparison_evidence_part4._publish_temporary_capture_directory", side_effect=racing_publish):
        with pytest.raises(evidence.P30ComparisonEvidenceError, match="capture output directory already exists"):
            evidence.write_capture_artifact(bundle, dest_f)

    # Destination was NOT overwritten
    assert (dest_f / "raced_marker.txt").read_text(encoding="utf-8") == "raced"
    assert not (dest_f / "manifest.json").exists()

    # 5. Temporary directory cleanup proof:
    # No orphaned temporary directories remained in envelope
    temp_dirs = [p for p in envelope.iterdir() if p.name.startswith("p3-0-evidence-")]
    assert temp_dirs == []

    # 6. Production wrapper wraps writer rejection as CAPTURE_ARTIFACT_PUBLICATION_FAILED
    with pytest.raises(capture_part1.P30PairedCaptureError) as exc_info:
        capture_part1._publish_capture_artifact(bundle, dest_f)
    assert exc_info.value.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
    assert isinstance(exc_info.value.__cause__, evidence.P30ComparisonEvidenceError)
    assert "capture output directory already exists" in str(exc_info.value.__cause__)
