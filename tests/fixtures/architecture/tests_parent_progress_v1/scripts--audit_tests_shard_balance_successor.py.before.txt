"""Exact Tests-only successor, composed outside frozen P4/D5/retention proofs.

This module reads tracked source evidence and evaluates a single maintenance
transition. It never invokes historical proof builders, A2, transport or Actions.
Current Python source identities are independently authenticated by current A2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/tests.yml'
FIXTURE = 'tests/fixtures/architecture/revised_workflows/tests-pre-shard-balance-v1.yml'
RECEIPT = 'artifacts/architecture/tests_shard_balance_successor_v1.json'
SNAPSHOT = 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_shard_balance_v1.json'
RECEIPT_SHA256 = 'cafe21063a9fb7e4cf560269ef1b4acdd2a4214557c907dda68e5962528117c3'
V1_RECEIPT = RECEIPT
V1_SNAPSHOT = SNAPSHOT
V2_RECEIPT = 'artifacts/architecture/tests_shard_balance_successor_v2.json'
V2_SNAPSHOT = 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_shard_balance_v2.json'
V2_FIXTURE = 'tests/fixtures/architecture/revised_workflows/tests-pre-rebalance-v2.yml'
V2_TEST_FIXTURE = 'tests/fixtures/architecture/tests_shard_balance_v2/tests--test_tests_shard_balance_successor.py.before.txt'
V2_SOURCE_FIXTURE = 'tests/fixtures/architecture/tests_shard_balance_v2/scripts--audit_tests_shard_balance_successor.py.before.txt'
BEFORE_TREE = '77c3a70e38833756766e43a4a31ba2a7cc55a45d'
V1_AFTER_TREE = 'cd25278ee9e89459a33faeadc21f54ca2b99a6e5'
AFTER_TREE = 'a1ff8602c939de78c38359ea18fd3dd56ab2075d'
BEFORE_B4_TREE = 'dd703507488f1495767b8e0055d71a9f488390bf'
V1_AFTER_B4_TREE = '006a1a40caf2d2f934e87925f778792e686449e2'
AFTER_B4_TREE = '3e01d5f40b5d0cf133b72ad5c75a1c36a9314334'
BEFORE = {'git_blob_sha1': 'a5eafa0afebc01abe02389739abf71c9ece2d1b4', 'source_sha256': '62dc0cd30df67534f424fddc9706a0b50f9b22ea86bc5b3c6a005e8c57006606', 'byte_count': 3322}
V1_AFTER = {'git_blob_sha1': 'e8141712880fbae707ab96e02d5d7e0edb0f085f', 'source_sha256': 'bf90a865faa6302e5d70bd36bcaea0d602bb500acd96274bf8932b5cd6ee4374', 'byte_count': 5343}
AFTER = {'git_blob_sha1': '7bdf0e33758f29e463a1a2a754314c6f9ac7d965', 'source_sha256': '840a284abd7802f14cc438f3e93b21f29cba26971a5fe0f3214f981db2aec899', 'byte_count': 5642}
POLICY_ID = 'ATHENA_P4_TESTS_EIGHT_SHARD_BALANCE_MAINTENANCE_V1'
IDENTITY_KEYS = ('git_blob_sha1', 'source_sha256')


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical({k: v for k, v in value.items()
                                     if k != 'canonical_sha256'})).hexdigest()


def identity(raw):
    return {'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'byte_count': len(raw)}


def read_blob(path):
    """Regular tracked bytes with no linked ancestor; safe CRLF materialization."""
    logical = Path(path)
    if logical.is_absolute() or logical.as_posix() != path or '..' in logical.parts:
        raise ValueError('Tests successor evidence path is not exact')
    target = ROOT / logical
    for node in (*reversed(target.parents), target):
        status = node.lstat()
        regular = stat.S_ISREG(status.st_mode) if node == target else stat.S_ISDIR(status.st_mode)
        if (not regular or stat.S_ISLNK(status.st_mode)
                or getattr(status, 'st_file_attributes', 0) & 0x400):
            raise ValueError('Tests successor linked/nonregular evidence: ' + path)
    mode = subprocess.check_output(['git', 'ls-tree', 'HEAD', '--', path], cwd=ROOT)
    if (type(mode) is not bytes or len(mode.splitlines()) != 1
            or mode.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob']):
        raise ValueError('Tests successor evidence Git tree mode drift: ' + path)
    from runtime.source_identity import read_tracked_head_blob
    raw, _ = read_tracked_head_blob(ROOT, path)
    # Fixtures are LF Git objects even in a clean Windows CRLF worktree.
    return raw


def receipt():
    raw = read_blob(RECEIPT)
    value = json.loads(raw)
    if (canonical(value) != raw or value.get('canonical_sha256') != RECEIPT_SHA256
            or digest(value) != RECEIPT_SHA256):
        raise ValueError('Tests successor receipt identity drift')
    return value


def tree_entries():
    return subprocess.check_output(['git', 'ls-tree', 'HEAD:.github/workflows'], cwd=ROOT)


def tree_identity(entries, replacements=None):
    replacements = replacements or {}
    body = b''
    seen = set()
    for line in entries.splitlines():
        header, name = line.split(b'\t', 1)
        mode, kind, blob = header.split()
        text = name.decode('utf-8')
        if text in replacements:
            if mode != b'100644' or kind != b'blob':
                raise ValueError('Tests successor workflow tree mode drift')
            blob = replacements[text].encode('ascii')
            seen.add(text)
        body += mode + b' ' + name + b'\0' + bytes.fromhex(blob.decode('ascii'))
    if seen != set(replacements):
        raise ValueError('Tests successor workflow tree is missing an exact path')
    return hashlib.sha1(b'tree ' + str(len(body)).encode() + b'\0' + body).hexdigest()


def expected_workflow(value=None, *, expected_identity=None):
    value = receipt() if value is None else value
    expected_identity = AFTER if expected_identity is None else expected_identity
    before = read_blob(FIXTURE)
    if identity(before) != BEFORE:
        raise ValueError('Tests successor predecessor workflow drift')
    old, new = value['selection_before'].encode(), value['selection_after'].encode()
    if before.count(old) != 1:
        raise ValueError('Tests successor selection predecessor seam drift')
    expected = before.replace(old, new)
    if identity(expected) != expected_identity:
        raise ValueError('Tests successor recipe exceeds the exact reviewed partition')
    return expected


def predecessor_source(path, raw):
    """Restore one pinned source edge only; unknown paths/bytes gain no alias."""
    from scripts import audit_phase_a_b4_test_source_successor as test_source
    raw = test_source.predecessor_source(path, raw)
    row = receipt()['source_forward'].get(path)
    if row is None:
        return raw
    if identity(raw) != row['after']:
        raise ValueError('Tests successor restoration current source drift: ' + path)
    before = read_blob(row['fixture'])
    if identity(before) != row['before']:
        raise ValueError('Tests successor source predecessor drift: ' + path)
    expected = before
    for old, new in row['patches']:
        if expected.count(old.encode()) != 1:
            raise ValueError('Tests successor source recipe seam drift: ' + path)
        expected = expected.replace(old.encode(), new.encode())
    if raw != expected:
        raise ValueError('Tests successor source exceeds its exact recipe: ' + path)
    return before


def _authenticate_v1_prefix():
    """Authenticate the published V1 transition after V2 proves its predecessor."""
    value = receipt()
    if (value['policy_id'] != POLICY_ID or value['workflow_path'] != WORKFLOW
            or value['authority_granted'] is not False
            or value['historical_bytes_changed'] is not False
            or value['required_contexts_changed'] is not False
            or type(value['shard_count']) is not int or value['shard_count'] != 8
            or value['workflow_before'] != BEFORE or value['workflow_after'] != V1_AFTER
            or value['workflow_tree_before_sha1'] != BEFORE_TREE
            or value['workflow_tree_after_sha1'] != V1_AFTER_TREE
            or value['b4_projected_before_sha1'] != BEFORE_B4_TREE
            or value['b4_projected_after_sha1'] != V1_AFTER_B4_TREE):
        raise ValueError('Tests V1 predecessor receipt scope or authority drift')
    # The V2 adapter proves this exact V1 source before any historical use.
    v1_workflow = read_blob(V2_FIXTURE)
    if (identity(v1_workflow) != V1_AFTER
            or v1_workflow != expected_workflow(value, expected_identity=V1_AFTER)):
        raise ValueError('Tests V2 predecessor is not the exact published V1 workflow')
    entries = []
    replaced = 0
    for line in tree_entries().splitlines():
        header, name = line.split(b'\t', 1)
        if name == b'tests.yml':
            mode, kind, _blob = header.split()
            if mode != b'100644' or kind != b'blob':
                raise ValueError('Tests V1 workflow predecessor mode drift')
            header = mode + b' ' + kind + b' ' + V1_AFTER['git_blob_sha1'].encode('ascii')
            replaced += 1
        entries.append(header + b'\t' + name + b'\n')
    v1_entries = b''.join(entries)
    if (replaced != 1 or tree_identity(v1_entries) != V1_AFTER_TREE
            or tree_identity(v1_entries, {'tests.yml': BEFORE['git_blob_sha1']}) != BEFORE_TREE):
        raise ValueError('Tests V1 workflow tree is not the exact authenticated predecessor')
    for path in value['source_forward']:
        predecessor_source(path, read_blob(path))
    for path, expected in value['added_python_sources'].items():
        current = read_blob(path)
        from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
        historical = pass_a._tests_shard_v2_predecessor_source(path, current)
        if identity(historical) != expected:
            raise ValueError('Tests V1 regression source drift: ' + path)
    prior_path = value['prior_snapshot']['path']
    prior = json.loads(read_blob(prior_path))
    snapshot_raw = read_blob(SNAPSHOT)
    current = json.loads(snapshot_raw)
    if canonical(current) != snapshot_raw:
        raise ValueError('Tests V1 snapshot bytes are not canonical')
    if (digest(prior) != value['prior_snapshot']['canonical_sha256']
            or digest(prior) != prior['canonical_sha256']
            or digest(current) != current['canonical_sha256']
            or current['canonical_sha256'] != value['workflow_evolution_ledger_sha256']
            or current['transitions'][:-1] != prior['transitions']
            or {k: current['transitions'][-1]['after'].get(k) for k in IDENTITY_KEYS}
                != {k: V1_AFTER[k] for k in IDENTITY_KEYS}
            or current['current_workflow_tree_sha1'] != V1_AFTER_TREE):
        raise ValueError('Tests V1 P4 immutable prefix/snapshot drift')
    exempt = {'transitions', 'current_workflow_tree_sha1', 'canonical_sha256'}
    if {k: v for k, v in current.items() if k not in exempt} != {
            k: v for k, v in prior.items() if k not in exempt}:
        raise ValueError('Tests V1 successor changed a historical P4 checkpoint')
    return value


def authenticate():
    """Authenticate the current V2 assignment and its immutable V1/P4 prefix."""
    from scripts import audit_phase_a_pass_a_tests_source_successor as pass_a
    value = pass_a._tests_shard_v2_receipt()
    expected_keys = {
        'active_inventory_predecessor', 'authority_granted', 'base_main_sha',
        'b4_projected_after_sha1', 'b4_projected_before_sha1',
        'canonical_sha256', 'historical_bytes_changed', 'policy_id',
        'prior_snapshot', 'required_contexts_changed', 'reviewed_workflow_transition',
        'schema_version', 'selection_after', 'selection_before', 'shard_count',
        'source_authority_changed', 'source_commit', 'source_forward',
        'test_membership', 'timing_evidence', 'workflow_after', 'workflow_before', 'workflow_path',
        'workflow_predecessor_fixture', 'workflow_tree_after_sha1',
        'workflow_tree_before_sha1', 'workflow_evolution_ledger_sha256',
    }
    if (set(value) != expected_keys
            or value.get('policy_id') != 'ATHENA_P4_TESTS_EIGHT_SHARD_BALANCE_MAINTENANCE_V2'
            or value.get('schema_version') != 1
            or value.get('base_main_sha') != '016ae05b9f0fcc6991a5b7f28bdfea3688185729'
            or value.get('workflow_predecessor_fixture') != V2_FIXTURE
            or value.get('test_membership') != 'ALL_DISCOVERED_TEST_FILES_EXACTLY_ONCE'
            or type(value.get('timing_evidence')) is not dict
            or value['timing_evidence'].get('run_id') != 40086219683
            or value['timing_evidence'].get('head_sha') != '8b346a672788b26cf73338c1d30d13c52b36ec92'
            or value.get('authority_granted') is not False
            or value.get('historical_bytes_changed') is not False
            or value.get('required_contexts_changed') is not False
            or value.get('source_authority_changed') is not False
            or value.get('active_inventory_predecessor') != {
                'generation': 364,
                'canonical_sha256': '2c3cb36bfb92cd0a06a11862a9ce514683ebf01f44b999583701850f3151045d',
                'rewritten': False,
            }
            or value.get('workflow_path') != WORKFLOW
            or value.get('workflow_before') != V1_AFTER
            or value.get('workflow_tree_before_sha1') != V1_AFTER_TREE
            or value.get('b4_projected_before_sha1') != V1_AFTER_B4_TREE
            or value.get('workflow_after') != AFTER
            or value.get('workflow_tree_after_sha1') != AFTER_TREE
            or value.get('b4_projected_after_sha1') != AFTER_B4_TREE
            or type(value.get('shard_count')) is not int or value['shard_count'] != 8):
        raise ValueError('Tests V2 successor scope or authority drift')
    v1 = _authenticate_v1_prefix()
    before = read_blob(V2_FIXTURE)
    current_workflow = read_blob(WORKFLOW)
    old_selection = value.get('selection_before')
    new_selection = value.get('selection_after')
    if (type(old_selection) is not str or type(new_selection) is not str
            or not old_selection or not new_selection or before.count(old_selection.encode()) != 1):
        raise ValueError('Tests V2 exact assignment replacement is not unique')
    expected = before.replace(old_selection.encode(), new_selection.encode())
    if (identity(before) != V1_AFTER or identity(expected) != AFTER
            or current_workflow != expected):
        raise ValueError('Tests V2 workflow exceeds the exact V1 assignment successor')
    entries = tree_entries()
    if (tree_identity(entries) != AFTER_TREE
            or tree_identity(entries, {'tests.yml': V1_AFTER['git_blob_sha1']}) != V1_AFTER_TREE
            or subprocess.check_output(['git', 'diff', '--name-only', 'HEAD', '--', '.github/workflows'], cwd=ROOT).strip()):
        raise ValueError('Tests V2 is not the exact one-path workflow tree successor')
    source_forward = value.get('source_forward')
    if (type(source_forward) is not dict
            or set(source_forward) != pass_a.TESTS_SHARD_V2_SOURCE_PATHS
            or source_forward['scripts/audit_tests_shard_balance_successor.py'].get('fixture')
                != V2_SOURCE_FIXTURE
            or source_forward['tests/test_tests_shard_balance_successor.py'].get('fixture')
                != V2_TEST_FIXTURE):
        raise ValueError('Tests V2 source-forward path set drift')
    for path in pass_a.TESTS_SHARD_V2_SOURCE_PATHS:
        row = source_forward[path]
        if pass_a._tests_shard_v2_predecessor_source(path, read_blob(path)) != read_blob(row['fixture']):
            raise ValueError('Tests V2 source predecessor mismatch: ' + path)
    if (value.get('source_commit') != '8b346a672788b26cf73338c1d30d13c52b36ec92'
            or value.get('prior_snapshot') != {
            'path': SNAPSHOT, 'canonical_sha256': v1['workflow_evolution_ledger_sha256']}
            or value.get('authority_granted') is not False
            or value.get('historical_bytes_changed') is not False
            or value.get('required_contexts_changed') is not False
            or value.get('source_authority_changed') is not False):
        raise ValueError('Tests V2 prior snapshot or authority fields drift')
    prior = json.loads(read_blob(V1_SNAPSHOT))
    snapshot_raw = read_blob(V2_SNAPSHOT)
    snapshot = json.loads(snapshot_raw)
    if (canonical(snapshot) != snapshot_raw
            or digest(snapshot) != snapshot.get('canonical_sha256')
            or snapshot.get('canonical_sha256') != value.get('workflow_evolution_ledger_sha256')
            or snapshot.get('transitions', [])[:-1] != prior.get('transitions')
            or snapshot.get('current_workflow_tree_sha1') != AFTER_TREE):
        raise ValueError('Tests V2 P4 snapshot is not an append-only V1 extension')
    exempt = {'transitions', 'current_workflow_tree_sha1', 'canonical_sha256'}
    if {k: v for k, v in snapshot.items() if k not in exempt} != {
            k: v for k, v in prior.items() if k not in exempt}:
        raise ValueError('Tests V2 P4 snapshot changes an immutable checkpoint')
    transition = snapshot['transitions'][-1]
    reviewed = {k: v for k, v in transition.items() if k != 'evidence_body_sha256'}
    if reviewed != value.get('reviewed_workflow_transition'):
        raise ValueError('Tests V2 P4 transition differs from its receipt')
    from scripts import audit_p4_workflow_evolution_ledger as p4
    if (transition.get('evidence_body_sha256') != p4.receipt_evidence_body_sha256(value)
            or transition.get('workflow_path') != WORKFLOW
            or transition.get('maintenance_contract') != p4.TESTS_SHARD_BALANCE_CONTRACT):
        raise ValueError('Tests V2 P4 evidence or maintenance contract drift')
    evaluated = p4.apply_transitions(
        {WORKFLOW: {k: V1_AFTER[k] for k in IDENTITY_KEYS}}, [transition],
        frozen_baseline_paths={WORKFLOW}, baseline_families={WORKFLOW: 'TESTS'},
        evidence_receipts={V2_RECEIPT: value},
        historical_before_fixture_bytes={V2_FIXTURE: before})
    if evaluated != {WORKFLOW: {k: AFTER[k] for k in IDENTITY_KEYS}}:
        raise ValueError('Tests V2 P4 transition does not derive the exact workflow')
    return value


def previous_workflow_context(observed_tree):
    authenticate()
    if observed_tree != AFTER_TREE:
        raise ValueError('Tests successor current workflow tree drift')
    rows = []
    for line in tree_entries().splitlines():
        header, name = line.split(b'\t', 1)
        if name == b'tests.yml':
            mode, kind, _blob = header.split()
            header = mode + b' ' + kind + b' ' + BEFORE['git_blob_sha1'].encode()
        rows.append(header + b'\t' + name + b'\n')
    return BEFORE_TREE, b''.join(rows)


def project_tree(observed):
    if observed not in {AFTER_TREE, V1_AFTER_TREE}:
        return observed
    authenticate()
    return BEFORE_TREE


def project_b4_tree(observed):
    if observed not in {AFTER_B4_TREE, V1_AFTER_B4_TREE}:
        return observed
    authenticate()
    return BEFORE_B4_TREE


def previous_p4_context(observed, head_tree):
    if head_tree not in {AFTER_TREE, V1_AFTER_TREE}:
        return observed, head_tree
    authenticate()
    result = dict(observed)
    if WORKFLOW in result:
        expected = AFTER if head_tree == AFTER_TREE else V1_AFTER
        if result[WORKFLOW] != {k: expected[k] for k in IDENTITY_KEYS}:
            raise ValueError('Tests successor observed P4 workflow identity drift')
        result[WORKFLOW] = {k: BEFORE[k] for k in IDENTITY_KEYS}
    return result, BEFORE_TREE


def install_context(context):
    """Compose this source edge into existing exact historical inventory views.

    No builder/A2 import here: dependency direction is A2 -> retention -> this
    evidence-only adapter -> raw Git objects and the pure P4 evaluator.
    """
    value = receipt()
    current = authenticate()
    for path, row in value['source_forward'].items():
        context['BOOTSTRAP_AFTER'][path] = row['after']
        if path in context['HISTORICAL_PREDECESSORS']:
            context['HISTORICAL_PREDECESSORS'][path] = dict(
                context['HISTORICAL_PREDECESSORS'][path], after=row['after'])
    context['HISTORICAL_PREDECESSORS'][WORKFLOW] = {
        'fixture': FIXTURE, **BEFORE, 'after': AFTER}
    for path, row in current['source_forward'].items():
        context['BOOTSTRAP_AFTER'][path] = row['after']
        context['HISTORICAL_PREDECESSORS'][path] = {
            'fixture': row['fixture'], **row['before'], 'after': row['after']}
    metadata = {'artifacts/architecture/tests_shard_balance_successor_v1.json': {'git_blob_sha1': 'a99b67cea439809742a5c67226041f67cc9c2a02', 'source_sha256': '3e02e0d579c7e89ef6790d8f7d9ea55b1ed6ef0ed43e73372a96c7a7e0b292eb', 'byte_count': 12783}, 'artifacts/architecture/p4_workflow_evolution_snapshots/tests_shard_balance_v1.json': {'git_blob_sha1': '3e40bd6469fc1eab8f59834c6c3675a2a33a3b88', 'source_sha256': '16154d825f20648c5e1284b5b3bbfa190d8ead647df2d1143a7a6c0f12546c4c', 'byte_count': 24786}, 'tests/fixtures/architecture/revised_workflows/tests-pre-shard-balance-v1.yml': {'git_blob_sha1': 'a5eafa0afebc01abe02389739abf71c9ece2d1b4', 'source_sha256': '62dc0cd30df67534f424fddc9706a0b50f9b22ea86bc5b3c6a005e8c57006606', 'byte_count': 3322}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': 'e37cd985d456528fc2d14595bd3238fc0e442516', 'source_sha256': 'ebaf5bcb6caabe259a8e3375b41d589b7d4b94a49f69687d0c1f75cc40ba0204', 'byte_count': 58081}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_data_01c_restore_portability.py.before.txt': {'git_blob_sha1': '48088a35086ac8c15928fd2d6d0039adf47fbd87', 'source_sha256': '834d84ef290197283b74de48b65d20c68d57f7a7e3a0121a9b23bd58b5069b84', 'byte_count': 21506}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_p4_workflow_evolution_ledger.py.before.txt': {'git_blob_sha1': '5b808f4b915fac6146b21bce76dbb578b9fa5633', 'source_sha256': '0c99fd321dbcdc6f09ffce3c7e0d62be0580d12809da3270e0a1dc82692da4e6', 'byte_count': 68531}, 'tests/fixtures/architecture/tests_shard_balance_v1/scripts--audit_core_01d_retained_workflow_status_v3.py.before.txt': {'git_blob_sha1': '5c793bafd0e9b43bcebce213b67e808ecdb12803', 'source_sha256': '823b12aa6492eb03c881d161ce9e3c20f0f6239ff89c57cb1e18d2243ea46436', 'byte_count': 42468}}
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **metadata)
    v2_metadata = {
        V2_RECEIPT: identity(read_blob(V2_RECEIPT)),
        V2_SNAPSHOT: identity(read_blob(V2_SNAPSHOT)),
        V2_FIXTURE: identity(read_blob(V2_FIXTURE)),
    }
    for row in current['source_forward'].values():
        v2_metadata[row['fixture']] = row['before']
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **v2_metadata)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **v2_metadata)
    context['ADDED_PYTHON_PATHS'] |= frozenset({
        'scripts/audit_tests_shard_balance_successor.py',
        'tests/test_tests_shard_balance_successor.py'})
    added_python_identities = dict(context['ADDED_PYTHON_IDENTITIES'])
    added_python_identities.update(value['added_python_sources'])
    added_python_identities.update({path: row['after']
                                    for path, row in current['source_forward'].items()})
    context['ADDED_PYTHON_IDENTITIES'] = added_python_identities
