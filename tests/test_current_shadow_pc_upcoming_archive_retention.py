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


def test_nested_reconciliation_claims_match_the_accepted_source(tmp_path, monkeypatch):
    repo, out, _, _, receipt = _build(tmp_path, monkeypatch)
    doc = json.loads(receipt.read_bytes())
    doc['source_summary']['current_reconciliation_by_request_date'] = {
        '20261022': {'provider_discovery_manifest_sha256': '0' * 64}}
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
