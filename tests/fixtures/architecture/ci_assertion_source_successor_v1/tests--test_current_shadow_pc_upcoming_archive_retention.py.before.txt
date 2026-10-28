"""Offline runtime-writer fixtures, never real provider captures or authority."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
import yaml

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from scripts import verify_current_shadow_pc_upcoming_archive as archive
from scripts import audit_phase_a_pc_upcoming_retention_successor as successor
from tests.test_inc_20261010_pc_upcoming_bounded_epoch_stabilization import (
    _install_pages, _drift,
)


def _build(tmp_path, monkeypatch, *, partial=False, failed_epoch=False):
    repository = tmp_path / 'repo'
    repository.mkdir(parents=True)
    pages = [(i + 1, 531, range(i * 100 + 1, min((i + 1) * 100 + 1, 532)))
             for i in range(6)]
    if partial:
        pages = [(1, 531, range(1, 101)), (2, 531, range(101, 201))]
    elif failed_epoch:
        pages = _drift(10000) + pages
    requested = _install_pages(monkeypatch, pages)
    if partial:
        # Real parse-failure journal; failed bytes retained BEFORE source parse.
        prior = source._fetch_page
        def fetch(page, nonce, **kwargs):
            if page == 2:
                from datetime import datetime, timezone
                return b'{malformed', datetime.fromtimestamp(nonce / 1000, timezone.utc)
            return prior(page, nonce, **kwargs)
        monkeypatch.setattr(source, '_fetch_page', fetch)
    monkeypatch.setattr(runtime.time, 'sleep', lambda seconds: None)
    if partial:
        with pytest.raises(runtime.PcUpcomingRuntimeReconciliationError):
            runtime.capture_current_pc_upcoming_discovery(repository_root=repository, execute_live_network=True)
        manifest = None
    else:
        _, manifest = runtime.capture_current_pc_upcoming_discovery(
            repository_root=repository, execute_live_network=True)
        assert requested == ([1, 2] if failed_epoch else []) + list(range(1, 7))
    # Prove the unmodified source is valid BEFORE any adversarial mutation.
    state = runtime.verify_runtime_capture_stabilization(repository_root=repository)
    assert (state['accepted_attempt_index'] is None) is partial
    original = repository / source.EVIDENCE_ROOT
    output = repository / archive.OUTPUT
    preserved = output / 'source-evidence' / source.EVIDENCE_ROOT.name
    preserved.parent.mkdir(parents=True)
    shutil.copytree(original, preserved)
    summary = {} if partial else {
        'provider_discovery_manifest_sha256': manifest.canonical_sha256,
        'provider_discovery_page_count': 6,
        'provider_discovery_event_count': 531,
        'provider_discovery_observation_count': 6,
        'provider_discovery_pagination_complete': True,
        'provider_discovery_source_method': runtime.DISCOVERY_SOURCE_METHOD,
        'provider_discovery_strategy_id': runtime.CURRENT_SHADOW_UPCOMING_POLICY_ID,
        'provider_total_num': 531,
        'provider_event_count': 531,
        'provider_discovery_first_observed_at': manifest.first_observed_at.isoformat().replace('+00:00', 'Z'),
        'provider_discovery_last_observed_at': manifest.last_observed_at.isoformat().replace('+00:00', 'Z'),
    }
    receipt = output / 'current-shadow-all-market-run-receipt.json'
    receipt.write_text(json.dumps({'source_summary': summary}), encoding='utf-8')
    expected = 'VERIFIED_PARTIAL_CAPTURE' if partial else 'VERIFIED_COMPLETE'
    assert archive.verify_archive(repository_root=repository, output_root=output)['status'] == expected
    return repository, output, original, preserved, receipt


def _snapshot(repository):
    return {p.relative_to(repository).as_posix(): p.read_bytes()
            for p in repository.rglob('*') if p.is_file()}


@pytest.mark.parametrize('failed_epoch', [False, True])
def test_real_six_page_531_event_runtime_capture_and_uploaded_zip_replay(tmp_path, monkeypatch, failed_epoch):
    repo, out, original, preserved, _ = _build(tmp_path, monkeypatch, failed_epoch=failed_epoch)
    before = _snapshot(repo)
    first = archive.verify_archive(repository_root=repo, output_root=out)
    assert archive.verify_archive(repository_root=repo, output_root=out) == first
    assert first['status'] == 'VERIFIED_COMPLETE'
    assert _snapshot(repo) == before
    assert archive._file_inventory(original) == archive._file_inventory(preserved)
    # Actual ZIP content, not just a directory assertion. Hosted uploader proof
    # is still a separate qualification gate; this is an offline archive test.
    zip_path = tmp_path / 'synthetic-artifact.zip'
    with zipfile.ZipFile(zip_path, 'w') as zipped:
        for p in out.rglob('*'):
            if p.is_file():
                zipped.write(p, p.relative_to(out))
    mirror = tmp_path / 'downloaded'
    shutil.copytree(repo, mirror)
    shutil.rmtree(mirror / archive.OUTPUT)
    with zipfile.ZipFile(zip_path) as zipped:
        zipped.extractall(mirror / archive.OUTPUT)
    assert archive.verify_archive(repository_root=mirror, output_root=mirror / archive.OUTPUT) == first


@pytest.mark.parametrize('relative', [
    'manifest.json', 'pages/page-001.raw.json', 'runtime-capture-stabilization.json',
    'runtime-attempts/attempt-001/attempt-receipt.json',
    'runtime-attempts/attempt-001/page-observations.json',
    'runtime-attempts/attempt-001/raw-response-observations.json',
    'runtime-attempts/attempt-001/raw-responses/page-001.raw.json',
])
@pytest.mark.parametrize('mutation', ['missing', 'tampered'])
def test_equal_source_archive_corruption_fails_source_owned_replay(tmp_path, monkeypatch, relative, mutation):
    repo, out, original, preserved, _ = _build(tmp_path, monkeypatch)
    for root in (original, preserved):
        path = root / relative
        if mutation == 'missing':
            path.unlink()
        else:
            path.write_bytes(b'{"wrong":true}')
    before = _snapshot(repo)
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=repo, output_root=out)
    assert _snapshot(repo) == before


@pytest.mark.parametrize('mutation', ['empty_attempts', 'orphan_raw', 'wrong_page', 'extra_epoch', 'hash', 'index', 'pagination'])
def test_epoch_inventory_and_canonical_ancestry_fail_closed(tmp_path, monkeypatch, mutation):
    repo, out, original, preserved, _ = _build(tmp_path, monkeypatch)
    for root in (original, preserved):
        attempt = root / 'runtime-attempts/attempt-001'
        if mutation == 'empty_attempts':
            shutil.rmtree(root / 'runtime-attempts'); (root / 'runtime-attempts').mkdir()
        elif mutation == 'orphan_raw':
            (attempt / 'raw-responses/orphan.raw.json').write_bytes(b'{}')
        elif mutation == 'wrong_page':
            shutil.copyfile(attempt / 'pages/page-001.raw.json', attempt / 'pages/page-007.raw.json')
        elif mutation == 'extra_epoch':
            shutil.copytree(attempt, root / 'runtime-attempts/attempt-002')
        else:
            path = root / 'runtime-capture-stabilization.json' if mutation == 'index' else attempt / ('manifest.json' if mutation == 'pagination' else 'attempt-receipt.json')
            doc = json.loads(path.read_bytes())
            if mutation == 'index': doc['accepted_attempt_index'] = 2
            elif mutation == 'pagination': doc['pagination_complete'] = False
            else: doc['canonical_sha256'] = '0' * 64
            path.write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=repo, output_root=out)


@pytest.mark.parametrize('key,value', [
    ('provider_discovery_manifest_sha256', None), ('provider_discovery_manifest_sha256', ''),
    ('provider_discovery_manifest_sha256', 'A' * 64),
    ('provider_discovery_page_count', True), ('provider_discovery_event_count', True),
    ('provider_discovery_observation_count', '6'), ('provider_discovery_event_count', '531'),
    ('provider_discovery_pagination_complete', 1), ('provider_discovery_page_count', 5),
    ('provider_discovery_strategy_id', 'OTHER'), ('provider_discovery_source_method', 'OTHER'),
])
def test_exact_typed_receipt_correspondence(tmp_path, monkeypatch, key, value):
    repo, out, _, _, receipt = _build(tmp_path, monkeypatch)
    doc = json.loads(receipt.read_bytes()); doc['source_summary'][key] = value
    receipt.write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=repo, output_root=out)


@pytest.mark.parametrize('summary', [
    {'provider_discovery_page_count': 6, 'provider_discovery_pagination_complete': True},
    {'provider_discovery_page_count': 0}, {'provider_discovery_manifest_sha256': None},
    {'provider_event_count': 531}, {'provider_discovery_source_method': runtime.DISCOVERY_SOURCE_METHOD},
    [], None,
])
def test_missing_source_with_any_claim_never_means_not_acquired(tmp_path, summary):
    out = tmp_path / archive.OUTPUT; out.mkdir(parents=True)
    (out / 'current-shadow-all-market-run-receipt.json').write_text(json.dumps({'source_summary': summary}))
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=tmp_path, output_root=out)


def test_source_not_started_is_explicit_noncomplete(tmp_path):
    out = tmp_path / archive.OUTPUT
    assert archive.verify_archive(repository_root=tmp_path, output_root=out) == {'status': 'NOT_ACQUIRED', 'file_count': 0}


def test_partial_failed_parse_keeps_exact_bytes_without_complete_claim(tmp_path, monkeypatch):
    repo, out, original, preserved, receipt = _build(tmp_path, monkeypatch, partial=True)
    before = _snapshot(repo)
    assert archive.verify_archive(repository_root=repo, output_root=out)['status'] == 'VERIFIED_PARTIAL_CAPTURE'
    assert _snapshot(repo) == before
    receipt.write_text(json.dumps({'source_summary': {'provider_discovery_page_count': 6}}))
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=repo, output_root=out)
    for root in (original, preserved):
        (root / 'runtime-attempts/attempt-001/raw-response-observations.json').unlink()
    receipt.write_text(json.dumps({'source_summary': {}}))
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=repo, output_root=out)


@pytest.mark.parametrize('relative', [
    '.', '.cache', source.EVIDENCE_ROOT.as_posix(), 'artifacts',
    'artifacts/current-shadow-all-market',
    'artifacts/current-shadow-all-market/source-evidence',
    'artifacts/current-shadow-all-market/source-evidence/' + source.EVIDENCE_ROOT.name,
    'artifacts/current-shadow-all-market/current-shadow-all-market-run-receipt.json',
    (source.EVIDENCE_ROOT / 'manifest.json').as_posix(),
    (source.EVIDENCE_ROOT / 'runtime-attempts/attempt-001/raw-response-observations.json').as_posix(),
    (source.EVIDENCE_ROOT / 'runtime-attempts/attempt-001/raw-responses/page-001.raw.json').as_posix(),
])
def test_linked_evidence_ancestors_and_files_rejected(tmp_path, monkeypatch, relative):
    repo, out, _, _, _ = _build(tmp_path, monkeypatch)
    path = repo / relative
    target = tmp_path / 'outside-evidence'
    path.rename(target)
    try:
        path.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip('OS account does not permit creation of symlinks')
    with pytest.raises(archive.PcUpcomingArchiveError, match='linked'):
        archive.verify_archive(repository_root=repo, output_root=out)


def test_preservation_failure_keeps_identity_and_durable_failure_diagnostic(tmp_path, monkeypatch):
    repo, out, original, preserved, _ = _build(tmp_path, monkeypatch)
    shutil.rmtree(preserved)
    identity = repo / '.cache/identity.json'; identity.write_bytes(b'{"retained":"identity"}')
    monkeypatch.setenv('ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH', str(identity))
    # A regular file where a source directory is expected causes a real error.
    shutil.rmtree(original); original.write_bytes(b'not a directory')
    assert archive.main(['--repository-root', str(repo), '--output-root', str(out), '--preserve']) == 2
    assert (out / 'identity-state/identity.json').read_bytes() == identity.read_bytes()
    assert archive.main(['--repository-root', str(repo), '--output-root', str(out)]) == 2
    assert json.loads((out / archive.DIAGNOSTIC).read_bytes())['status'] == 'FAILED'
    workflow = yaml.load(Path(successor.WORKFLOW).read_text(), Loader=yaml.BaseLoader)
    steps = next(job['steps'] for job in workflow['jobs'].values()
                 if any(step.get('id') == 'preserve_shadow_evidence' for step in job.get('steps', [])))
    verify = next(s for s in steps if s.get('id') == 'verify_shadow_archive')
    upload = next(s for s in steps if s.get('uses') == 'actions/upload-artifact@v4')
    email = next(s for s in steps if s.get('name', '').startswith('Email durable'))
    assert verify['if'] == upload['if'] == 'always()'
    assert steps.index(verify) < steps.index(upload)
    assert 'steps.verify_shadow_archive.outcome' in email['if']
    assert 'steps.preserve_shadow_evidence.outcome' in email['if']
    assert 'continue-on-error' not in verify
    assert upload['with']['name'] == 'current-shadow-all-market-request'
    assert upload['with']['retention-days'] == '30'


def test_path_exact_successor_and_frozen_prefix():
    receipt = successor.authenticate()
    assert receipt['unresolved_disposition'] == 'UNKNOWN_PROVENANCE'
    assert successor.project_b4_tree(successor.AFTER_B4_TREE) == successor.BEFORE_B4_TREE
    from scripts import audit_data_01c_restore_portability as d5
    from scripts import audit_p4_workflow_evolution_ledger as p4
    d5.authenticate_workflow()
    p4.validate_current_state()


@pytest.mark.parametrize('mutation', ['timeout-minutes:', 'permissions:', 'concurrency:', 'workflow_dispatch:', 'execute_current_shadow_request', 'send_current_shadow_email', 'upload-artifact@v4'])
def test_successor_does_not_allow_authority_or_behavior_neighbor_edits(monkeypatch, mutation):
    raw = successor.expected_workflow()
    assert mutation.encode() in raw
    read = successor._read
    monkeypatch.setattr(successor, '_read', lambda path: raw.replace(mutation.encode(), b'UNREVIEWED', 1) if path == successor.WORKFLOW else read(path))
    with pytest.raises(ValueError, match='path-exact'):
        successor.authenticate()


def test_successor_rejects_unrelated_tree(monkeypatch):
    monkeypatch.setattr(successor.subprocess, 'check_output', lambda *args, **kwargs: '0' * 40)
    with pytest.raises(ValueError, match='tree'):
        successor.authenticate()


@pytest.mark.parametrize("raw", [
    b'{"source_summary":{"provider_discovery_page_count":6},"source_summary":{}}',
    b'{"source_summary":{"nested":{"provider_discovery_page_count":6}}}',
    b'{"status":"RESEARCH_SHADOW_PORTFOLIO_READY","source_summary":{}}',
])
def test_hidden_or_success_claims_cannot_be_downgraded_to_not_acquired(tmp_path, raw):
    out = tmp_path / archive.OUTPUT
    out.mkdir(parents=True)
    (out / 'current-shadow-all-market-run-receipt.json').write_bytes(raw)
    with pytest.raises(archive.PcUpcomingArchiveError):
        archive.verify_archive(repository_root=tmp_path, output_root=out)


@pytest.mark.parametrize("container", ["mapping", "list"])
def test_nested_reconciliation_claims_match_the_accepted_source(tmp_path, monkeypatch, container):
    repo, out, _, _, receipt = _build(tmp_path, monkeypatch)
    doc = json.loads(receipt.read_bytes())
    doc['source_summary']['current_reconciliation_by_request_date'] = {
        '20261022': {'provider_discovery_manifest_sha256': '0' * 64}}
    if container == 'list':
        doc['source_summary']['current_reconciliation_by_request_date'] = [
            doc['source_summary']['current_reconciliation_by_request_date']]
    receipt.write_text(json.dumps(doc))
    with pytest.raises(archive.PcUpcomingArchiveError, match='nested'):
        archive.verify_archive(repository_root=repo, output_root=out)


@pytest.mark.parametrize('mutation', ['omitted', 'changed'])
def test_archive_only_corruption_cannot_borrow_valid_original_replay(tmp_path, monkeypatch, mutation):
    repo, out, original, preserved, _ = _build(tmp_path, monkeypatch)
    path = preserved / 'runtime-attempts/attempt-001/raw-responses/page-001.raw.json'
    before = archive._file_inventory(original)
    if mutation == 'omitted':
        path.unlink()
    else:
        path.write_bytes(b'archive-only corruption')
    with pytest.raises(archive.PcUpcomingArchiveError, match='byte-inconsistent'):
        archive.verify_archive(repository_root=repo, output_root=out)
    assert archive._file_inventory(original) == before


@pytest.mark.parametrize('which', ['predecessor', 'current'])
def test_exact_b4_consumer_forward_rejects_source_identity_drift(monkeypatch, which):
    read = successor._read
    path = successor.B4_FORWARD_FIXTURE if which == 'predecessor' else successor.B4_FORWARD_SOURCE
    monkeypatch.setattr(successor, '_read', lambda name: read(name) + b'\n# unreviewed drift\n' if name == path else read(name))
    with pytest.raises(ValueError, match='B4 consumer source-forward'):
        successor.authenticate()


def test_historical_projection_is_exact_idempotent_and_keeps_unknown_rows():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    latest = a2.authenticate_inventory()
    raw = subprocess.check_output(['git', 'ls-tree', '-r', 'HEAD'])
    projected = successor.project_retention_inventory(raw, latest=latest)
    assert successor.project_retention_inventory(projected, latest=latest) == projected
    rows = {line.split(b'\t', 1)[1].decode(): line.split(b'\t', 1)[0]
            for line in projected.splitlines()}
    assert not set(successor.ADDED_METADATA) & set(rows)
    assert not successor.ADDED_PYTHON_PATHS & set(rows)
    for path, descriptor in successor.HISTORICAL_PREDECESSORS.items():
        if path in successor.ADDED_PYTHON_PATHS:
            assert path not in rows
        else:
            assert rows[path].split()[-1].decode() == descriptor['git_blob_sha1']
    extra = b'100644 blob ' + b'0' * 40 + b'\truntime/unapproved-neighbor.py\n'
    assert successor.project_retention_inventory(raw + extra, latest=latest).endswith(extra)


def test_retention_historical_views_preserve_frozen_producer_and_inventory():
    from scripts import core_01d_historical_source as historical
    from scripts import audit_core_01d_authority_reachability_review_a as review
    from scripts import audit_core_01d_scheduled_shadow_ownership as schedule
    _, identity = historical.historical_tracked(successor.ROOT, successor.WORKFLOW)
    assert identity.git_blob_sha1 == historical.identities()[successor.WORKFLOW]['git_blob_sha1']
    schedule.validate_workflow_source()
    frozen = review.authenticate_inventory()
    assert frozen['canonical_sha256'] == review.INVENTORY_SHA


def test_historical_projection_requires_exact_reviewed_after_bytes(monkeypatch):
    """A matching self-described source row cannot authorize an arbitrary edit."""
    from dataclasses import replace
    import hashlib
    from copy import deepcopy
    from runtime import source_identity
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    latest = deepcopy(a2.authenticate_inventory())
    target = 'scripts/audit_core_01d_scheduled_shadow_ownership.py'
    original = source_identity.read_tracked_head_blob
    payload, observed = original(successor.ROOT, target)
    changed = payload + b'\n# unreviewed successor\n'
    blob = hashlib.sha1(b'blob ' + str(len(changed)).encode() + b'\0' + changed).hexdigest()
    changed_identity = replace(observed, git_blob_sha1=blob,
                               git_blob_payload_sha256=hashlib.sha256(changed).hexdigest())
    for row in latest['source_identities']:
        if row['path'] == target:
            row['lf_source_sha256'] = hashlib.sha256(changed).hexdigest()
    monkeypatch.setattr(source_identity, 'read_tracked_head_blob',
        lambda root, path, **kwargs: (changed, changed_identity) if path == target else original(root, path, **kwargs))
    raw = subprocess.check_output(['git', 'ls-tree', '-r', 'HEAD'])
    with pytest.raises(ValueError, match='exact reviewed retention successor|bootstrap successor current source identity drift'):
        successor.project_retention_inventory(raw, latest=latest)


@pytest.mark.parametrize('original_auditor', [False, True, 'prior'])
def test_bootstrap_accepts_only_current_successor_or_preserved_original(monkeypatch, original_auditor):
    import runpy
    import offline_transport
    read = Path.read_bytes
    auditor = successor.BOOTSTRAP_AUDITOR
    original = successor._read(successor.HISTORICAL_PREDECESSORS[auditor]['fixture'])
    if original_auditor == 'prior':
        original = successor._raw_blob(successor._CURRENT_INTEGRATION['prior_admitted_auditor_fixture'])
    if original_auditor:
        monkeypatch.setattr(Path, 'read_bytes', lambda p: original if p == successor.ROOT / auditor else read(p))
    installed = []
    monkeypatch.setattr(offline_transport, 'install', lambda: installed.append(True))
    monkeypatch.setattr(sys, 'orig_argv', ['python', '-m', 'pytest'])
    runpy.run_path(str(successor.ROOT / 'sitecustomize.py'))
    assert installed == [True]


@pytest.mark.parametrize('logical', [
    'scripts/audit_core_01d_ci_offline_transport_boundary.py',
    'tests/_offline_bootstrap/sitecustomize.py', 'tests/conftest.py',
    'tests/offline_linux.py', 'tests/offline_transport.py',
])
def test_bootstrap_rejects_every_guard_drift_before_install(monkeypatch, logical):
    import runpy
    import offline_transport
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda p: b'# unreviewed replacement\n' if p == successor.ROOT / logical else read(p))
    installed = []
    monkeypatch.setattr(offline_transport, 'install', lambda: installed.append(True))
    monkeypatch.setattr(sys, 'orig_argv', ['python', '-m', 'pytest'])
    with pytest.raises(SystemExit, match='failed to activate'):
        runpy.run_path(str(successor.ROOT / 'sitecustomize.py'))
    assert installed == []


@pytest.mark.parametrize('mutation', ['successor_path', 'successor_hash', 'original_pin', 'deny_check'])
def test_bootstrap_source_recipe_rejects_neighboring_acceptance_changes(mutation):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    text = (successor.ROOT / 'sitecustomize.py').read_text()
    if mutation == 'successor_path':
        text = text.replace('ROOT_TEST_SOURCE_SUCCESSORS = {',
                            'ROOT_TEST_SOURCE_SUCCESSORS = {"tests/offline_transport.py": "' + '0' * 64 + '",')
    elif mutation == 'successor_hash':
        text = text.replace(successor.BOOTSTRAP_AFTER[successor.BOOTSTRAP_AUDITOR]['source_sha256'], '0' * 64)
    elif mutation == 'original_pin':
        text = text.replace('3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404', '0' * 64)
    else:
        text = text.replace('if _digest != _expected and _digest not in ROOT_TEST_SOURCE_SUCCESSORS.get(_path, ()):', 'if False:')
    with pytest.raises(ValueError, match='bootstrap successor'):
        successor.authenticate_bootstrap_successor(text, a2.source)


@pytest.mark.parametrize('logical', ['sitecustomize.py', 'scripts/audit_core_01d_ci_offline_transport_boundary.py'])
def test_bootstrap_predecessor_drift_is_not_resealed(monkeypatch, logical):
    read = successor._bootstrap_blob
    target = successor.BOOTSTRAP_PREDECESSORS[logical]['fixture']
    monkeypatch.setattr(successor, '_bootstrap_blob',
                        lambda p: read(p) + b'\n# changed predecessor\n' if p == target else read(p))
    with pytest.raises(ValueError, match='bootstrap predecessor'):
        successor.authenticate_bootstrap_sources()


def test_bootstrap_source_contract_retains_original_boundary_and_inventory():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    successor.authenticate_bootstrap_sources()
    assert a2.authenticate_activation_and_no_bypass() is True
    assert a2.authenticate_historical_activation_and_no_bypass() is True
    latest = a2.authenticate_inventory()
    assert latest['generation'] >= 348
    raw = subprocess.check_output(['git', 'ls-tree', '-r', 'HEAD'])
    projected = successor.project_retention_inventory(raw, latest=latest)
    rows = {row.split(b'\t', 1)[1].decode(): row.split(b'\t', 1)[0] for row in projected.splitlines()}
    for path in ('sitecustomize.py', 'tests/test_core_01d_ci_offline_transport_inventory_evolution.py'):
        assert rows[path].split()[-1].decode() == successor.BOOTSTRAP_PREDECESSORS[path]['git_blob_sha1']
    assert successor.project_retention_inventory(projected, latest=latest) == projected


def test_integrated_main_prefix_and_provisional_archive_are_distinct():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    prefix = successor.authenticate_main_prefix()
    archive_receipt = successor.authenticate_provisional_archive()
    assert prefix['main_commit'] == successor.MAIN_SHA
    assert prefix['latest_generation'] == 347
    assert archive_receipt['active_chain_member'] is False
    active = {path for _, path in a2.discover_inventory_generations()}
    assert not active & {row['archive_path'] for row in archive_receipt['files']}
    assert all(row['diverges_from_main'] for row in archive_receipt['files'])
    a2.authenticate_inventory()
    assert a2.read_generation(a2.inventory_generation_path(348))['predecessor_inventory']['canonical_sha256'] == prefix['latest_canonical_sha256']


@pytest.mark.parametrize('generation', [338, 339, 341, 347])
def test_integrated_prefix_rejects_missing_changed_or_provisional_row(monkeypatch, generation):
    read = successor._read
    target = f'tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v{generation}.json'
    manifest = successor._json(successor.ARCHIVE_MANIFEST, successor.ARCHIVE_MANIFEST_SHA256)
    replacement = next((row['archive_path'] for row in manifest['files'] if row['generation'] == generation), None)
    bad = successor._raw_blob(replacement) if replacement else b'{}\n'
    monkeypatch.setattr(successor, '_read', lambda p: bad if p == target else read(p))
    with pytest.raises(ValueError, match='main inventory prefix'):
        successor.authenticate_main_prefix()


@pytest.mark.parametrize('mutation', ['bytes', 'manifest_hash', 'archive_name', 'symlink'])
def test_integrated_archive_never_promotes_or_reseals_bad_evidence(monkeypatch, mutation):
    read = successor._raw_blob
    manifest = successor._json(successor.ARCHIVE_MANIFEST, successor.ARCHIVE_MANIFEST_SHA256)
    target = manifest['files'][0]['archive_path']
    if mutation == 'bytes':
        monkeypatch.setattr(successor, '_raw_blob', lambda p: read(p) + b' ' if p == target else read(p))
    elif mutation == 'manifest_hash':
        original = successor._read
        monkeypatch.setattr(successor, '_read', lambda p: b'{}' if p == successor.ARCHIVE_MANIFEST else original(p))
    elif mutation == 'archive_name':
        original = successor._json
        from copy import deepcopy
        malformed = deepcopy(manifest)
        malformed['files'][0]['archive_basename'] = 'canonical-v338.json'
        monkeypatch.setattr(successor, '_json', lambda p,h: malformed if p == successor.ARCHIVE_MANIFEST else original(p,h))
    else:
        original = Path.lstat
        import stat
        from types import SimpleNamespace
        monkeypatch.setattr(Path, 'lstat', lambda p: SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
                            if p == successor.ROOT / target else original(p))
    with pytest.raises(ValueError):
        successor.authenticate_provisional_archive()


def test_integrated_extension_rejects_wrong_canonical_main_anchor():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from copy import deepcopy
    chain = deepcopy(a2.load_inventory_generations())
    chain[346][1]['canonical_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='main inventory prefix'):
        successor.checkpoint_retention_extension(chain)



def test_integrated_auditor_rejects_forged_delegated_checkpoint_bytes(monkeypatch):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    before, current = successor.checkpoint_v2_retention_sources()
    kwargs = dict(fixture=False, expected_blob=successor.V313_CHECKPOINT_BLOB,
                  expected_lf=successor.V313_CHECKPOINT_SHA256, expected_size=len(before))
    assert a2._e3_source_forward_file_identity(successor.CHECKPOINT_V2_PATH, **kwargs) == before
    monkeypatch.setattr(successor, 'checkpoint_v2_retention_sources',
                        lambda: (before, current + b'\n# forged delegated successor\n'))
    with pytest.raises(AssertionError, match='retention current successor identity drift'):
        a2._e3_source_forward_file_identity(successor.CHECKPOINT_V2_PATH, **kwargs)
