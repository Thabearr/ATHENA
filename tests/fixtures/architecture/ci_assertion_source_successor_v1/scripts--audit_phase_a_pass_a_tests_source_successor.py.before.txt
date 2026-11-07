"""One historical Pass-A Tests view, authenticated against current source first.

The pure core reads fixed tracked bytes/recipes only. A2 bootstrap may invoke it;
only the public historical source function invokes A2 and the Tests successor.
No frozen receipt, workflow, source authority or live discovery is changed.
"""
from __future__ import annotations
import hashlib
from collections.abc import Callable
import json
from scripts import audit_phase_a_b4_test_source_successor as safe

ROOT = safe.ROOT
FROZEN_IDENTITY = {'git_blob_sha1': '051c5061ce9a620c714cac4538bd6da97b00abae', 'source_sha256': 'c8fea2ac437a6dd167d9e0c4e555706d796f6ba74a22e12431a57d4444ac20e2', 'byte_count': 319457}
SOURCE = 'scripts/audit_core_01d_authority_reachability_review_a.py'
RECEIPT = 'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json'
RECEIPT_SHA256 = 'b0c7aa65d49413835137dff39b4c90b8d0aa530c8a2c0e36603451e612eb4f4c'
EDGES = {'scripts/audit_core_01d_authority_reachability_review_a.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt', 'before': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'after': {'git_blob_sha1': 'a7b7113de32e0d878c2d8d8b6a0823ee1bdb9fec', 'source_sha256': '9a6448f92f2e1373e928218ee73d9702fcd1a2e61f3dcb82bdec3f7ee134d754', 'byte_count': 47083}, 'replacement_before': 'def source_bytes(path):\n', 'replacement_after': "def source_bytes(path):\n if path == '.github/workflows/tests.yml':\n  from scripts import audit_phase_a_pass_a_tests_source_successor as forward\n  try:\n   return forward.historical_workflow_source()\n  except ValueError as exc:\n   require(False, 'exact Tests historical source-forward failed: '+str(exc))\n"}, 'scripts/audit_phase_a_b4_test_source_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt', 'before': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'after': {'git_blob_sha1': '7c8371a2f30379078f9428585443d28effa4145f', 'source_sha256': 'b7f9a61cd347e56eb8c66cfee83ff9292f45ed8ff2a61e2fd82cd011697333de', 'byte_count': 10702}, 'replacement_before': '    value = receipt()\n    if path == SOURCE:\n', 'replacement_after': '    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a\n    raw = pass_a.predecessor_source(path, raw)\n    value = receipt()\n    if path == SOURCE:\n'}, 'scripts/audit_phase_a_pc_upcoming_retention_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt', 'before': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}, 'after': {'git_blob_sha1': 'a7903e2d45abc8409f90987c0259c7a12ee7c193', 'source_sha256': '8a3d9ca477f991f2420af352aa125e30ed6f643b9355609c86853a54fd032836', 'byte_count': 59617}, 'append': '\n\n# Source-only Pass-A historical Tests view; current workflow stays unchanged.\nfrom scripts import audit_phase_a_pass_a_tests_source_successor as _pass_a_tests\n_pass_a_tests.install_context(globals())\n_authenticate_before_pass_a_tests = authenticate\n\n\ndef authenticate():\n    _pass_a_tests.authenticate_core()\n    return _authenticate_before_pass_a_tests()\n'}}
METADATA = {'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json': {'git_blob_sha1': '3b49db0bca4ef1b31dfe586415c94e13b98fc6cc', 'source_sha256': 'f112dad4cf1737e9bf281c4500daa0ff1fe4d47d8d9343a83c4c3540c780161c', 'byte_count': 6414}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}}
TEST = 'tests/test_phase_a_pass_a_tests_source_successor.py'
TEST_IDENTITY = {'git_blob_sha1': '53a0e5633a480cc238b15a585d17c90ca975d012', 'source_sha256': '2288b6f179bf16ff0fc80ce0347d5a2fe48cd8759ff08b98566802c51484f3de', 'byte_count': 6317}
TESTS_SHARD_V2_RECEIPT = 'artifacts/architecture/tests_shard_balance_successor_v2.json'
TESTS_SHARD_V2_RECEIPT_SHA256 = '63d7284158562e5f4dcabc93aca896ef009340cbbadb0724ad942c97aacdd4f3'
TESTS_SHARD_V2_SOURCE_PATHS = frozenset({
    'scripts/audit_tests_shard_balance_successor.py',
    'tests/test_tests_shard_balance_successor.py',
})
B1_SOURCE = 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py'
B1_FIXTURE = 'tests/fixtures/architecture/phase_a_b1_test_source_v1/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.before.txt'
B1_RECEIPT = 'artifacts/architecture/phase_a_b1_test_source_successor_v1.json'
B1_RECEIPT_SHA256 = '93c99d58eccefff00649c8dbf5a4e04930a107f1bbae76f81670880b4b771205'
B1_BEFORE = {'git_blob_sha1': '16217d76259d7a2784d4a6168737226df45dd576', 'source_sha256': 'cee602e4eea0dd9b9bfb13f56be87f820d3f5c7dbd336923a9ec1d2bf7a4089a', 'byte_count': 17122}
B1_AFTER = {'git_blob_sha1': '76890d944a83b122f3bf3e258cd67773eb7d88bc', 'source_sha256': '29ad602af336186642f3078c7550d2b3f04fbc45c79d442900a968873282659b', 'byte_count': 18418}
B1_V3_RECEIPT = 'artifacts/architecture/phase_a_published_evidence_restoration_v3.json'
B1_V3_RECEIPT_SHA256 = '99bc32331353735fef512e45c788ba8a1dd8887cee75f94bb40ccf9d9b51d1d0'
B1_A2_PREDECESSOR = {'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v359.json', 'generation': 359, 'canonical_sha256': '58042674ae09c4e2a92b48bdc99d4a08dc0a83c8e87702522496db026415501e', 'rewritten': False}
B1_METADATA = {
    B1_RECEIPT: {'git_blob_sha1': '6b528062ead8baadf3565c6a0490816fb524b3a6', 'source_sha256': '993d67dce0c23e4438b774a15bf252bbb8cf5d38fc4f308877de12a5af337323', 'byte_count': 3538},
    B1_FIXTURE: B1_BEFORE,
}
B1_V2_RECEIPT = 'artifacts/architecture/phase_a_b1_test_source_successor_v2.json'
B1_V2_RECEIPT_SHA256 = 'fdeeba1d16ae12359fd6f373231c10573e27be4063802509dccd5135c91604dd'
B1_V2_FIXTURE = 'tests/fixtures/architecture/phase_a_b1_test_source_v2/tests--test_core_01d_exact_pr_trigger_disposition_b1.py.before.txt'
B1_V2_AFTER = {'git_blob_sha1': 'a25b573a982c26c893714fce2c6342abd3c653b3', 'source_sha256': '1d0d861f7653748989bf8a1e1af2f81f5c7b14ea6bc9f66c4dd61c7eb54d831a', 'byte_count': 18441}
B1_V2_A2_PREDECESSOR = {'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v361.json', 'generation': 361, 'canonical_sha256': '5e6da09db4a8a883e3da75ae0c4451f2ba853d5615c09db6a9984917a02efb63', 'rewritten': False}
B1_V2_METADATA = {
    B1_V2_RECEIPT: {'git_blob_sha1': 'e055453425f5238978a94059901d5a3630b520c3', 'source_sha256': 'c74c60c661f4e91d832db76b27bad78c8b7df5b2d81398a1656dbd2ce7cfdb7c', 'byte_count': 1767},
    B1_V2_FIXTURE: B1_AFTER,
}
A2_TEXT_SOURCE = 'scripts/audit_core_01d_ci_offline_transport_boundary.py'
A2_TEXT_RECEIPT = 'artifacts/architecture/phase_a_a2_historical_tests_text_source_forward_v1.json'
A2_TEXT_RECEIPT_SHA256 = 'b3d0660fe8cde79e836cb129afd50abe7a259ab5a88e377c0f67c85aa84fea14'
A2_TEXT_V360 = {'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v360.json', 'generation': 360, 'canonical_sha256': '484f05fc839699c26a03cf12493bbc4bb06068ce1fa6c4de18df195d34053173', 'rewritten': False}
A2_TEXT_METADATA = {
    A2_TEXT_RECEIPT: {'git_blob_sha1': '5eb93cdf52f1a83b3bf50f10a18e767c0494eabf', 'source_sha256': '785997e568787c1dab8f5bbf157b18947f92e85653b598d9950706bb5e1f0f77', 'byte_count': 3207},
    'tests/fixtures/architecture/phase_a_historical_tests_projection_v1/a2-auditor-before.py.txt': {'git_blob_sha1': '1ee7a0660be131ba7deff01e4cce45fbfd663073', 'source_sha256': '61056b7e5d233bcfe259716985dd8626d2be38bd00f0015329725b0da6a080c5', 'byte_count': 178778},
    'tests/fixtures/architecture/phase_a_historical_tests_projection_v1/sitecustomize-before.py.txt': {'git_blob_sha1': 'b5d4a19c5fb5596158d6cab6bd63dc7dfc98d7c4', 'source_sha256': '1c3ba0d4d8d799279f18214a4797aa40f8e1fd07160705bc8ba749fce224b315', 'byte_count': 2515},
}


