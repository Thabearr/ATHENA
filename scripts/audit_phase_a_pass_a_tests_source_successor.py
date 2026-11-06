"""One historical Pass-A Tests view, authenticated against current source first.

The pure core reads fixed tracked bytes/recipes only. A2 bootstrap may invoke it;
only the public historical source function invokes A2 and the Tests successor.
No frozen receipt, workflow, source authority or live discovery is changed.
"""
from __future__ import annotations
import hashlib
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import json
import marshal
import os
import sys
import threading
from scripts import audit_phase_a_b4_test_source_successor as safe

ROOT = safe.ROOT


def _inventory_validation_contract():
    """Exact callable identity for the pure V376 JSON validator inputs."""
    global_bindings = (
        safe.canonical.__globals__.get("json"),
        safe.canonical_digest.__globals__.get("canonical"),
        safe.canonical_digest.__globals__.get("hashlib"),
    )
    functions = (
        safe.canonical,
        safe.canonical_digest,
        json.loads,
        json.dumps,
        json.JSONDecoder,
        json.JSONDecoder.__init__,
        json.JSONDecoder.decode,
        json.JSONDecoder.raw_decode,
        json.JSONEncoder,
        json.JSONEncoder.__init__,
        json.JSONEncoder.encode,
        json.JSONEncoder.iterencode,
        hashlib.sha256,
        marshal.dumps,
        marshal.loads,
    )
    identities = []
    for function in functions:
        code = getattr(function, "__code__", None)
        identities.append((
            id(function),
            code,
            repr(getattr(function, "__defaults__", None)),
            repr(getattr(function, "__kwdefaults__", None)),
        ))
    # Retain the actual module/function references in the key: a stable
    # function object can otherwise keep its identity while a relevant global
    # binding is replaced in place.
    return (tuple(identities), global_bindings, id(hashlib.sha256))


@lru_cache(maxsize=4)
def _canonical_inventory_snapshot(raw, expected_sha256, expected_generation,
                                  validator_contract, failure_message):
    """Cache only a pure parse/canonicalization transform keyed by exact bytes.

    Callers reread the bytes on every invocation. The cached payload is a
    marshal serialization, never a parsed mutable object or authentication
    verdict; every return is decoded into a new object graph.
    """
    if type(raw) is not bytes:
        raise ValueError(failure_message)
    inventory = json.loads(raw)
    if (type(inventory) is not dict
            or safe.canonical(inventory) != raw
            or safe.canonical_digest(inventory) != expected_sha256
            or inventory.get("canonical_sha256") != expected_sha256
            or inventory.get("generation") != expected_generation):
        raise ValueError(failure_message)
    return marshal.dumps(inventory, 4)


def _read_canonical_inventory_snapshot(reader, predecessor, failure_message):
    raw = reader(predecessor["path"])
    if type(raw) is not bytes:
        raise ValueError(failure_message)
    payload = _canonical_inventory_snapshot(
        raw,
        predecessor["canonical_sha256"],
        predecessor["generation"],
        _inventory_validation_contract(),
        failure_message,
    )
    return raw, marshal.loads(payload)
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
    """Read a tracked source blob, reusing bytes only inside one fenced audit.

    The enclosing checkpoint receipt scope binds HEAD, index, filtered
    worktree, Git configuration and A2 bytes at entry/exit.  A cache entry is
    only the immutable HEAD blob already checked by ``safe.read_blob``; it is
    never an identity or PASS verdict.  Each hit still checks the path's
    filesystem type/link posture and the relevant reader contract.
    """
    from runtime import source_identity
    relative = source_identity.validate_repository_relative_path(path)
    scope = _active_checkpoint_derivation_scope()
    if scope is None:
        scope = _active_source_derivation_scope()
    if scope is None:
        return safe.read_blob(relative)
    contract = _scoped_source_read_contract()
    key = "pass-a.source-blob:" + relative
    cached = scope.load_derivation(key, contract)
    if cached is not None:
        if type(cached) is not bytes:
            raise ValueError('Pass-A scoped source blob is not immutable bytes')
        _verify_scoped_source_path(relative)
        if contract != _scoped_source_read_contract():
            raise ValueError('Pass-A source reader changed during scoped reuse')
        return cached
    raw = scope.read(relative) if isinstance(scope, _SourceReadScope) else safe.read_blob(relative)
    if type(raw) is not bytes:
        raise ValueError('Pass-A source reader returned non-byte data')
    if contract != _scoped_source_read_contract():
        raise ValueError('Pass-A source reader changed during scoped read')
    scope.store_derivation(key, contract, raw)
    return raw


def _active_checkpoint_derivation_scope():
    engine = sys.modules.get('scripts.audit_core_01d_checkpoint_e_completion_v8')
    if engine is None:
        return None
    active = engine._ACTIVE_RECEIPT_SCOPES.get()
    preferred = active.get('checkpoint-master-audit')
    if (preferred is not None and getattr(preferred, 'enabled', False)
            and getattr(preferred, 'unit', None) == engine._execution_unit()
            and callable(getattr(preferred, 'load_derivation', None))
            and callable(getattr(preferred, 'store_derivation', None))):
        return preferred
    # ContextVar mappings preserve insertion order.  The first enabled scope
    # is the outermost bounded audit owner and survives short-lived child
    # scopes, whose derivation dictionaries are cleared on exit.
    unit = engine._execution_unit()
    for key, scope in tuple(active.items()):
        if key == 'pytest-session-a2':
            continue
        if (getattr(scope, 'enabled', False)
                and getattr(scope, 'unit', None) == unit
                and callable(getattr(scope, 'load_derivation', None))
                and callable(getattr(scope, 'store_derivation', None))):
            return scope
    return None


_ACTIVE_SOURCE_DERIVATION_SCOPE = ContextVar(
    'athena_pass_a_source_derivation_scope', default=None)


def _source_execution_unit():
    import asyncio
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return (os.getpid(), threading.get_ident(), None if task is None else id(task))


def _assert_source_scope_execution_unit(scope):
    """Reject direct use of a retained owner outside its creating unit."""
    if getattr(scope, 'execution_unit', None) != _source_execution_unit():
        raise ValueError(
            'Pass-A source derivation scope crossed a process/thread/task boundary')


def _active_source_derivation_scope():
    scope = _ACTIVE_SOURCE_DERIVATION_SCOPE.get()
    if scope is None:
        return None
    if scope.execution_unit != _source_execution_unit():
        raise ValueError('Pass-A source derivation scope crossed a process/thread/task boundary')
    if (not _trusted_source_reader_contract()
            or read_blob is not scope.reader
            or safe.read_blob is not scope.safe_reader
            or not _trusted_source_scope_instance(scope)):
        raise ValueError('Pass-A source derivation reader changed during its request')
    return scope


@contextmanager
def source_derivation_scope():
    """Share immutable source derivations over one direct Pass-A request.

    An enclosing checkpoint receipt scope remains the owner when present. The
    source-only owner is for call paths such as the V2 local-products test,
    whose deliberately wrapped Git reader prevents an unrelated receipt scope
    from being eligible. It caches bytes/pure canonical derivations only and
    revalidates every observed path, filtered worktree identity and HEAD before
    the enclosing public call returns. The context is never inherited across
    processes, threads or asyncio tasks, and all payloads are cleared in ``finally``.
    """
    checkpoint_scope = _active_checkpoint_derivation_scope()
    if (checkpoint_scope is not None
            and not getattr(checkpoint_scope, '_athena_pytest_session_a2', False)):
        yield checkpoint_scope
        return
    active = _active_source_derivation_scope()
    if active is not None:
        yield active
        return
    if not _trusted_source_reader_contract():
        raise ValueError('Pass-A source reader is not the reviewed public reader')
    scope = _SourceReadScope(_TRUSTED_PUBLIC_READ_BLOB,
                             underlying_reader=_TRUSTED_SAFE_READ_BLOB)
    token = _ACTIVE_SOURCE_DERIVATION_SCOPE.set(scope)
    try:
        yield scope
        scope.verify()
    finally:
        scope.sources.clear()
        scope.derivation_bytes.clear()
        _ACTIVE_SOURCE_DERIVATION_SCOPE.reset(token)


def _scoped_source_read_contract():
    """Bind the reader and path-validation code used by scoped byte reuse."""
    from runtime import source_identity
    digest = hashlib.sha256()
    for name, function in (
        ('pass_a.read_blob', read_blob),
        ('pass_a._active_checkpoint_derivation_scope', _active_checkpoint_derivation_scope),
        ('pass_a._active_source_derivation_scope', _active_source_derivation_scope),
        ('pass_a._source_execution_unit', _source_execution_unit),
        ('pass_a._assert_source_scope_execution_unit', _assert_source_scope_execution_unit),
        ('pass_a.source_derivation_scope', source_derivation_scope),
        ('pass_a._SourceReadScope.__init__', _SourceReadScope.__init__),
        ('pass_a._SourceReadScope.read', _SourceReadScope.read),
        ('pass_a._SourceReadScope.verify', _SourceReadScope.verify),
        ('pass_a._SourceReadScope.load_derivation', _SourceReadScope.load_derivation),
        ('pass_a._SourceReadScope.store_derivation', _SourceReadScope.store_derivation),
        ('pass_a._trusted_source_reader_contract', _trusted_source_reader_contract),
        ('pass_a._trusted_source_scope_instance', _trusted_source_scope_instance),
        ('pass_a._ci_assertion_v2_scope_owner', _ci_assertion_v2_scope_owner),
        ('pass_a._ci_assertion_v2_contract_digest', _ci_assertion_v2_contract_digest),
        ('pass_a._ci_assertion_v2_chain', _ci_assertion_v2_chain),
        ('pass_a._ci_assertion_v2_chain_uncached', _ci_assertion_v2_chain_uncached),
        ('pass_a._ci_assertion_v4_chain_uncached', _ci_assertion_v4_chain_uncached),
        ('pass_a._ci_assertion_predecessor_source', _ci_assertion_predecessor_source),
        ('pass_a._ci_assertion_predecessor_source_with_reader',
         _ci_assertion_predecessor_source_with_reader),
        ('pass_a._ci_assertion_v3_projected_read', _ci_assertion_v3_projected_read),
        ('pass_a._ci_assertion_v8_chain_details', _ci_assertion_v8_chain_details),
        ('pass_a._ci_assertion_v8_chain_uncached', _ci_assertion_v8_chain_uncached),
        ('pass_a._ci_assertion_v8_reconstitute_cached', _ci_assertion_v8_reconstitute_cached),
        ('pass_a._ci_assertion_v8_current_source_bytes', _ci_assertion_v8_current_source_bytes),
        ('pass_a._ci_assertion_v8_inventory_sources', _ci_assertion_v8_inventory_sources),
        ('pass_a._ci_assertion_v8_projected_reader', _ci_assertion_v8_projected_reader),
        ('pass_a._CIAssertionV8ProjectedReader.__init__',
         _CIAssertionV8ProjectedReader.__init__),
        ('pass_a._CIAssertionV8ProjectedReader.__call__',
         _CIAssertionV8ProjectedReader.__call__),
        ('pass_a._ci_assertion_v9_chain_details', _ci_assertion_v9_chain_details),
        ('pass_a._ci_assertion_v9_chain_uncached', _ci_assertion_v9_chain_uncached),
        ('pass_a._ci_assertion_v9_reconstitute_cached', _ci_assertion_v9_reconstitute_cached),
        ('pass_a._ci_assertion_v9_observe', _ci_assertion_v9_observe),
        ('pass_a._ci_assertion_v9_projected_read', _ci_assertion_v9_projected_read),
        ('pass_a._ci_assertion_v9_normalize_reader', _ci_assertion_v9_normalize_reader),
        ('pass_a._ci_assertion_v9_reader_graph', _ci_assertion_v9_reader_graph),
        ('pass_a._ci_assertion_v9_reader_phase', _ci_assertion_v9_reader_phase),
        ('pass_a._ci_assertion_v9_composed_v381', _ci_assertion_v9_composed_v381),
        ('pass_a._ci_assertion_v9_authenticated_input', _ci_assertion_v9_authenticated_input),
        ('pass_a._CIAssertionV9ProjectedReader.__init__',
         _CIAssertionV9ProjectedReader.__init__),
        ('pass_a._CIAssertionV9ProjectedReader.__call__',
         _CIAssertionV9ProjectedReader.__call__),
        ('pass_a._predecessor_source_for_reader', _predecessor_source_for_reader),
        ('pass_a._tests_shard_v2_predecessor_source', _tests_shard_v2_predecessor_source),
        ('pass_a._integrated_lineage_predecessor', _integrated_lineage_predecessor),
        ('pass_a._parent_progress_predecessor_source', _parent_progress_predecessor_source),
        ('safe.read_blob', safe.read_blob),
        ('safe._read_blob', safe._read_blob),
        ('safe._source_scope_head', safe._source_scope_head),
        ('safe._verify_scoped_source_inputs', safe._verify_scoped_source_inputs),
        ('safe.subprocess.run', safe.subprocess.run),
        ('safe.subprocess.check_output', safe.subprocess.check_output),
        ('safe.Path.lstat', safe.Path.lstat),
        ('safe.Path.resolve', safe.Path.resolve),
        ('safe.Path.is_dir', safe.Path.is_dir),
        ('safe.Path.is_file', safe.Path.is_file),
        ('safe.Path.is_symlink', safe.Path.is_symlink),
        ('safe.stat.S_ISREG', safe.stat.S_ISREG),
        ('safe.hashlib.sha1', safe.hashlib.sha1),
        ('safe.json.dumps', safe.json.dumps),
        ('source_identity.read_tracked_head_blob', source_identity.read_tracked_head_blob),
        ('source_identity.read_raw_file_bytes', source_identity.read_raw_file_bytes),
        ('source_identity._ensure_repository_root', source_identity._ensure_repository_root),
        ('source_identity._ascii_git_output', source_identity._ascii_git_output),
        ('source_identity._run_git', source_identity._run_git),
        ('source_identity._tracked_worktree_path', source_identity._tracked_worktree_path),
        ('source_identity.validate_repository_relative_path',
         source_identity.validate_repository_relative_path),
    ):
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(repr((id(function), id(getattr(function, '__code__', None)),
                            getattr(function, '__defaults__', None),
                            getattr(function, '__kwdefaults__', None))).encode('utf-8'))
    digest.update(repr((str(ROOT), str(safe.ROOT), id(safe), id(source_identity))).encode('utf-8'))
    return digest.hexdigest()


def _verify_scoped_source_path(path):
    """Repeat cheap filesystem-type checks on a scoped immutable-byte hit."""
    import stat
    from pathlib import Path
    from runtime import source_identity
    root = Path(safe.ROOT).resolve(strict=True)
    source_identity.validate_repository_relative_path(path)
    target = root.joinpath(*path.split('/'))
    current = root
    for part in path.split('/'):
        current = current / part
        metadata = current.lstat()
        is_last = current == target
        regular = stat.S_ISREG(metadata.st_mode) if is_last else stat.S_ISDIR(metadata.st_mode)
        if (not regular or stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, 'st_file_attributes', 0) & 0x400
                or (is_last and getattr(metadata, 'st_nlink', 1) != 1)):
            raise ValueError('Pass-A scoped source path is linked or nonregular: ' + path)


def _scoped_tracked_head_reader_contract():
    """Bind the exact Git reader and per-hit filesystem checks for HEAD bytes."""
    from runtime import source_identity
    functions = (
        ('source_identity.read_tracked_head_blob', source_identity.read_tracked_head_blob),
        ('source_identity._ensure_repository_root', source_identity._ensure_repository_root),
        ('source_identity._run_git', source_identity._run_git),
        ('source_identity._ascii_git_output', source_identity._ascii_git_output),
        ('source_identity._tracked_worktree_path', source_identity._tracked_worktree_path),
        ('source_identity.read_raw_file_bytes', source_identity.read_raw_file_bytes),
        ('source_identity.validate_repository_relative_path',
         source_identity.validate_repository_relative_path),
        ('source_identity.DevelopmentSourceIdentity', source_identity.DevelopmentSourceIdentity),
        ('hashlib.sha256', hashlib.sha256),
        ('marshal.dumps', marshal.dumps),
        ('marshal.loads', marshal.loads),
        ('PassA._active_checkpoint_derivation_scope', _active_checkpoint_derivation_scope),
        ('PassA._verify_scoped_source_path', _verify_scoped_source_path),
        ('PassA._tracked_head_mode', _tracked_head_mode),
        ('PassA.read_tracked_head_blob_scoped', read_tracked_head_blob_scoped),
    )
    entries = []
    for name, function in functions:
        code = getattr(function, '__code__', None)
        entries.append((name, id(function), id(code),
                        repr(getattr(function, '__defaults__', None)),
                        repr(getattr(function, '__kwdefaults__', None))))
    return hashlib.sha256(repr((str(ROOT), id(source_identity), tuple(entries))).encode()).hexdigest()


def _tracked_head_mode(root, relative, expected_blob):
    """Read and validate one HEAD tree entry when a scoped blob is first seen."""
    from runtime import source_identity
    entry = source_identity._run_git(root, 'ls-tree', '-z', 'HEAD', '--', relative)
    if type(entry) is not bytes or entry.count(b'\0') != 1 or not entry.endswith(b'\0'):
        raise ValueError('scoped tracked-source tree entry is malformed: ' + relative)
    metadata, logical = entry[:-1].split(b'\t', 1)
    fields = metadata.split()
    if (len(fields) != 3 or fields[1] != b'blob'
            or logical != relative.encode('utf-8')
            or fields[2].decode('ascii', 'strict') != expected_blob):
        raise ValueError('scoped tracked-source HEAD entry differs from its blob: ' + relative)
    return fields[0].decode('ascii', 'strict')


def read_tracked_head_blob_scoped(repository_root, relative_path, *,
                                  verify_worktree_filtered_identity=True,
                                  expected_mode=None):
    """Reuse immutable HEAD bytes only within the active fenced checkpoint scope.

    Scope hits still re-check every path component with lstat, reject links,
    reparse points, non-regular files and multiply-linked files, and compare
    the source-identity reader contract. HEAD/index/worktree/filter state is
    bounded by the owning receipt scope's entry/exit state digest. Outside that
    scope this delegates to the ordinary source-identity reader.
    """
    from pathlib import Path
    from runtime import source_identity
    relative = source_identity.validate_repository_relative_path(relative_path)
    if type(verify_worktree_filtered_identity) is not bool:
        raise source_identity.SourceIdentityError(
            'verify_worktree_filtered_identity must be exact bool')
    if expected_mode is not None and (type(expected_mode) is not str
                                      or expected_mode not in {'100644', '100755'}):
        raise source_identity.SourceIdentityError('expected_mode is malformed')
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, TypeError, ValueError):
        # Preserve the ordinary reader's typed failure and diagnostics.
        return source_identity.read_tracked_head_blob(
            repository_root, relative, verify_worktree_filtered_identity=verify_worktree_filtered_identity)
    if not root.is_dir() or root != Path(ROOT).resolve(strict=True):
        result = source_identity.read_tracked_head_blob(
            repository_root, relative, verify_worktree_filtered_identity=verify_worktree_filtered_identity)
        if expected_mode is not None:
            mode = _tracked_head_mode(root, relative, result[1].git_blob_sha1)
            if mode != expected_mode:
                raise ValueError('scoped tracked-source mode differs from its exact HEAD mode: ' + relative)
        return result

    scope = _active_checkpoint_derivation_scope()
    if scope is None or not getattr(scope, 'enabled', False):
        result = source_identity.read_tracked_head_blob(
            repository_root, relative, verify_worktree_filtered_identity=verify_worktree_filtered_identity)
        if expected_mode is not None:
            mode = _tracked_head_mode(root, relative, result[1].git_blob_sha1)
            if mode != expected_mode:
                raise ValueError('scoped tracked-source mode differs from its exact HEAD mode: ' + relative)
        return result

    contract = _scoped_tracked_head_reader_contract()
    if contract != _TRUSTED_SCOPED_TRACKED_HEAD_READER_CONTRACT:
        raise ValueError('scoped tracked-source reader contract changed')
    key = ('pass-a.tracked-head-blob:' + str(root) + ':' + relative + ':'
           + str(verify_worktree_filtered_identity) + ':' + str(expected_mode))
    cached = scope.load_derivation(key, contract)
    if cached is not None:
        try:
            raw, fields, mode = marshal.loads(cached)
        except (EOFError, ValueError, TypeError) as exc:
            raise ValueError('scoped tracked-source cache payload is malformed') from exc
        if (type(raw) is not bytes or type(fields) is not tuple or len(fields) != 5
                or (mode is not None and type(mode) is not str) or fields[0] != relative
                or any(value is not None and type(value) is not str for value in fields[1:])):
            raise ValueError('scoped tracked-source cache fields are malformed')
        if expected_mode is not None and mode != expected_mode:
            raise ValueError('scoped tracked-source cached mode differs from its contract: ' + relative)
        # The caller may deliberately decline the filtered-worktree identity
        # comparison for an immutable predecessor fixture, but path type/link
        # checks remain mandatory on every scoped hit.
        _verify_scoped_source_path(relative)
        if contract != _scoped_tracked_head_reader_contract():
            raise ValueError('scoped tracked-source reader changed during cache hit')
        identity = source_identity.DevelopmentSourceIdentity(*fields)
        return raw, identity

    result = source_identity.read_tracked_head_blob(
        repository_root, relative,
        verify_worktree_filtered_identity=verify_worktree_filtered_identity)
    raw, identity = result
    if type(raw) is not bytes or type(identity) is not source_identity.DevelopmentSourceIdentity:
        raise ValueError('scoped tracked-source reader returned an invalid result')
    mode = (_tracked_head_mode(root, relative, identity.git_blob_sha1)
            if expected_mode is not None else None)
    if expected_mode is not None and mode != expected_mode:
        raise ValueError('scoped tracked-source mode differs from its exact HEAD mode: ' + relative)
    if verify_worktree_filtered_identity:
        _verify_scoped_source_path(relative)
    if contract != _scoped_tracked_head_reader_contract():
        raise ValueError('scoped tracked-source reader changed during authenticated read')
    fields = (identity.repository_relative_path, identity.git_blob_sha1,
              identity.git_blob_payload_sha256,
              identity.filtered_worktree_git_blob_sha1, identity.raw_worktree_sha256)
    scope.store_derivation(key, contract, marshal.dumps((raw, fields, mode), 4))
    return result


_TRUSTED_SCOPED_TRACKED_HEAD_READER_CONTRACT = _scoped_tracked_head_reader_contract()


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
    actual = _ci_assertion_predecessor_source(path, actual, _reader=reader)
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
    current_reader = reader
    reader, raw = _ci_assertion_v3_projected_read(path, raw, reader)
    # These composite adapters consume the CI assertion edge themselves.
    # Route them once and do not feed their older endpoint back through the
    # same edge below.  The B1 adapter also owns its integrated-lineage step.
    if path == B1_SOURCE:
        return _b1_predecessor_source(path, reader(path), _reader=reader)
    if path == 'scripts/audit_phase_a_pc_upcoming_retention_successor.py':
        raw = _root_performance_predecessor_source(path, raw, _reader=reader)
    if path == safe.SOURCE:
        raw = _git_mode_regression_predecessor(path, raw, _reader=reader)
    raw = _blob_reuse_predecessor(path, raw, _reader=reader)
    raw = _integrated_lineage_predecessor(path, raw, _reader=reader)
    ci_assertion_consumed = path in INTEGRATED_LINEAGE_PATHS
    raw = _tests_shard_v2_predecessor_source(path, raw, _reader=reader)
    ci_assertion_consumed = ci_assertion_consumed or path in TESTS_SHARD_V2_SOURCE_PATHS
    if (path in CI_ASSERTION_V2_PATHS and path not in ROOT_PERFORMANCE_PATHS
            and not ci_assertion_consumed):
        # The reader may now expose V3 predecessor fixtures for the V2/V1
        # projection.  Pass its original current reader separately; the
        # predecessor verifier authenticates V3 against that reader before it
        # accepts this historical view.  A projected fixture map is never a
        # current-source authority by itself.
        projected_current = (type(reader) is _CIAssertionV3ProjectedReader
                             and reader.source_reader is current_reader)
        raw = _ci_assertion_predecessor_source(
            path, raw, _reader=reader,
            _current_reader=current_reader if projected_current else None)
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
    _authenticate_ci_assertion_successor(_reader=reader)
    return value

