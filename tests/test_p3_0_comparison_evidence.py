from __future__ import annotations

import ast
import copy
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from domain import p3_0_comparison_evidence as evidence
from domain.markets import DecisionStatus
from services.analysis_pipeline import AnalysisPipeline


def _identity(**overrides):
    value = {
        "fixture_identity": "FOTMOB:fixture-100",
        "fixture_identity_policy": "EXACT_SOURCE_ID_V1",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "home_source_id": 101,
        "away_source_id": 202,
        "competition_identity": "COMP:1",
        "competition_name": "Test League",
        "kickoff": "2026-10-01T15:00:00Z",
        "fixture_source": "FOTMOB",
        "fixture_source_event_id": "100",
        "fixture_source_observed_at": "2026-09-30T12:00:00Z",
        "fixture_source_artifact_sha256": "a" * 64,
        "fixture_source_manifest_sha256": "b" * 64,
    }
    value.update(overrides)
    return value


def _timing(**overrides):
    value = {
        "legacy_evidence_observed_at": "2026-09-30T12:00:00Z",
        "legacy_evaluation_time": "2026-09-30T12:05:00Z",
        "probability_evaluation_time": "2026-09-30T12:05:00Z",
        "provider_quote_observed_at": "2026-09-30T12:04:00Z",
        "canonical_price_all_evaluation_time": "2026-09-30T12:05:00Z",
        "canonical_router_evaluation_time": "2026-09-30T12:05:00Z",
        "kickoff_time": "2026-10-01T15:00:00Z",
        "common_as_of_time": "2026-09-30T12:05:00Z",
        "common_as_of_proven": True,
    }
    value.update(overrides)
    return value


def _authority(profile="SHADOW"):
    return {
        "canonical_core_policy_id": "ATHENA_SHARED_CANONICAL_CORE_V1",
        "canonical_core_contract_sha256": "c" * 64,
        "authority_manifest_sha256": "d" * 64,
        "registry_canonical_sha256": "e" * 64,
        "authority_profile": profile,
        "resolved_components": [
            {
                "responsibility_id": responsibility,
                "component_id": component,
                "contract_sha256": "f" * 64,
                "artifact_git_blob_sha": f"{index + 1:x}" * 40,
            }
            for index, (responsibility, component) in enumerate(
                (
                    ("provider_market_semantics", "domain.provider_market_semantics"),
                    ("price_all_and_de_vig", "domain.price_all"),
                    ("market_router", "domain.market_router_canonical_adapter"),
                    ("portfolio_optimizer", "domain.portfolio_optimizer"),
                    ("delivery_share_code_transport", "domain.sportybet_share_code"),
                )
            )
        ],
    }


def _full_record(**overrides):
    values = {
        "fixture_capture_id": "fixture-100",
        "legacy_identity": _identity(),
        "canonical_identity": _identity(),
        "timing": _timing(),
        "canonical_authority": _authority(),
        "legacy_input": {"fixture_id": "fixture-100", "current_home_form": {"score": 0.7}},
        "legacy_output": {"decision_status": "ANALYTICAL_CANDIDATE", "recommended_analytical_verdict": "HOME_WIN"},
        "canonical_fixture_state": {"fixture_identity": "FOTMOB:fixture-100"},
        "probability_bundle": {"canonical_sha256": "0" * 64},
        "provider_semantics": {"provider_event_id": "100", "market_identity": "MATCH_RESULT"},
        "quote_snapshot": {"quote_identity_sha256": "9" * 64, "decimal_odds": 1.5},
        "price_all_output": {"canonical_sha256": "8" * 64},
        "router_output": {"canonical_sha256": "7" * 64},
    }
    values.update(overrides)
    return evidence.build_fixture_record(**values)


def _bundle(records=None):
    return evidence.build_capture_bundle(
        repository_commit_sha="a" * 40,
        capture_id="capture-20261001-a",
        capture_started_at="2026-09-30T12:00:00Z",
        capture_completed_at="2026-09-30T12:06:00Z",
        requested_dates=["20261001"],
        legacy_execution_identity={"path": "AnalysisPipeline.run_pipeline_snapshot"},
        canonical_execution_identity={"path": "CanonicalCoreBindings.price_all_as_of->route_as_of"},
        authority_state={"main_authority": False, "authority_profile": "SHADOW"},
        source_artifacts=[{"artifact_sha256": "a" * 64, "kind": "captured_source"}],
        fixture_records=records if records is not None else [_full_record()],
    )


