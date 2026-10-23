"""One historical Pass-A Tests view, authenticated against current source first.

The pure core reads fixed tracked bytes/recipes only. A2 bootstrap may invoke it;
only the public historical source function invokes A2 and the Tests successor.
No frozen receipt, workflow, source authority or live discovery is changed.
"""
from __future__ import annotations
import hashlib
import json
from scripts import audit_phase_a_b4_test_source_successor as safe

ROOT = safe.ROOT
SOURCE = 'scripts/audit_core_01d_authority_reachability_review_a.py'
RECEIPT = 'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json'
RECEIPT_SHA256 = 'b0c7aa65d49413835137dff39b4c90b8d0aa530c8a2c0e36603451e612eb4f4c'
EDGES = {'scripts/audit_core_01d_authority_reachability_review_a.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt', 'before': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'after': {'git_blob_sha1': 'a7b7113de32e0d878c2d8d8b6a0823ee1bdb9fec', 'source_sha256': '9a6448f92f2e1373e928218ee73d9702fcd1a2e61f3dcb82bdec3f7ee134d754', 'byte_count': 47083}, 'replacement_before': 'def source_bytes(path):\n', 'replacement_after': "def source_bytes(path):\n if path == '.github/workflows/tests.yml':\n  from scripts import audit_phase_a_pass_a_tests_source_successor as forward\n  try:\n   return forward.historical_workflow_source()\n  except ValueError as exc:\n   require(False, 'exact Tests historical source-forward failed: '+str(exc))\n"}, 'scripts/audit_phase_a_b4_test_source_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt', 'before': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'after': {'git_blob_sha1': '7c8371a2f30379078f9428585443d28effa4145f', 'source_sha256': 'b7f9a61cd347e56eb8c66cfee83ff9292f45ed8ff2a61e2fd82cd011697333de', 'byte_count': 10702}, 'replacement_before': '    value = receipt()\n    if path == SOURCE:\n', 'replacement_after': '    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a\n    raw = pass_a.predecessor_source(path, raw)\n    value = receipt()\n    if path == SOURCE:\n'}, 'scripts/audit_phase_a_pc_upcoming_retention_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt', 'before': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}, 'after': {'git_blob_sha1': 'a7903e2d45abc8409f90987c0259c7a12ee7c193', 'source_sha256': '8a3d9ca477f991f2420af352aa125e30ed6f643b9355609c86853a54fd032836', 'byte_count': 59617}, 'append': '\n\n# Source-only Pass-A historical Tests view; current workflow stays unchanged.\nfrom scripts import audit_phase_a_pass_a_tests_source_successor as _pass_a_tests\n_pass_a_tests.install_context(globals())\n_authenticate_before_pass_a_tests = authenticate\n\n\ndef authenticate():\n    _pass_a_tests.authenticate_core()\n    return _authenticate_before_pass_a_tests()\n'}}
METADATA = {'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json': {'git_blob_sha1': '3b49db0bca4ef1b31dfe586415c94e13b98fc6cc', 'source_sha256': 'f112dad4cf1737e9bf281c4500daa0ff1fe4d47d8d9343a83c4c3540c780161c', 'byte_count': 6414}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}}
TEST = 'tests/test_phase_a_pass_a_tests_source_successor.py'
TEST_IDENTITY = {'git_blob_sha1': '53a0e5633a480cc238b15a585d17c90ca975d012', 'source_sha256': '2288b6f179bf16ff0fc80ce0347d5a2fe48cd8759ff08b98566802c51484f3de', 'byte_count': 6317}


def read_blob(path):
    return safe.read_blob(path)


def receipt():
    raw = read_blob(RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != RECEIPT_SHA256
            or value.get('canonical_sha256') != RECEIPT_SHA256
            or value.get('authority_granted') is not False
            or value.get('workflow_changed') is not False
            or value.get('historical_bytes_changed') is not False
            or value.get('source_forward') != EDGES):
        raise ValueError('Pass-A Tests source successor receipt drift')
    return value


def predecessor_source(path, raw):
    row = EDGES.get(path)
    if row is None:
        return raw
    receipt()
    if safe.identity(raw) != row['after']:
        raise ValueError('Pass-A Tests current source identity drift: ' + path)
    before = read_blob(row['fixture'])
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


def authenticate_core():
    value = receipt()
    for path in EDGES:
        predecessor_source(path, read_blob(path))
    for path, expected in METADATA.items():
        if safe.identity(read_blob(path)) != expected:
            raise ValueError('Pass-A Tests successor metadata drift: ' + path)
    if safe.identity(read_blob(TEST)) != TEST_IDENTITY:
        raise ValueError('Pass-A Tests successor regression source drift')
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
    shards.authenticate()  # Proves actual HEAD tree plus one-path inverse.
    current = read_blob(shards.WORKFLOW)
    before = read_blob(shards.FIXTURE)
    if safe.identity(current) != shards.AFTER or safe.identity(before) != shards.BEFORE:
        raise ValueError('Pass-A Tests workflow or historical predecessor drift')
    # The frozen Pass-A row is an independent, immutable source anchor.
    frozen = json.loads(read_blob(receipt()['frozen_inventory']['path']))
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
    context['HISTORICAL_PREDECESSORS'][SOURCE] = dict(
        context['HISTORICAL_PREDECESSORS'][SOURCE], after=EDGES[SOURCE]['after'])
    context['BOOTSTRAP_AFTER'] = dict(context['BOOTSTRAP_AFTER'], **{
        **{path: row['after'] for path, row in EDGES.items()}, TEST: TEST_IDENTITY})
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **METADATA)
    context['ADDED_PYTHON_PATHS'] |= frozenset({__name__.replace('.', '/') + '.py', TEST})