def authenticate_core():
    active = _active_source_derivation_scope()
    if active is not None:
        contract = _scoped_source_read_contract() + ':' + _ci_assertion_v2_contract_digest()
        cached = active.load_derivation('pass-a.authenticate-core', contract)
        if cached is not None:
            value = json.loads(cached)
            if type(value) is not dict or safe.canonical(value) != cached:
                raise ValueError('Pass-A cached authentication result is not canonical')
            active.verify()
            return value
        value = _authenticate_core_for_reader(_reader=active.read)
        active.verify()
        active.store_derivation(
            'pass-a.authenticate-core', contract, safe.canonical(value))
        return value
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
    v3_before = read_blob(shards.V3_FIXTURE)
    if (safe.identity(current) != shards.V3_AFTER
            or safe.identity(before) != shards.BEFORE
            or safe.identity(v3_before) != shards.V3_BEFORE):
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
    restored, restored_successor = _pytest_restoration_chain()
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
    successor_metadata = {
        PYTEST_RESTORATION_V2_RECEIPT: safe.identity(read_blob(PYTEST_RESTORATION_V2_RECEIPT))
    }
    for path, row in restored_successor['source_forward'].items():
        successor_metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **successor_metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **successor_metadata)
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
    install_ci_assertion_context(context)
    _install_ci_assertion_v3_context(context)



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
        current_reader = reader
        current = reader(path)
        current, historical_reader = _ci_assertion_predecessor_source_with_reader(
            path, current, _reader=current_reader)
        # The CI helper returns the authenticated V3 historical reader along
        # with its V2/V1 byte endpoint.  Restoration must consume that same
        # phase view: its cold validator still reads ``path`` independently,
        # and an ordinary current reader would expose V3 bytes there.
        current = _pytest_restoration_predecessor(
            path, current, _reader=historical_reader)
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
    # Preserve both the original current-source reader and the authenticated
    # historical reader produced by the CI projection.  This accepts either a
    # direct current-source caller or the already V3-projected reader used by
    # composite callers, while restoration validates through the same view.
    raw, historical_reader = _ci_assertion_predecessor_source_with_reader(
        path, raw, _reader=reader)
    raw = _pytest_restoration_predecessor(path, raw, _reader=historical_reader)
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
PYTEST_RESTORATION_V2_RECEIPT = 'tests/fixtures/architecture/pytest_configuration_restoration_v2/receipt.json'
PYTEST_RESTORATION_V2_SHA = '2dc3648d00c0bcd4daca56704846ad28116caa1baded8af955b2fdcfb21cce24'
PYTEST_RESTORATION_V2_PATHS = frozenset({'scripts/audit_checkpoint_e_workflows.py'})
PYTEST_RESTORATION_V2_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v376.json',
    'generation': 376,
    'canonical_sha256': '486e41d2e67bf844371683b5efcdd6cae7510e874889bb3416d2ff5713646102',
    'rewritten': False,
}


def _pytest_restoration_v1_receipt(*, _reader=None):
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


def _pytest_restoration_chain(*, _reader=None):
    """Validate the immutable V1 edge, then its exact append-only V2 successor."""
    reader = read_blob if _reader is None else _reader
    owner = _ci_assertion_v2_scope_owner(reader)
    if owner is None:
        return _pytest_restoration_chain_uncached(reader)
    contract = _ci_assertion_v2_contract_digest()
    cache_key = 'pass-a.pytest-restoration-v2-chain'
    cached = owner.load_derivation(cache_key, contract)
    if cached is not None:
        if contract != _ci_assertion_v2_contract_digest():
            raise ValueError('pytest restoration verifier changed during scoped reuse')
        prior, successor = json.loads(cached)
        return prior, successor
    result = _pytest_restoration_chain_uncached(reader)
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('pytest restoration verifier changed during scoped authentication')
    owner.store_derivation(cache_key, contract, safe.canonical([result[0], result[1]]))
    return result


def _pytest_restoration_chain_uncached(reader):
    """Perform the complete immutable restoration V1->V2 proof."""
    raw = reader(PYTEST_RESTORATION_V2_RECEIPT)
    value = json.loads(raw)
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != PYTEST_RESTORATION_V2_SHA
            or value.get('canonical_sha256') != PYTEST_RESTORATION_V2_SHA
            or value.get('schema_version') != 2
            or value.get('policy_id') != 'ATHENA_PYTEST_CONFIGURATION_RESTORATION_V2'
            or set(value.get('source_forward', {})) != PYTEST_RESTORATION_V2_PATHS
            or value.get('predecessor_inventory') != PYTEST_RESTORATION_V2_PREDECESSOR_INVENTORY
            or value.get('predecessor_receipt') != {
                'path': PYTEST_RESTORATION_RECEIPT,
                'canonical_sha256': PYTEST_RESTORATION_SHA,
                'rewritten': False,
            }
            or any(value.get(k) is not False for k in (
                'authority_granted', 'current_workflow_authority_changed',
                'historical_bytes_changed', 'provider_or_delivery_authority_changed',
                'test_selection_changed', 'workflow_changed'))):
        raise ValueError('pytest restoration V2 receipt drift')

    _predecessor_raw, predecessor = _read_canonical_inventory_snapshot(
        reader,
        PYTEST_RESTORATION_V2_PREDECESSOR_INVENTORY,
        'pytest restoration V2 A2 predecessor inventory drift',
    )

    # Authenticate the current Pass-A source chain, then use its exact V3
    # projection for both restoration generations. A direct current reader
    # must not be mistaken for the older V1 test-file image. Composite callers
    # may already supply this projection; in that case, reauthenticate the
    # original reader and require an identical fixture map before reusing it.
    if type(reader) is _CIAssertionV3ProjectedReader:
        current_reader = reader.source_reader
        _historical, _successor, current_v3 = _ci_assertion_v3_chain(
            _reader=current_reader)
        expected_reader = _ci_assertion_v3_projected_reader(
            current_reader, current_v3)
        if reader.fixtures != expected_reader.fixtures:
            raise ValueError(
                'pytest restoration V3 projected reader differs from authenticated current source')
        historical_reader = reader
    else:
        _historical, _successor, current_v3 = _ci_assertion_v3_chain(
            _reader=reader)
        historical_reader = _ci_assertion_v3_projected_reader(reader, current_v3)

    # Project the authenticated V3 image back to the exact V1 after-image
    # solely while revalidating immutable V1. The V2 workflow row introduces
    # one intermediate V2 image; all other V1 rows, including the checkpoint
    # V2 test source, are supplied by the authenticated V3 fixture map.
    rows = value['source_forward']
    def v1_reader(path):
        if path in rows:
            return historical_reader(rows[path]['fixture'])
        return historical_reader(path)

    prior = _pytest_restoration_v1_receipt(_reader=v1_reader)
    for path, row in rows.items():
        prior_row = prior['source_forward'].get(path)
        before, current = historical_reader(row['fixture']), historical_reader(path)
        if (prior_row is None or row.get('before') != prior_row['after']
                or safe.identity(before) != row['before']
                or safe.identity(current) != row['after']):
            raise ValueError('pytest restoration V2 source identity drift: ' + path)
        predecessor_sources = {item['path']: item['lf_source_sha256']
                               for item in predecessor.get('source_identities', ())}
        if predecessor_sources.get(path) != row['before']['source_sha256']:
            raise ValueError('pytest restoration V2 source is not the V376 predecessor: ' + path)
        expected = before
        for patch in row.get('patches', ()):
            old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
            if not old or expected.count(old) != 1:
                raise ValueError('pytest restoration V2 source patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('pytest restoration V2 source exceeds exact recipe: ' + path)
    return prior, value


def _pytest_restoration_receipt(*, _reader=None):
    """Return V1 only after authenticating the append-only current-source edge."""
    return _pytest_restoration_chain(_reader=_reader)[0]


def _pytest_restoration_predecessor(path, raw, *, _reader=None):
    reader = read_blob if _reader is None else _reader
    if path not in PYTEST_RESTORATION_PATHS:
        return raw
    prior, successor = _pytest_restoration_chain(_reader=reader)
    row = prior['source_forward'][path]
    observed = safe.identity(raw)
    successor_row = successor['source_forward'].get(path)
    current_identity = successor_row['after'] if successor_row is not None else row['after']
    # A caller can compose the Pass-A V2 projection before this restoration
    # projection. In that case it supplies exactly the authenticated V2
    # predecessor (which the chain has already proved equals the immutable V1
    # after-image), rather than the current V2 after-image. Accept only those
    # two exact identities; arbitrary or stale source bytes still fail closed.
    intermediate_identity = successor_row['before'] if successor_row is not None else None
    if observed != current_identity and observed != intermediate_identity:
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
            if path in CI_ASSERTION_V3_PATHS and path not in ROOT_PERFORMANCE_PATHS:
                # V3-only rows must reach the Git-mode receipt at its own phase.
                incoming = reader if type(reader) is _CIAssertionV3ProjectedReader else None
                live = incoming.source_reader if incoming is not None else reader
                projected, current = _ci_assertion_v3_projected_read(path, live(path), live)
                if incoming is not None and incoming.fixtures != projected.fixtures:
                    raise ValueError('Git-mode regression V3 projected reader drift: ' + path)
            else:
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
        current = _ci_assertion_predecessor_source(path, reader(path), _reader=reader)
        current = _root_performance_project_checked_source(path, current, _reader=reader)
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
    # The parent-progress receipt remains a V2 historical assertion. Authenticate
    # the later exact V3 upload-step edge first, then evaluate the old transition
    # against its V2 workflow projection.
    shards._authenticate_v3()
    before = read_blob(PARENT_PROGRESS_FIXTURE)
    current = read_blob(shards.WORKFLOW)
    v2_current = read_blob(shards.V3_FIXTURE)
    # Both readers retain their ordinary source/mode/filter checks. The second
    # also preserves the existing auditor's injected-reader negative seam.
    if current != shards.read_blob(shards.WORKFLOW):
        raise ValueError('parent progress workflow reader drift')
    old, new = PARENT_PROGRESS_COMMAND_BEFORE.encode(), PARENT_PROGRESS_COMMAND_AFTER.encode()
    if (safe.identity(before) != shards.V2_AFTER or before.count(old) != 1
            or before.replace(old, new) != v2_current
            or safe.identity(v2_current) != shards.AFTER
            or safe.identity(current) != shards.V3_AFTER
            or value.get('workflow_before') != shards.V2_AFTER
            or value.get('workflow_after') != shards.AFTER
            or value.get('workflow_tree_before_sha1') != shards.V2_AFTER_TREE
            or value.get('workflow_tree_after_sha1') != shards.AFTER_TREE
            or value.get('b4_projected_before_sha1') != shards.V2_AFTER_B4_TREE
            or value.get('b4_projected_after_sha1') != shards.AFTER_B4_TREE):
        raise ValueError('parent progress workflow exceeds the exact CLI successor')
    entries = shards.tree_entries()
    if (shards.tree_identity(entries) not in {shards.AFTER_TREE, shards.V3_AFTER_TREE}
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

    NODEID_KEY_ALGORITHM = "sha256-utf8-surrogatepass-v1"
    COLLECTION_KEY_CHUNK_SIZE = 256

    def __init__(self):
        import os
        import sys
        import json
        self.pid = os.getpid()
        self.stream = sys.__stdout__
        self.jsonl = None
        self.jsonl_bytes = 0
        self.jsonl_limit = 8 * 1024 * 1024
        # These are GitHub's non-secret event identifiers. Never serialize
        # the full environment: it may contain credentials or provider data.
        self.run_identity = {
            key.lower(): value[:256] for key in (
                "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB",
                "GITHUB_SHA", "GITHUB_REF",
            ) if (value := os.environ.get(key))
        }
        self.run_identity["worker"] = os.environ.get("PYTEST_XDIST_WORKER", "parent")
        self.source_identity = self._source_identities(os, json)
        self._open_jsonl(os)

    @staticmethod
    def _source_identities(os, json):
        import re
        import subprocess

        def git_text(*args):
            try:
                completed = subprocess.run(
                    ["git", "-C", str(ROOT), *args], check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=3, text=True,
                )
            except (OSError, subprocess.SubprocessError):
                return None
            return completed.stdout.strip()

        def sha(value):
            return value.lower() if isinstance(value, str) and re.fullmatch(
                r"[0-9a-fA-F]{40}", value) else None

        checkout = sha(git_text("rev-parse", "--verify", "HEAD^{commit}") or "")
        parents_text = git_text("show", "-s", "--format=%P", "HEAD") or ""
        parents = [value for value in parents_text.split() if sha(value)]
        github_sha = sha(os.environ.get("GITHUB_SHA", ""))
        pr_head = None
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path:
            try:
                with open(event_path, "rb") as event_file:
                    event_raw = event_file.read(1_048_577)
                if len(event_raw) <= 1_048_576:
                    event = json.loads(event_raw)
                    pr = event.get("pull_request") if isinstance(event, dict) else None
                    head = pr.get("head") if isinstance(pr, dict) else None
                    pr_head = sha(head.get("sha", "")) if isinstance(head, dict) else None
            except (OSError, ValueError, TypeError):
                pr_head = None
        return {
            "tested_checkout_sha": checkout,
            "tested_checkout_sha_verified": checkout is not None,
            "checkout_parent_shas": parents[:2],
            "github_sha": github_sha,
            "github_sha_matches_checkout": bool(github_sha and checkout == github_sha),
            "tested_merge_sha": (checkout if github_sha and checkout == github_sha
                                 and pr_head and len(parents) >= 2 else None),
            "pr_head_sha": pr_head,
            "pr_head_matches_merge_parent": bool(pr_head and len(parents) >= 2
                                                 and pr_head == parents[1]),
        }

    def _open_jsonl(self, os):
        import re
        import stat
        from pathlib import Path

        descriptor = None
        try:
            raw_temp = os.environ.get("RUNNER_TEMP")
            if not raw_temp:
                return
            runner_temp = Path(raw_temp).resolve(strict=True)
            if not runner_temp.is_dir():
                return
            repository = ROOT.resolve(strict=True)
            report_dir = runner_temp / "athena-pytest-progress"
            prospective = report_dir.resolve(strict=False)
            if prospective == repository or repository in prospective.parents:
                # Reject the destination before mkdir can create anything in
                # the authenticated checkout, including through RUNNER_TEMP or
                # a pre-existing report-directory symlink.
                return
            report_dir.mkdir(mode=0o700, exist_ok=True)
            directory_info = report_dir.lstat()
            if stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode):
                return
            report_dir = report_dir.resolve(strict=True)
            if report_dir == repository or repository in report_dir.parents:
                return

            def safe_component(value):
                return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:64] or "unknown"

            filename = "-".join((
                "progress", safe_component(self.run_identity.get("github_run_id", "local")),
                safe_component(self.run_identity.get("github_run_attempt", "1")),
                safe_component(self.run_identity.get("github_job", "pytest")),
                safe_component(self.run_identity.get("worker", "parent")),
                str(self.pid),
            )) + ".jsonl"
            target = report_dir / filename
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(target, flags, 0o600)
            file_info = os.fstat(descriptor)
            if not stat.S_ISREG(file_info.st_mode) or file_info.st_nlink != 1:
                os.close(descriptor)
                descriptor = None
                target.unlink(missing_ok=True)
                return
            self.jsonl = os.fdopen(descriptor, "w", encoding="utf-8", buffering=1)
            descriptor = None
        except Exception:
            # A diagnostic destination is optional. Never turn reporter setup
            # trouble into a pytest failure or redirect it into the checkout.
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self.jsonl = None

    @staticmethod
    def _safe_repo_path(value):
        from pathlib import Path
        try:
            path = Path(str(value))
            if not path.is_absolute():
                path = ROOT / path
            resolved = path.resolve(strict=False)
            return resolved.relative_to(ROOT.resolve()).as_posix()
        except (OSError, ValueError, RuntimeError):
            return Path(str(value)).name[:160]

    @staticmethod
    def _redact_text(value, limit):
        import re
        text = str(value)[:4096]
        header = re.search(
            r"(?i)\b(?:proxy-authorization|authorization|set-cookie|cookie)"
            r"(?:\\?[\"'])?[ \t]*[:=][ \t]*",
            text,
        )
        if header is not None:
            # Header values can contain multiple credentials or continuation
            # lines. Keep the diagnostic prefix and omit the complete tail.
            text = text[:header.end()] + "<redacted>"
        text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", text)
        sensitive_field = re.compile(
            r"(?i)(?P<prefix>(?:\\?[\"'])?"
            r"(?:authorization|token|password|secret|api[_-]?key|cookie)"
            r"(?:\\?[\"'])?\s*[:=]\s*)"
            r"(?P<value>\\?\"(?:\\.|[^\"\\])*\\?\"|"
            r"\\?'(?:\\.|[^'\\])*\\?'|[^\s,}\]]+)"
        )
        text = sensitive_field.sub(r"\g<prefix><redacted>", text)
        text = re.sub(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"AKIA[0-9A-Z]{16})\b", "<redacted-token>", text)
        text = re.sub(r"https?://[^\s]+", "<url>", text)
        structured_positions = [position for delimiter in "{[("
                                if (position := text.find(delimiter)) >= 0]
        if structured_positions:
            # Assertion payloads and pytest parameter reprs can contain
            # arbitrary fixture values unrelated to recognized credential
            # field names. Keep the diagnostic prefix and exception category,
            # but omit the opaque structured tail entirely.
            text = text[:min(structured_positions)].rstrip() + " <structured payload redacted>"
        return text[:limit]

    @staticmethod
    def _nodeid_key(nodeid):
        """Hash the complete original pytest ID before display redaction.

        The byte encoding is UTF-8 with ``surrogatepass`` so the key remains
        deterministic even if an unusual node ID contains lone surrogates.
        This key is diagnostic correlation only, never test/source authority.
        """
        if not isinstance(nodeid, str):
            nodeid = str(nodeid)
        return hashlib.sha256(nodeid.encode("utf-8", errors="surrogatepass")).hexdigest()

    @staticmethod
    def _failure_details(report):
        fields = {}
        try:
            longrepr = getattr(report, "longrepr", None)
            crash = getattr(longrepr, "reprcrash", None)
            message = getattr(crash, "message", "")
            message = message if isinstance(message, str) else ""
            category_candidate = message.partition(":")[0].strip()
            if (category_candidate.endswith(("Error", "Exception"))
                    and all(char.isalnum() or char in "._" for char in category_candidate)):
                fields["failure_category"] = category_candidate[:96]
            elif message.startswith(("assert ", "assertion failed")):
                fields["failure_category"] = "AssertionError"
            else:
                fields["failure_category"] = "pytest-failure"

            # Keep only a bounded explanation. Known credential forms and URLs
            # are redacted; traceback locals, fixture reprs and the environment
            # are never serialized.
            fields["failure_explanation"] = _ParentNodeProgress._redact_text(message, 512)
            if crash is not None:
                crash_path = getattr(crash, "path", None)
                crash_line = getattr(crash, "lineno", None)
                if crash_path is not None:
                    fields["crash_file"] = _ParentNodeProgress._safe_repo_path(crash_path)
                if type(crash_line) is int:
                    fields["crash_line"] = crash_line
                    fields["crash_line_basis"] = "pytest_reprcrash_lineno"

            traceback_repr = getattr(longrepr, "reprtraceback", None)
            entries = getattr(traceback_repr, "reprentries", ())
            frames = []
            for index, entry in enumerate(entries):
                if index >= 8:
                    break
                location = getattr(entry, "reprfileloc", None)
                if location is None:
                    continue
                frame = {}
                frame_path = getattr(location, "path", None)
                frame_line = getattr(location, "lineno", None)
                if frame_path is not None:
                    frame["file"] = _ParentNodeProgress._safe_repo_path(frame_path)
                if type(frame_line) is int:
                    frame["line"] = frame_line
                if frame:
                    frames.append(frame)
            if frames:
                fields["trace_frames"] = frames

            test_location = getattr(report, "location", None)
            if isinstance(test_location, tuple) and len(test_location) >= 2:
                fields["test_file"] = _ParentNodeProgress._safe_repo_path(test_location[0])
                fields["test_line_zero_based"] = (
                    test_location[1] if type(test_location[1]) is int else None)
                if len(test_location) >= 3 and isinstance(test_location[2], str):
                    fields["test_domain"] = test_location[2][:160]
        except Exception:
            # Preserve the report outcome even when pytest changes repr shapes.
            fields = {"failure_category": "pytest-failure"}
        return fields

    def _emit(self, event, nodeid, **fields):
        import os
        from datetime import datetime, timezone
        if os.getpid() != self.pid:
            return
        try:
            original_nodeid = nodeid if isinstance(nodeid, str) else str(nodeid)
            value = {**fields,
                     'schema': 'athena.pytest.progress.v2',
                     'event': event, 'nodeid_display': original_nodeid, 'pid': self.pid,
                     'utc': datetime.now(timezone.utc).isoformat(),
                     'run': self.run_identity, 'source': self.source_identity}
            if original_nodeid:
                value['nodeid_key_sha256'] = self._nodeid_key(original_nodeid)
                value['nodeid_key_algorithm'] = self.NODEID_KEY_ALGORITHM
            value['nodeid_display'] = self._redact_text(original_nodeid, 512)
            if isinstance(value.get('test_domain'), str):
                value['test_domain'] = self._redact_text(value['test_domain'], 160)
            line = json.dumps(value, sort_keys=True, separators=(",", ":"))
        except Exception:
            return
        if self.jsonl is not None:
            try:
                record = line + "\n"
                record_size = len(record.encode("utf-8"))
                if self.jsonl_bytes + record_size > self.jsonl_limit:
                    self.jsonl.close()
                    self.jsonl = None
                else:
                    self.jsonl.write(record)
                    self.jsonl_bytes += record_size
                    self.jsonl.flush()
            except Exception:
                try:
                    self.jsonl.close()
                except Exception:
                    pass
                self.jsonl = None
        if self.stream is not None:
            try:
                self.stream.write('\nATHENA_PYTEST_PROGRESS ' + line + '\n')
                self.stream.flush()
            except Exception:
                self.stream = None

    def pytest_sessionstart(self, session):
        self._emit('session_start', '')

    def pytest_collection_finish(self, session):
        """Emit a bounded exact-node inventory using the phase event key rule."""
        import os
        if os.getpid() != self.pid:
            return
        nodeids = [item.nodeid if isinstance(item.nodeid, str) else str(item.nodeid)
                   for item in session.items]
        keys = [self._nodeid_key(nodeid) for nodeid in nodeids]
        ordered_digest = hashlib.sha256("\n".join(keys).encode("ascii")).hexdigest()
        chunk_size = self.COLLECTION_KEY_CHUNK_SIZE
        chunk_count = max(1, (len(keys) + chunk_size - 1) // chunk_size)
        for chunk_index in range(chunk_count):
            start = chunk_index * chunk_size
            self._emit(
                'collection_inventory', '',
                node_key_algorithm=self.NODEID_KEY_ALGORITHM,
                collection_chunk_index=chunk_index,
                collection_chunk_count=chunk_count,
                collected_node_count=len(keys),
                collected_node_keys_sha256=ordered_digest,
                node_keys=keys[start:start + chunk_size],
            )

    def pytest_runtest_logstart(self, nodeid, location):
        self._emit('start', nodeid)

    def pytest_runtest_logreport(self, report):
        fields = {'outcome': report.outcome, 'seconds': round(report.duration, 6)}
        if report.failed:
            fields.update(self._failure_details(report))
        self._emit(report.when, report.nodeid, **fields)

    def pytest_runtest_logfinish(self, nodeid, location):
        self._emit('finish', nodeid)

    def pytest_sessionfinish(self, session, exitstatus):
        self._emit('session_finish', '', exit_status=int(exitstatus))
        if self.jsonl is not None:
            try:
                self.jsonl.flush()
                self.jsonl.close()
            except Exception:
                pass
            self.jsonl = None

    def pytest_unconfigure(self, config):
        if self.jsonl is not None:
            try:
                self.jsonl.flush()
                self.jsonl.close()
            except Exception:
                pass
            self.jsonl = None


def pytest_configure(config):
    # pytest calls this only when this module is explicitly loaded with -p.
    # No PYTEST_ADDOPTS, environment marker, root conftest or child argv change.
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_core_01d_checkpoint_e_completion_v8 as receipt_scope
    config._athena_a2_scope = receipt_scope._bounded_receipt_scope(
        'checkpoint-master-audit',
        (a2,),
        receipt_scope._auditor_contract_digest(a2),
    )
    config._athena_a2_scope.__enter__()
    config._athena_a2_scope._athena_pytest_session_a2 = True
    config._athena_source_derivation_scope = source_derivation_scope()
    config._athena_source_derivation_scope.__enter__()
    config.pluginmanager.register(_ParentNodeProgress(), 'athena-parent-node-progress')


def pytest_unconfigure(config):
    scope = getattr(config, "_athena_source_derivation_scope", None)
    if scope is not None:
        scope.__exit__(None, None, None)
    a2_scope = getattr(config, '_athena_a2_scope', None)
    if a2_scope is not None:
        a2_scope.__exit__(None, None, None)


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
    # An earlier Pass-A layer may already have projected the callable reader
    # to the V3 before-image. Reacquire its original reader, authenticate the
    # current edge, and then construct one fresh historical view. A projected
    # reader is provenance, never authority by itself.
    projected_input = (reader if type(reader) is _CIAssertionV3ProjectedReader else None)
    current_reader = (projected_input.source_reader if projected_input is not None
                      else reader)
    v2_value = None
    v3_value = None
    if path in CI_ASSERTION_V3_PATHS or path in CI_ASSERTION_V2_PATHS:
        _prior, v2_value, v3_value = _ci_assertion_v3_chain(_reader=current_reader)
        if path in CI_ASSERTION_V2_PATHS and path in CI_ASSERTION_V3_PATHS:
            v2_row = v2_value['source_forward'].get(path)
            v3_row = v3_value['source_forward'].get(path)
            if (type(v2_row) is dict and type(v3_row) is dict
                    and set(v2_row) == {'fixture', 'before', 'after', 'patches'}
                    and set(v3_row) == {'fixture', 'before', 'after', 'patches'}):
                _require_v2_v3_source_edge(path, v2_row, v3_row, current_reader)
    if path in CI_ASSERTION_V3_PATHS:
        live_current = current_reader(path)
        reader, projected_current = _ci_assertion_v3_projected_read(
            path, live_current, current_reader, _value=v3_value)
        if projected_input is not None and current != projected_current:
            raise ValueError('root performance V3 projected caller source drift: ' + path)
        current = projected_current
    else:
        live_current = current_reader(path)
        if current != live_current:
            raise ValueError('root performance caller current source drift: ' + path)
        reader = current_reader
        current = live_current
    if path in CI_ASSERTION_V2_PATHS:
        # The V3 chain above authenticated V2 against its exact V3
        # before-reader. Consume that result directly; the historical V2
        # compatibility accessor would re-enter current V3 validation using
        # projected bytes as though they were the current source.
        successor_row = v2_value['source_forward'][path]
        before_successor = reader(successor_row['fixture'])
        if (current != reader(path)
                or safe.identity(current) != successor_row['after']
                or safe.identity(before_successor) != successor_row['before']):
            raise ValueError('root performance V2 current/predecessor source drift: ' + path)
        current = before_successor
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
    root_value = _root_performance_receipt()
    auditor_row = root_value['source_forward'][A2_TEXT_SOURCE]
    bootstrap_row = root_value['source_forward']['sitecustomize.py']
    bootstrap_before = read_blob(bootstrap_row['fixture'])
    if expected != bootstrap_before or safe.identity(expected) != bootstrap_row['before']:
        raise ValueError('root performance bootstrap before-image drift')
    marker = ('        "' + auditor_row['after']['source_sha256'] + '\",\n    ),').encode()
    retained = ('        "' + auditor_row['before']['source_sha256'] + '\",\n').encode()
    if expected.count(marker) != 1:
        raise ValueError('root performance exact added auditor pin seam drift')
    result = expected.replace(marker, retained + marker)
    expected_root_after = bootstrap_before
    for patch in bootstrap_row['patches']:
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if not old or expected_root_after.count(old) != 1:
            raise ValueError('root performance bootstrap recipe seam drift')
        expected_root_after = expected_root_after.replace(old, new)
    if result != expected_root_after or safe.identity(result) != bootstrap_row['after']:
        raise ValueError('root performance bootstrap exceeds its exact source recipe')

    _historical, v2, v3 = _ci_assertion_v3_chain()
    v2_row = v2['source_forward'].get('sitecustomize.py')
    v3_row = v3['source_forward'].get('sitecustomize.py')
    if (type(v2_row) is not dict or type(v3_row) is not dict
            or set(v2_row) != {'fixture', 'before', 'after', 'patches'}
            or set(v3_row) != {'fixture', 'before', 'after', 'patches'}):
        raise ValueError('bootstrap V2/V3 source-forward rows are missing or malformed')
    v2_before = read_blob(v2_row['fixture'])
    if result != v2_before or safe.identity(v2_before) != v2_row['before']:
        raise ValueError('bootstrap V2 three-to-four pin predecessor drift')
    v2_after = v2_before
    for patch in v2_row['patches']:
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if not old or v2_after.count(old) != 1:
            raise ValueError('bootstrap V2 exact source recipe seam drift')
        v2_after = v2_after.replace(old, new)
    if safe.identity(v2_after) != v2_row['after']:
        raise ValueError('bootstrap V2 exact source recipe output drift')
    v3_before = read_blob(v3_row['fixture'])
    if v2_after != v3_before or safe.identity(v3_before) != v3_row['before']:
        raise ValueError('bootstrap V3 before-image does not equal the authenticated V2 after-image')
    v3_after = v3_before
    for patch in v3_row['patches']:
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if not old or v3_after.count(old) != 1:
            raise ValueError('bootstrap V3 exact source recipe seam drift')
        v3_after = v3_after.replace(old, new)
    current = read_blob('sitecustomize.py')
    if v3_after != current or safe.identity(current) != v3_row['after']:
        raise ValueError('bootstrap V3 source exceeds its exact fifth-pin recipe')
    return current


class _SourceReadScope:
    """Local immutable inputs for exactly one independently fenced audit call."""

    def __init__(self, reader: Callable[[str], bytes], *,
                 underlying_reader: Callable[[str], bytes] | None = None) -> None:
        from runtime import source_identity
        self.root = safe.ROOT
        self.head = safe._source_scope_head(self.root)
        self.reader = reader
        self.underlying_reader = reader if underlying_reader is None else underlying_reader
        self.safe_reader = safe.read_blob
        self.runtime_reader = source_identity.read_tracked_head_blob
        self.reader_contract_fn = _scoped_source_read_contract
        self.reader_contract_code = self.reader_contract_fn.__code__
        self.reader_contract_defaults = repr(self.reader_contract_fn.__defaults__)
        self.reader_contract_kwdefaults = repr(self.reader_contract_fn.__kwdefaults__)
        self.reader_contract = self.reader_contract_fn()
        self.sources: dict[str, bytes] = {}
        self.derivation_bytes: dict[str, tuple[str, bytes]] = {}
        self.metrics: dict[str, int] = {}
        self.execution_unit = _source_execution_unit()

    def _metric(self, name: str) -> None:
        self.metrics[name] = self.metrics.get(name, 0) + 1

    def read(self, path: str) -> bytes:
        _assert_source_scope_execution_unit(self)
        if path not in self.sources:
            raw = self.underlying_reader(path)
            if type(raw) is not bytes:
                raise ValueError('scoped source input must be immutable bytes')
            self.sources[path] = raw
            self._metric('source_read_misses')
        else:
            self._metric('source_read_hits')
        return self.sources[path]

    def verify(self) -> None:
        _assert_source_scope_execution_unit(self)
        from runtime import source_identity
        if (safe.ROOT != self.root or not _trusted_source_reader_contract()
                or read_blob is not self.reader
                or safe.read_blob is not self.safe_reader
                or source_identity.read_tracked_head_blob is not self.runtime_reader
                or _scoped_source_read_contract is not self.reader_contract_fn
                or self.reader_contract_fn.__code__ is not self.reader_contract_code
                or repr(self.reader_contract_fn.__defaults__) != self.reader_contract_defaults
                or repr(self.reader_contract_fn.__kwdefaults__) != self.reader_contract_kwdefaults
                or self.reader_contract_fn() != self.reader_contract):
            raise ValueError('scoped source root or reader changed during authentication')
        safe._verify_scoped_source_inputs(self.root, self.head, self.sources)

    def load_derivation(self, name: str, contract: str) -> bytes | None:
        _assert_source_scope_execution_unit(self)
        entry = self.derivation_bytes.get(name)
        if entry is None:
            self._metric('derivation_misses')
            return None
        prior_contract, payload = entry
        if prior_contract != contract or type(payload) is not bytes:
            raise ValueError('Pass-A scoped derivation contract changed')
        self._metric('derivation_hits')
        return payload

    def store_derivation(self, name: str, contract: str, payload: bytes) -> None:
        _assert_source_scope_execution_unit(self)
        if type(payload) is not bytes:
            raise ValueError('Pass-A scoped derivation payload is mutable')
        self.derivation_bytes[name] = (contract, payload)
        self._metric('derivation_stores')


# Source-only correction of exact-HEAD CI assertions. All predecessor receipts,
# source fixtures, workflow identities and the V375 inventory remain immutable.
CI_ASSERTION_RECEIPT = 'artifacts/architecture/phase_a_ci_assertion_source_successor_v1.json'
CI_ASSERTION_SHA256 = '58b85948bb1299ab11ef601b774c6cef0967ad44c072fb7b158ad4652a15b25c'
CI_ASSERTION_PATHS = frozenset({
    'tests/test_tests_shard_balance_successor.py',
    'tests/test_core_01d_ci_offline_transport_inventory_evolution.py',
    'tests/test_current_shadow_pc_upcoming_archive_retention.py',
})
CI_ASSERTION_PREDECESSOR = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v375.json',
    'generation': 375,
    'canonical_sha256': '248788edbc5e66d7d0a7ab0af9ed5c1fc3ce29a59e8b7d679f0e144bdb8b1b69',
    'rewritten': False,
}
CI_ASSERTION_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v1/'
CI_ASSERTION_V2_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v2/receipt.json'
CI_ASSERTION_V2_SHA256 = 'd83bcd7484071f47964b8ad3511bb4716cf0afea97ea56e2fb33d9ced6bbb34e'
CI_ASSERTION_V2_SOURCE = __name__.replace('.', '/') + '.py'
CI_ASSERTION_V2_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v2/'
CI_ASSERTION_V2_PATHS = frozenset({
    CI_ASSERTION_V2_SOURCE,
    'scripts/audit_checkpoint_e_workflows.py',
    'scripts/audit_core_01d_canonical_drive_transfer_completed_history.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v10.py',
    'scripts/audit_core_01d_checkpoint_e_completion.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v6.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v7.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v8.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v9.py',
    'scripts/audit_core_01d_exact_pr_trigger_disposition_b1.py',
    'scripts/audit_core_01d_frozen_artifact_replay_authority_b5.py',
    'scripts/audit_core_01d_historical_warehouse_transfer_authority_b2.py',
    'scripts/audit_core_01d_owner_one_shot_issue_comment_authority_b3.py',
    'scripts/audit_core_01d_port02c_trigger_authority_b6.py',
    'scripts/audit_core_01d_retained_workflow_status_v2.py',
    'scripts/audit_core_01d_retained_workflow_status_v4.py',
    'scripts/audit_core_01d_win_either_half_trigger_authority_b7.py',
    'scripts/audit_phase_a_pc_upcoming_retention_successor.py',
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v2.py',
    'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py',
    'scripts/audit_phase_a_b4_test_source_successor.py',
    'scripts/audit_data_01c_restore_portability.py',
    'scripts/audit_data_01c_app_store_complete.py',
    'sitecustomize.py',
    'tests/test_core_01d_ci_offline_transport_inventory_evolution.py',
})
CI_ASSERTION_V2_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v376.json',
    'generation': 376,
    'canonical_sha256': '486e41d2e67bf844371683b5efcdd6cae7510e874889bb3416d2ff5713646102',
    'rewritten': False,
}
CI_ASSERTION_V3_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v3/receipt.json'
CI_ASSERTION_V3_SHA256 = 'a36133a02143ca1ca3f5f7cb06ee25c41a51bf473f96b2bffc7acf497c1d9334'
CI_ASSERTION_V3_SOURCE = __name__.replace('.', '/') + '.py'
CI_ASSERTION_V3_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v3/'
CI_ASSERTION_V3_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V2_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V2_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V3_PRIOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v376.json',
    'generation': 376,
    'canonical_sha256': '486e41d2e67bf844371683b5efcdd6cae7510e874889bb3416d2ff5713646102',
    'rewritten': False,
}
CI_ASSERTION_V3_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v377.json',
    'generation': 377,
    'canonical_sha256': '467846f44798c99dd8582e6bcc54b23c8a390c9e833a3ae175722b0bf288c191',
    'rewritten': False,
}
CI_ASSERTION_V3_PATHS = frozenset({
    '.github/workflows/tests.yml',
    'scripts/audit_checkpoint_e_workflows.py',
    'scripts/audit_core_01d_checkpoint_e_completion_v2.py',
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    'scripts/audit_data_01c_restore_portability.py',
    CI_ASSERTION_V3_SOURCE,
    'scripts/audit_phase_a_pc_upcoming_retention_successor.py',
    'scripts/audit_tests_shard_balance_successor.py',
    'sitecustomize.py',
    'tests/test_core_01d_canonical_drive_transfer_completed_history.py',
    'tests/test_core_01d_checkpoint_e_completion_v2.py',
    'tests/test_core_01d_ci_offline_transport_inventory_evolution.py',
    'tests/test_core_01d_pass_a_v300_source_predecessors.py',
    'tests/test_core_01d_sportybet_current_trigger_authority_b4.py',
    'tests/test_current_shadow_pc_upcoming_archive_retention.py',
    'tests/test_phase_a_pass_a_tests_source_successor.py',
    'tests/test_tests_shard_balance_successor.py',
})