class P30ComparisonEvidenceTests(unittest.TestCase):
    def test_complete_capture_is_deterministic_and_exactly_joined(self):
        first = _bundle()
        second = _bundle()
        self.assertEqual(first, second)
        row = first["fixture_records"][0]
        self.assertEqual(row["join_receipt"]["join_state"], "EXACT_SAME_FIXTURE_PROVEN")
        self.assertEqual(row["completeness_receipt"]["state"], "P3_0_CAPTURE_COMPLETE")
        self.assertEqual(evidence.verify_capture_bundle(first), first)

    def test_duplicate_json_and_non_finite_values_fail_closed(self):
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            evidence.load_json_bytes(b'{"a":1,"a":2}')
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            evidence.canonical_json_bytes({"value": math.nan})
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            evidence.canonical_json_bytes({"value": math.inf})

    def test_exact_fixture_join_rejects_identity_kickoff_and_competition_drift(self):
        exact = evidence.build_join_receipt(_identity(), _identity(), _timing())
        self.assertEqual(exact["join_state"], "EXACT_SAME_FIXTURE_PROVEN")
        different_team_name = evidence.build_join_receipt(
            _identity(home_team="Alpha United"), _identity(), _timing()
        )
        self.assertEqual(different_team_name["join_state"], "EXACT_SAME_FIXTURE_PROVEN")
        # Team names are evidence, never a fuzzy join key; exact source identity
        # is what proves this pair.
        mismatch = evidence.build_join_receipt(
            _identity(fixture_identity="FOTMOB:100"), _identity(fixture_identity="FOTMOB:101"), _timing()
        )
        self.assertEqual(mismatch["join_state"], "IDENTITY_AMBIGUOUS")
        kickoff = evidence.build_join_receipt(_identity(), _identity(kickoff="2026-10-01T16:00:00Z"), _timing())
        self.assertEqual(kickoff["join_state"], "KICKOFF_MISMATCH")
        competition = evidence.build_join_receipt(_identity(), _identity(competition_identity="COMP:2"), _timing())
        self.assertEqual(competition["join_state"], "COMPETITION_MISMATCH")

    def test_missing_evidence_stays_partial_and_common_as_of_is_not_invented(self):
        record = _full_record(
            legacy_output=None,
            probability_bundle=None,
            quote_snapshot=None,
            timing=_timing(common_as_of_proven=False, common_as_of_time=None, provider_quote_observed_at=None),
        )
        self.assertEqual(record["completeness_receipt"]["state"], "P3_0_CAPTURE_PARTIAL")
        self.assertEqual(
            record["completeness_receipt"]["missing_reasons"],
            ["COMMON_AS_OF_UNPROVEN", "MISSING_LEGACY_OUTPUT", "MISSING_MARKET_PROBABILITY_BUNDLE", "MISSING_QUOTE", "MISSING_QUOTE_OBSERVED_AT"],
        )

    def test_ambiguous_join_is_unusable(self):
        record = _full_record(canonical_identity=_identity(fixture_identity="FOTMOB:fixture-101"))
        self.assertEqual(record["completeness_receipt"]["state"], "P3_0_CAPTURE_UNUSABLE")

    def test_shadow_only_canonical_authority_and_sensitive_projection_are_enforced(self):
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            evidence.normalize_canonical_authority(_authority("MAIN"))
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            _full_record(legacy_input={"fixture_id": "fixture-100", "authorization": "forbidden"})
        with self.assertRaises(evidence.P30ComparisonEvidenceError):
            _full_record(quote_snapshot={"cookie_value": "forbidden"})

    def test_manifest_hashes_detect_tampering(self):
        bundle = _bundle()
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "p3-evidence"
            evidence.write_capture_artifact(bundle, output)
            self.assertEqual(evidence.verify_capture_artifact(output)["canonical_sha256"], bundle["canonical_sha256"])
            (output / "bundle.json").write_bytes(b"{}\n")
            with self.assertRaises(evidence.P30ComparisonEvidenceError):
                evidence.verify_capture_artifact(output)

    def test_observer_captures_copies_and_cannot_mutate_pipeline_result(self):
        observer = evidence.LegacyEvidenceObserver()
        source_context = {"fixture_id": "fixture-100", "current_home_form": {"score": 0.7}}
        source_pre_gate = {"decision_status": "BET", "accumulator_eligible_selection": {"market": "HOME_WIN"}}
        source_analysis = {"decision_status": "ANALYTICAL_CANDIDATE", "no_bet_reasons": []}
        exported = {"fixture_id": "fixture-100", "decision_status": "ANALYTICAL_CANDIDATE"}
        observer(source_context, source_pre_gate, source_analysis, exported)
        source_context["current_home_form"]["score"] = 0.1
        source_pre_gate["accumulator_eligible_selection"]["market"] = "MUTATED"
        source_analysis["no_bet_reasons"].append("mutated")
        self.assertEqual(observer.observations()[0]["legacy_input"]["current_home_form"]["score"], 0.7)
        self.assertEqual(
            observer.observations()[0]["legacy_output"]["legacy_analysis_before_runtime_gate"]["accumulator_eligible_selection"]["market"],
            "HOME_WIN",
        )
        self.assertEqual(observer.observations()[0]["legacy_output"]["authorized_analysis"]["no_bet_reasons"], [])

    def test_pipeline_observer_is_default_off_return_ignored_and_failure_contained(self):
        fixture = {
            "fixture_id": "capture-fixture",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "league": "Test League",
            "match_date": "2026-10-01T15:00:00",
        }

        def analyst_result(_context):
            return {
                "decision_status": DecisionStatus.BET.value,
                "recommended_analytical_verdict": "HOME_WIN",
                "viable_markets": [],
                "accumulator_eligible_selection": None,
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
            pre_gate["decision_status"] = "ANALYTICAL_CANDIDATE"
            analysis["decision_status"] = "BET"
            row["decision_status"] = "BET"
            received.append((context, pre_gate, analysis, row))
            return {"replacement": "forbidden"}

        observed = pipeline().run_pipeline_snapshot(override_fixtures=[copy.deepcopy(fixture)], evidence_observer=observer)
        self.assertEqual(observed, baseline)
        self.assertEqual(len(received), 1)
        contained = pipeline().run_pipeline_snapshot(
            override_fixtures=[copy.deepcopy(fixture)],
            evidence_observer=lambda *_args: (_ for _ in ()).throw(RuntimeError("capture failure")),
        )
        self.assertEqual(contained, baseline)

    def test_capture_code_has_no_provider_delivery_or_wager_imports(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = {"requests", "selenium", "playwright", "wallet", "wager", "staking", "sportybet"}
        for relative in ("domain/p3_0_comparison_evidence.py", "scripts/capture_p3_0_comparison_evidence.py"):
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertTrue(forbidden.isdisjoint(imports), f"{relative} imports forbidden boundary: {imports}")


if __name__ == "__main__":
    unittest.main()
