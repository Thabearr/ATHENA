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
FROZEN_IDENTITY = {'git_blob_sha1': '051c5061ce9a620c714cac4538bd6da97b00abae', 'source_sha256': 'c8fea2ac437a6dd167d9e0c4e555706d796f6ba74a22e12431a57d4444ac20e2', 'byte_count': 319457}
SOURCE = 'scripts/audit_core_01d_authority_reachability_review_a.py'
RECEIPT = 'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json'
RECEIPT_SHA256 = 'b0c7aa65d49413835137dff39b4c90b8d0aa530c8a2c0e36603451e612eb4f4c'
EDGES = {'scripts/audit_core_01d_authority_reachability_review_a.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt', 'before': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'after': {'git_blob_sha1': 'a7b7113de32e0d878c2d8d8b6a0823ee1bdb9fec', 'source_sha256': '9a6448f92f2e1373e928218ee73d9702fcd1a2e61f3dcb82bdec3f7ee134d754', 'byte_count': 47083}, 'replacement_before': 'def source_bytes(path):\n', 'replacement_after': "def source_bytes(path):\n if path == '.github/workflows/tests.yml':\n  from scripts import audit_phase_a_pass_a_tests_source_successor as forward\n  try:\n   return forward.historical_workflow_source()\n  except ValueError as exc:\n   require(False, 'exact Tests historical source-forward failed: '+str(exc))\n"}, 'scripts/audit_phase_a_b4_test_source_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt', 'before': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'after': {'git_blob_sha1': '7c8371a2f30379078f9428585443d28effa4145f', 'source_sha256': 'b7f9a61cd347e56eb8c66cfee83ff9292f45ed8ff2a61e2fd82cd011697333de', 'byte_count': 10702}, 'replacement_before': '    value = receipt()\n    if path == SOURCE:\n', 'replacement_after': '    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a\n    raw = pass_a.predecessor_source(path, raw)\n    value = receipt()\n    if path == SOURCE:\n'}, 'scripts/audit_phase_a_pc_upcoming_retention_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt', 'before': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}, 'after': {'git_blob_sha1': 'a7903e2d45abc8409f90987c0259c7a12ee7c193', 'source_sha256': '8a3d9ca477f991f2420af352aa125e30ed6f643b9355609c86853a54fd032836', 'byte_count': 59617}, 'append': '\n\n# Source-only Pass-A historical Tests view; current workflow stays unchanged.\nfrom scripts import audit_phase_a_pass_a_tests_source_successor as _pass_a_tests\n_pass_a_tests.install_context(globals())\n_authenticate_before_pass_a_tests = authenticate\n\n\ndef authenticate():\n    _pass_a_tests.authenticate_core()\n    return _authenticate_before_pass_a_tests()\n'}}
METADATA = {'artifacts/architecture/phase_a_pass_a_tests_source_successor_v1.json': {'git_blob_sha1': '3b49db0bca4ef1b31dfe586415c94e13b98fc6cc', 'source_sha256': 'f112dad4cf1737e9bf281c4500daa0ff1fe4d47d8d9343a83c4c3540c780161c', 'byte_count': 6414}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_core_01d_authority_reachability_review_a.py.before.txt': {'git_blob_sha1': '1156f52e9dc78b1c8071a3c7d4e1cd5876b2b2cd', 'source_sha256': '320fa11109672ae1af23ef1ee5b62c5a007de195a8f3c5ad593d1e8f7437e748', 'byte_count': 46804}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_b4_test_source_successor.py.before.txt': {'git_blob_sha1': 'ada6901b3d9d3c0de13eb145b31e2abd9f863b19', 'source_sha256': 'e5cad5dce9d9bf4fdca1603712524e1cb1623907de9e19e12fdd9fb4abf02bec', 'byte_count': 10577}, 'tests/fixtures/architecture/phase_a_pass_a_tests_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}}
TEST = 'tests/test_phase_a_pass_a_tests_source_successor.py'
TEST_IDENTITY = {'git_blob_sha1': '53a0e5633a480cc238b15a585d17c90ca975d012', 'source_sha256': '2288b6f179bf16ff0fc80ce0347d5a2fe48cd8759ff08b98566802c51484f3de', 'byte_count': 6317}
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
A2_TEXT_SOURCE = 'scripts/audit_core_01d_ci_offline_transport_boundary.py'
A2_TEXT_RECEIPT = 'artifacts/architecture/phase_a_a2_historical_tests_text_source_forward_v1.json'
A2_TEXT_RECEIPT_SHA256 = 'b3d0660fe8cde79e836cb129afd50abe7a259ab5a88e377c0f67c85aa84fea14'
A2_TEXT_V360 = {'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v360.json', 'generation': 360, 'canonical_sha256': '484f05fc839699c26a03cf12493bbc4bb06068ce1fa6c4de18df195d34053173', 'rewritten': False}
A2_TEXT_METADATA = {
    A2_TEXT_RECEIPT: {'git_blob_sha1': '5eb93cdf52f1a83b3bf50f10a18e767c0494eabf', 'source_sha256': '785997e568787c1dab8f5bbf157b18947f92e85653b598d9950706bb5e1f0f77', 'byte_count': 3207},
    'tests/fixtures/architecture/phase_a_historical_tests_projection_v1/a2-auditor-before.py.txt': {'git_blob_sha1': '1ee7a0660be131ba7deff01e4cce45fbfd663073', 'source_sha256': '61056b7e5d233bcfe259716985dd8626d2be38bd00f0015329725b0da6a080c5', 'byte_count': 178778},
    'tests/fixtures/architecture/phase_a_historical_tests_projection_v1/sitecustomize-before.py.txt': {'git_blob_sha1': 'b5d4a19c5fb5596158d6cab6bd63dc7dfc98d7c4', 'source_sha256': '1c3ba0d4d8d799279f18214a4797aa40f8e1fd07160705bc8ba749fce224b315', 'byte_count': 2515},
}


def _a2_text_receipt():
    raw = read_blob(A2_TEXT_RECEIPT)
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


def _a2_text_predecessor_source(path, raw):
    value = _a2_text_receipt()
    row = value['source_forward'].get(path)
    if row is None:
        return raw
    before = read_blob(row['fixture'])
    current = read_blob(path)
    if safe.identity(before) != row['before'] or safe.identity(current) != row['after'] or raw != current:
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


def _authenticate_a2_text_successor():
    value = _a2_text_receipt()
    inventory_raw = read_blob(A2_TEXT_V360['path'])
    inventory = json.loads(inventory_raw)
    if (safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != A2_TEXT_V360['canonical_sha256']
            or inventory.get('generation') != 360
            or inventory.get('canonical_sha256') != A2_TEXT_V360['canonical_sha256']
            or inventory.get('predecessor_inventory') != B1_A2_PREDECESSOR):
        raise ValueError('A2 V360 predecessor is not the authenticated V359 chain point')
    for path in value['source_forward']:
        row = value['source_forward'][path]
        if _a2_text_predecessor_source(path, read_blob(path)) != read_blob(row['fixture']):
            raise ValueError('A2 historical source projection mismatch: ' + path)
    for path, expected in A2_TEXT_METADATA.items():
        if safe.identity(read_blob(path)) != expected:
            raise ValueError('A2 historical source-forward metadata drift: ' + path)
    return value


def _b1_receipt():
    raw = read_blob(B1_RECEIPT)
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


def _b1_predecessor_source(path, raw):
    if path != B1_SOURCE:
        return raw
    value = _b1_receipt()
    before = read_blob(B1_FIXTURE)
    current = read_blob(B1_SOURCE)
    if safe.identity(before) != B1_BEFORE or safe.identity(current) != B1_AFTER or raw != current:
        raise ValueError('B1 current or historical source identity drift')
    prior_raw = read_blob(B1_V3_RECEIPT)
    prior = json.loads(prior_raw)
    if (safe.canonical(prior) != prior_raw
            or safe.canonical_digest(prior) != B1_V3_RECEIPT_SHA256
            or prior.get('canonical_sha256') != B1_V3_RECEIPT_SHA256
            or prior.get('source_forward', {}).get(B1_SOURCE, {}).get('after') != B1_BEFORE):
        raise ValueError('B1 predecessor is not the immutable restoration V3 source')
    recipe = value['exact_patch']
    old, new = recipe['before'].encode('utf-8'), recipe['after'].encode('utf-8')
    if before.count(old) != 1 or before.replace(old, new) != current:
        raise ValueError('B1 historical source exceeds the exact reviewed patch')
    return before


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
        b1_source = _b1_predecessor_source(path, raw)
        if b1_source is not raw:
            return b1_source
        return _a2_text_predecessor_source(path, raw)
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
    _b1_predecessor_source(B1_SOURCE, read_blob(B1_SOURCE))
    _authenticate_a2_text_successor()
    for path, expected in METADATA.items():
        if safe.identity(read_blob(path)) != expected:
            raise ValueError('Pass-A Tests successor metadata drift: ' + path)
    for path, expected in B1_METADATA.items():
        if safe.identity(read_blob(path)) != expected:
            raise ValueError('B1 source successor metadata drift: ' + path)
    for path, expected in A2_TEXT_METADATA.items():
        if safe.identity(read_blob(path)) != expected:
            raise ValueError('A2 historical source-forward metadata drift: ' + path)
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
    b1_rows = [row for row in latest['source_identities'] if row['path'] == B1_SOURCE]
    if (latest['generation'] < 360
            or b1_rows != [{'path': B1_SOURCE, 'lf_source_sha256': B1_AFTER['source_sha256']}]):
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
    _authenticate_a2_text_successor()
    context['HISTORICAL_PREDECESSORS'][SOURCE] = dict(
        context['HISTORICAL_PREDECESSORS'][SOURCE], after=EDGES[SOURCE]['after'])
    a2_text_after = {path: row['after'] for path, row in _a2_text_receipt()['source_forward'].items()}
    context['BOOTSTRAP_AFTER'] = dict(context['BOOTSTRAP_AFTER'], **{
        **{path: row['after'] for path, row in EDGES.items()}, TEST: TEST_IDENTITY, **a2_text_after})
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **METADATA)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **B1_METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **B1_METADATA)
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **A2_TEXT_METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **A2_TEXT_METADATA)
    context['ADDED_PYTHON_PATHS'] |= frozenset({__name__.replace('.', '/') + '.py', TEST})