# The pytest-restoration reader correction is an append-only source edge. V3
# remains immutable and is authenticated through the exact V4 before-image.
CI_ASSERTION_V4_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v4/receipt.json'
CI_ASSERTION_V4_SHA256 = 'c7a38ef1e140adf442b937f18ee3f158bbfc80c286287de75e5a359ed986aa15'
CI_ASSERTION_V4_SOURCE = __name__.replace('.', '/') + '.py'
CI_ASSERTION_V4_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v4/'
CI_ASSERTION_V4_TEST_SOURCE = 'tests/test_core_01d_checkpoint_e_completion_v2.py'
CI_ASSERTION_V4_TEST_FIXTURE = CI_ASSERTION_V4_FIXTURES + CI_ASSERTION_V4_TEST_SOURCE.replace('/', '--') + '.before.txt'
CI_ASSERTION_V4_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V3_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V3_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V4_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v378.json',
    'generation': 378,
    'canonical_sha256': 'e246e834c03cfcee8cf753e333c1a1092041eeee36375803249dd53fb0706146',
    'rewritten': False,
}
CI_ASSERTION_V4_PATHS = frozenset({CI_ASSERTION_V4_SOURCE, CI_ASSERTION_V4_TEST_SOURCE})

# V5 is a request-local current-source edge from the authenticated V379
# inventory. It projects only those exact current bytes back to V379 before
# the immutable V4/V3 history is evaluated.
CI_ASSERTION_V5_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v5/receipt.json'
CI_ASSERTION_V5_SHA256 = 'c4627df2f55df85799e9f3b86a9fcf8f41029159ed01b9e0ac3d15b7c3300419'
CI_ASSERTION_V5_SOURCE = CI_ASSERTION_V4_SOURCE
CI_ASSERTION_V5_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v5/'
CI_ASSERTION_V5_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V4_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V4_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V5_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v379.json',
    'generation': 379,
    'canonical_sha256': '98415497a405ad44a491d6514c6ec5b16b415812e26432ed181afd51df956daa',
    'rewritten': False,
}
CI_ASSERTION_V5_PREDECESSOR_RAW_SHA256 = 'b6e0f7ddc10cbdf987c9c9169ef0c7b03afb1280aebbc843332bad6d46d80258'
CI_ASSERTION_V5_TEST_SOURCE = 'tests/test_core_01d_sportybet_current_trigger_authority_b4.py'
CI_ASSERTION_V5_ROOT_PIN_TEST = (
    'tests/test_core_01d_ci_offline_transport_inventory_evolution.py')
CI_ASSERTION_V5_RETENTION_SOURCE = (
    'scripts/audit_phase_a_pc_upcoming_retention_successor.py')
CI_ASSERTION_V5_PATHS = frozenset({
    CI_ASSERTION_V5_SOURCE,
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    CI_ASSERTION_V5_RETENTION_SOURCE,
    CI_ASSERTION_V5_TEST_SOURCE,
    CI_ASSERTION_V5_ROOT_PIN_TEST,
    'sitecustomize.py',
})

# V6 admits the corrected B4 test together with the exact Pass-A verifier and
# retention-consumer transition from authenticated V380.  The self-source is
# bound by a single receipt-digest token; V381 is deliberately outside this
# verifier's dependency graph.
CI_ASSERTION_V6_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v6/receipt.json'
CI_ASSERTION_V6_SHA256 = 'fa2cc26043444e447115dae74e0d172c4079d5a41a9d2d23d69a2d1fdc7f26b1'
CI_ASSERTION_V6_SOURCE = CI_ASSERTION_V5_SOURCE
CI_ASSERTION_V6_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v6/'
CI_ASSERTION_V6_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V5_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V5_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V6_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v380.json',
    'generation': 380,
    'canonical_sha256': '1181469878df98b06f9e5f82ffe63a2298ba3e13df651e365c7f39d0742586fb',
    'rewritten': False,
}
CI_ASSERTION_V6_PREDECESSOR_RAW_SHA256 = '8649e41d05b7e63caf3c766bf0a0f169abd7ce8b71465079fefd39642ee2810d'
CI_ASSERTION_V6_PATHS = frozenset({
    CI_ASSERTION_V6_SOURCE,
    CI_ASSERTION_V5_RETENTION_SOURCE,
    CI_ASSERTION_V5_TEST_SOURCE,
})

# V7 is a request-local append-only correction for the Pass-A scope tests and
# the two source-forward consumers that must understand the new phase.  It is
# anchored to the exact authenticated V6 receipt and V381 inventory; V382 is
# deliberately outside this proof so inventory succession remains a later
# independent step.
CI_ASSERTION_V7_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v7/receipt.json'
CI_ASSERTION_V7_SHA256 = 'f6cff55ecfe4b0200694993b9f969156a53fa7b5d39ef1553a5f02242c57b605'
CI_ASSERTION_V7_SOURCE = CI_ASSERTION_V6_SOURCE
CI_ASSERTION_V7_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v7/'
CI_ASSERTION_V7_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V6_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V6_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V7_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v381.json',
    'generation': 381,
    'canonical_sha256': 'd00ccbcbe9dd41f6ec283a47f4ee0d3acbc496659b8efabcb6f5d45221256fea',
    'rewritten': False,
}
CI_ASSERTION_V7_PREDECESSOR_RAW_SHA256 = '73e4d00c88e23b98d0967bea59de6eaa7bd0627c13d815da5bc0fb4ddd997aa2'
CI_ASSERTION_V7_TEST_SOURCE = 'tests/test_phase_a_pass_a_tests_source_successor.py'
CI_ASSERTION_V7_RETENTION_SOURCE = CI_ASSERTION_V5_RETENTION_SOURCE
CI_ASSERTION_V7_PATHS = frozenset({
    CI_ASSERTION_V7_SOURCE,
    CI_ASSERTION_V7_RETENTION_SOURCE,
    CI_ASSERTION_V7_TEST_SOURCE,
})

# V8 closes the exact V382-to-current source edge for the Pass-A verifier,
# retention consumer, and its focused scope regression.  V383 is deliberately
# outside this receipt and remains a later inventory successor.
CI_ASSERTION_V8_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v8/receipt.json'
CI_ASSERTION_V8_SHA256 = 'd268b5e83e4bcfeec7bf5ea1d587102aed9e68a46a2d1f35836591289d625c35'
CI_ASSERTION_V8_SOURCE = CI_ASSERTION_V7_SOURCE
CI_ASSERTION_V8_RETENTION_SOURCE = CI_ASSERTION_V7_RETENTION_SOURCE
CI_ASSERTION_V8_TEST_SOURCE = CI_ASSERTION_V7_TEST_SOURCE
CI_ASSERTION_V8_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v8/'
CI_ASSERTION_V8_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V7_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V7_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V8_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v382.json',
    'generation': 382,
    'canonical_sha256': '1a53e7d9abcd819cffe91c4d82fd4f85582f47cb7928b1b5103baf6315ffeabf',
    'rewritten': False,
}
CI_ASSERTION_V8_PREDECESSOR_RAW_SHA256 = 'd2c24e6394f9f44d2cd673a57e24a58054e80812fd3ad24018b6c1deacc90013'
CI_ASSERTION_V8_PATHS = frozenset({
    CI_ASSERTION_V8_SOURCE,
    CI_ASSERTION_V8_RETENTION_SOURCE,
    CI_ASSERTION_V8_TEST_SOURCE,
})
CI_ASSERTION_V8_DERIVATION_KEY = 'pass-a.ci-assertion-v8-chain-details-v1'

