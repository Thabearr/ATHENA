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

if __name__ == '__main__':
    unittest.main()
