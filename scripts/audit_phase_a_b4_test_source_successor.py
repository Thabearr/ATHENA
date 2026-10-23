"""Source-only successor for B4's stale live-tree test caller.

Pure core authentication reads fixed Git objects/recipes only. The public test
qualification additionally authenticates A2. No builder, workflow evaluator or
transport is called from the core, so bootstrap authentication stays acyclic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'tests/test_core_01d_sportybet_current_trigger_authority_b4.py'
FIXTURE = 'tests/fixtures/architecture/phase_a_b4_test_source_v1/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.before.txt'
RECEIPT = 'artifacts/architecture/phase_a_b4_test_source_successor_v1.json'
RECEIPT_SHA256 = '980e08ba133797e041649b246912b4a18c8729554c4031dd6c37bc2d88f99d78'
INVENTORY = 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v355.json'
PREDECESSOR_SHA256 = '98a3549dde3e6c83b1b91982d8088c42ac613b1b1b7ba6ae40ef947d3a66abc0'
BEFORE = {'git_blob_sha1': '1d32931152fcb1e364d7a7aab6d4dfbe42b27173', 'source_sha256': '231af6aaecaad3a749be0acf658b642c7a927f2e186ee380e1850c6099c9aea0', 'byte_count': 41376}
AFTER = {'git_blob_sha1': 'cf44d492960a2cd0a5f1f97bb49c9e1bd133a8f2', 'source_sha256': '6429f0833e7cefd993d64072707b5d36f3bbf4b64ede1120798cdf4879f85663', 'byte_count': 45554}
ADAPTER_EDGES = {'scripts/audit_phase_a_pc_upcoming_retention_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_b4_test_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt', 'before': {'git_blob_sha1': '2efde8f36b6cd37307fe4a5d8ef0f0b64b01a8f8', 'source_sha256': '5a4e224fa24515f0cb0c916c8fbbdc7b4689342737836448e9048fbf30c545b8', 'byte_count': 58898}, 'after': {'git_blob_sha1': '670ce275b1560994fe636000444f915512b713d0', 'source_sha256': '08caf995647681b16ddea8f561e5f02fa570e0751b00a1bf70c601ef9e6bb82a', 'byte_count': 59259}, 'append': "\n\n# Source-only correction of B4's stale caller; no verifier/workflow change.\nfrom scripts import audit_phase_a_b4_test_source_successor as _b4_test_source\n_b4_test_source.install_context(globals())\n_authenticate_before_b4_test_source = authenticate\n\n\ndef authenticate():\n    _b4_test_source.authenticate_core()\n    return _authenticate_before_b4_test_source()\n"}, 'scripts/audit_tests_shard_balance_successor.py': {'fixture': 'tests/fixtures/architecture/phase_a_b4_test_source_v1/scripts--audit_tests_shard_balance_successor.py.before.txt', 'before': {'git_blob_sha1': '6c260f656eb421b83baf6520101cc72dd49f2e68', 'source_sha256': '1ea3de1b3720d714168863827e9af6b34172a114c9e6743324f29b36849c0232', 'byte_count': 13894}, 'after': {'git_blob_sha1': '71978a5bc1de04150177a88c264bd2794d537bfd', 'source_sha256': 'deb74590ede28e2918ad860b71a4865bd8cd9ea04c1ef384bd2cca8a97cc98eb', 'byte_count': 14024}, 'replacement_before': "    row = receipt()['source_forward'].get(path)\n", 'replacement_after': "    from scripts import audit_phase_a_b4_test_source_successor as test_source\n    raw = test_source.predecessor_source(path, raw)\n    row = receipt()['source_forward'].get(path)\n"}}
METADATA = {'artifacts/architecture/phase_a_b4_test_source_successor_v1.json': {'git_blob_sha1': '564efc872215fd26a0621f34d64e1865029c0940', 'source_sha256': 'eca8254fdcd420a139ae33129021daca5256a7a4968030cba622641615a8c6e0', 'byte_count': 6243}, 'tests/fixtures/architecture/phase_a_b4_test_source_v1/tests--test_core_01d_sportybet_current_trigger_authority_b4.py.before.txt': {'git_blob_sha1': '1d32931152fcb1e364d7a7aab6d4dfbe42b27173', 'source_sha256': '231af6aaecaad3a749be0acf658b642c7a927f2e186ee380e1850c6099c9aea0', 'byte_count': 41376}, 'tests/fixtures/architecture/phase_a_b4_test_source_v1/scripts--audit_phase_a_pc_upcoming_retention_successor.py.before.txt': {'git_blob_sha1': '2efde8f36b6cd37307fe4a5d8ef0f0b64b01a8f8', 'source_sha256': '5a4e224fa24515f0cb0c916c8fbbdc7b4689342737836448e9048fbf30c545b8', 'byte_count': 58898}, 'tests/fixtures/architecture/phase_a_b4_test_source_v1/scripts--audit_tests_shard_balance_successor.py.before.txt': {'git_blob_sha1': '6c260f656eb421b83baf6520101cc72dd49f2e68', 'source_sha256': '1ea3de1b3720d714168863827e9af6b34172a114c9e6743324f29b36849c0232', 'byte_count': 13894}}


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def canonical_digest(value):
    return hashlib.sha256(canonical({k: v for k, v in value.items()
                                     if k != 'canonical_sha256'})).hexdigest()


def identity(raw):
    return {'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'byte_count': len(raw)}


def read_blob(path):
    logical = Path(path)
    if logical.is_absolute() or logical.as_posix() != path or '..' in logical.parts:
        raise ValueError('B4 test source evidence path drift')
    target = ROOT / logical
    for node in (*reversed(target.parents), target):
        status = node.lstat()
        regular = stat.S_ISREG(status.st_mode) if node == target else stat.S_ISDIR(status.st_mode)
        if (not regular or stat.S_ISLNK(status.st_mode)
                or getattr(status, 'st_file_attributes', 0) & 0x400
                or (node == target and getattr(status, 'st_nlink', 1) != 1)):
            raise ValueError('B4 test source evidence is linked or nonregular: ' + path)
    mode = subprocess.check_output(['git', 'ls-tree', 'HEAD', '--', path], cwd=ROOT)
    if (type(mode) is not bytes or len(mode.splitlines()) != 1
            or mode.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob']):
        raise ValueError('B4 test source evidence Git mode drift: ' + path)
    from runtime.source_identity import read_tracked_head_blob
    # The reader authenticates exact Git bytes and clean LF/CRLF worktree
    # materialization; no frozen fixture is normalized or rewritten on disk.
    raw, _ = read_tracked_head_blob(ROOT, path)
    return raw


def receipt():
    raw = read_blob(RECEIPT)
    value = json.loads(raw)
    if (raw != canonical(value) or canonical_digest(value) != RECEIPT_SHA256
            or value.get('canonical_sha256') != RECEIPT_SHA256
            or value.get('source_path') != SOURCE
            or value.get('predecessor_fixture') != FIXTURE
            or value.get('before') != BEFORE or value.get('after') != AFTER
            or any(value.get(key) is not False for key in (
                'authority_granted', 'workflow_changed', 'b4_verifier_changed',
                'historical_bytes_changed', 'live_tree_fence_weakened'))):
        raise ValueError('B4 test source successor receipt drift')
    return value


def predecessor_source(path, raw):
    """An exact new source may expose its own pinned previous view only."""
    value = receipt()
    if path == SOURCE:
        row = {'fixture': FIXTURE, 'before': BEFORE, 'after': AFTER,
               'replacement_before': value['replacement_before'],
               'replacement_after': value['replacement_after'],
               'append': value['append_after_unique_patch']}
    else:
        row = ADAPTER_EDGES.get(path)
    if row is None:
        return raw
    if identity(raw) != row['after']:
        raise ValueError('B4 test current source identity drift: ' + path)
    before = read_blob(row['fixture'])
    if identity(before) != row['before']:
        raise ValueError('B4 test predecessor source identity drift: ' + path)
    expected = before
    if 'replacement_before' in row:
        old, new = row['replacement_before'].encode(), row['replacement_after'].encode()
        if expected.count(old) != 1:
            raise ValueError('B4 test source recipe is not unique: ' + path)
        expected = expected.replace(old, new)
    expected += row.get('append', '').encode()
    if raw != expected:
        raise ValueError('B4 test source exceeds exact replacement/append recipe: ' + path)
    return before


def authenticate_core():
    """No A2/builder imports here: usable from A2's existing source context."""
    value = receipt()
    for path in (SOURCE, *ADAPTER_EDGES):
        predecessor_source(path, read_blob(path))
    for path, expected in METADATA.items():
        if identity(read_blob(path)) != expected:
            raise ValueError('B4 test source successor metadata drift: ' + path)
    return value