# V9 authenticates the exact V383 current image before projecting the three
# admitted source paths back to V8. V383 remains immutable and is V9's parent.
CI_ASSERTION_V9_RECEIPT = 'tests/fixtures/architecture/ci_assertion_source_successor_v9/receipt.json'
CI_ASSERTION_V9_SHA256 = 'f35b37ed6f6ca442048b4ddf81ec829c07ac898445d6cca041c30dee4ebcacb5'
CI_ASSERTION_V9_SOURCE = CI_ASSERTION_V8_SOURCE
CI_ASSERTION_V9_RETENTION_SOURCE = CI_ASSERTION_V8_RETENTION_SOURCE
CI_ASSERTION_V9_TEST_SOURCE = 'tests/test_tests_shard_balance_successor.py'
CI_ASSERTION_V9_FIXTURES = 'tests/fixtures/architecture/ci_assertion_source_successor_v9/'
CI_ASSERTION_V9_PREDECESSOR_RECEIPT = {
    'path': CI_ASSERTION_V8_RECEIPT,
    'canonical_sha256': CI_ASSERTION_V8_SHA256,
    'rewritten': False,
}
CI_ASSERTION_V9_PREDECESSOR_INVENTORY = {
    'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v383.json',
    'generation': 383,
    'canonical_sha256': '794bf2b830a8937b0fac6effeee871093add1a22d6accf101737720bac875362',
    'rewritten': False,
}
CI_ASSERTION_V9_PREDECESSOR_RAW_SHA256 = '9cc7caffc2eb6a93237ae180b2b0e0d3577a1927a54ab93e9ad9dc607536eaf9'
CI_ASSERTION_V9_PREDECESSOR_BLOB_SHA1 = 'b4b25836f64c6ded62f95328db3d40e90b4e3862'
CI_ASSERTION_V9_PREDECESSOR_BYTES = 1270972
CI_ASSERTION_V9_ORDERED_PATHS_SHA256 = 'ba9d087054be09be80fbb6e4b5416d36dcec8e9c642593dc59ad48cec2c91848'
CI_ASSERTION_V9_PATHS = frozenset({
    CI_ASSERTION_V9_SOURCE,
    CI_ASSERTION_V9_RETENTION_SOURCE,
    CI_ASSERTION_V9_TEST_SOURCE,
})
CI_ASSERTION_V9_DERIVATION_KEY = 'pass-a.ci-assertion-v9-chain-details-v1'


def _ci_assertion_v1_successor_receipt(*, _reader=None):
    """Authenticate the frozen V375 anchor and fixed, authority-neutral scope."""
    reader = read_blob if _reader is None else _reader
    try:
        raw = reader(CI_ASSERTION_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_PREDECESSOR['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion receipt or predecessor cannot be read') from exc
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != CI_ASSERTION_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V1'
            or type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or value.get('source_commit') != '4549de616ae3345a842ffb6d2d467fcb7f7f3f7a'
            or value.get('predecessor_inventory') != CI_ASSERTION_PREDECESSOR
            or type(value.get('source_forward')) is not dict
            or set(value['source_forward']) != CI_ASSERTION_PATHS
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed', 'workflow_changed',
                'test_file_assignment_changed', 'existing_tests_removed_or_skipped',
                'authority_verdict_cached'))
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != CI_ASSERTION_PREDECESSOR['canonical_sha256']
            or inventory.get('canonical_sha256') != CI_ASSERTION_PREDECESSOR['canonical_sha256']
            or type(inventory.get('generation')) is not int or inventory['generation'] != 375):
        raise ValueError('CI assertion receipt or V375 predecessor drift')
    sources = {row['path']: row['lf_source_sha256'] for row in inventory['source_identities']}
    for path, row in value['source_forward'].items():
        fixture = CI_ASSERTION_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or set(row) != {'fixture', 'before', 'after', 'patches'}
                or row['fixture'] != fixture
                or sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion source scope or predecessor drift: ' + path)
    anchor = value.get('pass_a_predecessor')
    anchor_path = __name__.replace('.', '/') + '.py'
    fixture = CI_ASSERTION_FIXTURES + anchor_path.replace('/', '--') + '.before.txt'
    if (type(anchor) is not dict or set(anchor) != {'path', 'fixture', 'identity', 'recipe'}
            or anchor['path'] != anchor_path or anchor['fixture'] != fixture
            or safe.identity(reader(fixture)) != anchor['identity']
            or sources.get(anchor_path) != anchor['identity'].get('source_sha256')):
        raise ValueError('CI assertion Pass-A predecessor anchor drift')
    recipe = anchor['recipe']
    token = '<CI_ASSERTION_' + 'DIGEST>'
    if (type(recipe) is not dict or set(recipe) != {'before', 'after'}
            or type(recipe['before']) is not str or type(recipe['after']) is not str
            or recipe['before'].encode() != reader(fixture)
            or recipe['after'].count(token) != 1
            or recipe['after'].replace(token, CI_ASSERTION_SHA256).encode() != reader(anchor_path)):
        raise ValueError('CI assertion Pass-A exact source recipe drift')
    return value


def _ci_assertion_v2_contract_digest():
    """Bind the exact local validator seams without dynamic import-graph state."""
    digest = hashlib.sha256()
    for name in (
        '_ci_assertion_v2_chain', '_ci_assertion_v2_chain_uncached',
        '_ci_assertion_v3_chain', '_ci_assertion_v3_chain_uncached',
        '_ci_assertion_v3_chain_details',
        '_ci_assertion_v4_chain_uncached', '_ci_assertion_v5_chain_uncached',
        '_ci_assertion_v6_chain_uncached', '_ci_assertion_v6_chain_details',
        '_ci_assertion_v6_projected_reader', '_ci_assertion_v6_projected_read',
        '_ci_assertion_v6_current_source_bytes',
        '_ci_assertion_v7_chain_uncached', '_ci_assertion_v7_chain_details',
        '_ci_assertion_v7_projected_reader', '_ci_assertion_v7_projected_read',
        '_ci_assertion_v7_current_source_bytes',
        '_ci_assertion_v8_chain_uncached', '_ci_assertion_v8_chain_details',
        '_ci_assertion_v8_reconstitute_cached', '_ci_assertion_v8_current_source_bytes',
        '_ci_assertion_v8_inventory_sources', '_ci_assertion_v8_projected_reader',
        '_ci_assertion_v9_chain_uncached', '_ci_assertion_v9_chain_details',
        '_ci_assertion_v9_reconstitute_cached', '_ci_assertion_v9_cache_payload',
        '_ci_assertion_v9_observe', '_ci_assertion_v9_current_source_bytes',
        '_ci_assertion_v9_inventory_sources', '_ci_assertion_v9_projected_reader',
        '_ci_assertion_v9_phase_values', '_ci_assertion_v9_projected_read',
        '_ci_assertion_v9_normalize_reader',
        '_ci_assertion_v9_reader_graph', '_ci_assertion_v9_reader_phase',
        '_ci_assertion_v9_composed_v381', '_ci_assertion_v9_authenticated_input',
        '_CIAssertionV8ProjectedReader.__init__',
        '_CIAssertionV8ProjectedReader.__call__',
        '_CIAssertionV9ProjectedReader.__init__',
        '_CIAssertionV9ProjectedReader.__call__',
        '_ci_assertion_v4_projected_reader',
        '_ci_assertion_v5_projected_read', '_ci_assertion_v5_projected_reader',
        '_record_ci_assertion_v3_scope_metric',
        '_ci_assertion_v3_projected_read', '_ci_assertion_v3_projected_reader',
        '_ci_assertion_v3_projected_read_with_value',
        '_CIAssertionV4ProjectedReader.__init__',
        '_CIAssertionV4ProjectedReader.__call__',
        '_CIAssertionV5ProjectedReader.__init__',
        '_CIAssertionV5ProjectedReader.__call__',
        '_CIAssertionV6ProjectedReader.__init__',
        '_CIAssertionV6ProjectedReader.__call__',
        '_CIAssertionV7ProjectedReader.__init__',
        '_CIAssertionV7ProjectedReader.__call__',
        '_ci_assertion_predecessor_source', '_ci_assertion_predecessor_source_with_reader',
        '_predecessor_source_for_reader',
        '_tests_shard_v2_predecessor_source', '_integrated_lineage_receipt',
        '_integrated_lineage_predecessor', '_parent_progress_receipt',
        '_parent_progress_predecessor_source',
        '_apply_exact_source_forward_row', '_require_v2_v3_source_edge',
        '_install_ci_assertion_v3_context',
        '_ci_assertion_v1_successor_receipt', '_read_canonical_inventory_snapshot',
        '_canonical_inventory_snapshot', '_inventory_validation_contract',
        '_ci_assertion_v2_scope_owner', '_active_checkpoint_derivation_scope',
        '_active_source_derivation_scope', '_source_execution_unit',
        'source_derivation_scope', '_SourceReadScope.__init__',
        '_scoped_source_read_contract', '_verify_scoped_source_path',
        '_pytest_restoration_chain', '_pytest_restoration_chain_uncached',
        '_pytest_restoration_v1_receipt', '_SourceReadScope.read',
        '_SourceReadScope.verify', '_SourceReadScope.load_derivation',
        '_SourceReadScope.store_derivation', 'read_blob',
    ):
        parts = name.split('.')
        value = globals()[parts[0]]
        for attribute in parts[1:]:
            value = getattr(value, attribute)
        code = getattr(value, '__code__', None)
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(repr((id(value), id(code), getattr(value, '__defaults__', None),
                            getattr(value, '__kwdefaults__', None))).encode('utf-8'))
        # Code objects are immutable and held by the function for this scope.
        # Their identity detects __code__ replacement without marshal serializing
        # CPython's adaptive/quickened execution state differently after hot calls.
    for name in (
        'CI_ASSERTION_RECEIPT', 'CI_ASSERTION_SHA256', 'CI_ASSERTION_PATHS',
        'CI_ASSERTION_PREDECESSOR', 'CI_ASSERTION_FIXTURES',
        'CI_ASSERTION_V2_RECEIPT', 'CI_ASSERTION_V2_SHA256',
        'CI_ASSERTION_V2_SOURCE', 'CI_ASSERTION_V2_FIXTURES',
        'CI_ASSERTION_V2_PATHS', 'CI_ASSERTION_V2_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V3_RECEIPT', 'CI_ASSERTION_V3_SHA256',
        'CI_ASSERTION_V3_SOURCE', 'CI_ASSERTION_V3_FIXTURES',
        'CI_ASSERTION_V3_PATHS', 'CI_ASSERTION_V3_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V3_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V4_RECEIPT', 'CI_ASSERTION_V4_SHA256',
        'CI_ASSERTION_V4_SOURCE', 'CI_ASSERTION_V4_FIXTURES',
        'CI_ASSERTION_V4_PATHS', 'CI_ASSERTION_V4_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V4_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V5_RECEIPT', 'CI_ASSERTION_V5_SHA256',
        'CI_ASSERTION_V5_SOURCE', 'CI_ASSERTION_V5_FIXTURES',
        'CI_ASSERTION_V5_PATHS', 'CI_ASSERTION_V5_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V5_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V5_PREDECESSOR_RAW_SHA256', 'CI_ASSERTION_V5_TEST_SOURCE',
        'CI_ASSERTION_V5_ROOT_PIN_TEST', 'CI_ASSERTION_V5_RETENTION_SOURCE',
        'CI_ASSERTION_V6_RECEIPT', 'CI_ASSERTION_V6_SHA256',
        'CI_ASSERTION_V6_SOURCE', 'CI_ASSERTION_V6_FIXTURES',
        'CI_ASSERTION_V6_PATHS', 'CI_ASSERTION_V6_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V6_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V6_PREDECESSOR_RAW_SHA256',
        'CI_ASSERTION_V7_RECEIPT', 'CI_ASSERTION_V7_SHA256',
        'CI_ASSERTION_V7_SOURCE', 'CI_ASSERTION_V7_FIXTURES',
        'CI_ASSERTION_V7_PATHS', 'CI_ASSERTION_V7_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V7_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V7_PREDECESSOR_RAW_SHA256',
        'CI_ASSERTION_V7_TEST_SOURCE', 'CI_ASSERTION_V7_RETENTION_SOURCE',
        'CI_ASSERTION_V8_RECEIPT', 'CI_ASSERTION_V8_SHA256',
        'CI_ASSERTION_V8_SOURCE', 'CI_ASSERTION_V8_RETENTION_SOURCE',
        'CI_ASSERTION_V8_TEST_SOURCE', 'CI_ASSERTION_V8_FIXTURES',
        'CI_ASSERTION_V8_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V8_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V8_PREDECESSOR_RAW_SHA256', 'CI_ASSERTION_V8_PATHS',
        'CI_ASSERTION_V8_DERIVATION_KEY',
        'CI_ASSERTION_V9_RECEIPT', 'CI_ASSERTION_V9_SHA256',
        'CI_ASSERTION_V9_SOURCE', 'CI_ASSERTION_V9_RETENTION_SOURCE',
        'CI_ASSERTION_V9_TEST_SOURCE', 'CI_ASSERTION_V9_FIXTURES',
        'CI_ASSERTION_V9_PREDECESSOR_RECEIPT',
        'CI_ASSERTION_V9_PREDECESSOR_INVENTORY',
        'CI_ASSERTION_V9_PREDECESSOR_RAW_SHA256',
        'CI_ASSERTION_V9_PREDECESSOR_BLOB_SHA1',
        'CI_ASSERTION_V9_PREDECESSOR_BYTES',
        'CI_ASSERTION_V9_ORDERED_PATHS_SHA256', 'CI_ASSERTION_V9_PATHS',
        'CI_ASSERTION_V9_DERIVATION_KEY',
        'PYTEST_RESTORATION_RECEIPT', 'PYTEST_RESTORATION_SHA',
        'PYTEST_RESTORATION_PATHS', 'PYTEST_RESTORATION_V2_RECEIPT',
        'PYTEST_RESTORATION_V2_SHA', 'PYTEST_RESTORATION_V2_PATHS',
        'PYTEST_RESTORATION_V2_PREDECESSOR_INVENTORY',
        '_ACTIVE_SOURCE_DERIVATION_SCOPE',
    ):
        digest.update(name.encode('utf-8') + b'\0' + repr(globals()[name]).encode('utf-8'))
    for function in (safe.canonical, safe.canonical_digest, safe.identity,
                     json.loads, json.dumps, json.JSONDecoder,
                     json.JSONDecoder.__init__, json.JSONDecoder.decode,
                     json.JSONDecoder.raw_decode, json.JSONEncoder,
                     json.JSONEncoder.__init__, json.JSONEncoder.encode,
                     json.JSONEncoder.iterencode, hashlib.sha1, hashlib.sha256):
        digest.update(repr((id(function), id(getattr(function, '__code__', None)),
                            getattr(function, '__defaults__', None),
                            getattr(function, '__kwdefaults__', None))).encode('utf-8'))
    for value in (
        safe,
        json, hashlib, marshal,
        safe.canonical.__globals__.get('json'),
        safe.canonical_digest.__globals__.get('canonical'),
        safe.canonical_digest.__globals__.get('hashlib'),
        safe.identity.__globals__.get('hashlib'),
        marshal.dumps, marshal.loads,
    ):
        digest.update(repr((type(value).__module__, type(value).__qualname__, id(value))).encode('utf-8'))
    for name, function in (
        ('_CIAssertionV3ProjectedReader.__init__', _CIAssertionV3ProjectedReader.__init__),
        ('_CIAssertionV3ProjectedReader.__call__', _CIAssertionV3ProjectedReader.__call__),
        ('_CIAssertionV6ProjectedReader.__init__', _CIAssertionV6ProjectedReader.__init__),
        ('_CIAssertionV6ProjectedReader.__call__', _CIAssertionV6ProjectedReader.__call__),
        ('_CIAssertionV7ProjectedReader.__init__', _CIAssertionV7ProjectedReader.__init__),
        ('_CIAssertionV7ProjectedReader.__call__', _CIAssertionV7ProjectedReader.__call__),
        ('_CIAssertionV8ProjectedReader.__init__', _CIAssertionV8ProjectedReader.__init__),
        ('_CIAssertionV8ProjectedReader.__call__', _CIAssertionV8ProjectedReader.__call__),
    ):
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(repr((id(function), id(function.__code__), function.__defaults__,
                            function.__kwdefaults__)).encode('utf-8'))
    self = globals()['_ci_assertion_v2_contract_digest']
    digest.update(repr((id(self), id(self.__code__), self.__defaults__,
                        self.__kwdefaults__)).encode('utf-8'))
    return digest.hexdigest()


def _ci_assertion_v2_scope_owner(reader):
    # A short-lived Pass-A SourceReadScope still verifies its own observed
    # paths on exit, but the immutable V1/V2 receipt derivation can be shared
    # by the enclosing checkpoint-master scope. This prevents each nested
    # reader scope from re-running the same eight-file historical chain.
    checkpoint_scope = _active_checkpoint_derivation_scope()
    owner = getattr(reader, '__self__', None)
    if isinstance(owner, _TRUSTED_SOURCE_SCOPE_CLASS):
        # Even an untrusted/substituted scope instance may not be invoked as an
        # uncached escape hatch from a different process/thread/task.
        _assert_source_scope_execution_unit(owner)
    # Checkpoint ownership does not authenticate an arbitrary caller reader.
    # Only the pinned public seam or its reviewed bound scope may reuse proof.
    if (checkpoint_scope is not None and _trusted_source_reader_contract()
            and (reader is _TRUSTED_PUBLIC_READ_BLOB
                 or (getattr(reader, '__func__', None) is _TRUSTED_SOURCE_SCOPE_READ
                     and _trusted_source_scope_instance(owner)))):
        return checkpoint_scope
    source_scope = _active_source_derivation_scope()
    if (source_scope is not None
            and _trusted_source_reader_contract()
            and (reader is _TRUSTED_PUBLIC_READ_BLOB
                 or (owner is source_scope
                     and getattr(reader, '__func__', None) is _TRUSTED_SOURCE_SCOPE_READ))):
        return source_scope
    # authenticate_core() creates a short-lived, reviewed SourceReadScope for
    # each nested public request. Its bound reader is a distinct owner, but it
    # has the same pinned implementation, root, HEAD and underlying reader as
    # this request's outer owner. Share only the immutable V1/V2 derivation;
    # direct bytes are read through the outer owner so its final ledger covers
    # every input. Custom/bound readers remain uncached.
    if (source_scope is not None
            and owner is not source_scope
            and getattr(reader, '__func__', None) is _TRUSTED_SOURCE_SCOPE_READ
            and _trusted_source_scope_instance(owner)
            and owner.execution_unit == source_scope.execution_unit
            and owner.root == source_scope.root
            and owner.head == source_scope.head
            and owner.reader_contract == source_scope.reader_contract
            and owner.reader is _TRUSTED_PUBLIC_READ_BLOB
            and owner.underlying_reader in (
                _TRUSTED_PUBLIC_READ_BLOB, _TRUSTED_SAFE_READ_BLOB)
            and owner.safe_reader is source_scope.safe_reader
            and source_scope.safe_reader is _TRUSTED_SAFE_READ_BLOB):
        return source_scope
    if (_trusted_source_reader_contract()
            and _trusted_source_scope_instance(owner)
            and getattr(reader, '__self__', None) is owner
            and getattr(reader, '__func__', None) is _TRUSTED_SOURCE_SCOPE_READ):
        return owner
    return None


def _ci_assertion_v2_chain(*, _reader=None):
    """Return historical V1/V2 proof only after current V9 also verifies.

    V2 remains an immutable historical accessor. The V9 source-forward edge is
    checked on every independent request, or reused only as immutable bytes in
    the existing request-bound derivation scope.
    """
    details = _ci_assertion_v9_chain_details(_reader=_reader)
    return details[0], details[1]


def _ci_assertion_v2_chain_uncached(reader):
    """Authenticate the V1 receipt through its exact source, then the V2 edge."""
    source_scope = _active_source_derivation_scope()
    if source_scope is not None:
        source_scope._metric('pass_a_ci_assertion_v2_uncached')
    try:
        raw = reader(CI_ASSERTION_V2_RECEIPT)
        value = json.loads(raw)
        _inventory_raw, inventory = _read_canonical_inventory_snapshot(
            reader,
            CI_ASSERTION_V2_PREDECESSOR_INVENTORY,
            'CI assertion V2 receipt or V376 predecessor drift',
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V2 receipt or predecessor cannot be read') from exc
    if (safe.canonical(value) != raw or safe.canonical_digest(value) != CI_ASSERTION_V2_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V2_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V2'
            or type(value.get('schema_version')) is not int or value['schema_version'] != 2
            or set(value) != {
                'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
                'source_forward', 'policy_id', 'predecessor_inventory',
                'predecessor_receipt', 'provider_or_delivery_authority_changed',
                'reason', 'schema_version', 'test_selection_changed', 'workflow_changed'}
            or value.get('predecessor_receipt') != {
                'path': CI_ASSERTION_RECEIPT, 'canonical_sha256': CI_ASSERTION_SHA256,
                'rewritten': False}
            or value.get('predecessor_inventory') != CI_ASSERTION_V2_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_selection_changed',
                'workflow_changed'))
            or inventory.get('canonical_sha256') != CI_ASSERTION_V2_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 376):
        raise ValueError('CI assertion V2 receipt or V376 predecessor drift')

    sources = {item['path']: item['lf_source_sha256']
               for item in inventory.get('source_identities', ())}
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V2_PATHS:
        raise ValueError('CI assertion V2 source path set drift')
    self_fixture = None
    for path, row in rows.items():
        expected_fixture = CI_ASSERTION_V2_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != expected_fixture
                or path not in sources or sources[path] != row.get('before', {}).get('source_sha256')):
            raise ValueError('CI assertion V2 source predecessor drift: ' + path)
        fixture = reader(row['fixture'])
        if safe.identity(fixture) != row['before']:
            raise ValueError('CI assertion V2 source fixture identity drift: ' + path)
        if path == CI_ASSERTION_V2_SOURCE:
            if set(row) != {'fixture', 'before', 'recipe'}:
                raise ValueError('CI assertion V2 Pass-A recipe shape drift')
            recipe = row['recipe']
            token = '<CI_ASSERTION_' + 'V2_DIGEST>'
            if (type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe['before']) is not str or type(recipe['after']) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V2_SHA256).encode('utf-8')
                        != reader(path)):
                raise ValueError('CI assertion V2 Pass-A exact source recipe drift')
            self_fixture = fixture
            continue
        if set(row) != {'fixture', 'before', 'after', 'patches'}:
            raise ValueError('CI assertion V2 source recipe shape drift: ' + path)
        current = reader(path)
        if safe.identity(current) != row['after']:
            raise ValueError('CI assertion V2 current source identity drift: ' + path)
        expected = fixture
        for patch in row['patches']:
            old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
            if not old or expected.count(old) != 1:
                raise ValueError('CI assertion V2 source patch seam drift: ' + path)
            expected = expected.replace(old, new)
        if expected != current:
            raise ValueError('CI assertion V2 source exceeds its exact recipe: ' + path)

    # Project only the current Pass-A file back to its exact V1 after-image
    # while the immutable V1 receipt is independently revalidated.
    def v1_reader(path):
        if path == CI_ASSERTION_V2_SOURCE:
            return self_fixture
        return reader(path)

    prior = _ci_assertion_v1_successor_receipt(_reader=v1_reader)
    return prior, value


def _ci_assertion_v3_chain(*, _reader=None):
    """Authenticate the append-only V9 -> V8 -> V7 -> V3 -> V2 source chain.

    The cached payload contains canonical receipt objects only. The active
    source/receipt scope owns all observed bytes and revalidates its live input
    boundary; no prior acceptance verdict is stored or returned. The return
    shape remains the historical V1/V2/V3 tuple for existing consumers.
    """
    return _ci_assertion_v9_chain_details(_reader=_reader)[:3]


def _ci_assertion_v3_chain_details(*, _reader=None):
    """Preserve the five-value historical API after authenticating V8."""
    return _ci_assertion_v7_chain_details(_reader=_reader)[:5]


def _ci_assertion_v6_chain_details(*, _reader=None):
    """Preserve the six-value V6 API after authenticating its V7/V8 successors."""
    return _ci_assertion_v7_chain_details(_reader=_reader)[:6]


