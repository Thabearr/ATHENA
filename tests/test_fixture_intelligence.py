import unittest
import datetime
import json
from domain.fixture_intelligence import (
    IntelligenceCategory,
    SourceRole,
    IntelligenceFactStatus,
    FixtureIntelligenceFact,
    CategoryCoverage,
    FixtureIntelligenceSnapshot,
    FixtureIntelligenceError,
    build_snapshot,
    snapshot_to_dict,
    canonical_snapshot_bytes,
    sha256_bytes,
    DATASET_NAME,
    SCHEMA_VERSION
)

class TestFixtureIntelligence(unittest.TestCase):
    def _make_fact(self, **kwargs):
        defaults = {
            "category": IntelligenceCategory.FIXTURE_CONTEXT,
            "field": "test-field",
            "status": IntelligenceFactStatus.SUPPORTED,
            "value": {"some": "data"},
            "source_provider": "test-provider",
            "source_role": SourceRole.PRIMARY_FOOTBALL_CONTEXT,
            "source_reference": "ref",
            "observed_at": datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc),
            "evidence_file_path": "path/to/evidence.json",
            "evidence_sha256": "a" * 64,
            "notes": None
        }
        defaults.update(kwargs)
        return FixtureIntelligenceFact(**defaults)

    def _make_snapshot(self, facts, kickoff=None, as_of=None):
        ko = kickoff or datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = as_of or datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        return build_snapshot("test-fixture", ko, ao, facts)

    def test_01_valid_supported_fact(self):
        f = self._make_fact(status=IntelligenceFactStatus.SUPPORTED)
        self.assertEqual(f.status, IntelligenceFactStatus.SUPPORTED)

    def test_02_valid_stale_fact(self):
        f = self._make_fact(status=IntelligenceFactStatus.STALE)
        self.assertEqual(f.status, IntelligenceFactStatus.STALE)

    def test_03_valid_conflicted_fact(self):
        f = self._make_fact(status=IntelligenceFactStatus.CONFLICTED)
        self.assertEqual(f.status, IntelligenceFactStatus.CONFLICTED)

    def test_04_valid_unverified_fact(self):
        f = self._make_fact(status=IntelligenceFactStatus.UNVERIFIED)
        self.assertEqual(f.status, IntelligenceFactStatus.UNVERIFIED)

    def test_05_discovery_only_unverified(self):
        f = self._make_fact(source_role=SourceRole.DISCOVERY_ONLY, status=IntelligenceFactStatus.UNVERIFIED)
        self.assertEqual(f.status, IntelligenceFactStatus.UNVERIFIED)

    def test_06_discovery_only_supported_raises(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_role=SourceRole.DISCOVERY_ONLY, status=IntelligenceFactStatus.SUPPORTED)

    def test_07_naive_observed_at_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(observed_at=datetime.datetime(2023, 1, 1))

    def test_08_observed_at_after_as_of_rejected(self):
        f = self._make_fact(observed_at=datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc))
        ko = datetime.datetime(2023, 1, 3, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            self._make_snapshot([f], ko, ao)

    def test_09_naive_as_of_rejected(self):
        f = self._make_fact()
        ko = datetime.datetime(2023, 1, 3, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1)
        with self.assertRaises(FixtureIntelligenceError):
            self._make_snapshot([f], ko, ao)

    def test_10_as_of_gte_kickoff_rejected(self):
        f = self._make_fact()
        ko = datetime.datetime(2023, 1, 3, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 3, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            self._make_snapshot([f], ko, ao)
        ao2 = datetime.datetime(2023, 1, 4, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            self._make_snapshot([f], ko, ao2)

    def test_11_invalid_sha_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_sha256="short")

    def test_12_uppercase_sha_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_sha256=("A" * 64))

    def test_13_absolute_evidence_path_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path="/tmp/test.json")

    def test_14_traversal_evidence_path_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path="../test.json")

    def test_15_padded_field_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(field=" test")

    def test_16_padded_source_provider_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_provider=" test")

    def test_17_blank_source_reference_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_reference="")

    def test_18_nan_value_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(value=float('nan'))

    def test_19_infinity_value_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(value=float('inf'))

    def test_20_non_string_dict_key_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(value={1: "a"})

    def test_21_unsupported_object_value_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(value=set([1, 2]))

    def test_22_deterministic_fact_sorting(self):
        f1 = self._make_fact(field="b")
        f2 = self._make_fact(field="a")
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(snap.facts[0].field, "a")
        self.assertEqual(snap.facts[1].field, "b")

    def test_23_input_reordering_yields_identical_bytes(self):
        f1 = self._make_fact(field="a")
        f2 = self._make_fact(field="b")
        b1 = canonical_snapshot_bytes(self._make_snapshot([f1, f2]))
        b2 = canonical_snapshot_bytes(self._make_snapshot([f2, f1]))
        self.assertEqual(b1, b2)

    def test_24_duplicate_equivalent_supported_no_conflict(self):
        f1 = self._make_fact(value={"a": 1})
        f2 = self._make_fact(value={"a": 1}, source_provider="other")
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(len(snap.conflicted_fields), 0)

    def test_25_different_supported_values_conflict(self):
        f1 = self._make_fact(value={"a": 1})
        f2 = self._make_fact(value={"a": 2}, source_provider="other")
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(len(snap.conflicted_fields), 1)
        self.assertEqual(snap.conflicted_fields[0], (IntelligenceCategory.FIXTURE_CONTEXT.value, "test-field"))

    def test_26_stale_vs_supported_no_override(self):
        f1 = self._make_fact(status=IntelligenceFactStatus.SUPPORTED)
        f2 = self._make_fact(status=IntelligenceFactStatus.STALE, value={"diff": 1})
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(len(snap.conflicted_fields), 0)

    def test_27_unverified_vs_supported_no_override(self):
        f1 = self._make_fact(status=IntelligenceFactStatus.SUPPORTED)
        f2 = self._make_fact(status=IntelligenceFactStatus.UNVERIFIED, value={"diff": 1})
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(len(snap.conflicted_fields), 0)
        self.assertEqual(len(snap.unverified_fields), 1)

    def test_28_category_coverage_includes_all(self):
        snap = self._make_snapshot([])
        self.assertEqual(len(snap.category_coverage), len(IntelligenceCategory))

    def test_29_empty_categories_remain_zero(self):
        snap = self._make_snapshot([])
        for cov in snap.category_coverage:
            self.assertEqual(cov.supported, 0)
            self.assertEqual(cov.has_any_evidence, False)

    def test_30_unverified_fields_deterministic(self):
        f1 = self._make_fact(field="b", status=IntelligenceFactStatus.UNVERIFIED)
        f2 = self._make_fact(field="a", status=IntelligenceFactStatus.UNVERIFIED)
        snap = self._make_snapshot([f1, f2])
        self.assertEqual(snap.unverified_fields[0][1], "a")
        self.assertEqual(snap.unverified_fields[1][1], "b")

    def test_31_conflicted_fields_deterministic(self):
        f1 = self._make_fact(field="b", value=1)
        f2 = self._make_fact(field="b", value=2, source_provider="o")
        f3 = self._make_fact(field="a", value=1)
        f4 = self._make_fact(field="a", value=2, source_provider="o")
        snap = self._make_snapshot([f1, f2, f3, f4])
        self.assertEqual(snap.conflicted_fields[0][1], "a")
        self.assertEqual(snap.conflicted_fields[1][1], "b")

    def test_32_canonical_utc_serialization(self):
        f = self._make_fact()
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        snap = build_snapshot("test", ko, ao, [f])
        d = snapshot_to_dict(snap)
        self.assertTrue(d["kickoff"].endswith("Z") or d["kickoff"].endswith("+00:00"))
        
    def test_33_canonical_snapshot_bytes_ends_with_newline(self):
        snap = self._make_snapshot([])
        b = canonical_snapshot_bytes(snap)
        self.assertTrue(b.endswith(b'\n'))

    def test_34_exact_dataset_name(self):
        snap = self._make_snapshot([])
        self.assertEqual(snap.dataset_name, 'athena-fixture-intelligence-snapshot-v1')

    def test_35_exact_schema_version(self):
        snap = self._make_snapshot([])
        self.assertEqual(snap.schema_version, 1)

    def test_36_every_safety_flag_false(self):
        snap = self._make_snapshot([])
        for k, v in snap.safety.items():
            self.assertFalse(v)

    def test_37_forbidden_network_imports_absent(self):
        with open("domain/fixture_intelligence.py", "r") as f:
            content = f.read()
        forbidden = ['import requests', 'import httpx', 'import aiohttp', 'import urllib.request', 'import playwright', 'import selenium']
        for bad in forbidden:
            self.assertNotIn(bad, content)

    def test_38_forbidden_betting_fields_absent(self):
        with open("domain/fixture_intelligence.py", "r") as f:
            content = f.read()
        forbidden = [' odds', 'kelly', 'expected_value', 'staking', 'accumulator']
        for bad in forbidden:
            self.assertNotIn(bad, content)

    def test_39_fixture_identifier_preserved(self):
        snap = self._make_snapshot([], kickoff=datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc), as_of=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc))
        self.assertEqual(snap.fixture_identifier, "test-fixture")

    def test_40_no_implicit_wall_clock_calls(self):
        with open("domain/fixture_intelligence.py", "r") as f:
            content = f.read()
        self.assertNotIn("datetime.now()", content)
        self.assertNotIn("time.time()", content)


    _SAFE_DICT = {
        "network_acquisition_authorized": False,
        "scraping_authorized": False,
        "browser_automation_authorized": False,
        "pricing_authorized": False,
        "market_activation_authorized": False,
        "prospective_claim_authorized": False,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "bet_authorized": False
    }

    def test_nested_dict_mutation_after_construction(self):
        val = {'key': [1, 2, 3]}
        fact = self._make_fact(value=val)
        val['key'].append(99)
        self.assertEqual(list(fact.value['key']), [1, 2, 3])

    def test_nested_list_mutation_after_construction(self):
        val = [{'a': 1}]
        fact = self._make_fact(value=val)
        val.append({'b': 2})
        self.assertEqual(len(fact.value), 1)

    def test_fact_value_cannot_be_mutated(self):
        fact = self._make_fact(value={'key': 'val'})
        with self.assertRaises(TypeError):
            fact.value['key'] = 'mutated'

    def test_snapshot_safety_immutable(self):
        snap = self._make_snapshot([])
        with self.assertRaises(TypeError):
            snap.safety['bet_authorized'] = True

    def test_caller_safety_mutation_does_not_affect_snapshot(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        my_safety = dict(self._SAFE_DICT)
        snap = FixtureIntelligenceSnapshot(
            schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
            kickoff=ko, as_of=ao, facts=real_snap.facts,
            category_coverage=real_snap.category_coverage,
            conflicted_fields=real_snap.conflicted_fields,
            unverified_fields=real_snap.unverified_fields,
            safety=my_safety)
        b1 = canonical_snapshot_bytes(snap)
        my_safety['bet_authorized'] = True
        self.assertFalse(snap.safety['bet_authorized'])
        b2 = canonical_snapshot_bytes(snap)
        self.assertEqual(b1, b2)
        with self.assertRaises(TypeError):
            snap.safety['bet_authorized'] = True

    def test_canonical_bytes_stable_after_input_mutation(self):
        val = {'key': [1, 2]}
        snap = self._make_snapshot(facts=[self._make_fact(value=val)])
        b1 = canonical_snapshot_bytes(snap)
        val['key'].append(99)
        b2 = canonical_snapshot_bytes(snap)
        self.assertEqual(b1, b2)

    def test_dishonest_conflicted_fields_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        f1 = self._make_fact(status=IntelligenceFactStatus.SUPPORTED, value='alpha', evidence_sha256='a'*64)
        f2 = self._make_fact(status=IntelligenceFactStatus.SUPPORTED, value='beta', evidence_sha256='b'*64)
        real_snap = build_snapshot('X', ko, ao, [f1, f2])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=(),
                unverified_fields=real_snap.unverified_fields,
                safety=dict(self._SAFE_DICT))

    def test_dishonest_unverified_fields_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        f1 = self._make_fact(status=IntelligenceFactStatus.UNVERIFIED, value='alpha', evidence_sha256='a'*64)
        real_snap = build_snapshot('X', ko, ao, [f1])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=(),
                safety=dict(self._SAFE_DICT))

    def test_dishonest_category_coverage_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        f1 = self._make_fact()
        real_snap = build_snapshot('X', ko, ao, [f1])
        bad_cov = [CategoryCoverage(c.category, 0, 0, 0, 0, False) for c in real_snap.category_coverage]
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=tuple(bad_cov),
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=dict(self._SAFE_DICT))

    def test_negative_coverage_count_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            CategoryCoverage(IntelligenceCategory.FIXTURE_CONTEXT, -1, 0, 0, 0, False)

    def test_duplicate_coverage_category_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        bad_cov = list(real_snap.category_coverage)
        bad_cov[1] = bad_cov[0]
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=tuple(bad_cov),
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=dict(self._SAFE_DICT))

    def test_missing_coverage_category_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        bad_cov = list(real_snap.category_coverage)[1:]
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=tuple(bad_cov),
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=dict(self._SAFE_DICT))

    def test_discovery_only_stale_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_role=SourceRole.DISCOVERY_ONLY, status=IntelligenceFactStatus.STALE)

    def test_discovery_only_conflicted_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_role=SourceRole.DISCOVERY_ONLY, status=IntelligenceFactStatus.CONFLICTED)

    def test_discovery_only_unverified_accepted(self):
        fact = self._make_fact(source_role=SourceRole.DISCOVERY_ONLY, status=IntelligenceFactStatus.UNVERIFIED)
        self.assertIsNotNone(fact)

    def test_string_category_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(category='FORM')

    def test_string_status_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(status='SUPPORTED')

    def test_string_source_role_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_role='DISCOVERY_ONLY')

    def test_non_fact_in_raw_facts_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            build_snapshot('X', ko, ao, ['not-a-fact'])

    def test_build_snapshot_none_raw_facts_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            build_snapshot('X', ko, ao, None)

    def test_build_snapshot_int_raw_facts_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            build_snapshot('X', ko, ao, 123)

    def test_build_snapshot_string_raw_facts_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        with self.assertRaises(FixtureIntelligenceError):
            build_snapshot('X', ko, ao, 'bad')

    def test_build_snapshot_mixed_raw_facts_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        valid_fact = self._make_fact()
        with self.assertRaises(FixtureIntelligenceError):
            build_snapshot('X', ko, ao, [valid_fact, 'bad_string'])

    def test_tie_breaking_determinism(self):
        sha = 'a' * 64
        f1 = self._make_fact(value='alpha_value', source_reference='ref-alpha', evidence_sha256=sha)
        f2 = self._make_fact(value='beta_value', source_reference='ref-beta', evidence_sha256=sha)
        snap_forward = self._make_snapshot([f1, f2])
        snap_reverse = self._make_snapshot([f2, f1])
        self.assertEqual(canonical_snapshot_bytes(snap_forward), canonical_snapshot_bytes(snap_reverse))

    def test_tie_breaking_determinism_reverse(self):
        sha = 'a' * 64
        f1 = self._make_fact(value='alpha_value', source_reference='ref-alpha', evidence_sha256=sha)
        f2 = self._make_fact(value='beta_value', source_reference='ref-beta', evidence_sha256=sha)
        snap_forward = self._make_snapshot([f1, f2])
        snap_reverse = self._make_snapshot([f2, f1])
        self.assertEqual(canonical_snapshot_bytes(snap_forward), canonical_snapshot_bytes(snap_reverse))

    def test_windows_backslash_path_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='C:\\evidence\\fact.json')

    def test_windows_forward_slash_path_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='C:/evidence/fact.json')

    def test_unc_path_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='\\\\server\\share\\evidence.json')

    def test_posix_absolute_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='/etc/evidence.json')

    def test_traversal_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='../../etc/passwd')

    def test_embedded_traversal_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='folder\\..\\fact.json')

    def test_normal_relative_path_accepted(self):
        fact = self._make_fact(evidence_file_path='evidence/fixture_123/fact.json')
        self.assertIsNotNone(fact)

    def test_windows_drive_relative_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='C:folder\\fact.json')

    def test_windows_root_relative_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='\\folder\\fact.json')

    def test_posix_unc_style_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(evidence_file_path='//server/share/fact.json')

    def test_windows_relative_with_backslashes_accepted(self):
        fact = self._make_fact(evidence_file_path='evidence\\fixture_123\\fact.json')
        self.assertIsNotNone(fact)

    def test_safety_zero_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        bad_safety = dict(self._SAFE_DICT)
        bad_safety['network_acquisition_authorized'] = 0
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=bad_safety)

    def test_safety_none_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        bad_safety = dict(self._SAFE_DICT)
        bad_safety['network_acquisition_authorized'] = None
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=bad_safety)

    def test_safety_empty_string_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        bad_safety = dict(self._SAFE_DICT)
        bad_safety['network_acquisition_authorized'] = ""
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety=bad_safety)

    def test_safety_exact_false_accepted(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        snap = FixtureIntelligenceSnapshot(
            schema_version=1, dataset_name=DATASET_NAME, fixture_identifier='X',
            kickoff=ko, as_of=ao, facts=real_snap.facts,
            category_coverage=real_snap.category_coverage,
            conflicted_fields=real_snap.conflicted_fields,
            unverified_fields=real_snap.unverified_fields,
            safety=dict(self._SAFE_DICT))
        self.assertIsNotNone(snap)

    def test_to_dict_method_exists(self):
        snap = self._make_snapshot([])
        result = snap.to_dict()
        self.assertIsInstance(result, dict)

    def test_to_dict_equals_compat_helper(self):
        snap = self._make_snapshot([])
        self.assertEqual(snap.to_dict(), snapshot_to_dict(snap))

    def test_to_dict_is_json_serializable(self):
        snap = self._make_snapshot([])
        json.dumps(snap.to_dict())

    def test_final_newline(self):
        snap = self._make_snapshot([])
        self.assertTrue(canonical_snapshot_bytes(snap).endswith(b'\n'))

    def test_whitespace_only_source_reference_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_reference='   ')

    def test_padded_source_reference_rejected(self):
        with self.assertRaises(FixtureIntelligenceError):
            self._make_fact(source_reference=' http://example.com')

    def test_category_coverage_has_all_ten_categories(self):
        snap = self._make_snapshot([])
        covered = {c.category for c in snap.category_coverage}
        self.assertEqual(covered, set(IntelligenceCategory))

    def test_no_forbidden_imports_in_domain(self):
        import inspect
        import domain.fixture_intelligence as mod
        src = inspect.getsource(mod)
        for forbidden in ['import requests', 'import httpx', 'import aiohttp', 'from urllib.request', 'kelly', 'expected_value', 'accumulator']:
            self.assertNotIn(forbidden, src.lower())

    def test_schema_version_true_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=True, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety={k: False for k in [
                    'network_acquisition_authorized', 'scraping_authorized',
                    'browser_automation_authorized', 'pricing_authorized',
                    'market_activation_authorized', 'prospective_claim_authorized',
                    'selection_authorized', 'production_approval_authorized', 'bet_authorized'
                ]})

    def test_schema_version_float_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=1.0, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety={k: False for k in [
                    'network_acquisition_authorized', 'scraping_authorized',
                    'browser_automation_authorized', 'pricing_authorized',
                    'market_activation_authorized', 'prospective_claim_authorized',
                    'selection_authorized', 'production_approval_authorized', 'bet_authorized'
                ]})

    def test_schema_version_string_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version='1', dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety={k: False for k in [
                    'network_acquisition_authorized', 'scraping_authorized',
                    'browser_automation_authorized', 'pricing_authorized',
                    'market_activation_authorized', 'prospective_claim_authorized',
                    'selection_authorized', 'production_approval_authorized', 'bet_authorized'
                ]})

    def test_schema_version_zero_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=0, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety={k: False for k in [
                    'network_acquisition_authorized', 'scraping_authorized',
                    'browser_automation_authorized', 'pricing_authorized',
                    'market_activation_authorized', 'prospective_claim_authorized',
                    'selection_authorized', 'production_approval_authorized', 'bet_authorized'
                ]})

    def test_schema_version_two_rejected(self):
        ko = datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc)
        ao = datetime.datetime(2023, 1, 1, 12, tzinfo=datetime.timezone.utc)
        real_snap = build_snapshot('X', ko, ao, [])
        with self.assertRaises(FixtureIntelligenceError):
            FixtureIntelligenceSnapshot(
                schema_version=2, dataset_name=DATASET_NAME, fixture_identifier='X',
                kickoff=ko, as_of=ao, facts=real_snap.facts,
                category_coverage=real_snap.category_coverage,
                conflicted_fields=real_snap.conflicted_fields,
                unverified_fields=real_snap.unverified_fields,
                safety={k: False for k in [
                    'network_acquisition_authorized', 'scraping_authorized',
                    'browser_automation_authorized', 'pricing_authorized',
                    'market_activation_authorized', 'prospective_claim_authorized',
                    'selection_authorized', 'production_approval_authorized', 'bet_authorized'
                ]})

    def test_schema_version_is_exact_int_in_snapshot(self):
        snap = self._make_snapshot([])
        self.assertIs(type(snap.schema_version), int)
        self.assertEqual(snap.schema_version, 1)

    def test_schema_version_is_exact_int_in_to_dict(self):
        snap = self._make_snapshot([])
        d = snap.to_dict()
        self.assertIs(type(d['schema_version']), int)
        self.assertEqual(d['schema_version'], 1)

if __name__ == '__main__':
    unittest.main()
