from tests._p3_0_comparison_evidence_support import *  # noqa: F401,F403

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


def test_bundle_and_artifact_are_deterministic(tmp_path):
    first = _bundle(); second = _bundle()
    assert first == second
    assert evidence.verify_capture_bundle(first) == first
    output = tmp_path / "capture"
    evidence.write_capture_artifact(first, output)
    assert evidence.verify_capture_artifact(output) == first