def _ci_assertion_v7_chain_details(*, _reader=None):
    """Preserve the historical API after V9 authenticates current sources."""
    return _ci_assertion_v8_chain_details(_reader=_reader)[:8]


def _ci_assertion_v4_chain_uncached(reader):
    """Authenticate the Pass-A correction without rewriting its V3 history.

    V4 binds the exact current Pass-A bytes to the V378 predecessor inventory.
    The old V3 verifier is then run against a reader that projects only that
    file back to the V4 before-image. V3's own immutable source and receipt
    checks remain unchanged, while current readers continue to authenticate
    the V4 bytes independently.
    """
    try:
        raw = reader(CI_ASSERTION_V4_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V4_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V4 receipt or V378 predecessor cannot be read') from exc
    expected_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt', 'provider_or_delivery_authority_changed',
        'reason', 'schema_version', 'source_forward', 'test_assignments_changed',
        'test_selection_changed', 'workflow_changed',
    }
    if (safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V4_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V4_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V4'
            or value.get('schema_version') != 4
            or set(value) != expected_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V4_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V4_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != CI_ASSERTION_V4_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256') != CI_ASSERTION_V4_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 378
            or inventory.get('schema_version') != 378
            or inventory.get('policy_id') != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V378'
            or inventory.get('predecessor_inventory') != CI_ASSERTION_V3_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V4 receipt scope or V378 predecessor drift')

    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V4_PATHS:
        raise ValueError('CI assertion V4 source path set drift')
    inventory_sources = {
        item['path']: item['lf_source_sha256']
        for item in inventory.get('source_identities', ()) if type(item) is dict
    }
    for path in sorted(CI_ASSERTION_V4_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V4_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V4 source recipe shape drift: ' + path)
        try:
            fixture = reader(fixture_path)
            current = reader(path)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('CI assertion V4 source cannot be read: ' + path) from exc
        if (safe.identity(fixture) != row['before']
                or inventory_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V4 source predecessor identity drift: ' + path)
        if path == CI_ASSERTION_V4_SOURCE:
            recipe = row.get('recipe')
            token = '<CI_ASSERTION_' + 'V4_DIGEST>'
            if (set(row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V4_SHA256).encode('utf-8') != current):
                raise ValueError('CI assertion V4 Pass-A exact source recipe drift')
        else:
            if (set(row) != {'fixture', 'before', 'after', 'patches'}
                    or type(row.get('after')) is not dict
                    or safe.identity(current) != row['after']
                    or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V4 current source identity drift: ' + path)
            expected = fixture
            for patch in row['patches']:
                if (type(patch) is not dict or set(patch) != {'before', 'after'}
                        or type(patch.get('before')) is not str
                        or type(patch.get('after')) is not str):
                    raise ValueError('CI assertion V4 patch schema drift: ' + path)
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V4 patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V4 exact source recipe drift: ' + path)

    # V3 is still the immutable predecessor proof. Its self-source row sees
    # only the authenticated V4 before-image; every other source is read from
    # the caller's current reader and rechecked by the original V3 verifier.
    def v3_reader(candidate):
        if candidate in CI_ASSERTION_V4_PATHS:
            return reader(rows[candidate]['fixture'])
        return reader(candidate)

    prior, v2, v3 = _ci_assertion_v3_chain_uncached(v3_reader)
    v3_rows = v3.get('source_forward', {})
    pass_a_v3 = v3_rows.get(CI_ASSERTION_V4_SOURCE, {})
    pass_a_v3_recipe = pass_a_v3.get('recipe', {})
    pass_a_v3_token = '<CI_ASSERTION_' + 'V3_DIGEST>'
    pass_a_v3_current = pass_a_v3_recipe.get('after', '').replace(
        pass_a_v3_token, CI_ASSERTION_V3_SHA256).encode('utf-8')
    if (v3.get('canonical_sha256') != CI_ASSERTION_V3_SHA256
            or set(CI_ASSERTION_V4_PATHS) - set(v3_rows)
            or pass_a_v3.get('fixture')
                != CI_ASSERTION_V3_FIXTURES + CI_ASSERTION_V4_SOURCE.replace('/', '--') + '.before.txt'
            or pass_a_v3_current != reader(rows[CI_ASSERTION_V4_SOURCE]['fixture'])
            or rows[CI_ASSERTION_V4_TEST_SOURCE]['before']
                != v3_rows[CI_ASSERTION_V4_TEST_SOURCE].get('after')):
        raise ValueError('CI assertion V4 does not extend the exact V3 source chain')
    return prior, v2, v3


def _ci_assertion_v5_chain_uncached(reader):
    """Authenticate the exact V379->V380-preparation edge before V4/V3.

    V5 is a current source transition only. It authenticates the V379 bytes,
    exact current A2/B4 identities, the root-pin addition, and this verifier's
    self-recipe. Its historical reader then supplies those authenticated V379
    bytes to the unchanged V4/V3 validators.
    """
    contract = _ci_assertion_v2_contract_digest()
    try:
        raw = reader(CI_ASSERTION_V5_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V5_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V5 receipt or V379 predecessor cannot be read') from exc
    expected_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt',
        'provider_or_delivery_authority_changed', 'reason', 'schema_version',
        'source_forward', 'test_assignments_changed', 'test_selection_changed',
        'workflow_changed',
    }
    if (safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V5_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V5_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V5'
            or value.get('schema_version') != 5
            or set(value) != expected_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V5_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V5_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or safe.canonical(inventory) != inventory_raw
            or hashlib.sha256(inventory_raw).hexdigest() != CI_ASSERTION_V5_PREDECESSOR_RAW_SHA256
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V5_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V5_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 379
            or inventory.get('schema_version') != 379
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V379'
            or inventory.get('predecessor_inventory')
                != CI_ASSERTION_V4_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V5 receipt scope or V379 predecessor drift')

    rows = value.get('source_forward')
    if (type(rows) is not dict or set(rows) != CI_ASSERTION_V5_PATHS
            or not CI_ASSERTION_V5_PATHS <= CI_ASSERTION_V3_PATHS):
        raise ValueError('CI assertion V5 source path set drift')
    predecessor_sources = {
        row['path']: row['lf_source_sha256']
        for row in inventory.get('source_identities', ()) if type(row) is dict
    }
    current_bytes = {}
    fixture_bytes = {}
    for path in sorted(CI_ASSERTION_V5_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V5_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V5 source recipe shape drift: ' + path)
        try:
            fixture = reader(fixture_path)
            current = reader(path)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('CI assertion V5 source cannot be read: ' + path) from exc
        if (type(fixture) is not bytes or type(current) is not bytes
                or safe.identity(fixture) != row['before']
                or predecessor_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V5 source predecessor identity drift: ' + path)
        fixture_bytes[path] = fixture
        if path == CI_ASSERTION_V5_SOURCE:
            recipe = row.get('recipe')
            token = '<CI_ASSERTION_' + 'V5_DIGEST>'
            if (set(row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V5_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V5 Pass-A exact source recipe drift')
        else:
            if (set(row) != {'fixture', 'before', 'after', 'patches'}
                    or type(row.get('after')) is not dict
                    or safe.identity(current) != row['after']
                    or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V5 current source identity drift: ' + path)
            expected = fixture
            for patch in row['patches']:
                if (type(patch) is not dict or set(patch) != {'before', 'after'}
                        or type(patch.get('before')) is not str
                        or type(patch.get('after')) is not str):
                    raise ValueError('CI assertion V5 patch schema drift: ' + path)
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V5 patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V5 exact source recipe drift: ' + path)
        current_bytes[path] = current

    for path, observed in current_bytes.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V5 current source changed during authentication: ' + path)

    projected = _CIAssertionV5ProjectedReader(reader, fixture_bytes)
    prior, v2, v3 = _ci_assertion_v4_chain_uncached(projected)
    v4_value = json.loads(projected(CI_ASSERTION_V4_RECEIPT))
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V5 verifier changed during source projection')
    return prior, v2, v3, v4_value, value, projected


def _ci_assertion_v6_chain_uncached(reader):
    """Authenticate V6 from V380, then validate V5 through the exact V6 before-view."""
    contract = _ci_assertion_v2_contract_digest()
    try:
        raw = reader(CI_ASSERTION_V6_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V6_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V6 receipt or V380 predecessor cannot be read') from exc
    expected_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt',
        'provider_or_delivery_authority_changed', 'reason', 'schema_version',
        'source_forward', 'test_assignments_changed', 'test_selection_changed',
        'workflow_changed',
    }
    if (type(raw) is not bytes or type(value) is not dict or type(inventory) is not dict
            or safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V6_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V6_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V6'
            or value.get('schema_version') != 6 or set(value) != expected_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V6_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V6_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or type(inventory_raw) is not bytes
            or hashlib.sha256(inventory_raw).hexdigest() != CI_ASSERTION_V6_PREDECESSOR_RAW_SHA256
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V6_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V6_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 380 or inventory.get('schema_version') != 380
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V380'
            or inventory.get('predecessor_inventory')
                != CI_ASSERTION_V5_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V6 receipt scope or V380 predecessor drift')

    rows = value.get('source_forward')
    if (type(rows) is not dict or set(rows) != CI_ASSERTION_V6_PATHS
            or not CI_ASSERTION_V6_PATHS <= CI_ASSERTION_V5_PATHS):
        raise ValueError('CI assertion V6 source path set drift')
    inventory_sources = {}
    for source_row in inventory.get('source_identities', ()):
        if type(source_row) is not dict or set(source_row) != {'path', 'lf_source_sha256'}:
            raise ValueError('V380 source identity row schema drift')
        if source_row['path'] in inventory_sources:
            raise ValueError('V380 source identity path is duplicated')
        inventory_sources[source_row['path']] = source_row['lf_source_sha256']

    fixture_bytes = {}
    for path in sorted(CI_ASSERTION_V6_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V6_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V6 source recipe shape drift: ' + path)
        fixture = reader(fixture_path)
        if (type(fixture) is not bytes or safe.identity(fixture) != row['before']
                or inventory_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V6 V380 predecessor identity drift: ' + path)
        fixture_bytes[path] = fixture

    # A V6 historical reader supplies only the exact V380 before-images. V5
    # then authenticates the V379->V380 transition, its self-recipe, and the
    # immutable V4/V3/V2/V1 prefix against those bytes.
    projected = _CIAssertionV6ProjectedReader(reader, fixture_bytes)
    prior, v2, v3, v4, v5, _v5_projected = _ci_assertion_v5_chain_uncached(projected)
    v5_rows = v5.get('source_forward', {})
    current_bytes = {}
    for path in sorted(CI_ASSERTION_V6_PATHS):
        v6_row = rows[path]
        v5_row = v5_rows.get(path)
        if type(v5_row) is not dict:
            raise ValueError('CI assertion V6 has no authenticated V5 predecessor row: ' + path)
        if path == CI_ASSERTION_V6_SOURCE:
            token = '<CI_ASSERTION_' + 'V5_DIGEST>'
            recipe = v5_row.get('recipe')
            if (type(recipe) is not dict or type(recipe.get('after')) is not str
                    or recipe['after'].count(token) != 1):
                raise ValueError('CI assertion V5 Pass-A predecessor recipe is malformed')
            v5_after = recipe['after'].replace(token, CI_ASSERTION_V5_SHA256).encode('utf-8')
        else:
            _v5_before, v5_after = _apply_exact_source_forward_row(
                path, v5_row, reader, label='CI assertion V5 predecessor')
        if (v5_after != fixture_bytes[path]
                or safe.identity(v5_after) != v6_row['before']):
            raise ValueError('CI assertion V5->V6 source continuity drift: ' + path)

        current = reader(path)
        if type(current) is not bytes:
            raise ValueError('CI assertion V6 current source is not bytes: ' + path)
        if path == CI_ASSERTION_V6_SOURCE:
            recipe = v6_row.get('recipe')
            token = '<CI_ASSERTION_' + 'V6_DIGEST>'
            if (set(v6_row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture_bytes[path]
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V6_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V6 Pass-A exact source recipe drift')
        else:
            if (set(v6_row) != {'fixture', 'before', 'after', 'patches'}
                    or type(v6_row.get('after')) is not dict
                    or safe.identity(current) != v6_row['after']
                    or type(v6_row.get('patches')) is not list):
                raise ValueError('CI assertion V6 current source identity drift: ' + path)
            expected = fixture_bytes[path]
            for patch in v6_row['patches']:
                if (type(patch) is not dict or set(patch) != {'before', 'after'}
                        or type(patch.get('before')) is not str
                        or type(patch.get('after')) is not str):
                    raise ValueError('CI assertion V6 source patch schema drift: ' + path)
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V6 source patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V6 exact source recipe drift: ' + path)
        current_bytes[path] = current

    for path, observed in current_bytes.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V6 current source changed during authentication: ' + path)
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V6 verifier changed during source projection')
    return prior, v2, v3, v4, v5, value, projected


def _ci_assertion_v6_current_source_bytes(value, reader):
    """Re-read Pass-A bytes and prove them against the authenticated V6 self-recipe."""
    contract = _ci_assertion_v2_contract_digest()
    if (type(value) is not dict or value.get('canonical_sha256') != CI_ASSERTION_V6_SHA256
            or safe.canonical_digest(value) != CI_ASSERTION_V6_SHA256):
        raise ValueError('CI assertion V6 Pass-A source proof is stale')
    row = value.get('source_forward', {}).get(CI_ASSERTION_V6_SOURCE)
    if type(row) is not dict or set(row) != {'fixture', 'before', 'recipe'}:
        raise ValueError('CI assertion V6 Pass-A source row is malformed')
    raw = reader(CI_ASSERTION_V6_SOURCE)
    token = '<CI_ASSERTION_' + 'V6_DIGEST>'
    recipe = row.get('recipe')
    if (type(raw) is not bytes or type(recipe) is not dict
            or type(recipe.get('after')) is not str
            or recipe.get('after', '').count(token) != 1
            or recipe['after'].replace(token, CI_ASSERTION_V6_SHA256).encode('utf-8') != raw
            or safe.identity(reader(row['fixture'])) != row['before']
            or contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V6 Pass-A live source differs from its authenticated recipe')
    return raw


class _CIAssertionV6ProjectedReader:
    """Request-local reader for the exact V380 phase authenticated by V6."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v6_projected_reader(reader, value):
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V6_PATHS:
        raise ValueError('CI assertion V6 source path set drift')
    fixtures = {}
    for path in sorted(CI_ASSERTION_V6_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V6_FIXTURES + path.replace('/', '--') + '.before.txt'
        fixture = reader(fixture_path)
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(fixture) is not bytes or safe.identity(fixture) != row.get('before')):
            raise ValueError('CI assertion V6 projected fixture identity drift: ' + path)
        fixtures[path] = fixture
    return _CIAssertionV6ProjectedReader(reader, fixtures)


def _ci_assertion_v6_projected_read(path, raw, reader, *, _value=None):
    """Authenticate V6 on its real reader before returning a V380 phase view."""
    if path not in CI_ASSERTION_V6_PATHS:
        return reader, raw
    if type(reader) is _CIAssertionV6ProjectedReader:
        current_reader = reader.source_reader
        details = _ci_assertion_v6_chain_details(_reader=current_reader)
        authenticated = details[5]
        if _value is not None and _value != authenticated:
            raise ValueError('CI assertion V6 supplied projection is not current-authenticated')
        expected_reader = _ci_assertion_v6_projected_reader(current_reader, authenticated)
        if (reader.fixtures != expected_reader.fixtures or raw != reader(path)
                or reader(path) != expected_reader(path)):
            raise ValueError('CI assertion V6 projected reader differs from authenticated fixtures: ' + path)
        return reader, raw
    details = _ci_assertion_v6_chain_details(_reader=reader)
    authenticated = details[5]
    if _value is not None and _value != authenticated:
        raise ValueError('CI assertion V6 supplied projection is not current-authenticated')
    if type(raw) is not bytes or raw != reader(path):
        raise ValueError('CI assertion V6 current source read changed: ' + path)
    projected = _ci_assertion_v6_projected_reader(reader, authenticated)
    return projected, projected(path)


def _ci_assertion_v7_chain_uncached(reader):
    """Authenticate the V381->V7 edge before validating the V6/V5/V4/V3 prefix."""
    contract = _ci_assertion_v2_contract_digest()
    try:
        raw = reader(CI_ASSERTION_V7_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V7_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V7 receipt or V381 predecessor cannot be read') from exc
    expected_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt',
        'provider_or_delivery_authority_changed', 'reason', 'schema_version',
        'source_forward', 'test_assignments_changed', 'test_selection_changed',
        'workflow_changed',
    }
    if (type(raw) is not bytes or type(value) is not dict or type(inventory) is not dict
            or safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V7_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V7_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V7'
            or value.get('schema_version') != 7 or set(value) != expected_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V7_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V7_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or type(inventory_raw) is not bytes
            or hashlib.sha256(inventory_raw).hexdigest() != CI_ASSERTION_V7_PREDECESSOR_RAW_SHA256
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V7_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V7_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 381 or inventory.get('schema_version') != 381
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V381'
            or inventory.get('predecessor_inventory')
                != CI_ASSERTION_V6_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V7 receipt scope or V381 predecessor drift')

    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V7_PATHS:
        raise ValueError('CI assertion V7 source path set drift')
    inventory_sources = {}
    for source_row in inventory.get('source_identities', ()):
        if type(source_row) is not dict or set(source_row) != {'path', 'lf_source_sha256'}:
            raise ValueError('V381 source identity row schema drift')
        if source_row['path'] in inventory_sources:
            raise ValueError('V381 source identity path is duplicated')
        inventory_sources[source_row['path']] = source_row['lf_source_sha256']

    fixture_bytes = {}
    current_bytes = {}
    for path in sorted(CI_ASSERTION_V7_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V7_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V7 source recipe shape drift: ' + path)
        fixture, current = reader(fixture_path), reader(path)
        if (type(fixture) is not bytes or type(current) is not bytes
                or safe.identity(fixture) != row['before']
                or inventory_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V7 V381 predecessor identity drift: ' + path)
        fixture_bytes[path] = fixture
        current_bytes[path] = current
        if path == CI_ASSERTION_V7_SOURCE:
            recipe = row.get('recipe')
            token = '<CI_ASSERTION_' + 'V7_DIGEST>'
            if (set(row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V7_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V7 Pass-A exact source recipe drift')
        else:
            if (set(row) != {'fixture', 'before', 'after', 'patches'}
                    or type(row.get('after')) is not dict
                    or safe.identity(current) != row['after']
                    or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V7 current source identity drift: ' + path)
            expected = fixture
            for patch in row['patches']:
                if (type(patch) is not dict or set(patch) != {'before', 'after'}
                        or type(patch.get('before')) is not str
                        or type(patch.get('after')) is not str):
                    raise ValueError('CI assertion V7 source patch schema drift: ' + path)
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V7 source patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V7 exact source recipe drift: ' + path)

    # The V7 before-images form one complete V381 reader. Use that phase for
    # the V6 self-recipe and lower V6/V5/V4/V3 validators; never ask those
    # historical validators to authenticate V7's newer bytes as V6 current.
    projected = _CIAssertionV7ProjectedReader(reader, fixture_bytes)
    prior, v2, v3, v4, v5, v6, _v6_projected = _ci_assertion_v6_chain_uncached(projected)
    v6_pass_a = _ci_assertion_v6_current_source_bytes(v6, projected)
    if v6_pass_a != fixture_bytes[CI_ASSERTION_V7_SOURCE]:
        raise ValueError('CI assertion V6 Pass-A self-recipe does not end at V7 before-image')
    retention_path = CI_ASSERTION_V7_RETENTION_SOURCE
    v6_retention = v6.get('source_forward', {}).get(retention_path)
    if (type(v6_retention) is not dict
            or v6_retention.get('after') != safe.identity(fixture_bytes[retention_path])):
        raise ValueError('CI assertion V6 retention edge does not end at V7 before-image')
    v3_test = v3.get('source_forward', {}).get(CI_ASSERTION_V7_TEST_SOURCE)
    if (type(v3_test) is not dict
            or v3_test.get('after') != safe.identity(fixture_bytes[CI_ASSERTION_V7_TEST_SOURCE])
            or CI_ASSERTION_V7_TEST_SOURCE in CI_ASSERTION_V4_PATHS
            or CI_ASSERTION_V7_TEST_SOURCE in CI_ASSERTION_V5_PATHS
            or CI_ASSERTION_V7_TEST_SOURCE in CI_ASSERTION_V6_PATHS):
        raise ValueError('CI assertion V7 test before-image is not the exact V3 endpoint')
    for path, observed in current_bytes.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V7 current source changed during authentication: ' + path)
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V7 verifier changed during source projection')
    return prior, v2, v3, v4, v5, v6, value, projected


def _ci_assertion_v7_current_source_bytes(value, reader):
    """Prove the live Pass-A bytes through the authenticated V7 self-recipe."""
    contract = _ci_assertion_v2_contract_digest()
    if (type(value) is not dict or value.get('canonical_sha256') != CI_ASSERTION_V7_SHA256
            or safe.canonical_digest(value) != CI_ASSERTION_V7_SHA256):
        raise ValueError('CI assertion V7 Pass-A source proof is stale')
    row = value.get('source_forward', {}).get(CI_ASSERTION_V7_SOURCE)
    if type(row) is not dict or set(row) != {'fixture', 'before', 'recipe'}:
        raise ValueError('CI assertion V7 Pass-A source row is malformed')
    raw = reader(CI_ASSERTION_V7_SOURCE)
    recipe = row.get('recipe')
    token = '<CI_ASSERTION_' + 'V7_DIGEST>'
    if (type(raw) is not bytes or type(recipe) is not dict
            or type(recipe.get('after')) is not str
            or recipe['after'].count(token) != 1
            or recipe['after'].replace(token, CI_ASSERTION_V7_SHA256).encode('utf-8') != raw
            or safe.identity(reader(row['fixture'])) != row['before']
            or contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V7 Pass-A live source differs from its authenticated recipe')
    return raw


class _CIAssertionV7ProjectedReader:
    """Request-local reader for the exact V381 phase authenticated by V7."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v7_projected_reader(reader, value):
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V7_PATHS:
        raise ValueError('CI assertion V7 source path set drift')
    fixtures = {}
    for path in sorted(CI_ASSERTION_V7_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V7_FIXTURES + path.replace('/', '--') + '.before.txt'
        fixture = reader(fixture_path)
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(fixture) is not bytes or safe.identity(fixture) != row.get('before')):
            raise ValueError('CI assertion V7 projected fixture identity drift: ' + path)
        fixtures[path] = fixture
    return _CIAssertionV7ProjectedReader(reader, fixtures)


def _ci_assertion_v7_projected_read(path, raw, reader, *, _value=None):
    """Project current or V382 bytes to V381 after authenticating the live chain."""
    if path not in CI_ASSERTION_V7_PATHS and (
            type(reader) not in (_CIAssertionV8ProjectedReader, _CIAssertionV9ProjectedReader)
            or path not in CI_ASSERTION_V3_PATHS):
        return reader, raw
    # Older phase readers are validated by their own phase-specific branch in
    # _ci_assertion_v3_projected_read; they are never promoted to current input.
    if type(reader) in (_CIAssertionV3ProjectedReader, _CIAssertionV6ProjectedReader):
        return reader, raw
    if type(reader) is _CIAssertionV8ProjectedReader:
        current_reader = reader.source_reader
        details = _ci_assertion_v8_chain_details(_reader=current_reader)
        authenticated_v7, expected_v382 = details[6], details[9]
        if _value is not None and _value != authenticated_v7:
            raise ValueError('CI assertion V7 supplied projection is not current-authenticated')
        if (type(reader.fixtures) is not dict or reader.fixtures != expected_v382.fixtures
                or type(raw) is not bytes or raw != reader(path)
                or reader(path) != expected_v382(path)):
            raise ValueError('CI assertion V8 projected reader differs from authenticated fixtures: ' + path)
        projected_v7 = details[7]
        return projected_v7, projected_v7(path)
    if type(reader) is _CIAssertionV7ProjectedReader:
        current_reader = reader.source_reader
        details = _ci_assertion_v7_chain_details(_reader=current_reader)
        authenticated = details[6]
        if _value is not None and _value != authenticated:
            raise ValueError('CI assertion V7 supplied projection is not current-authenticated')
        expected_reader = _ci_assertion_v7_projected_reader(current_reader, authenticated)
        if (reader.fixtures != expected_reader.fixtures or raw != reader(path)
                or reader(path) != expected_reader(path)):
            raise ValueError('CI assertion V7 projected reader differs from authenticated fixtures: ' + path)
        return reader, raw
    details = _ci_assertion_v7_chain_details(_reader=reader)
    authenticated = details[6]
    if _value is not None and _value != authenticated:
        raise ValueError('CI assertion V7 supplied projection is not current-authenticated')
    if type(raw) is not bytes or raw != reader(path):
        raise ValueError('CI assertion V7 current source read changed: ' + path)
    projected = _ci_assertion_v7_projected_reader(reader, authenticated)
    return projected, projected(path)


class _CIAssertionV8ProjectedReader:
    """Request-local reader for the complete authenticated V382 source phase."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v8_projected_reader(reader, value):
    """Rebuild the exact three-path V382 view from authenticated V8 fixtures."""
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V8_PATHS:
        raise ValueError('CI assertion V8 source path set drift')
    fixtures = {}
    for path in sorted(CI_ASSERTION_V8_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V8_FIXTURES + path.replace('/', '--') + '.before.txt'
        fixture = reader(fixture_path)
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict
                or type(fixture) is not bytes or safe.identity(fixture) != row['before']):
            raise ValueError('CI assertion V8 projected fixture identity drift: ' + path)
        fixtures[path] = fixture
    return _CIAssertionV8ProjectedReader(reader, fixtures)


def _ci_assertion_v8_current_source_bytes(value, reader):
    """Prove the current Pass-A bytes through the authenticated V8 self-recipe."""
    contract = _ci_assertion_v2_contract_digest()
    if (type(value) is not dict or value.get('canonical_sha256') != CI_ASSERTION_V8_SHA256
            or safe.canonical_digest(value) != CI_ASSERTION_V8_SHA256):
        raise ValueError('CI assertion V8 Pass-A source proof is stale')
    row = value.get('source_forward', {}).get(CI_ASSERTION_V8_SOURCE)
    if type(row) is not dict or set(row) != {'fixture', 'before', 'recipe'}:
        raise ValueError('CI assertion V8 Pass-A source row is malformed')
    fixture = reader(row['fixture'])
    raw = reader(CI_ASSERTION_V8_SOURCE)
    recipe = row.get('recipe')
    token = '<CI_ASSERTION_' + 'V8_DIGEST>'
    if (type(fixture) is not bytes or safe.identity(fixture) != row['before']
            or type(raw) is not bytes or type(recipe) is not dict
            or set(recipe) != {'before', 'after'}
            or recipe.get('before') != fixture.decode('utf-8')
            or type(recipe.get('after')) is not str
            or recipe['after'].count(token) != 1
            or recipe['after'].replace(token, CI_ASSERTION_V8_SHA256).encode('utf-8') != raw
            or contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V8 Pass-A live source differs from its authenticated recipe')
    return raw


def _ci_assertion_v8_inventory_sources(inventory):
    """Return the pinned V382 source map after exact row-shape validation."""
    rows = inventory.get('source_identities') if type(inventory) is dict else None
    if type(rows) is not list or len(rows) != 1254:
        raise ValueError('V382 source identity inventory shape drift')
    sources = {}
    for row in rows:
        if (type(row) is not dict or set(row) != {'path', 'lf_source_sha256'}
                or type(row.get('path')) is not str
                or type(row.get('lf_source_sha256')) is not str
                or len(row['lf_source_sha256']) != 64
                or row['path'] in sources):
            raise ValueError('V382 source identity row schema or uniqueness drift')
        sources[row['path']] = row['lf_source_sha256']
    return sources


def _ci_assertion_v8_chain_uncached(reader):
    """Authenticate V8 from exact V382 bytes, then run V7 on that phase view."""
    contract = _ci_assertion_v2_contract_digest()
    try:
        raw = reader(CI_ASSERTION_V8_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V8_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V8 receipt or V382 predecessor cannot be read') from exc
    expected_receipt_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt',
        'provider_or_delivery_authority_changed', 'reason', 'schema_version',
        'source_forward', 'test_assignments_changed', 'test_selection_changed',
        'workflow_changed',
    }
    if (type(raw) is not bytes or type(value) is not dict or type(inventory) is not dict
            or safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V8_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V8_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V8'
            or type(value.get('schema_version')) is not int or value['schema_version'] != 8
            or type(value.get('reason')) is not str or not value['reason']
            or set(value) != expected_receipt_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V8_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V8_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or type(inventory_raw) is not bytes
            or hashlib.sha256(inventory_raw).hexdigest() != CI_ASSERTION_V8_PREDECESSOR_RAW_SHA256
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V8_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V8_PREDECESSOR_INVENTORY['canonical_sha256']
            or type(inventory.get('generation')) is not int or inventory['generation'] != 382
            or type(inventory.get('schema_version')) is not int or inventory['schema_version'] != 382
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V382'
            or inventory.get('predecessor_inventory')
                != CI_ASSERTION_V7_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V8 receipt scope or V382 predecessor drift')

    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V8_PATHS:
        raise ValueError('CI assertion V8 source path set drift')
    inventory_sources = _ci_assertion_v8_inventory_sources(inventory)

    fixture_bytes, current_bytes = {}, {}
    for path in sorted(CI_ASSERTION_V8_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V8_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V8 source recipe shape drift: ' + path)
        fixture, current = reader(fixture_path), reader(path)
        if (type(fixture) is not bytes or type(current) is not bytes
                or safe.identity(fixture) != row['before']
                or inventory_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V8 V382 predecessor identity drift: ' + path)
        fixture_bytes[path], current_bytes[path] = fixture, current
        if path == CI_ASSERTION_V8_SOURCE:
            recipe = row.get('recipe')
            token = '<CI_ASSERTION_' + 'V8_DIGEST>'
            if (set(row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V8_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V8 Pass-A exact source recipe drift')
        else:
            if (set(row) != {'fixture', 'before', 'after', 'patches'}
                    or type(row.get('after')) is not dict or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V8 explicit source row schema drift: ' + path)
            replayed_before, replayed_after = _apply_exact_source_forward_row(
                path, row, reader, label='CI assertion V8')
            if replayed_before != fixture or replayed_after != current:
                raise ValueError('CI assertion V8 exact source after-image drift: ' + path)

    # Validate the V7 prefix only through the complete V382 before-image map.
    # The live reader remains attached to both returned phase wrappers.
    projected_v382 = _CIAssertionV8ProjectedReader(reader, fixture_bytes)
    prior, v2, v3, v4, v5, v6, v7, _v7_projected = (
        _ci_assertion_v7_chain_uncached(projected_v382))
    if _ci_assertion_v7_current_source_bytes(v7, projected_v382) \
            != fixture_bytes[CI_ASSERTION_V8_SOURCE]:
        raise ValueError('CI assertion V7 Pass-A self-recipe does not end at V382 before-image')
    for path in (CI_ASSERTION_V8_RETENTION_SOURCE, CI_ASSERTION_V8_TEST_SOURCE):
        prior_row = v7.get('source_forward', {}).get(path)
        if (type(prior_row) is not dict or prior_row.get('after') != rows[path]['before']
                or safe.identity(fixture_bytes[path]) != prior_row.get('after')):
            raise ValueError('CI assertion V7->V8 source endpoint does not compose: ' + path)

    for path, observed in current_bytes.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V8 current source changed during authentication: ' + path)
    if reader(CI_ASSERTION_V8_RECEIPT) != raw \
            or reader(CI_ASSERTION_V8_PREDECESSOR_INVENTORY['path']) != inventory_raw:
        raise ValueError('CI assertion V8 receipt or V382 bytes changed during authentication')
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V8 verifier changed during source projection')
    projected_v7 = _ci_assertion_v7_projected_reader(reader, v7)
    projected_v382 = _CIAssertionV8ProjectedReader(reader, fixture_bytes)
    return (prior, v2, v3, v4, v5, v6, v7, projected_v7, value, projected_v382)


def _ci_assertion_v8_reconstitute_cached(reader, payload):
    """Check cached canonical receipts against fresh scoped bytes and rebuild views."""
    if type(payload) is not dict or type(payload.get('chain')) is not list:
        raise ValueError('CI assertion V8 cached receipt chain is malformed')
    receipts = (
        (CI_ASSERTION_RECEIPT, payload['chain'][0], CI_ASSERTION_SHA256),
        (CI_ASSERTION_V2_RECEIPT, payload['chain'][1], CI_ASSERTION_V2_SHA256),
        (CI_ASSERTION_V3_RECEIPT, payload['chain'][2], CI_ASSERTION_V3_SHA256),
        (CI_ASSERTION_V4_RECEIPT, payload['v4'], CI_ASSERTION_V4_SHA256),
        (CI_ASSERTION_V5_RECEIPT, payload['v5'], CI_ASSERTION_V5_SHA256),
        (CI_ASSERTION_V6_RECEIPT, payload['v6'], CI_ASSERTION_V6_SHA256),
        (CI_ASSERTION_V7_RECEIPT, payload['v7'], CI_ASSERTION_V7_SHA256),
        (CI_ASSERTION_V8_RECEIPT, payload['v8'], CI_ASSERTION_V8_SHA256),
    )
    for path, value, digest in receipts:
        raw = reader(path)
        if (type(value) is not dict or type(raw) is not bytes
                or safe.canonical(value) != raw
                or safe.canonical_digest(value) != digest
                or value.get('canonical_sha256') != digest):
            raise ValueError('CI assertion V8 cached receipt bytes changed: ' + path)
    inventory_raw = reader(CI_ASSERTION_V8_PREDECESSOR_INVENTORY['path'])
    inventory = json.loads(inventory_raw)
    if (type(inventory_raw) is not bytes or type(inventory) is not dict
            or hashlib.sha256(inventory_raw).hexdigest() != CI_ASSERTION_V8_PREDECESSOR_RAW_SHA256
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V8_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V8_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 382 or inventory.get('schema_version') != 382
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V382'
            or inventory.get('predecessor_inventory') != CI_ASSERTION_V7_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V8 cached V382 predecessor changed')

    prior, v2, v3 = payload['chain']
    v7, v8 = payload['v7'], payload['v8']
    if (v8.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V8'
            or type(v8.get('schema_version')) is not int or v8['schema_version'] != 8
            or type(v8.get('reason')) is not str or not v8['reason']
            or v8.get('predecessor_receipt') != CI_ASSERTION_V8_PREDECESSOR_RECEIPT
            or v8.get('predecessor_inventory') != CI_ASSERTION_V8_PREDECESSOR_INVENTORY
            or any(v8.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or type(v8.get('source_forward')) is not dict
            or set(v8['source_forward']) != CI_ASSERTION_V8_PATHS):
        raise ValueError('CI assertion V8 cached receipt scope drift')
    inventory_sources = _ci_assertion_v8_inventory_sources(inventory)
    for path in sorted(CI_ASSERTION_V8_PATHS):
        row = v8['source_forward'][path]
        if inventory_sources.get(path) != row.get('before', {}).get('source_sha256'):
            raise ValueError('CI assertion V8 cached V382 source edge changed: ' + path)
    projected_v7 = _ci_assertion_v7_projected_reader(reader, v7)
    projected_v382 = _ci_assertion_v8_projected_reader(reader, v8)
    if _ci_assertion_v7_current_source_bytes(v7, projected_v382) != projected_v382(CI_ASSERTION_V8_SOURCE):
        raise ValueError('CI assertion V7 Pass-A cached phase does not match V382')
    for path in (CI_ASSERTION_V8_RETENTION_SOURCE, CI_ASSERTION_V8_TEST_SOURCE):
        prior_row = v7.get('source_forward', {}).get(path)
        row = v8.get('source_forward', {}).get(path)
        if (type(prior_row) is not dict or type(row) is not dict
                or prior_row.get('after') != row.get('before')
                or safe.identity(projected_v382(path)) != row.get('before')):
            raise ValueError('CI assertion V7/V8 cached phase edge changed: ' + path)

    _ci_assertion_v8_current_source_bytes(v8, reader)
    for path in (CI_ASSERTION_V8_RETENTION_SOURCE, CI_ASSERTION_V8_TEST_SOURCE):
        row = v8['source_forward'][path]
        before, expected = _apply_exact_source_forward_row(
            path, row, reader, label='CI assertion V8 cached')
        if (before != projected_v382(path) or reader(path) != expected
                or safe.identity(reader(path)) != row.get('after')):
            raise ValueError('CI assertion V8 cached current source changed: ' + path)
    return (prior, v2, v3, payload['v4'], payload['v5'], payload['v6'],
            v7, projected_v7, v8, projected_v382)


def _ci_assertion_v8_chain_details(*, _reader=None):
    """Expose the historical ten-value view only after current V9 proof.

    Reader ownership selects V9's cold or scoped path; it never selects an
    older authentication policy. V9's cold and warm implementations call the
    private V8 derivation primitives directly on their authenticated V383
    phase, so this compatibility facade cannot recurse into itself.
    """
    return _ci_assertion_v9_chain_details(_reader=_reader)[:10]


def _ci_assertion_v9_inventory_sources(inventory):
    """Validate the exact ordered V383 source map used by V9."""
    rows = inventory.get('source_identities') if type(inventory) is dict else None
    if type(rows) is not list or len(rows) != 1254:
        raise ValueError('V383 source identity inventory shape drift')
    sources = {}
    for row in rows:
        if (type(row) is not dict or set(row) != {'path', 'lf_source_sha256'}
                or type(row.get('path')) is not str
                or type(row.get('lf_source_sha256')) is not str
                or len(row['lf_source_sha256']) != 64
                or row['path'] in sources):
            raise ValueError('V383 source identity row schema or uniqueness drift')
        sources[row['path']] = row['lf_source_sha256']
    ordered = '\n'.join(row['path'] for row in rows).encode('utf-8')
    if hashlib.sha256(ordered).hexdigest() != CI_ASSERTION_V9_ORDERED_PATHS_SHA256:
        raise ValueError('V383 ordered source path set drift')
    return sources


def _ci_assertion_v9_observe(reader):
    """Read and verify fresh V9, V383, fixture, and current source bytes."""
    contract = _ci_assertion_v2_contract_digest()
    try:
        raw = reader(CI_ASSERTION_V9_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V9_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V9 receipt or V383 predecessor cannot be read') from exc
    expected_keys = {
        'authority_granted', 'canonical_sha256', 'historical_bytes_changed',
        'policy_id', 'predecessor_inventory', 'predecessor_receipt',
        'provider_or_delivery_authority_changed', 'reason', 'schema_version',
        'source_forward', 'test_assignments_changed', 'test_selection_changed',
        'workflow_changed',
    }
    if (type(raw) is not bytes or type(value) is not dict
            or safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V9_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V9_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V9'
            or type(value.get('schema_version')) is not int or value['schema_version'] != 9
            or type(value.get('reason')) is not str or not value['reason']
            or set(value) != expected_keys
            or value.get('predecessor_receipt') != CI_ASSERTION_V9_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V9_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'))
            or type(inventory_raw) is not bytes
            or len(inventory_raw) != CI_ASSERTION_V9_PREDECESSOR_BYTES
            or hashlib.sha256(inventory_raw).hexdigest()
                != CI_ASSERTION_V9_PREDECESSOR_RAW_SHA256
            or safe.identity(inventory_raw)['git_blob_sha1']
                != CI_ASSERTION_V9_PREDECESSOR_BLOB_SHA1
            or type(inventory) is not dict
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V9_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256')
                != CI_ASSERTION_V9_PREDECESSOR_INVENTORY['canonical_sha256']
            or type(inventory.get('generation')) is not int or inventory['generation'] != 383
            or type(inventory.get('schema_version')) is not int or inventory['schema_version'] != 383
            or inventory.get('policy_id')
                != 'ATHENA_CORE_01D_CI_OFFLINE_TRANSPORT_SOURCE_INVENTORY_V383'
            or inventory.get('predecessor_inventory')
                != CI_ASSERTION_V8_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V9 receipt scope or V383 predecessor drift')

    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V9_PATHS:
        raise ValueError('CI assertion V9 source path set drift')
    inventory_sources = _ci_assertion_v9_inventory_sources(inventory)
    fixtures, currents = {}, {}
    for path in sorted(CI_ASSERTION_V9_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V9_FIXTURES + path.replace('/', '--') + '.before.txt'
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict):
            raise ValueError('CI assertion V9 source row shape drift: ' + path)
        fixture, current = reader(fixture_path), reader(path)
        if (type(fixture) is not bytes or type(current) is not bytes
                or safe.identity(fixture) != row['before']
                or inventory_sources.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V9 V383 predecessor identity drift: ' + path)
        fixtures[path], currents[path] = fixture, current
        if path == CI_ASSERTION_V9_SOURCE:
            recipe = row.get('recipe')
            token = '<CI_ASSERTION_' + 'V9_DIGEST>'
            if (set(row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe.get('before')) is not str
                    or type(recipe.get('after')) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V9_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V9 Pass-A exact source recipe drift')
        else:
            if (set(row) != {'fixture', 'before', 'after', 'patches'}
                    or type(row.get('after')) is not dict
                    or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V9 explicit source row schema drift: ' + path)
            before, expected = _apply_exact_source_forward_row(
                path, row, reader, label='CI assertion V9')
            if (before != fixture or expected != current
                    or safe.identity(current) != row['after']):
                raise ValueError('CI assertion V9 exact source after-image drift: ' + path)
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V9 verifier changed during source observation')
    return raw, value, inventory_raw, inventory, fixtures, currents


def _ci_assertion_v9_current_source_bytes(value, reader):
    """Prove current Pass-A bytes against the authenticated V9 self-recipe."""
    contract = _ci_assertion_v2_contract_digest()
    if (type(value) is not dict or value.get('canonical_sha256') != CI_ASSERTION_V9_SHA256
            or safe.canonical_digest(value) != CI_ASSERTION_V9_SHA256):
        raise ValueError('CI assertion V9 Pass-A source proof is stale')
    row = value.get('source_forward', {}).get(CI_ASSERTION_V9_SOURCE)
    if type(row) is not dict or set(row) != {'fixture', 'before', 'recipe'}:
        raise ValueError('CI assertion V9 Pass-A source row is malformed')
    fixture, raw = reader(row['fixture']), reader(CI_ASSERTION_V9_SOURCE)
    recipe = row.get('recipe')
    token = '<CI_ASSERTION_' + 'V9_DIGEST>'
    if (type(fixture) is not bytes or safe.identity(fixture) != row['before']
            or type(raw) is not bytes or type(recipe) is not dict
            or set(recipe) != {'before', 'after'}
            or recipe.get('before') != fixture.decode('utf-8')
            or type(recipe.get('after')) is not str
            or recipe['after'].count(token) != 1
            or recipe['after'].replace(token, CI_ASSERTION_V9_SHA256).encode('utf-8') != raw
            or contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V9 Pass-A live source differs from its authenticated recipe')
    return raw


class _CIAssertionV9ProjectedReader:
    """Request-local reader for the complete authenticated V383 source phase."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v9_projected_reader(reader, value):
    """Rebuild the exact three-path V383 view from authenticated fixtures."""
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V9_PATHS:
        raise ValueError('CI assertion V9 source path set drift')
    fixtures = {}
    for path in sorted(CI_ASSERTION_V9_PATHS):
        row = rows[path]
        fixture_path = CI_ASSERTION_V9_FIXTURES + path.replace('/', '--') + '.before.txt'
        fixture = reader(fixture_path)
        if (type(row) is not dict or row.get('fixture') != fixture_path
                or type(row.get('before')) is not dict
                or type(fixture) is not bytes or safe.identity(fixture) != row['before']):
            raise ValueError('CI assertion V9 projected fixture identity drift: ' + path)
        fixtures[path] = fixture
    return _CIAssertionV9ProjectedReader(reader, fixtures)


def _ci_assertion_v9_phase_values(v8_details, value, projected_v383):
    """Require V8 and V3 predecessor endpoints to meet exact V9 before-images."""
    if (type(v8_details) is not tuple or len(v8_details) != 10
            or type(value) is not dict or type(projected_v383) is not _CIAssertionV9ProjectedReader):
        raise ValueError('CI assertion V9 phase composition input is malformed')
    v3, v8 = v8_details[2], v8_details[8]
    rows = value.get('source_forward', {})
    pass_a = rows.get(CI_ASSERTION_V9_SOURCE, {})
    retention = rows.get(CI_ASSERTION_V9_RETENTION_SOURCE, {})
    test = rows.get(CI_ASSERTION_V9_TEST_SOURCE, {})
    v8_pass_a = _ci_assertion_v8_current_source_bytes(v8, projected_v383)
    v8_retention = v8.get('source_forward', {}).get(CI_ASSERTION_V9_RETENTION_SOURCE)
    v3_test = v3.get('source_forward', {}).get(CI_ASSERTION_V9_TEST_SOURCE)
    if (type(pass_a) is not dict or type(retention) is not dict or type(test) is not dict
            or safe.identity(v8_pass_a) != pass_a.get('before')
            or safe.identity(projected_v383(CI_ASSERTION_V9_SOURCE)) != pass_a.get('before')
            or type(v8_retention) is not dict
            or v8_retention.get('after') != retention.get('before')
            or safe.identity(projected_v383(CI_ASSERTION_V9_RETENTION_SOURCE))
                != retention.get('before')
            or type(v3_test) is not dict
            or v3_test.get('after') != test.get('before')
            or safe.identity(projected_v383(CI_ASSERTION_V9_TEST_SOURCE)) != test.get('before')
            or CI_ASSERTION_V9_TEST_SOURCE not in CI_ASSERTION_V3_PATHS
            or any(CI_ASSERTION_V9_TEST_SOURCE in paths for paths in (
                CI_ASSERTION_V4_PATHS, CI_ASSERTION_V5_PATHS, CI_ASSERTION_V6_PATHS,
                CI_ASSERTION_V7_PATHS, CI_ASSERTION_V8_PATHS))):
        raise ValueError('CI assertion V8/V3 predecessor endpoints do not compose with V9')
    return True


def _ci_assertion_v9_chain_uncached(reader):
    """Authenticate V9 and V383 first, then run the immutable V8 chain on V383."""
    contract = _ci_assertion_v2_contract_digest()
    raw, value, inventory_raw, _inventory, fixtures, currents = _ci_assertion_v9_observe(reader)
    projected_v383 = _ci_assertion_v9_projected_reader(reader, value)
    # V8 must see the authenticated V383 before-image, never the newer V9 bytes.
    # This is the historical V8 proof over the already-authenticated V383
    # phase. Do not enter the public V8 compatibility facade here: that
    # facade must authenticate the current V9 source edge for every caller.
    v8_details = _ci_assertion_v8_chain_uncached(projected_v383)
    _ci_assertion_v9_phase_values(v8_details, value, projected_v383)
    for path, observed in currents.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V9 current source changed during authentication: ' + path)
    if (reader(CI_ASSERTION_V9_RECEIPT) != raw
            or reader(CI_ASSERTION_V9_PREDECESSOR_INVENTORY['path']) != inventory_raw
            or contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V9 receipt, inventory, or verifier changed during projection')
    return v8_details + (value, projected_v383)


def _ci_assertion_v9_cache_payload(details):
    """Serialize only canonical receipt objects; readers and verdicts stay local."""
    if type(details) is not tuple or len(details) != 12:
        raise ValueError('CI assertion V9 cache source details are malformed')
    return {
        'v8': {
            'chain': list(details[:3]), 'v4': details[3], 'v5': details[4],
            'v6': details[5], 'v7': details[6], 'v8': details[8],
        },
        'v9': details[10],
    }


def _ci_assertion_v9_reconstitute_cached(reader, payload):
    """Recheck current V9/V383 bytes, then rebuild V8/V3 phase readers afresh."""
    if (type(payload) is not dict or set(payload) != {'v8', 'v9'}
            or type(payload.get('v8')) is not dict or type(payload.get('v9')) is not dict):
        raise ValueError('CI assertion V9 cached derivation payload is malformed')
    raw, value, inventory_raw, _inventory, fixtures, currents = _ci_assertion_v9_observe(reader)
    if safe.canonical(payload['v9']) != raw or payload['v9'] != value:
        raise ValueError('CI assertion V9 cached receipt bytes changed')
    projected_v383 = _ci_assertion_v9_projected_reader(reader, value)
    v8_details = _ci_assertion_v8_reconstitute_cached(projected_v383, payload['v8'])
    _ci_assertion_v9_phase_values(v8_details, value, projected_v383)
    for path, observed in currents.items():
        if reader(path) != observed:
            raise ValueError('CI assertion V9 current source changed during scoped reuse: ' + path)
    if reader(CI_ASSERTION_V9_RECEIPT) != raw \
            or reader(CI_ASSERTION_V9_PREDECESSOR_INVENTORY['path']) != inventory_raw:
        raise ValueError('CI assertion V9 receipt or V383 bytes changed during scoped reuse')
    return v8_details + (value, projected_v383)


def _ci_assertion_v9_chain_details(*, _reader=None):
    """Return V1..V9 receipts and fresh V383/V382/V381 phase readers."""
    request_reader = read_blob if _reader is None else _reader
    if type(request_reader) in (
            _CIAssertionV9ProjectedReader, _CIAssertionV8ProjectedReader,
            _CIAssertionV7ProjectedReader, _CIAssertionV6ProjectedReader,
            _CIAssertionV5ProjectedReader, _CIAssertionV4ProjectedReader,
            _CIAssertionV3ProjectedReader):
        # Authenticate the root and complete fixture maps before invoking the
        # supplied wrapper, then compare its selected result with that proof.
        _root, _normalized, _observed, details = _ci_assertion_v9_authenticated_input(
            CI_ASSERTION_V9_SOURCE, None, request_reader, _read_supplied=True)
        return details
    owner = _ci_assertion_v2_scope_owner(request_reader)
    if owner is None:
        return _ci_assertion_v9_chain_uncached(request_reader)
    active_source_scope = _active_source_derivation_scope()
    reader = request_reader
    if owner is active_source_scope:
        def read_scoped(path):
            _verify_scoped_source_path(path)
            return owner.read(path)
        reader = read_scoped
    contract = _ci_assertion_v2_contract_digest()
    cached = owner.load_derivation(CI_ASSERTION_V9_DERIVATION_KEY, contract)
    if cached is not None:
        payload = json.loads(cached)
        if type(payload) is not dict or safe.canonical(payload) != cached:
            raise ValueError('CI assertion V9 scoped derivation payload is not canonical')
        details = _ci_assertion_v9_reconstitute_cached(reader, payload)
        if contract != _ci_assertion_v2_contract_digest():
            raise ValueError('CI assertion V9 verifier changed during scoped reuse')
        _record_ci_assertion_v3_scope_metric(owner, 'pass_a_ci_assertion_v3_hits')
        if safe.canonical(_ci_assertion_v9_cache_payload(details)) != cached:
            raise ValueError('CI assertion V9 scoped canonical receipt cache changed')
    else:
        _record_ci_assertion_v3_scope_metric(owner, 'pass_a_ci_assertion_v3_uncached')
        details = _ci_assertion_v9_chain_uncached(reader)
        if contract != _ci_assertion_v2_contract_digest():
            raise ValueError('CI assertion V9 verifier changed during scoped authentication')
        owner.store_derivation(
            CI_ASSERTION_V9_DERIVATION_KEY, contract,
            safe.canonical(_ci_assertion_v9_cache_payload(details)))
    if reader is request_reader:
        return details
    # Reattach fresh wrappers to the caller's exact source seam, using maps
    # already authenticated by the selected owner. Do not refill them through
    # the caller on a warm request.
    projected_v383 = _CIAssertionV9ProjectedReader(
        request_reader, details[11].fixtures)
    projected_v382 = _CIAssertionV8ProjectedReader(
        projected_v383, details[9].fixtures)
    projected_v7 = _CIAssertionV7ProjectedReader(
        projected_v383, details[7].fixtures)
    return details[:7] + (projected_v7, details[8], projected_v382,
                          details[10], projected_v383)


def _ci_assertion_v9_reader_graph(reader):
    """Inspect exact supported wrappers without invoking their call methods."""
    wrapper_ranks = {
        _CIAssertionV3ProjectedReader: 3,
        _CIAssertionV4ProjectedReader: 4,
        _CIAssertionV5ProjectedReader: 5,
        _CIAssertionV6ProjectedReader: 6,
        _CIAssertionV7ProjectedReader: 7,
        _CIAssertionV8ProjectedReader: 8,
        _CIAssertionV9ProjectedReader: 9,
    }
    current = reader
    wrappers = []
    seen = set()
    previous_rank = 2
    while type(current) in wrapper_ranks:
        if id(current) in seen:
            raise ValueError('CI assertion projected reader graph is cyclic')
        seen.add(id(current))
        rank = wrapper_ranks[type(current)]
        if rank <= previous_rank:
            raise ValueError('CI assertion projected reader phase order is invalid')
        try:
            parent = current.source_reader
            fixtures = current.fixtures
        except AttributeError as exc:
            raise ValueError('CI assertion projected reader wrapper is malformed') from exc
        if parent is current or not callable(parent) or type(fixtures) is not dict:
            raise ValueError('CI assertion projected reader wrapper is malformed')
        wrappers.append((current, parent, fixtures, dict(fixtures), rank))
        previous_rank = rank
        current = parent
    if not callable(current):
        raise ValueError('CI assertion current source reader is not callable')
    return current, tuple(wrappers)


def _ci_assertion_v9_composed_v381(details):
    """Compose V7 over V8 over V9 using only authenticated phase maps."""
    if type(details) is not tuple or len(details) != 12:
        raise ValueError('CI assertion V9 phase details are malformed')
    v383 = details[11]
    v382 = _CIAssertionV8ProjectedReader(v383, details[9].fixtures)
    return _CIAssertionV7ProjectedReader(v382, details[7].fixtures)


def _ci_assertion_v9_reader_phase(root, details, rank, phases):
    """Build a fresh authenticated phase reader for an incoming wrapper rank."""
    if rank in phases:
        return phases[rank]
    if rank == 9:
        phase = details[11]
    elif rank == 8:
        phase = details[9]
    elif rank == 7:
        phase = details[7]
    elif rank == 6:
        phase = _ci_assertion_v6_projected_reader(
            _ci_assertion_v9_composed_v381(details), details[5])
    elif rank == 5:
        phase = _ci_assertion_v5_projected_reader(
            _ci_assertion_v9_reader_phase(root, details, 6, phases), details[4])
    elif rank == 4:
        if not CI_ASSERTION_V4_PATHS:
            raise ValueError('CI assertion V4 source path set is empty')
        phase = _ci_assertion_v4_projected_reader(
            sorted(CI_ASSERTION_V4_PATHS)[0],
            _ci_assertion_v9_reader_phase(root, details, 5, phases), details[3])
    elif rank == 3:
        phase = _ci_assertion_v3_projected_reader(root, details[2])
    else:
        raise ValueError('CI assertion projected reader phase is unknown')
    expected_type = {
        3: _CIAssertionV3ProjectedReader,
        4: _CIAssertionV4ProjectedReader,
        5: _CIAssertionV5ProjectedReader,
        6: _CIAssertionV6ProjectedReader,
        7: _CIAssertionV7ProjectedReader,
        8: _CIAssertionV8ProjectedReader,
        9: _CIAssertionV9ProjectedReader,
    }[rank]
    if type(phase) is not expected_type:
        raise ValueError('CI assertion authenticated phase reader has the wrong type')
    phases[rank] = phase
    return phase


def _ci_assertion_v9_authenticated_input(path, raw, reader, *, _read_supplied=False):
    """Authenticate the live root and incoming overlay before normalizing it.

    Wrapper methods are not called until the complete graph and its full maps
    have been compared with a fresh V9 proof. This keeps incoming bytes in
    their original phase, separate from the historical phase used downstream.
    """
    if not _read_supplied and type(raw) is not bytes:
        raise ValueError('CI assertion V9 incoming source phase drift: ' + path)
    root, wrappers = _ci_assertion_v9_reader_graph(reader)
    contract = _ci_assertion_v2_contract_digest()
    details = _ci_assertion_v9_chain_details(_reader=root)
    if type(details) is not tuple or len(details) != 12:
        raise ValueError('CI assertion V9 current proof has an invalid shape')

    phases = {}
    maps = {}
    for _wrapper, _parent, fixtures, snapshot, rank in wrappers:
        expected = _ci_assertion_v9_reader_phase(root, details, rank, phases).fixtures
        if (type(expected) is not dict
                or any(type(key) is not str or type(blob) is not bytes
                       for mapping in (fixtures, snapshot) for key, blob in mapping.items())
                or fixtures != snapshot or fixtures != expected):
            raise ValueError('CI assertion V9 supplied phase fixture map drift')
        maps[rank] = expected

    observed = root(path)
    if type(observed) is not bytes:
        raise ValueError('CI assertion V9 live reader returned non-bytes: ' + path)
    if path in CI_ASSERTION_V3_PATHS:
        # A custom live reader can change after the proof returns. Compare
        # this selected read to the newest authenticated after-image before
        # accepting either the caller's bytes or an older wrapper fallback.
        for index in (10, 8, 6, 5, 4, 3, 2):
            row = details[index]['source_forward'].get(path)
            if row is not None:
                break
        if row is None:
            raise ValueError('CI assertion V9 live source has no authenticated row: ' + path)
        if path == CI_ASSERTION_V9_SOURCE:
            token = '<CI_ASSERTION_' + 'V9_DIGEST>'
            expected = row['recipe']['after'].replace(token, CI_ASSERTION_V9_SHA256)
            matches = observed == expected.encode('utf-8')
        else:
            matches = safe.identity(observed) == row['after']
        if not matches:
            raise ValueError('CI assertion V9 live source changed after current proof: ' + path)
    for _wrapper, _parent, _fixtures, _snapshot, rank in reversed(wrappers):
        if path in maps[rank]:
            observed = maps[rank][path]
    if _read_supplied:
        # This call is safe only now: every exact wrapper class, edge order,
        # and complete fixture map has already been authenticated.
        supplied = reader(path)
        if type(supplied) is not bytes or supplied != observed:
            raise ValueError('CI assertion V9 supplied reader differs from authenticated phase: ' + path)
    elif raw != observed:
        raise ValueError('CI assertion V9 incoming source phase drift: ' + path)

    normalized = root
    for wrapper, parent, fixtures, snapshot, rank in reversed(wrappers):
        if (wrapper.source_reader is not parent or wrapper.fixtures is not fixtures
                or any(type(key) is not str or type(blob) is not bytes
                       for key, blob in fixtures.items())
                or fixtures != snapshot or fixtures != maps[rank]):
            raise ValueError('CI assertion V9 supplied reader changed during authentication')
        normalized = type(wrapper)(normalized, maps[rank])
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V9 reader or helper contract changed during authentication')
    return root, normalized, observed, details


def _ci_assertion_v9_normalize_reader(path, raw, reader):
    """Preserve the incoming phase while authenticating its exact live root."""
    _root, normalized, observed, details = _ci_assertion_v9_authenticated_input(
        path, raw, reader)
    return normalized, observed, details


def _ci_assertion_v9_projected_read(path, raw, reader):
    """Project authenticated current V9 bytes back to the exact V383 phase."""
    wrapper_types = (
        _CIAssertionV9ProjectedReader, _CIAssertionV8ProjectedReader,
        _CIAssertionV7ProjectedReader, _CIAssertionV6ProjectedReader,
        _CIAssertionV5ProjectedReader, _CIAssertionV4ProjectedReader,
        _CIAssertionV3ProjectedReader,
    )
    wrapper = type(reader) in wrapper_types
    relevant = any(path in paths for paths in (
        CI_ASSERTION_V3_PATHS, CI_ASSERTION_V4_PATHS, CI_ASSERTION_V5_PATHS,
        CI_ASSERTION_V6_PATHS, CI_ASSERTION_V7_PATHS, CI_ASSERTION_V8_PATHS,
        CI_ASSERTION_V9_PATHS))
    if not wrapper and not relevant:
        return reader, raw
    _root, incoming, observed, details = _ci_assertion_v9_authenticated_input(
        path, raw, reader)
    if not relevant:
        return reader, raw
    phase = details[11]
    return phase, phase(path)


def _record_ci_assertion_v3_scope_metric(owner, name):
    """Record real cold/hit work through the selected scope's supported API.

    Pass-A source scopes own a local ``metrics`` map and expose ``_metric``.
    Checkpoint scopes intentionally expose the shared receipt-engine recorder
    instead.  The owner is revalidated here so metric dispatch cannot weaken
    checkpoint precedence, execution-unit isolation, or the scope contract.
    """
    if type(name) is not str or not name.startswith('pass_a_ci_assertion_v3_'):
        raise ValueError('CI assertion V3 scope metric name is malformed')
    if type(owner) is _TRUSTED_SOURCE_SCOPE_CLASS:
        if not _trusted_source_scope_instance(owner):
            raise ValueError('CI assertion V3 source owner contract changed')
        _TRUSTED_SOURCE_SCOPE_CLASS._metric(owner, name)
        return

    engine = sys.modules.get('scripts.audit_core_01d_checkpoint_e_completion_v8')
    scope_type = None if engine is None else getattr(engine, '_BoundedReceiptScope', None)
    if engine is None or scope_type is None or type(owner) is not scope_type:
        raise TypeError('CI assertion V3 scope owner has no supported metric interface')
    if (not getattr(owner, 'enabled', False)
            or getattr(owner, 'unit', None) != engine._execution_unit()
            or not any(candidate is owner for candidate in
                       engine._ACTIVE_RECEIPT_SCOPES.get().values())):
        raise AssertionError('CI assertion V3 checkpoint owner is inactive or untrusted')
    recorder = getattr(engine, '_record_scope_metric', None)
    if not callable(recorder):
        raise TypeError('checkpoint receipt engine has no metric recorder')
    recorder(name)


def _apply_exact_source_forward_row(path, row, reader, *, label):
    """Replay one immutable byte edge and verify both endpoint identities."""
    if (type(row) is not dict
            or set(row) != {'fixture', 'before', 'after', 'patches'}
            or type(row.get('patches')) is not list):
        raise ValueError(label + ' source row schema drift: ' + path)
    before = reader(row['fixture'])
    if type(before) is not bytes or safe.identity(before) != row['before']:
        raise ValueError(label + ' predecessor fixture identity drift: ' + path)
    expected = before
    for patch in row['patches']:
        if type(patch) is not dict or set(patch) != {'before', 'after'}:
            raise ValueError(label + ' source patch schema drift: ' + path)
        old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
        if not old or expected.count(old) != 1:
            raise ValueError(label + ' source patch seam drift: ' + path)
        expected = expected.replace(old, new)
    if safe.identity(expected) != row['after']:
        raise ValueError(label + ' source edge after-image drift: ' + path)
    return before, expected


def _require_v2_v3_source_edge(path, v2_row, v3_row, reader):
    """Require same-path, forward V2->V3 byte continuity before projection."""
    if path not in CI_ASSERTION_V2_PATHS or path not in CI_ASSERTION_V3_PATHS:
        raise ValueError('CI assertion V2/V3 edge path is not admitted: ' + path)
    _v2_before, v2_after = _apply_exact_source_forward_row(
        path, v2_row, reader, label='CI assertion V2')
    v3_before, _v3_after = _apply_exact_source_forward_row(
        path, v3_row, reader, label='CI assertion V3')
    if (v2_row['after'] != v3_row['before']
            or v2_after != v3_before
            or safe.identity(v2_after) != v3_row['before']):
        raise ValueError('CI assertion V2->V3 source edge direction/path mismatch: ' + path)
    return v2_after


class _CIAssertionV3ProjectedReader:
    """Request-local historical reader retaining its original byte source."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


class _CIAssertionV4ProjectedReader:
    """Request-local reader for the authenticated V4 predecessor phase."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v4_projected_reader(path, reader, value):
    """Project V4 paths only after replaying their exact current source edges."""
    if path not in CI_ASSERTION_V4_PATHS:
        return reader
    contract = _ci_assertion_v2_contract_digest()
    receipt_raw = reader(CI_ASSERTION_V4_RECEIPT)
    inventory_raw = reader(CI_ASSERTION_V4_PREDECESSOR_INVENTORY['path'])
    try:
        inventory = json.loads(inventory_raw)
    except (ValueError, TypeError) as exc:
        raise ValueError('CI assertion V4 projected predecessor is malformed') from exc
    if (safe.canonical(value) != receipt_raw
            or safe.canonical_digest(value) != CI_ASSERTION_V4_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V4_SHA256
            or value.get('predecessor_receipt') != CI_ASSERTION_V4_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V4_PREDECESSOR_INVENTORY
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory)
                != CI_ASSERTION_V4_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 378
            or inventory.get('predecessor_inventory') != CI_ASSERTION_V3_PREDECESSOR_INVENTORY):
        raise ValueError('CI assertion V4 projected receipt or predecessor drift')
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V4_PATHS:
        raise ValueError('CI assertion V4 projected source path set drift')
    predecessor_sources = {
        row['path']: row['lf_source_sha256']
        for row in inventory.get('source_identities', ()) if type(row) is dict
    }
    fixtures = {}
    for candidate in sorted(CI_ASSERTION_V4_PATHS):
        row = rows[candidate]
        fixture_path = CI_ASSERTION_V4_FIXTURES + candidate.replace('/', '--') + '.before.txt'
        if type(row) is not dict or row.get('fixture') != fixture_path:
            raise ValueError('CI assertion V4 projected source row drift: ' + candidate)
        fixture = reader(fixture_path)
        current = reader(candidate)
        if (type(fixture) is not bytes or type(current) is not bytes
                or safe.identity(fixture) != row.get('before')
                or predecessor_sources.get(candidate) != row.get('before', {}).get('source_sha256')):
            raise ValueError('CI assertion V4 projected source identity drift: ' + candidate)
        if candidate == CI_ASSERTION_V4_SOURCE:
            recipe = row.get('recipe', {})
            token = '<CI_ASSERTION_' + 'V4_DIGEST>'
            if (recipe.get('before', '').encode('utf-8') != fixture
                    or recipe.get('after', '').count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V4_SHA256)
                        .encode('utf-8') != current):
                raise ValueError('CI assertion V4 projected Pass-A recipe drift')
        else:
            if (type(row.get('after')) is not dict
                    or safe.identity(current) != row['after']
                    or type(row.get('patches')) is not list):
                raise ValueError('CI assertion V4 projected current source drift: ' + candidate)
            expected = fixture
            for patch in row['patches']:
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V4 projected patch seam drift: ' + candidate)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V4 projected source recipe drift: ' + candidate)
        fixtures[candidate] = fixture
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V4 verifier changed during projection')
    return _CIAssertionV4ProjectedReader(reader, fixtures)


class _CIAssertionV5ProjectedReader:
    """Request-local reader for the authenticated V379 source phase."""

    __slots__ = ('source_reader', 'fixtures')

    def __init__(self, source_reader, fixtures):
        self.source_reader = source_reader
        self.fixtures = fixtures

    def __call__(self, path):
        if path in self.fixtures:
            return self.fixtures[path]
        return self.source_reader(path)


def _ci_assertion_v5_projected_reader(reader, value):
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V5_PATHS:
        raise ValueError('CI assertion V5 source path set drift')
    fixtures = {}
    for path in sorted(CI_ASSERTION_V5_PATHS):
        row = rows[path]
        fixture = reader(row.get('fixture'))
        current = reader(path)
        if type(fixture) is not bytes or type(current) is not bytes:
            raise ValueError('CI assertion V5 projected source is not bytes: ' + path)
        if safe.identity(fixture) != row.get('before'):
            raise ValueError('CI assertion V5 predecessor fixture identity drift: ' + path)
        if path == CI_ASSERTION_V5_SOURCE:
            token = '<CI_ASSERTION_' + 'V5_DIGEST>'
            recipe = row.get('recipe', {})
            if (recipe.get('after', '').count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V5_SHA256)
                        .encode('utf-8') != current):
                raise ValueError('CI assertion V5 Pass-A exact source recipe drift')
        else:
            if safe.identity(current) != row.get('after'):
                raise ValueError('CI assertion V5 current source identity drift: ' + path)
            expected = fixture
            for patch in row.get('patches', ()):
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V5 patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V5 exact source recipe drift: ' + path)
        fixtures[path] = fixture
    return _CIAssertionV5ProjectedReader(reader, fixtures)


def _ci_assertion_v3_projected_reader(reader, value):
    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V3_PATHS:
        raise ValueError('CI assertion V3 source path set drift')
    fixtures = {}
    for path, row in rows.items():
        fixture = reader(row.get('fixture'))
        if safe.identity(fixture) != row.get('before'):
            raise ValueError('CI assertion V3 predecessor fixture drift: ' + path)
        fixtures[path] = fixture

    return _CIAssertionV3ProjectedReader(reader, fixtures)


def _ci_assertion_v3_projected_read(path, raw, reader, *, _value=None):
    """Authenticate the current V9 root, then build the exact V3 phase view."""
    wrapper_types = (
        _CIAssertionV9ProjectedReader, _CIAssertionV8ProjectedReader,
        _CIAssertionV7ProjectedReader, _CIAssertionV6ProjectedReader,
        _CIAssertionV5ProjectedReader, _CIAssertionV4ProjectedReader,
        _CIAssertionV3ProjectedReader,
    )
    is_wrapper = type(reader) in wrapper_types
    if path not in CI_ASSERTION_V3_PATHS and not is_wrapper:
        return reader, raw

    contract = _ci_assertion_v2_contract_digest()
    root, incoming, observed, details = _ci_assertion_v9_authenticated_input(
        path, raw, reader)
    if path not in CI_ASSERTION_V3_PATHS:
        return reader, raw
    authenticated = details[2]
    if _value is not None and _value != authenticated:
        raise ValueError('CI assertion V3 supplied projection value is not current-authenticated')

    root_again, wrappers = _ci_assertion_v9_reader_graph(reader)
    if root_again is not root:
        raise ValueError('CI assertion V9 reader root changed during V3 projection')
    if wrappers and wrappers[0][4] == 3:
        # A valid V3 wrapper is already in the requested phase. Return a fresh
        # map rooted at the exact current callable so explicit-current V1/V2
        # re-entry can independently authenticate the current V9 proof.
        phase = _ci_assertion_v9_reader_phase(root, details, 3, {})
        if observed != phase(path):
            raise ValueError('CI assertion V3 supplied phase differs from its authenticated map: ' + path)
        result = (phase, phase(path))
    else:
        # Build V381 by composing the authenticated V8 map over V383 and the
        # V7 map over V382. Then invert only the exact older edges needed for
        # this selector, retaining the live root separately for the V3 wrapper.
        phase = _ci_assertion_v9_composed_v381(details)
        phase = _ci_assertion_v6_projected_reader(phase, details[5])
        if path in CI_ASSERTION_V5_PATHS or path in CI_ASSERTION_V4_PATHS:
            v5_path = path if path in CI_ASSERTION_V5_PATHS else CI_ASSERTION_V5_SOURCE
            phase = _ci_assertion_v5_projected_read(
                v5_path, phase(v5_path), phase, _value=details[4])
        if path in CI_ASSERTION_V4_PATHS:
            phase = _ci_assertion_v4_projected_reader(path, phase, details[3])
        result = _ci_assertion_v3_projected_read_with_value(
            path, phase(path), phase, authenticated, _current_reader=root)

    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V3 reader or helper contract changed during projection')
    return result


def _ci_assertion_v5_projected_read(path, raw, reader, *, _value=None):
    """Return V379 bytes after current V5 receipt and source checks."""
    if path not in CI_ASSERTION_V5_PATHS:
        return reader
    contract = _ci_assertion_v2_contract_digest()
    value = (_ci_assertion_v3_chain_details(_reader=reader)[4]
             if _value is None else _value)
    receipt_raw = reader(CI_ASSERTION_V5_RECEIPT)
    if (safe.canonical(value) != receipt_raw
            or safe.canonical_digest(value) != CI_ASSERTION_V5_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V5_SHA256):
        raise ValueError('CI assertion V5 supplied source proof is stale')
    projected = _ci_assertion_v5_projected_reader(reader, value)
    if raw != reader(path):
        raise ValueError('CI assertion V5 current source read changed: ' + path)
    if contract != _ci_assertion_v2_contract_digest():
        raise ValueError('CI assertion V5 verifier changed during projection')
    return projected


def _ci_assertion_v3_projected_read_with_value(
        path, raw, reader, value, *, _current_reader=None):
    """Create a historical reader after current V3 authentication."""
    if type(raw) is not bytes or raw != reader(path):
        raise ValueError('CI assertion V3 current source read changed: ' + path)
    row = value['source_forward'][path]
    fixture = reader(row['fixture'])
    if path == CI_ASSERTION_V3_SOURCE:
        template = row['recipe']['after']
        token = '<CI_ASSERTION_' + 'V3_DIGEST>'
        if (safe.identity(fixture) != row['before']
                or template.count(token) != 1
                or template.replace(token, CI_ASSERTION_V3_SHA256).encode('utf-8') != raw):
            raise ValueError('CI assertion V3 Pass-A exact source recipe drift')
    elif safe.identity(raw) != row['after']:
        raise ValueError('CI assertion V3 current source identity drift: ' + path)
    projected = _ci_assertion_v3_projected_reader(
        reader if _current_reader is None else _current_reader, value)
    return projected, projected(path)


def _ci_assertion_v3_chain_uncached(reader):
    """Verify the immutable V2 prefix, exact V377 link, and every V3 after-image."""
    try:
        raw = reader(CI_ASSERTION_V3_RECEIPT)
        value = json.loads(raw)
        inventory_raw = reader(CI_ASSERTION_V3_PREDECESSOR_INVENTORY['path'])
        inventory = json.loads(inventory_raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('CI assertion V3 receipt or V377 predecessor cannot be read') from exc
    if (safe.canonical(value) != raw
            or safe.canonical_digest(value) != CI_ASSERTION_V3_SHA256
            or value.get('canonical_sha256') != CI_ASSERTION_V3_SHA256
            or value.get('policy_id') != 'ATHENA_PHASE_A_CI_ASSERTION_SOURCE_SUCCESSOR_V3'
            or value.get('schema_version') != 3
            or set(value) != {
                'authority_granted', 'canonical_sha256', 'historical_bytes_changed', 'policy_id',
                'predecessor_inventory', 'predecessor_receipt', 'provider_or_delivery_authority_changed',
                'reason', 'schema_version', 'source_forward', 'test_assignments_changed',
                'test_selection_changed', 'workflow_changed'}
            or value.get('predecessor_receipt') != CI_ASSERTION_V3_PREDECESSOR_RECEIPT
            or value.get('predecessor_inventory') != CI_ASSERTION_V3_PREDECESSOR_INVENTORY
            or any(value.get(key) is not False for key in (
                'authority_granted', 'historical_bytes_changed',
                'provider_or_delivery_authority_changed', 'test_assignments_changed',
                'test_selection_changed'))
            or value.get('workflow_changed') is not True
            or safe.canonical(inventory) != inventory_raw
            or safe.canonical_digest(inventory) != CI_ASSERTION_V3_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('canonical_sha256') != CI_ASSERTION_V3_PREDECESSOR_INVENTORY['canonical_sha256']
            or inventory.get('generation') != 377
            or inventory.get('predecessor_inventory') != {
                'path': CI_ASSERTION_V3_PRIOR_INVENTORY['path'],
                'canonical_sha256': CI_ASSERTION_V3_PRIOR_INVENTORY['canonical_sha256'],
                'generation': 376, 'rewritten': False}):
        raise ValueError('CI assertion V3 receipt scope or V377 predecessor drift')

    rows = value.get('source_forward')
    if type(rows) is not dict or set(rows) != CI_ASSERTION_V3_PATHS:
        raise ValueError('CI assertion V3 source path set drift')
    source_rows = {row['path']: row['lf_source_sha256']
                   for row in inventory.get('source_identities', ()) if type(row) is dict}
    for path, row in rows.items():
        expected_fixture = CI_ASSERTION_V3_FIXTURES + path.replace('/', '--') + '.before.txt'
        fixture = reader(row.get('fixture'))
        if (type(row) is not dict or row.get('fixture') != expected_fixture
                or type(row.get('before')) is not dict
                or safe.identity(fixture) != row['before']
                or source_rows.get(path) != row['before'].get('source_sha256')):
            raise ValueError('CI assertion V3 source predecessor drift: ' + path)
        current = reader(path)
        if path == CI_ASSERTION_V3_SOURCE:
            if set(row) != {'fixture', 'before', 'recipe'}:
                raise ValueError('CI assertion V3 Pass-A recipe shape drift')
            recipe = row['recipe']
            token = '<CI_ASSERTION_' + 'V3_DIGEST>'
            if (type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or type(recipe['before']) is not str or type(recipe['after']) is not str
                    or recipe['before'].encode('utf-8') != fixture
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V3_SHA256)
                        .encode('utf-8') != current):
                raise ValueError('CI assertion V3 Pass-A exact source recipe drift')
        else:
            if set(row) != {'fixture', 'before', 'after', 'patches'} or safe.identity(current) != row.get('after'):
                raise ValueError('CI assertion V3 current source identity drift: ' + path)
            expected = fixture
            for patch in row['patches']:
                if (type(patch) is not dict or set(patch) != {'before', 'after'}
                        or type(patch['before']) is not str or type(patch['after']) is not str):
                    raise ValueError('CI assertion V3 source patch schema drift: ' + path)
                old, new = patch['before'].encode('utf-8'), patch['after'].encode('utf-8')
                if not old or expected.count(old) != 1:
                    raise ValueError('CI assertion V3 source patch seam drift: ' + path)
                expected = expected.replace(old, new)
            if expected != current:
                raise ValueError('CI assertion V3 source exceeds its exact recipe: ' + path)

    def v2_reader(path):
        if path in rows:
            return reader(rows[path]['fixture'])
        return reader(path)

    prior, predecessor = _ci_assertion_v2_chain_uncached(v2_reader)
    if (predecessor.get('canonical_sha256') != CI_ASSERTION_V3_PREDECESSOR_RECEIPT['canonical_sha256']
            or predecessor.get('predecessor_inventory') != CI_ASSERTION_V3_PRIOR_INVENTORY):
        raise ValueError('CI assertion V3 does not extend the exact V2/V376 prefix')
    return prior, predecessor, value


def _install_ci_assertion_v3_context(context):
    latest = _ci_assertion_v9_chain_details(_reader=read_blob)
    prior, successor, value = latest[:3]
    metadata = {CI_ASSERTION_V3_RECEIPT: safe.identity(read_blob(CI_ASSERTION_V3_RECEIPT))}
    for path, row in value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = safe.identity(read_blob(path))
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path] = dict(
                context['HISTORICAL_PREDECESSORS'][path], after=after)
        elif path.endswith('.py') or path == 'sitecustomize.py':
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path.endswith('.py') and path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    v4_raw = read_blob(CI_ASSERTION_V4_RECEIPT)
    v4_value = json.loads(v4_raw)
    metadata[CI_ASSERTION_V4_RECEIPT] = safe.identity(v4_raw)
    for path, row in v4_value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = safe.identity(read_blob(path))
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py'):
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    v5_raw = read_blob(CI_ASSERTION_V5_RECEIPT)
    v5_value = json.loads(v5_raw)
    metadata[CI_ASSERTION_V5_RECEIPT] = safe.identity(v5_raw)
    for path, row in v5_value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = (safe.identity(read_blob(path)) if path == CI_ASSERTION_V5_SOURCE
                 else row['after'])
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py') or path == 'sitecustomize.py':
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    (_v7_prior, _v7_v2, _v7_v3, _v7_v4, _v7_v5, v6, v7,
     v7_phase_reader, v8, v382_phase_reader, v9, v383_phase_reader) = latest
    v6_raw = read_blob(CI_ASSERTION_V6_RECEIPT)
    metadata[CI_ASSERTION_V6_RECEIPT] = safe.identity(v6_raw)
    for path, row in v6['source_forward'].items():
        metadata[row['fixture']] = row['before']
        # The Pass-A row is a self-recipe and intentionally has no ordinary
        # after identity. Validate it against the authenticated V381 phase
        # before deriving its historical V6 identity.
        after = (safe.identity(_ci_assertion_v6_current_source_bytes(v6, v7_phase_reader))
                 if path == CI_ASSERTION_V6_SOURCE else row['after'])
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py'):
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    v7_raw = read_blob(CI_ASSERTION_V7_RECEIPT)
    metadata[CI_ASSERTION_V7_RECEIPT] = safe.identity(v7_raw)
    for path, row in v7['source_forward'].items():
        metadata[row['fixture']] = row['before']
        # As for V6, the Pass-A row is bound by its one-token self-recipe.
        # V7's self-recipe terminates at the authenticated V382 phase, not
        # the newer V8 live Pass-A bytes.
        after = (safe.identity(_ci_assertion_v7_current_source_bytes(v7, v382_phase_reader))
                 if path == CI_ASSERTION_V7_SOURCE else row['after'])
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py'):
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    v8_raw = read_blob(CI_ASSERTION_V8_RECEIPT)
    metadata[CI_ASSERTION_V8_RECEIPT] = safe.identity(v8_raw)
    for path, row in v8['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = (safe.identity(_ci_assertion_v8_current_source_bytes(v8, v383_phase_reader))
                 if path == CI_ASSERTION_V8_SOURCE else row['after'])
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py'):
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    v9_raw = read_blob(CI_ASSERTION_V9_RECEIPT)
    metadata[CI_ASSERTION_V9_RECEIPT] = safe.identity(v9_raw)
    for path, row in v9['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = (safe.identity(_ci_assertion_v9_current_source_bytes(v9, read_blob))
                 if path == CI_ASSERTION_V9_SOURCE else row['after'])
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py'):
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)


def _ci_assertion_successor_receipt(*, _reader=None):
    """Return V1 only after its append-only V2 current-source edge verifies."""
    return _ci_assertion_v2_chain(_reader=_reader)[0]


def _ci_assertion_predecessor_source(path, raw, *, _reader=None, _current_reader=None):
    """Return the predecessor bytes while preserving the established API."""
    projected, _historical_reader = _ci_assertion_predecessor_source_with_reader(
        path, raw, _reader=_reader, _current_reader=_current_reader)
    return projected


def _ci_assertion_predecessor_source_with_reader(
        path, raw, *, _reader=None, _current_reader=None):
    """Invert the CI edge and return its authenticated phase-specific reader.

    A direct caller supplies the current reader.  A composite caller may
    already have applied the V3 projection, in which case the exact wrapper
    retains that same current reader.  The returned reader is used by the next
    historical edge so its independent cold reads observe the correct source
    phase; wrapper type or fixture contents alone never authenticate it.
    """
    reader = read_blob if _reader is None else _reader
    if path not in CI_ASSERTION_PATHS and path not in CI_ASSERTION_V2_PATHS:
        return raw, reader
    projection_contract = None
    if (_current_reader is None
            and type(reader) is _CIAssertionV3ProjectedReader):
        # Nested source-forward readers pass the phase wrapper through more
        # than one predecessor helper. Recover its original reader only as a
        # candidate input; the full V3 chain and exact projection are checked
        # below before any historical edge is consumed.
        _current_reader = reader.source_reader
    elif _current_reader is None and path in CI_ASSERTION_V3_PATHS:
        # Direct callers start with current bytes and an ordinary reader.
        # Authenticate and apply V3 first, so the later V2/V1 comparison sees
        # the exact predecessor phase it is meant to consume.
        reader, raw = _ci_assertion_v3_projected_read(path, raw, reader)
        _current_reader = reader.source_reader
    if _current_reader is None:
        prior, successor = _ci_assertion_v2_chain(_reader=reader)
    else:
        # A V3 historical reader cannot authenticate itself as current: its
        # source paths intentionally return immutable before-images.  Re-read
        # the current V3 chain through the original reader, reconstruct the
        # exact expected projection, and only then use the V2/V1 chain returned
        # by that authenticated current proof.  This is a phase-aware adapter,
        # not trust in a wrapper type, caller-supplied value, or mutable map.
        if (type(reader) is not _CIAssertionV3ProjectedReader
                or reader.source_reader is not _current_reader
                or type(reader.fixtures) is not dict):
            raise ValueError('CI assertion V3 projected reader/current source mismatch')
        projection_contract = _ci_assertion_v2_contract_digest()
        prior, successor, current_v3 = _ci_assertion_v3_chain(_reader=_current_reader)
        expected_reader = _ci_assertion_v3_projected_reader(_current_reader, current_v3)
        if reader.fixtures != expected_reader.fixtures:
            raise ValueError('CI assertion V3 projected reader differs from authenticated fixtures: ' + path)
        v3_row = current_v3.get('source_forward', {}).get(path)
        expected_path_bytes = (_current_reader(v3_row['fixture'])
                               if type(v3_row) is dict
                               else _current_reader(path))
        if reader(path) != expected_path_bytes:
            raise ValueError('CI assertion V3 projected path bytes differ from current proof: ' + path)
    successor_row = successor['source_forward'].get(path)
    current = reader(path)
    if raw != current:
        raise ValueError('CI assertion current source read changed: ' + path)
    if successor_row is not None:
        before_successor = reader(successor_row['fixture'])
        if (safe.identity(current) != successor_row['after']
                or safe.identity(before_successor) != successor_row['before']):
            raise ValueError('CI assertion V2 current or predecessor source drift: ' + path)
        if path == CI_ASSERTION_V2_SOURCE:
            recipe = successor_row.get('recipe')
            token = '<CI_ASSERTION_' + 'V2_DIGEST>'
            if (set(successor_row) != {'fixture', 'before', 'recipe'}
                    or type(recipe) is not dict or set(recipe) != {'before', 'after'}
                    or recipe['before'].encode('utf-8') != before_successor
                    or recipe['after'].count(token) != 1
                    or recipe['after'].replace(token, CI_ASSERTION_V2_SHA256).encode('utf-8')
                        != current):
                raise ValueError('CI assertion V2 Pass-A predecessor recipe drift: ' + path)
        else:
            reconstructed = before_successor
            for patch in successor_row['patches']:
                old, new = patch['before'].encode(), patch['after'].encode()
                if not old or reconstructed.count(old) != 1:
                    raise ValueError('CI assertion V2 source patch seam drift: ' + path)
                reconstructed = reconstructed.replace(old, new)
            if reconstructed != current:
                raise ValueError('CI assertion V2 source exceeds its exact recipe: ' + path)
        projected = before_successor
    else:
        projected = current
    if path not in CI_ASSERTION_PATHS:
        if (projection_contract is not None
                and projection_contract != _ci_assertion_v2_contract_digest()):
            raise ValueError('CI assertion V3 reader/helper contract changed during projection')
        return projected, reader
    row = prior['source_forward'][path]
    before = reader(row['fixture'])
    if (safe.identity(projected) != row['after']
            or safe.identity(before) != row['before']):
        raise ValueError('CI assertion V1 current or predecessor source drift: ' + path)
    expected = before
    for patch in row['patches']:
        old, new = patch['before'].encode(), patch['after'].encode()
        if not old or expected.count(old) != 1:
            raise ValueError('CI assertion V1 source patch seam drift: ' + path)
        expected = expected.replace(old, new)
    if expected != projected:
        raise ValueError('CI assertion source exceeds its exact recipe: ' + path)
    if (projection_contract is not None
            and projection_contract != _ci_assertion_v2_contract_digest()):
        raise ValueError('CI assertion V3 reader/helper contract changed during projection')
    return before, reader


def _authenticate_ci_assertion_successor(*, _reader=None):
    reader = read_blob if _reader is None else _reader
    value = _ci_assertion_successor_receipt(_reader=reader)
    for path in sorted(CI_ASSERTION_PATHS):
        _ci_assertion_predecessor_source(path, reader(path), _reader=reader)
    return value


def install_ci_assertion_context(context):
    value = _authenticate_ci_assertion_successor()
    _prior, successor = _ci_assertion_v2_chain()
    metadata = {CI_ASSERTION_RECEIPT: safe.identity(read_blob(CI_ASSERTION_RECEIPT)),
                value['pass_a_predecessor']['fixture']: value['pass_a_predecessor']['identity']}
    metadata[CI_ASSERTION_V2_RECEIPT] = safe.identity(read_blob(CI_ASSERTION_V2_RECEIPT))
    for path, row in successor['source_forward'].items():
        metadata[row['fixture']] = row['before']
        after = safe.identity(read_blob(path)) if path == CI_ASSERTION_V2_SOURCE else row['after']
        context['BOOTSTRAP_AFTER'][path] = after
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = after
        elif path.endswith('.py') or path == 'sitecustomize.py':
            context['HISTORICAL_PREDECESSORS'][path] = {
                'fixture': row['fixture'], **row['before'], 'after': after}
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = after
    for path, row in value['source_forward'].items():
        metadata[row['fixture']] = row['before']
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path]['after'] = row['after']
        if path in context['ADDED_PYTHON_IDENTITIES']:
            context['ADDED_PYTHON_IDENTITIES'][path] = row['after']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)


def _callable_source_binding(function):
    code = getattr(function, '__code__', None)
    defaults = getattr(function, '__defaults__', None)
    kwdefaults = getattr(function, '__kwdefaults__', None)
    closure = getattr(function, '__closure__', None) or ()
    captured = []
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            captured.append(('empty',))
        else:
            captured.append((id(value), repr(value)))
    return (id(function), id(code), id(defaults), repr(defaults),
            id(kwdefaults), repr(kwdefaults), tuple(captured))


def _trusted_source_reader_contract():
    """Allow source-only reuse only under the imported, reviewed reader seam."""
    if (_trusted_source_reader_contract is not _TRUSTED_SOURCE_READER_CONTRACT_FN
            or _callable_source_binding(_trusted_source_reader_contract)
                != _TRUSTED_SOURCE_READER_CONTRACT_BINDING
            or _trusted_source_scope_instance is not _TRUSTED_SOURCE_SCOPE_INSTANCE_FN
            or _callable_source_binding(_trusted_source_scope_instance)
                != _TRUSTED_SOURCE_SCOPE_INSTANCE_BINDING):
        return False
    if (read_blob is not _TRUSTED_PUBLIC_READ_BLOB
            or _callable_source_binding(read_blob) != _TRUSTED_PUBLIC_READ_BLOB_BINDING
            or safe.read_blob is not _TRUSTED_SAFE_READ_BLOB
            or _callable_source_binding(safe.read_blob) != _TRUSTED_SAFE_READ_BLOB_BINDING
            or _scoped_source_read_contract is not _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_FN
            or _callable_source_binding(_scoped_source_read_contract)
                != _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_BINDING):
        return False
    return (_TRUSTED_SCOPED_SOURCE_READ_CONTRACT_FN()
            == _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_DIGEST)


def _trusted_source_scope_instance(scope):
    if type(scope) is not _TRUSTED_SOURCE_SCOPE_CLASS:
        return False
    _assert_source_scope_execution_unit(scope)
    if (not _trusted_source_reader_contract()
            or scope.reader is not _TRUSTED_PUBLIC_READ_BLOB
            or scope.underlying_reader not in (
                _TRUSTED_PUBLIC_READ_BLOB, _TRUSTED_SAFE_READ_BLOB)
            or scope.safe_reader is not _TRUSTED_SAFE_READ_BLOB
            or scope.reader_contract_fn is not _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_FN
            or scope.reader_contract != _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_DIGEST):
        return False
    for name, expected in _TRUSTED_SOURCE_SCOPE_METHOD_BINDINGS:
        if _callable_source_binding(getattr(_TRUSTED_SOURCE_SCOPE_CLASS, name)) != expected:
            return False
    return True


# Capture only after the complete module has defined the public reader, source
# scope, and V2 verifier. A reader substituted before a request starts must use
# the uncached path or be rejected; it can never be silently replaced by the
# lower-level safe reader during scoped reuse.
_TRUSTED_PUBLIC_READ_BLOB = read_blob
_TRUSTED_PUBLIC_READ_BLOB_BINDING = _callable_source_binding(read_blob)
_TRUSTED_SAFE_READ_BLOB = safe.read_blob
_TRUSTED_SAFE_READ_BLOB_BINDING = _callable_source_binding(safe.read_blob)
_TRUSTED_SOURCE_SCOPE_CLASS = _SourceReadScope
_TRUSTED_SOURCE_SCOPE_READ = _SourceReadScope.read
_TRUSTED_SOURCE_SCOPE_METHOD_BINDINGS = tuple(
    (name, _callable_source_binding(getattr(_SourceReadScope, name)))
    for name in ('__init__', 'read', 'verify', 'load_derivation', 'store_derivation'))
_TRUSTED_SCOPED_SOURCE_READ_CONTRACT_FN = _scoped_source_read_contract
_TRUSTED_SCOPED_SOURCE_READ_CONTRACT_BINDING = _callable_source_binding(
    _scoped_source_read_contract)
_TRUSTED_SOURCE_READER_CONTRACT_FN = _trusted_source_reader_contract
_TRUSTED_SOURCE_READER_CONTRACT_BINDING = _callable_source_binding(
    _trusted_source_reader_contract)
_TRUSTED_SOURCE_SCOPE_INSTANCE_FN = _trusted_source_scope_instance
_TRUSTED_SOURCE_SCOPE_INSTANCE_BINDING = _callable_source_binding(
    _trusted_source_scope_instance)
_TRUSTED_SCOPED_SOURCE_READ_CONTRACT_DIGEST = (
    _TRUSTED_SCOPED_SOURCE_READ_CONTRACT_FN())