def _a2_text_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(A2_TEXT_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != A2_TEXT_RECEIPT_SHA256
            or value.get('canonical_sha256') != A2_TEXT_RECEIPT_SHA256
            or value.get('schema_version') != 1
            or value.get('policy_id') != 'ATHENA_PHASE_A_A2_HISTORICAL_TESTS_TEXT_SOURCE_FORWARD_V1'
            or value.get('a2_predecessor') != A2_TEXT_V360
            or set(value.get('source_forward', {})) != {A2_TEXT_SOURCE, 'sitecustomize.py'}
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'current_workflow_authority_changed', 'provider_or_delivery_authority_changed'))):
        raise ValueError('A2 historical Tests source-forward receipt drift')
    return value


def _a2_text_predecessor_source(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in {A2_TEXT_SOURCE, 'sitecustomize.py'}:
        return raw
    raw = _root_performance_predecessor_source(path, raw, _reader=reader)
    value = _a2_text_receipt(_reader=reader)
    row = value['source_forward'].get(path)
    if row is None:
        return raw
    before = reader(row['fixture'])
    # The public predecessor helper above already bound raw to the fresh current
    # source. Reuse that one local projected value, never a cross-call verdict.
    current = raw
    if safe.identity(before) != row['before'] or safe.identity(current) != row['after']:
        raise ValueError('A2 historical Tests source identity drift: ' + path)
    expected = before
    for patch in row['patches']:
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if expected.count(old) != 1:
            raise ValueError('A2 historical Tests source patch seam drift: ' + path)
        expected = expected.replace(old, new)
    if expected != current:
        raise ValueError('A2 historical Tests source exceeds exact successor: ' + path)
    return before


def _authenticate_a2_text_successor(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    value = _a2_text_receipt(_reader=reader)
    inventory_raw = reader(A2_TEXT_V360['path'])
    inventory = json.loads(inventory_raw)
    if (safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != A2_TEXT_V360['canonical_sha256']
            or inventory.get('generation') != 360
            or inventory.get('canonical_sha256') != A2_TEXT_V360['canonical_sha256']
            or inventory.get('predecessor_inventory') != B1_A2_PREDECESSOR):
        raise ValueError('A2 V360 predecessor is not the authenticated V359 chain point')
    historical_rows = {row['path']: row['lf_source_sha256']
                       for row in inventory.get('source_identities', [])}
    for path in value['source_forward']:
        row = value['source_forward'][path]
        if historical_rows.get(path) != row['before']['source_sha256']:
            raise ValueError('A2 V360 source does not match the exact successor predecessor: ' + path)
        if _a2_text_predecessor_source(path, reader(path), _reader=reader) != reader(row['fixture']):
            raise ValueError('A2 historical source projection mismatch: ' + path)
    for path, expected in A2_TEXT_METADATA.items():
        if safe.identity(reader(path)) != expected:
            raise ValueError('A2 historical source-forward metadata drift: ' + path)
    return value


def _b1_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(B1_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != B1_RECEIPT_SHA256
            or value.get('canonical_sha256') != B1_RECEIPT_SHA256
            or value.get('schema_version') != 1
            or value.get('policy_id') != 'ATHENA_PHASE_A_B1_TEST_SOURCE_SUCCESSOR_V1'
            or value.get('source_path') != B1_SOURCE
            or value.get('predecessor_fixture') != B1_FIXTURE
            or value.get('source_before') != B1_BEFORE
            or value.get('source_after') != B1_AFTER
            or value.get('historical_predecessor') != {
                'path': B1_V3_RECEIPT,
                'canonical_sha256': B1_V3_RECEIPT_SHA256,
                'source_forward_after': B1_BEFORE,
            }
            or value.get('a2_predecessor') != B1_A2_PREDECESSOR
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'current_source_authority_changed', 'workflow_changed'))):
        raise ValueError('B1 historical source successor receipt drift')
    return value


def _b1_v1_predecessor(raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    value = _b1_receipt(_reader=reader)
    before = reader(B1_FIXTURE)
    if safe.identity(before) != B1_BEFORE or safe.identity(raw) != B1_AFTER:
        raise ValueError('B1 V1 source identity drift')
    prior_raw = reader(B1_V3_RECEIPT)
    prior = json.loads(prior_raw)
    if (safe.canonical(prior) != prior_raw
            or safe.canonical_digest(prior) != B1_V3_RECEIPT_SHA256
            or prior.get('canonical_sha256') != B1_V3_RECEIPT_SHA256
            or prior.get('source_forward', {}).get(B1_SOURCE, {}).get('after') != B1_BEFORE):
        raise ValueError('B1 predecessor is not the immutable restoration V3 source')
    recipe = value['exact_patch']
    old, new = recipe['before'].encode('utf-8'), recipe['after'].encode('utf-8')
    if before.count(old) != 1 or before.replace(old, new) != raw:
        raise ValueError('B1 historical source exceeds the exact reviewed patch')
    return before


def _b1_v2_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(B1_V2_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != B1_V2_RECEIPT_SHA256
            or value.get('canonical_sha256') != B1_V2_RECEIPT_SHA256
            or value.get('schema_version') != 1
            or value.get('policy_id') != 'ATHENA_PHASE_A_B1_TEST_SOURCE_SUCCESSOR_V2'
            or value.get('source_path') != B1_SOURCE
            or value.get('predecessor_fixture') != B1_V2_FIXTURE
            or value.get('source_before') != B1_AFTER
            or value.get('source_after') != B1_V2_AFTER
            or value.get('historical_predecessor') != {
                'path': B1_RECEIPT,
                'canonical_sha256': B1_RECEIPT_SHA256,
                'source_forward_after': B1_AFTER,
            }
            or value.get('a2_predecessor') != B1_V2_A2_PREDECESSOR
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'current_source_authority_changed', 'workflow_changed'))):
        raise ValueError('B1 V2 source successor receipt drift')
    inventory_raw = reader(B1_V2_A2_PREDECESSOR['path'])
    inventory = json.loads(inventory_raw)
    rows = [row for row in inventory.get('source_identities', []) if row.get('path') == B1_SOURCE]
    if (safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != B1_V2_A2_PREDECESSOR['canonical_sha256']
            or inventory.get('generation') != B1_V2_A2_PREDECESSOR['generation']
            or inventory.get('canonical_sha256') != B1_V2_A2_PREDECESSOR['canonical_sha256']
            or inventory.get('predecessor_inventory') != A2_TEXT_V360
            or rows != [{'path': B1_SOURCE, 'lf_source_sha256': B1_AFTER['source_sha256']}]):
        raise ValueError('B1 V2 A2 predecessor does not authenticate the exact before-source')
    return value


