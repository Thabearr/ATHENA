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
