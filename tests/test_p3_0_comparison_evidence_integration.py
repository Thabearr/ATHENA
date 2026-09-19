from tests._p3_0_comparison_evidence_support import *  # noqa: F401,F403
from scripts import _p3_0_paired_capture_part1 as capture_part1


def _failure_receipt(tmp_path, exc):
    capture_part1._safe_failure(
        tmp_path, exact_commit_sha="a" * 40, capture_id="failure-test",
        started_at="2026-09-12T00:00:00.000000Z", exc=exc,
    )
    return json.loads((tmp_path / "p3-0-capture-failure.json").read_text(encoding="utf-8"))


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

    # 3. CAPTURE_ARTIFACT_PUBLICATION_FAILED: test wrapping and preserved cause
    try:
        try:
            raise OSError("disk full simulation")
        except OSError as inner:
            pub_err = capture_part1.P30PairedCaptureError(
                f"CAPTURE_ARTIFACT_PUBLICATION_FAILED: OSError: {inner}"
            )
            pub_err.failure_code = evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
            raise pub_err from inner
    except capture_part1.P30PairedCaptureError as raised_pub_err:
        assert raised_pub_err.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
        assert isinstance(raised_pub_err.__cause__, OSError)
        assert str(raised_pub_err.__cause__) == "disk full simulation"
        failure_dir = tmp_path / "failure_receipt_dir"
        capture_part1._safe_failure(
            failure_dir,
            exact_commit_sha="b" * 40,
            capture_id="pub-failure-test",
            started_at="2026-09-20T00:00:00.000000Z",
            exc=raised_pub_err,
        )
        receipt = json.loads((failure_dir / "p3-0-capture-failure.json").read_text(encoding="utf-8"))
        assert receipt["failure_code"] == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
        assert receipt["failure_type"] == "P30PairedCaptureError"
        assert receipt["failure_chain"][1]["exception_type"] == "OSError"
        assert receipt["failure_chain"][1]["message"] == "disk full simulation"

    # 4. Source acquisition failure is NOT mislabeled as publication failure
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