def verify_first_inventory(value):
    rows = [row for row in value.get('source_identities', []) if row.get('path') == SOURCE]
    if (type(value.get('generation')) is not int or value['generation'] != 355
            or canonical_digest(value) != value.get('canonical_sha256')
            or value.get('predecessor_inventory') != {
                'generation': 354,
                'path': 'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v354.json',
                'canonical_sha256': PREDECESSOR_SHA256, 'rewritten': False}
            or len(rows) != 1 or rows[0].get('lf_source_sha256') != AFTER['source_sha256']):
        raise ValueError('B4 test source A2 successor inventory drift')


def authenticate():
    """Public qualification: exact core AND the actual authenticated A2 corpus."""
    value = authenticate_core()
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    latest = a2.authenticate_inventory()
    verify_first_inventory(json.loads(read_blob(INVENTORY)))
    if (type(latest.get('generation')) is not int or latest['generation'] < 355
            or [row for row in latest['source_identities'] if row['path'] == SOURCE]
                != [{'path': SOURCE, 'lf_source_sha256': AFTER['source_sha256']}]):
        raise ValueError('B4 test current source is not authenticated by latest A2 inventory')
    return value


def install_context(context):
    """One named test successor plus exact adapters; old receipts stay pinned."""
    receipt()
    context['HISTORICAL_PREDECESSORS'][SOURCE] = dict(
        context['HISTORICAL_PREDECESSORS'][SOURCE], after=AFTER)
    context['BOOTSTRAP_AFTER'] = dict(context['BOOTSTRAP_AFTER'], **{
        SOURCE: AFTER, **{path: row['after'] for path, row in ADAPTER_EDGES.items()}})
    context['ADDED_METADATA'] = dict(context['ADDED_METADATA'], **METADATA)
    context['BOOTSTRAP_METADATA'] = dict(context['BOOTSTRAP_METADATA'], **METADATA)
    context['ADDED_PYTHON_PATHS'] |= frozenset({'scripts/audit_phase_a_b4_test_source_successor.py'})