def _b1_predecessor_source(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = _integrated_lineage_predecessor(path, raw, _reader=reader)
    if path != B1_SOURCE:
        return raw
    value = _b1_v2_receipt(_reader=reader)
    before_v1 = reader(B1_V2_FIXTURE)
    current = _integrated_lineage_predecessor(B1_SOURCE, reader(B1_SOURCE), _reader=reader)
    if safe.identity(before_v1) != B1_AFTER or safe.identity(current) != B1_V2_AFTER or raw != current:
        raise ValueError('B1 V2 current or historical source identity drift')
    recipe = value['exact_patches']
    expected = before_v1
    for patch in recipe:
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if expected.count(old) != 1:
            raise ValueError('B1 V2 source patch seam drift')
        expected = expected.replace(old, new)
    if expected != current:
        raise ValueError('B1 V2 source exceeds its exact reviewed patch')
    return _b1_v1_predecessor(before_v1, _reader=reader)


def read_blob(path):
    return safe.read_blob(path)


def _tests_shard_v2_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(TESTS_SHARD_V2_RECEIPT)
    value = json.loads(raw)
    source_forward = value.get('source_forward')
    if (safe.canonical(value) != raw
            or safe.canonical_digest(value) != TESTS_SHARD_V2_RECEIPT_SHA256
            or value.get('canonical_sha256') != TESTS_SHARD_V2_RECEIPT_SHA256
            or value.get('policy_id') != 'ATHENA_P4_TESTS_EIGHT_SHARD_BALANCE_MAINTENANCE_V2'
            or value.get('schema_version') != 1
            or type(source_forward) is not dict
            or set(source_forward) != TESTS_SHARD_V2_SOURCE_PATHS
            or value.get('authority_granted') is not False
            or value.get('historical_bytes_changed') is not False
            or value.get('required_contexts_changed') is not False
            or value.get('source_authority_changed') is not False):
        raise ValueError('Tests shard V2 source-forward receipt drift')
    return value


def _tests_shard_v2_predecessor_source(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in TESTS_SHARD_V2_SOURCE_PATHS:
        return raw
    value = _tests_shard_v2_receipt(_reader=reader)
    row = value['source_forward'][path]
    actual = reader(path)
    if raw != actual:
        raise ValueError('Tests shard V2 caller current source identity drift: ' + path)
    actual = _root_performance_project_checked_source(path, actual, _reader=reader)
    current = _parent_progress_predecessor_source(path, actual, _reader=reader)
    raw = current
    before = reader(row['fixture'])
    if (type(row) is not dict or set(row) != {'fixture', 'before', 'after'}
            or safe.identity(current) != row.get('after')
            or safe.identity(raw) != row.get('after') or raw != current
            or safe.identity(before) != row.get('before')):
        raise ValueError('Tests shard V2 current/predecessor source identity drift: ' + path)
    return before


def _receipt_for_reader(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != RECEIPT_SHA256
            or value.get('canonical_sha256') != RECEIPT_SHA256
            or value.get('authority_granted') is not False
            or value.get('workflow_changed') is not False
            or value.get('historical_bytes_changed') is not False
            or value.get('source_forward') != EDGES):
        raise ValueError('Pass-A Tests source successor receipt drift')
    return value

def receipt():
    return _receipt_for_reader()



def _predecessor_source_for_reader(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path == 'scripts/audit_phase_a_pc_upcoming_retention_successor.py':
        raw = _root_performance_predecessor_source(path, raw, _reader=reader)
    if path == safe.SOURCE:
        raw = _git_mode_regression_predecessor(path, raw, _reader=reader)
    raw = _blob_reuse_predecessor(path, raw, _reader=reader)
    raw = _integrated_lineage_predecessor(path, raw, _reader=reader)
    raw = _tests_shard_v2_predecessor_source(path, raw, _reader=reader)
    if path == B1_SOURCE:
        return _b1_predecessor_source(path, reader(path), _reader=reader)
    row = EDGES.get(path)
    if row is None:
        return _a2_text_predecessor_source(path, raw, _reader=reader)
    _receipt_for_reader(_reader=reader)
    if safe.identity(raw) != row['after']:
        raise ValueError('Pass-A Tests current source identity drift: ' + path)
    before = reader(row['fixture'])
    if safe.identity(before) != row['before']:
        raise ValueError('Pass-A Tests predecessor source identity drift: ' + path)
    expected = before
    if 'replacement_before' in row:
        old, new = row['replacement_before'].encode(), row['replacement_after'].encode()
        if expected.count(old) != 1:
            raise ValueError('Pass-A Tests source recipe is not unique: ' + path)
        expected = expected.replace(old, new)
    expected += row.get('append', '').encode()
    if expected != raw:
        raise ValueError('Pass-A Tests source exceeds exact recipe: ' + path)
    return before

def predecessor_source(path, raw):
    return _predecessor_source_for_reader(path, raw)



def _authenticate_core_for_reader(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    _git_mode_regression_receipt(_reader=reader)
    _blob_reuse_receipt(_reader=reader)
    _positive_fixture_receipt(_reader=reader)
    _integrated_lineage_receipt(_reader=reader)
    value = _receipt_for_reader(_reader=reader)
    for path in EDGES:
        _predecessor_source_for_reader(path, reader(path), _reader=reader)
    _b1_predecessor_source(B1_SOURCE, reader(B1_SOURCE), _reader=reader)
    _authenticate_a2_text_successor(_reader=reader)
    for path, expected in METADATA.items():
        if safe.identity(reader(path)) != expected:
            raise ValueError('Pass-A Tests successor metadata drift: ' + path)
    for path, expected in B1_METADATA.items():
        if safe.identity(reader(path)) != expected:
            raise ValueError('B1 source successor metadata drift: ' + path)
    _b1_v2_receipt(_reader=reader)
    for path, expected in B1_V2_METADATA.items():
        if safe.identity(reader(path)) != expected:
            raise ValueError('B1 V2 source successor metadata drift: ' + path)
    for path, expected in A2_TEXT_METADATA.items():
        if safe.identity(reader(path)) != expected:
            raise ValueError('A2 historical source-forward metadata drift: ' + path)
    if safe.identity(_blob_reuse_predecessor(TEST, reader(TEST), _reader=reader)) != TEST_IDENTITY:
        raise ValueError('Pass-A Tests successor regression source drift')
    _authenticate_root_performance(_reader=reader)
    return value

def authenticate_core():
    scope = _SourceReadScope(read_blob)
    value = _authenticate_core_for_reader(_reader=scope.read)
    scope.verify()
    return value



def historical_workflow_source():
    """Only this historical audit receives old YAML; caller cannot choose a tree."""
    authenticate_core()
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_tests_shard_balance_successor as shards
    latest = a2.authenticate_inventory()
    rows = [row for row in latest['source_identities'] if row['path'] == SOURCE]
    if (type(latest.get('generation')) is not int or latest['generation'] < 358
            or rows != [{'path': SOURCE, 'lf_source_sha256': EDGES[SOURCE]['after']['source_sha256']}]):
        raise ValueError('Pass-A current auditor is not authenticated by latest A2')
    b1_rows = [row for row in latest['source_identities'] if row['path'] == B1_SOURCE]
    if (latest['generation'] < 362
            or b1_rows != [{'path': B1_SOURCE, 'lf_source_sha256':
                _integrated_lineage_receipt()['source_forward'][B1_SOURCE]['after']['source_sha256']}]):
        raise ValueError('B1 current test source is not authenticated by the A2 successor')
    shards.authenticate()  # Proves actual HEAD tree plus one-path inverse.
    current = read_blob(shards.WORKFLOW)
    before = read_blob(shards.FIXTURE)
    if safe.identity(current) != shards.AFTER or safe.identity(before) != shards.BEFORE:
        raise ValueError('Pass-A Tests workflow or historical predecessor drift')
    # The frozen Pass-A row is an independent, immutable source anchor.
    frozen_raw = read_blob(receipt()['frozen_inventory']['path'])
    if safe.identity(frozen_raw) != FROZEN_IDENTITY:
        raise ValueError('Pass-A frozen inventory bytes drift')
    frozen = json.loads(frozen_raw)
    if (safe.canonical_digest(frozen) != receipt()['frozen_inventory']['canonical_sha256']
            or frozen.get('canonical_sha256') != receipt()['frozen_inventory']['canonical_sha256']):
        raise ValueError('Pass-A frozen inventory identity drift')
    expected = [row for row in frozen['sources'] if row['path'] == shards.WORKFLOW]
    if expected != [{'path': shards.WORKFLOW, 'git_blob_sha1': shards.BEFORE['git_blob_sha1'],
                     'normalized_source_sha256': shards.BEFORE['source_sha256']}]:
        raise ValueError('Pass-A frozen Tests workflow identity drift')
    return before


def install_context(context):
    receipt()
    a2_text_successor = _authenticate_a2_text_successor()
    context['HISTORICAL_PREDECESSORS'][SOURCE] = dict(
        context['HISTORICAL_PREDECESSORS'][SOURCE], after=EDGES[SOURCE]['after'])
    a2_text_after = {path: row['after'] for path, row in _a2_text_receipt()['source_forward'].items()}
    context['BOOTSTRAP_AFTER'] = dict(context['BOOTSTRAP_AFTER'], **{
        **{path: row['after'] for path, row in EDGES.items()}, TEST: TEST_IDENTITY,
        B1_SOURCE: B1_V2_AFTER, **a2_text_after})
    auditor_patches = a2_text_successor['source_forward'][A2_TEXT_SOURCE]['patches']
    context['BOOTSTRAP_AUDITOR_PATCHES'] = tuple(context['BOOTSTRAP_AUDITOR_PATCHES']) + tuple(
        (patch['before'], patch['after']) for patch in auditor_patches)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **METADATA)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **B1_METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **B1_METADATA)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **B1_V2_METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **B1_V2_METADATA)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **A2_TEXT_METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **A2_TEXT_METADATA)
    # The shard V2 adapter installed its exact current source-forward rows
    # before this historical Pass-A context. Reapply those rows after the
    # Pass-A V1 identities above so current bootstrap checks bind the current
    # adapter/test bytes; historical callers still receive only the pinned
    # V2 predecessor through _tests_shard_v2_predecessor_source().
    from scripts import audit_tests_shard_balance_successor as shards
    shard_successor = shards.authenticate()
    context['BOOTSTRAP_AFTER'] = dict(context['BOOTSTRAP_AFTER'], **{
        path: row['after'] for path, row in shard_successor['source_forward'].items()})
    context['ADDED_PYTHON_PATHS'] |= frozenset({__name__.replace('.', '/') + '.py', TEST})
    integrated = _integrated_lineage_receipt()
    metadata = {INTEGRATED_LINEAGE_RECEIPT: safe.identity(read_blob(INTEGRATED_LINEAGE_RECEIPT))}
    for path, row in integrated['source_forward'].items():
        metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path] = dict(context['HISTORICAL_PREDECESSORS'][path], after=row['after'])
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    positive_fixture = _positive_fixture_receipt()
    fixture_metadata = {POSITIVE_FIXTURE_RECEIPT: safe.identity(read_blob(POSITIVE_FIXTURE_RECEIPT))}
    for path, row in positive_fixture['source_forward'].items():
        fixture_metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path == 'pytest.ini':
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': row['after']}
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **fixture_metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **fixture_metadata)
    restored = _pytest_restoration_receipt()
    restored_metadata = {PYTEST_RESTORATION_RECEIPT: safe.identity(read_blob(PYTEST_RESTORATION_RECEIPT))}
    for path, row in restored['source_forward'].items():
        restored_metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
        elif path == CENSUS_TEST:
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': row['after']}
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **restored_metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **restored_metadata)
    reuse = _blob_reuse_receipt()
    metadata = {BLOB_REUSE_RECEIPT: safe.identity(read_blob(BLOB_REUSE_RECEIPT))}
    for path, row in reuse['source_forward'].items():
        metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    modes = _git_mode_regression_receipt()
    mode_metadata = {GIT_MODE_REGRESSION_RECEIPT: safe.identity(read_blob(GIT_MODE_REGRESSION_RECEIPT))}
    for path, row in modes['source_forward'].items():
        mode_metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **mode_metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **mode_metadata)
    install_parent_progress_context(context)
    install_root_performance_context(context)



INTEGRATED_LINEAGE_RECEIPT = 'artifacts/architecture/phase_a_integrated_lineage_source_successor_v1.json'
INTEGRATED_LINEAGE_SHA = '8d2f16ca61afd45d1ad43a03c5cfcad28563e3edbd04a65cfb478360d304d6d4'
INTEGRATED_LINEAGE_PATHS = frozenset({
    'scripts/audit_checkpoint_e_workflows.py',
    'tests/test_core_01d_exact_pr_trigger_disposition_b1.py',
    'tests/test_current_shadow_pc_upcoming_archive_retention.py',
})


def _integrated_lineage_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(INTEGRATED_LINEAGE_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != INTEGRATED_LINEAGE_SHA
            or value.get('canonical_sha256') != INTEGRATED_LINEAGE_SHA
            or value.get('policy_id') != 'ATHENA_PHASE_A_INTEGRATED_LINEAGE_SOURCE_SUCCESSOR_V1'
            or set(value.get('source_forward', {})) != INTEGRATED_LINEAGE_PATHS
            or any(value.get(k) is not False for k in ('authority_granted', 'historical_bytes_changed', 'workflow_changed'))):
        raise ValueError('integrated lineage receipt drift')
    predecessor = value['predecessor_inventory']
    inventory_raw = reader(predecessor['path'])
    inventory = json.loads(inventory_raw)
    if (predecessor['generation'] != 367 or predecessor['rewritten'] is not False
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != predecessor['canonical_sha256']
            or inventory.get('generation') != 367):
        raise ValueError('integrated lineage A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    for path, row in value['source_forward'].items():
        before = reader(row['fixture'])
        current = _pytest_restoration_predecessor(path, reader(path), _reader=reader)
        if (safe.identity(before) != row['before'] or safe.identity(current) != row['after']
                or sources.get(path) != row['before']['source_sha256']):
            raise ValueError('integrated lineage source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if expected.count(old) != 1:
                raise ValueError('integrated lineage patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('integrated lineage exceeds exact recipe: ' + path)
    return value


def _integrated_lineage_predecessor(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in INTEGRATED_LINEAGE_PATHS:
        return raw
    raw = _pytest_restoration_predecessor(path, raw, _reader=reader)
    row = _integrated_lineage_receipt(_reader=reader)['source_forward'][path]
    if safe.identity(raw) != row['after']:
        raise ValueError('integrated lineage caller source drift: ' + path)
    return reader(row['fixture'])


def authenticated_retention_artifact_paths():
    # No expensive audit cache authorizes bytes: replay exact metadata on every call.
    from scripts import audit_phase_a_pc_upcoming_retention_successor as retention
    retention.authenticate()
    retention.authenticate_bootstrap_sources()
    paths = set()
    for path, expected in retention.ADDED_METADATA.items():
        if path.startswith('artifacts/'):
            if safe.identity(read_blob(path)) != expected:
                raise ValueError('retention additive artifact identity drift: ' + path)
            paths.add(path)
    return paths

POSITIVE_FIXTURE_RECEIPT = 'artifacts/architecture/positive_audit_fixture_reuse_v1.json'
POSITIVE_FIXTURE_SHA = 'eb3de3dcea19e75b131c6757617525f50b2540d6da82cd92d19268c68d746501'
POSITIVE_FIXTURE_PATHS = frozenset({'pytest.ini', 'tests/test_core_01d_port02c_trigger_authority_b6.py',
                                    'tests/test_core_01d_checkpoint_e_completion_v9.py'})


def _positive_fixture_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(POSITIVE_FIXTURE_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != POSITIVE_FIXTURE_SHA
            or value.get('canonical_sha256') != POSITIVE_FIXTURE_SHA
            or value.get('policy_id') != 'ATHENA_POSITIVE_AUDIT_FIXTURE_REUSE_V1'
            or set(value.get('source_forward', {})) != POSITIVE_FIXTURE_PATHS
            or any(value.get(k) is not False for k in ('authority_granted', 'historical_bytes_changed', 'workflow_changed'))):
        raise ValueError('positive fixture reuse receipt drift')
    predecessor = value['predecessor_inventory']
    inventory_raw = reader(predecessor['path'])
    inventory = json.loads(inventory_raw)
    if (predecessor['generation'] != 368 or predecessor['rewritten'] is not False
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != predecessor['canonical_sha256']
            or inventory.get('generation') != 368):
        raise ValueError('positive fixture reuse A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    anchor = value['historical_configuration_anchor']
    frozen_raw = reader(anchor['path'])
    if (anchor['path'] != 'tests/fixtures/core_01d/exact-main-source-inventory.json'
            or safe.identity(frozen_raw) != anchor['identity']
            or json.loads(frozen_raw)['files']['pytest.ini'] != {
                'mode': '100644', 'git_blob_sha1': value['source_forward']['pytest.ini']['before']['git_blob_sha1']}):
        raise ValueError('positive fixture historical configuration anchor drift')
    for path, row in value['source_forward'].items():
        before = reader(row['fixture'])
        current = _pytest_restoration_predecessor(path, reader(path), _reader=reader)
        if (safe.identity(before) != row['before'] or safe.identity(current) != row['after']
                or (path != 'pytest.ini' and sources.get(path) != row['before']['source_sha256'])):
            raise ValueError('positive fixture reuse source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if expected.count(old) != 1:
                raise ValueError('positive fixture reuse patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('positive fixture reuse exceeds exact recipe: ' + path)
    return value


PYTEST_RESTORATION_RECEIPT = 'artifacts/architecture/pytest_configuration_restoration_v1.json'
PYTEST_RESTORATION_SHA = '8ff6d2fd25e7df474466e49fcea21d3b63844436ca80f1248833cbf67ef87b5a'
PYTEST_RESTORATION_PATHS = frozenset({'pytest.ini', 'tests/test_core_01d_checkpoint_e_completion_v2.py',
                                      'tests/test_p4_3a_workflow_capability_census.py',
                                      'scripts/audit_checkpoint_e_workflows.py'})


def _pytest_restoration_receipt(*, _reader=None):
    """Authenticate the forward restoration, retaining the published V1 bytes."""
    reader = read_blob if _reader is None else _reader
    raw = reader(PYTEST_RESTORATION_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != PYTEST_RESTORATION_SHA
            or value.get('canonical_sha256') != PYTEST_RESTORATION_SHA
            or value.get('policy_id') != 'ATHENA_PYTEST_CONFIGURATION_RESTORATION_V1'
            or set(value.get('source_forward', {})) != PYTEST_RESTORATION_PATHS
            or any(value.get(k) is not False for k in ('authority_granted', 'historical_bytes_changed', 'workflow_changed'))):
        raise ValueError('pytest restoration receipt drift')
    predecessor = value['predecessor_inventory']
    inventory_raw = reader(predecessor['path'])
    inventory = json.loads(inventory_raw)
    if (predecessor['generation'] != 369 or predecessor['rewritten'] is not False
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != predecessor['canonical_sha256']
            or inventory.get('generation') != 369):
        raise ValueError('pytest restoration A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    for path, row in value['source_forward'].items():
        before, current = reader(row['fixture']), reader(path)
        if (safe.identity(before) != row['before'] or safe.identity(current) != row['after']
                or (path != 'pytest.ini' and sources.get(path) != row['before']['source_sha256'])):
            raise ValueError('pytest restoration source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if expected.count(old) != 1:
                raise ValueError('pytest restoration patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('pytest restoration exceeds exact recipe: ' + path)
    return value


def _pytest_restoration_predecessor(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in PYTEST_RESTORATION_PATHS:
        return raw
    row = _pytest_restoration_receipt(_reader=reader)['source_forward'][path]
    if safe.identity(raw) != row['after']:
        raise ValueError('pytest restoration caller source identity drift: ' + path)
    return reader(row['fixture'])


CENSUS_TEST = 'tests/test_p4_3a_workflow_capability_census.py'


def historical_census_test_source():
    """Only Checkpoint-E's frozen lexical scan receives this exact predecessor."""
    value = _pytest_restoration_receipt()
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    latest = a2.authenticate_inventory()
    row = value['source_forward'][CENSUS_TEST]
    if (type(latest.get('generation')) is not int or latest['generation'] < 370
            or [r for r in latest['source_identities'] if r['path'] == CENSUS_TEST]
               != [{'path': CENSUS_TEST, 'lf_source_sha256': row['after']['source_sha256']}]):
        raise ValueError('census historical projection requires current A2 source identity')
    return read_blob(row['fixture'])


BLOB_REUSE_RECEIPT = 'artifacts/architecture/phase_a_blob_payload_reuse_v1.json'
BLOB_REUSE_SHA = '9c7ed921306d7c34104442b72817288ea16254100951528be955b1a6d6ee8be9'
BLOB_REUSE_PATHS = frozenset({'scripts/audit_phase_a_b4_test_source_successor.py',
                               'tests/test_phase_a_pass_a_tests_source_successor.py'})


def _blob_reuse_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(BLOB_REUSE_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != BLOB_REUSE_SHA
            or value.get('canonical_sha256') != BLOB_REUSE_SHA
            or value.get('policy_id') != 'ATHENA_PHASE_A_IMMUTABLE_BLOB_PAYLOAD_REUSE_V1'
            or set(value.get('source_forward', {})) != BLOB_REUSE_PATHS
            or any(value.get(k) is not False for k in ('authority_granted', 'historical_bytes_changed',
                                                     'workflow_changed', 'authority_verdict_cached'))):
        raise ValueError('blob reuse receipt drift')
    prior = value['predecessor_inventory']
    raw_prior = reader(prior['path'])
    inventory = json.loads(raw_prior)
    if (prior['generation'] != 370 or prior['rewritten'] is not False
            or safe.canonical(inventory) != raw_prior or inventory.get('generation') != 370
            or safe.canonical_digest(inventory) != prior['canonical_sha256']):
        raise ValueError('blob reuse A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    # This receipt is checked once per enclosing call, never cached between
    # calls. Each source and predecessor below still receives a fresh Git /
    # worktree check; only duplicate validation of the same receipt is avoided.
    try:
        mode_receipt = _git_mode_regression_receipt(_reader=reader)
    except ValueError as exc:
        # Keep the original error contract from the first loop iteration.
        path = next(iter(value['source_forward']))
        raise ValueError('blob reuse source identity drift: ' + path) from exc
    for path, row in value['source_forward'].items():
        before = reader(row['fixture'])
        try:
            current = _root_performance_current_predecessor(path, _reader=reader)
            if path in GIT_MODE_REGRESSION_PATHS:
                mode_row = mode_receipt['source_forward'][path]
                if safe.identity(current) != mode_row['after']:
                    raise ValueError('Git-mode regression caller source identity drift: ' + path)
                current = reader(mode_row['fixture'])
        except ValueError as exc:
            raise ValueError('blob reuse source identity drift: ' + path) from exc
        if (safe.identity(before) != row['before'] or safe.identity(current) != row['after']
                or sources.get(path) != row['before']['source_sha256']):
            raise ValueError('blob reuse source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if expected.count(old) != 1:
                raise ValueError('blob reuse patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('blob reuse exceeds exact recipe: ' + path)
    return value


def _blob_reuse_predecessor(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in BLOB_REUSE_PATHS:
        return raw
    raw = _git_mode_regression_predecessor(path, raw, _reader=reader)
    row = _blob_reuse_receipt(_reader=reader)['source_forward'][path]
    if safe.identity(raw) != row['after']:
        raise ValueError('blob reuse caller source identity drift: ' + path)
    return reader(row['fixture'])


GIT_MODE_REGRESSION_RECEIPT = 'artifacts/architecture/phase_a_git_mode_regression_source_successor_v1.json'
GIT_MODE_REGRESSION_SHA = '1ce4abf87e85c4d15e49dac8dac8bc879db2fe2273d66c4122f74a7311cdb7f3'
GIT_MODE_REGRESSION_PATHS = frozenset({'scripts/audit_phase_a_b4_test_source_successor.py',
                                       'tests/test_core_01d_sportybet_current_trigger_authority_b4.py',
                                       'tests/test_phase_a_pass_a_tests_source_successor.py'})


def _git_mode_regression_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(GIT_MODE_REGRESSION_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != GIT_MODE_REGRESSION_SHA
            or value.get('canonical_sha256') != GIT_MODE_REGRESSION_SHA
            or value.get('policy_id') != 'ATHENA_PHASE_A_GIT_MODE_REGRESSION_SOURCE_SUCCESSOR_V1'
            or set(value.get('source_forward', {})) != GIT_MODE_REGRESSION_PATHS
            or any(value.get(k) is not False for k in ('authority_granted', 'historical_bytes_changed',
                                                     'workflow_changed', 'production_reader_changed'))):
        raise ValueError('Git-mode regression receipt drift')
    prior = value['predecessor_inventory']
    prior_raw = reader(prior['path'])
    inventory = json.loads(prior_raw)
    if (prior['generation'] != 371 or prior['rewritten'] is not False
            or safe.canonical(inventory) != prior_raw or inventory.get('generation') != 371
            or safe.canonical_digest(inventory) != prior['canonical_sha256']):
        raise ValueError('Git-mode regression A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    for path, row in value['source_forward'].items():
        before = reader(row['fixture'])
        try:
            current = _root_performance_current_predecessor(path, _reader=reader)
        except ValueError as exc:
            raise ValueError('Git-mode regression source identity drift: ' + path) from exc
        if (safe.identity(before) != row['before'] or safe.identity(current) != row['after']
                or sources.get(path) != row['before']['source_sha256']):
            raise ValueError('Git-mode regression source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if expected.count(old) != 1:
                raise ValueError('Git-mode regression patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('Git-mode regression exceeds exact recipe: ' + path)
    return value


def _git_mode_regression_predecessor(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in GIT_MODE_REGRESSION_PATHS:
        return raw
    raw = _root_performance_predecessor_source(path, raw, _reader=reader)
    row = _git_mode_regression_receipt(_reader=reader)['source_forward'][path]
    if safe.identity(raw) != row['after']:
        raise ValueError('Git-mode regression caller source identity drift: ' + path)
    return reader(row['fixture'])


PARENT_PROGRESS_RECEIPT = 'artifacts/architecture/tests_parent_progress_successor_v1.json'
PARENT_PROGRESS_SHA256 = '38f4ac6ec65a27ca520149763bc66e2349ba7d5c7f67e94faaaed1ba12db2b27'
PARENT_PROGRESS_SNAPSHOT = 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_parent_progress_v1.json'
PARENT_PROGRESS_FIXTURE = 'tests/fixtures/architecture/revised_workflows/tests-pre-parent-progress-v1.yml'
PARENT_PROGRESS_PATHS = TESTS_SHARD_V2_SOURCE_PATHS
PARENT_PROGRESS_A2 = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v373.json',
    'generation': 373,
    'canonical_sha256': 'eb20af26800db496bd13c3887dc3f805da5e67b010b2c4f53fbd6101fa53f20d',
    'rewritten': False,
}
PARENT_PROGRESS_COMMAND_BEFORE = 'python -m pytest -q --durations=20 "${test_files[@]}"'
PARENT_PROGRESS_COMMAND_AFTER = 'python -m pytest -p scripts.audit_phase_a_pass_a_tests_source_successor -q --durations=20 "${test_files[@]}"'


def _parent_progress_receipt(*, _reader=None):
    """Pure tracked-byte source edge; no A2 bootstrap recursion or verdict cache."""
    reader = read_blob if _reader is None else _reader
    raw = reader(PARENT_PROGRESS_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw
            or safe.canonical_digest(value) != PARENT_PROGRESS_SHA256
            or value.get('canonical_sha256') != PARENT_PROGRESS_SHA256
            or value.get('policy_id') != 'ATHENA_TESTS_PARENT_ONLY_PROGRESS_V1'
            or type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or value.get('source_commit') != '3f8e353de3be986a5850153162306e9566f672ac'
            or value.get('active_inventory_predecessor') != PARENT_PROGRESS_A2
            or set(value.get('source_forward', {})) != PARENT_PROGRESS_PATHS
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed', 'required_contexts_changed',
                'test_assignments_changed', 'child_environment_changed'))
            or value.get('workflow_path') != '.github/workflows/tests.yml'
            or value.get('workflow_predecessor_fixture') != PARENT_PROGRESS_FIXTURE
            or value.get('command_before') != PARENT_PROGRESS_COMMAND_BEFORE
            or value.get('command_after') != PARENT_PROGRESS_COMMAND_AFTER):
        raise ValueError('parent progress receipt scope or identity drift')
    anchor_raw = reader(PARENT_PROGRESS_A2['path'])
    anchor = json.loads(anchor_raw)
    if (safe.canonical(anchor) != anchor_raw
            or safe.canonical_digest(anchor) != PARENT_PROGRESS_A2['canonical_sha256']
            or anchor.get('generation') != 373):
        raise ValueError('parent progress A2 predecessor drift')
    sources = {row['path']: row['lf_source_sha256'] for row in anchor['source_identities']}
    for path, row in value['source_forward'].items():
        fixture = ('tests/fixtures/architecture/tests_parent_progress_v1/'
                   + path.replace('/', '--') + '.before.txt')
        if (set(row) != {'before', 'after', 'fixture', 'patches'} or row['fixture'] != fixture
                or sources.get(path) != row['before']['source_sha256']):
            raise ValueError('parent progress source path/predecessor drift: ' + path)
        before = reader(fixture)
        current = _root_performance_current_predecessor(path, _reader=reader)
        if safe.identity(before) != row['before'] or safe.identity(current) != row['after']:
            raise ValueError('parent progress source identity drift: ' + path)
        expected = before
        for patch in row['patches']:
            old, new = patch['before'].encode(), patch['after'].encode()
            if not old or expected.count(old) != 1:
                raise ValueError('parent progress source patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if current != expected:
            raise ValueError('parent progress source exceeds exact recipe: ' + path)
    return value


def _parent_progress_predecessor_source(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in PARENT_PROGRESS_PATHS:
        return raw
    row = _parent_progress_receipt(_reader=reader)['source_forward'][path]
    if safe.identity(raw) != row['after']:
        raise ValueError('parent progress caller source identity drift: ' + path)
    return reader(row['fixture'])


def authenticate_parent_progress():
    """Prove the sole CLI change on actual HEAD and the immutable P4 extension."""
    value = _parent_progress_receipt()
    from scripts import audit_tests_shard_balance_successor as shards
    from scripts import audit_p4_workflow_evolution_ledger as p4
    before = read_blob(PARENT_PROGRESS_FIXTURE)
    current = read_blob(shards.WORKFLOW)
    # Both readers retain their ordinary source/mode/filter checks. The second
    # also preserves the existing auditor's injected-reader negative seam.
    if current != shards.read_blob(shards.WORKFLOW):
        raise ValueError('parent progress workflow reader drift')
    old, new = PARENT_PROGRESS_COMMAND_BEFORE.encode(), PARENT_PROGRESS_COMMAND_AFTER.encode()
    if (safe.identity(before) != shards.V2_AFTER or before.count(old) != 1
            or before.replace(old, new) != current or safe.identity(current) != shards.AFTER
            or value.get('workflow_before') != shards.V2_AFTER
            or value.get('workflow_after') != shards.AFTER
            or value.get('workflow_tree_before_sha1') != shards.V2_AFTER_TREE
            or value.get('workflow_tree_after_sha1') != shards.AFTER_TREE
            or value.get('b4_projected_before_sha1') != shards.V2_AFTER_B4_TREE
            or value.get('b4_projected_after_sha1') != shards.AFTER_B4_TREE):
        raise ValueError('parent progress workflow exceeds the exact CLI successor')
    entries = shards.tree_entries()
    if (shards.tree_identity(entries) != shards.AFTER_TREE
            or shards.tree_identity(entries, {'tests.yml': shards.V2_AFTER['git_blob_sha1']})
                != shards.V2_AFTER_TREE):
        raise ValueError('parent progress HEAD tree is not the one-path successor')
    prior_raw = read_blob(shards.V2_SNAPSHOT)
    prior = json.loads(prior_raw)
    snapshot_raw = read_blob(PARENT_PROGRESS_SNAPSHOT)
    snapshot = json.loads(snapshot_raw)
    if (safe.canonical(prior) != prior_raw or safe.canonical_digest(prior) != prior['canonical_sha256']
            or value.get('prior_snapshot') != {'path': shards.V2_SNAPSHOT,
                                              'canonical_sha256': prior['canonical_sha256']}
            or safe.canonical(snapshot) != snapshot_raw
            or safe.canonical_digest(snapshot) != snapshot.get('canonical_sha256')
            or snapshot.get('canonical_sha256') != value.get('workflow_evolution_ledger_sha256')
            or snapshot.get('transitions', [])[:-1] != prior.get('transitions')
            or snapshot.get('current_workflow_tree_sha1') != shards.AFTER_TREE):
        raise ValueError('parent progress P4 snapshot prefix drift')
    exempt = {'transitions', 'current_workflow_tree_sha1', 'canonical_sha256'}
    if {k: v for k, v in snapshot.items() if k not in exempt} != {
            k: v for k, v in prior.items() if k not in exempt}:
        raise ValueError('parent progress changed a historical P4 checkpoint')
    transition = snapshot['transitions'][-1]
    if ({k: v for k, v in transition.items() if k != 'evidence_body_sha256'}
            != value.get('reviewed_workflow_transition')
            or transition.get('transition_id') != 'P4_TESTS_PARENT_ONLY_PROGRESS_V1'
            or transition.get('maintenance_contract') != p4.TESTS_SHARD_BALANCE_CONTRACT
            or transition.get('evidence_body_sha256') != p4.receipt_evidence_body_sha256(value)):
        raise ValueError('parent progress P4 transition/evidence drift')
    projected = p4.apply_transitions(
        {shards.WORKFLOW: {k: shards.V2_AFTER[k] for k in shards.IDENTITY_KEYS}}, [transition],
        frozen_baseline_paths={shards.WORKFLOW}, baseline_families={shards.WORKFLOW: 'TESTS'},
        evidence_receipts={PARENT_PROGRESS_RECEIPT: value},
        historical_before_fixture_bytes={PARENT_PROGRESS_FIXTURE: before})
    if projected != {shards.WORKFLOW: {k: shards.AFTER[k] for k in shards.IDENTITY_KEYS}}:
        raise ValueError('parent progress P4 does not derive the exact workflow')
    return value


def install_parent_progress_context(context):
    value = _parent_progress_receipt()
    metadata = {path: safe.identity(read_blob(path)) for path in (
        PARENT_PROGRESS_RECEIPT, PARENT_PROGRESS_SNAPSHOT, PARENT_PROGRESS_FIXTURE)}
    for path, row in value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    context['ADDED_PYTHON_IDENTITIES'] = dict(context['ADDED_PYTHON_IDENTITIES'], **{
        path: row['after'] for path, row in value['source_forward'].items()})


class _ParentNodeProgress:
    """Explicit CLI-only plugin; importing the auditor has no reporting effects."""

    def __init__(self):
        import os
        import sys
        self.pid = os.getpid()
        self.stream = sys.__stdout__

    def _emit(self, event, nodeid, **fields):
        import os
        from datetime import datetime, timezone
        if os.getpid() != self.pid or self.stream is None:
            return
        value = {'event': event, 'nodeid': nodeid, 'pid': self.pid,
                 'utc': datetime.now(timezone.utc).isoformat(), **fields}
        self.stream.write('\nATHENA_PYTEST_PROGRESS ' + json.dumps(value, sort_keys=True) + '\n')
        self.stream.flush()

    def pytest_sessionstart(self, session):
        self._emit('session_start', '')

    def pytest_runtest_logstart(self, nodeid, location):
        self._emit('start', nodeid)

    def pytest_runtest_logreport(self, report):
        self._emit(report.when, report.nodeid, outcome=report.outcome,
                   seconds=round(report.duration, 6))

    def pytest_runtest_logfinish(self, nodeid, location):
        self._emit('finish', nodeid)


def pytest_configure(config):
    # pytest calls this only when this module is explicitly loaded with -p.
    # No PYTEST_ADDOPTS, environment marker, root conftest or child argv change.
    config.pluginmanager.register(_ParentNodeProgress(), 'athena-parent-node-progress')


ROOT_PERFORMANCE_RECEIPT = 'artifacts/architecture/root_auth_performance_source_successor_v1.json'
ROOT_PERFORMANCE_SHA256 = '3ffc8309ecc6e1a3a00b5a23c6641452aee6304aab93482e8b7755dd18fbbf16'
ROOT_PERFORMANCE_PATHS = frozenset({
    'scripts/audit_phase_a_b4_test_source_successor.py',
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    'scripts/audit_tests_shard_balance_successor.py',
    'scripts/audit_phase_a_pc_upcoming_retention_successor.py',
    'sitecustomize.py', TEST,
})
ROOT_PERFORMANCE_PREDECESSOR = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v374.json',
    'generation': 374,
    'canonical_sha256': '6dda8bea25376a87136a8e20d866ddc1a3c6589f21473243d45f7057108ea1e2',
    'rewritten': False,
}


def _root_performance_receipt(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    raw = reader(ROOT_PERFORMANCE_RECEIPT)
    import marshal
    value = marshal.loads(_root_performance_document(
        raw, ROOT_PERFORMANCE_SHA256, safe.canonical, safe.canonical_digest))
    # Scope/authority declarations are evaluated afresh, even when immutable
    # parsing/hash work was reused. No authorization verdict is memoized.
    if (value.get('policy_id') != 'ATHENA_ROOT_AUTH_PERFORMANCE_SOURCE_SUCCESSOR_V1'
            or value.get('predecessor_inventory') != ROOT_PERFORMANCE_PREDECESSOR
            or set(value.get('source_forward', {})) != ROOT_PERFORMANCE_PATHS
            or any(value.get(k) is not False for k in (
                'authority_granted', 'historical_bytes_changed', 'workflow_changed',
                'checks_skipped', 'authorization_verdict_cached', 'shared_runtime_changed'))):
        raise ValueError('root performance source receipt scope drift')
    return value


from functools import lru_cache as _root_performance_lru


@_root_performance_lru(maxsize=4)
def _root_performance_document(raw, expected_sha, canonical, canonical_digest):
    """Pure immutable-document transformation; all source guards remain fresh."""
    import marshal
    value = json.loads(raw)
    if (canonical(value) != raw or canonical_digest(value) != expected_sha
            or value.get('canonical_sha256') != expected_sha):
        raise ValueError('root performance source receipt drift')
    return marshal.dumps(value, 4)


def _root_performance_predecessor_source(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in ROOT_PERFORMANCE_PATHS:
        return raw
    current = reader(path)
    if raw != current:
        raise ValueError('root performance caller source drift: ' + path)
    return _root_performance_project_checked_source(path, current, _reader=reader)


def _root_performance_current_predecessor(path, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    current = reader(path)
    return _root_performance_project_checked_source(path, current, _reader=reader)


def _root_performance_project_checked_source(path, current, *, _reader=None):
    """Private pure recipe projection of bytes just obtained by a fresh reader.

    Every caller reads actual current bytes itself. This value is local to that
    invocation; independent public calls never inherit a prior source verdict.
    """
    reader = read_blob if _reader is None else _reader
    if path not in ROOT_PERFORMANCE_PATHS:
        return current
    row = _root_performance_receipt(_reader=reader)['source_forward'][path]
    before = reader(row['fixture'])
    if (safe.identity(current) != row['after'] or safe.identity(before) != row['before']):
        raise ValueError('root performance current/predecessor source drift: ' + path)
    expected = before
    for patch in row['patches']:
        old, new = patch['before'].encode(), patch['after'].encode()
        if not old or expected.count(old) != 1:
            raise ValueError('root performance source patch seam drift: ' + path)
        expected = expected.replace(old, new)
    if expected != current:
        raise ValueError('root performance source exceeds exact recipe: ' + path)
    return before


def _authenticate_root_performance(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    value = _root_performance_receipt(_reader=reader)
    raw = reader(ROOT_PERFORMANCE_PREDECESSOR['path'])
    inventory = json.loads(raw)
    if (safe.canonical(inventory) != raw
            or safe.canonical_digest(inventory) != ROOT_PERFORMANCE_PREDECESSOR['canonical_sha256']
            or inventory.get('generation') != 374):
        raise ValueError('root performance A2 predecessor drift')
    sources = {r['path']: r['lf_source_sha256'] for r in inventory['source_identities']}
    for path, row in value['source_forward'].items():
        if sources.get(path) != row['before']['source_sha256']:
            raise ValueError('root performance source is not the exact A2 predecessor: ' + path)
        _root_performance_current_predecessor(path, _reader=reader)
    anchor = value['pass_a_predecessor']
    before = reader(anchor['fixture'])
    if (anchor['path'] != __name__.replace('.', '/') + '.py'
            or safe.identity(before) != anchor['identity']
            or sources.get(anchor['path']) != anchor['identity']['source_sha256']):
        raise ValueError('root performance Pass-A predecessor anchor drift')
    return value


def install_root_performance_context(context):
    value = _authenticate_root_performance()
    metadata = {ROOT_PERFORMANCE_RECEIPT: safe.identity(read_blob(ROOT_PERFORMANCE_RECEIPT)),
                value['pass_a_predecessor']['fixture']: value['pass_a_predecessor']['identity']}
    for path, row in value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
    context['BOOTSTRAP_AUDITOR_PATCHES'] = tuple(context['BOOTSTRAP_AUDITOR_PATCHES']) + tuple(
        (p['before'], p['after']) for p in value['source_forward'][A2_TEXT_SOURCE]['patches'])
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    context['ADDED_PYTHON_IDENTITIES'] = dict(context['ADDED_PYTHON_IDENTITIES'], **{
        path: row['after'] for path, row in value['source_forward'].items()
        if path in context['ADDED_PYTHON_IDENTITIES']})


def root_performance_bootstrap_source(expected):
    row = _root_performance_receipt()['source_forward'][A2_TEXT_SOURCE]
    marker = ('        "' + row['after']['source_sha256'] + '",\n    ),').encode()
    retained = ('        "' + row['before']['source_sha256'] + '",\n').encode()
    if expected.count(marker) != 1:
        raise ValueError('root performance exact added auditor pin seam drift')
    result = expected.replace(marker, retained + marker)
    if result != read_blob('sitecustomize.py'):
        raise ValueError('root performance startup exceeds exact preserved-pin recipe')
    return result


class _SourceReadScope:
    """Local immutable inputs for exactly one independently fenced audit call."""

    def __init__(self, reader: Callable[[str], bytes]) -> None:
        from runtime import source_identity
        self.root = safe.ROOT
        self.head = safe._source_scope_head(self.root)
        self.reader = reader
        self.safe_reader = safe.read_blob
        self.runtime_reader = source_identity.read_tracked_head_blob
        self.sources: dict[str, bytes] = {}

    def read(self, path: str) -> bytes:
        if path not in self.sources:
            raw = self.reader(path)
            if type(raw) is not bytes:
                raise ValueError('scoped source input must be immutable bytes')
            self.sources[path] = raw
        return self.sources[path]

    def verify(self) -> None:
        from runtime import source_identity
        if (safe.ROOT != self.root or read_blob is not self.reader
                or safe.read_blob is not self.safe_reader
                or source_identity.read_tracked_head_blob is not self.runtime_reader):
            raise ValueError('scoped source root or reader changed during authentication')
        safe._verify_scoped_source_inputs(self.root, self.head, self.sources)
