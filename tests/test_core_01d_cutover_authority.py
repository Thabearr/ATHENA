"""Closed PORT-02C context and real CORE-01D authority tamper regressions."""
import ast
import copy
import inspect
import json
import socket
import smtplib
import urllib.request

import pytest

from scripts import audit_p4_workflow_evolution_ledger as e
from scripts import audit_core_01d_scheduled_shadow_ownership as a


@pytest.fixture(autouse=True)
def deny_external_transport(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("CORE-01D live action forbidden")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    monkeypatch.setattr(smtplib, "SMTP_SSL", deny)
    from runtime import worker_launcher
    monkeypatch.setattr(worker_launcher, "_spawn_process", deny)
    from scripts.restore_athena_artifact_roles import GitHubTransport
    monkeypatch.setattr(GitHubTransport, "api", deny)


CONTEXTS = [
    (e.PORT02C_REPLAY_WORKFLOW_TREE_SHA1, "d1c8d79ac48bf0521a609e29991014513bd2f7afed2389c5e3a9d6ec8bfba8a2"),
    (e.CORE01B_WORKFLOW_TREE_SHA1, e.CORE01B_LEDGER_SHA256),
    (e.CORE01C_WORKFLOW_TREE_SHA1, e.CORE01C_LEDGER_SHA256),
    (e.CORE01D_WORKFLOW_TREE_SHA1, e.CORE01D_LEDGER_SHA256),
]


@pytest.mark.parametrize("tree,ledger", CONTEXTS)
def test_port02c_exact_historical_and_new_contexts(tree, ledger):
    p = e.PORT02C_REPLAY_WORKFLOW_PATH
    derived = {p: dict(e.PORT02C_REPLAY_WORKFLOW_BEFORE), "other": {"untouched": True}}
    observed = {p: dict(e.PORT02C_REPLAY_WORKFLOW_AFTER)}
    result = e._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)
    assert result[p] == e.PORT02C_REPLAY_WORKFLOW_AFTER
    assert result["other"] == derived["other"] and derived[p] == e.PORT02C_REPLAY_WORKFLOW_BEFORE


@pytest.mark.parametrize("mutation", ["tree", "ledger", "before_blob", "before_sha", "after_blob", "after_sha",
    "wrong_path", "count13", "predecessor_ledger", "predecessor_tree", "future"])
def test_port02c_closed_context_tamper_rejects(mutation):
    p = e.PORT02C_REPLAY_WORKFLOW_PATH
    derived = {p: dict(e.PORT02C_REPLAY_WORKFLOW_BEFORE)}
    observed = {p: dict(e.PORT02C_REPLAY_WORKFLOW_AFTER)}
    tree, ledger = CONTEXTS[-1]
    if mutation == "tree": tree = "0" * 40
    elif mutation == "ledger": ledger = "0" * 64
    elif mutation == "before_blob": derived[p]["git_blob_sha1"] = "0" * 40
    elif mutation == "before_sha": derived[p]["source_sha256"] = "0" * 64
    elif mutation == "after_blob": observed[p]["git_blob_sha1"] = "0" * 40
    elif mutation == "after_sha": observed[p]["source_sha256"] = "0" * 64
    elif mutation == "wrong_path": observed[".github/workflows/other.yml"] = observed.pop(p)
    elif mutation == "count13": tree = "1" * 40; ledger = "1" * 64; derived["transitions"] = [None] * 13
    elif mutation == "predecessor_ledger": ledger = e.CORE01C_LEDGER_SHA256
    elif mutation == "predecessor_tree": tree = e.CORE01C_WORKFLOW_TREE_SHA1
    else: tree = "2" * 40; ledger = "2" * 64
    with pytest.raises(e.WorkflowEvolutionError, match="exact PORT-02C"):
        e._port02c_current_source_forward(derived, observed, head_tree=tree, ledger_sha=ledger)


def test_port02c_four_closed_contexts_no_new_transition_source_unchanged():
    source = ast.parse(inspect.getsource(e._port02c_current_source_forward))
    values = next(n.value for n in ast.walk(source) if isinstance(n, ast.Assign) and
                  any(isinstance(t, ast.Name) and t.id == "reviewed_contexts" for t in n.targets))
    assert isinstance(values, ast.Set) and len(values.elts) == 4
    ledger = a.validate_evolution()
    assert len(ledger["transitions"]) == 13
    assert e.source_identity(a.raw(e.PORT02C_REPLAY_WORKFLOW_PATH)) == e.PORT02C_REPLAY_WORKFLOW_AFTER


@pytest.mark.parametrize("path,before,after", [
    (a.CANONICAL, "--scheduled-shadow-create-share-code false", "--scheduled-shadow-create-share-code true"),
    (a.CANONICAL, "--scheduled-shadow-create-share-code false", ""),
    (a.CANONICAL, "    steps:\n", "    steps:\n      - run: python -m scripts.send_current_shadow_email\n"),
    (a.CANONICAL, '["main","shadow"]', '["main"]'),
    (a.CANONICAL, "current-shadow-all-market", "different-shadow"),
    (a.CANONICAL, "-scheduled-shadow", "-shadow"),
    (a.LEGACY, "on:\n", 'on:\n  schedule:\n    - cron: "0 9 * * *"\n'),
    (a.LEGACY, "  workflow_dispatch:", "  removed_dispatch:"),
    (a.LEGACY, "  issue_comment:", "  removed_comment:"),
    (a.LEGACY, "== 276", "== 277"),
    (a.LEGACY, "github.repository_owner", "'other'"),
    (a.LEGACY, "python -m scripts.send_current_shadow_email", "true # removed email"),
    (a.LEGACY, "group: current-shadow-all-market", "group: different-shadow"),
])
def test_owner_policy_actual_workflow_tamper_rejects(monkeypatch, path, before, after):
    original = a.raw
    payload = original(path).decode()
    assert before in payload
    changed = payload.replace(before, after).encode()
    monkeypatch.setattr(a, "raw", lambda p: changed if str(p) == path else original(p))
    with pytest.raises(ValueError): a.validate_workflow_source()


@pytest.fixture(scope="module")
def evidence():
    ledger = json.loads(a.raw(e.LEDGER_PATH))
    receipts = {t["evidence_receipt_path"]: json.loads(a.raw(t["evidence_receipt_path"])) for t in ledger["transitions"]}
    snapshots = {t["checkpoint_snapshot_path"]: json.loads(a.raw(t["checkpoint_snapshot_path"])) for t in ledger["transitions"]}
    return ledger, receipts, snapshots


@pytest.mark.parametrize("index", [11, 12])
@pytest.mark.parametrize("field", [k for k, v in e.CORE01D_SCHEDULE_OWNER_CONTRACT.items() if type(v) is bool])
def test_maintenance_contract_every_boolean_is_exact(evidence, index, field):
    contract = copy.deepcopy(evidence[0]["transitions"][index]["maintenance_contract"])
    contract[field] = not contract[field]
    with pytest.raises(e.WorkflowEvolutionError): e._validate_maintenance_contract(contract)


@pytest.mark.parametrize("index", [11, 12])
@pytest.mark.parametrize("field,value", [("phase_id", "CORE-01C"), ("workflow_path", ".github/workflows/tests.yml"),
    ("canonical_family", "TESTS")])
def test_core01d_contract_reserved_exact_phase_path_family(evidence, index, field, value):
    ledger, receipts, _ = copy.deepcopy(evidence)
    transitions = ledger["transitions"]
    t = transitions[index]
    t[field] = value
    r = receipts[t["evidence_receipt_path"]]
    r["reviewed_workflow_transition"] = {k: v for k, v in t.items() if k != "evidence_body_sha256"}
    t["evidence_body_sha256"] = e.receipt_evidence_body_sha256(r)
    r["canonical_sha256"] = e.canonical_sha256(r)
    history = e.retirement.validate_retirement_history()
    matrix, _ = e.retirement.load_baseline()
    fixtures = {t["historical_before_fixture"]["path"]: a.raw(t["historical_before_fixture"]["path"])
                for t in transitions if t["operation"] == "MAINTENANCE_REVISE"}
    with pytest.raises(e.WorkflowEvolutionError):
        e.apply_transitions(e.baseline_state(history), transitions,
            frozen_baseline_paths=[r["workflow_path"] for r in matrix["workflow_rows"]], evidence_receipts=receipts,
            baseline_families={r["workflow_path"]: r["successor_family"] for r in matrix["workflow_rows"]},
            historical_before_fixture_bytes=fixtures)


@pytest.mark.parametrize("mutation", ["reorder", "prefix", "snapshot", "missing_receipt", "transition_receipt"])
def test_evolution_checkpoint_tamper_rejects(evidence, mutation):
    ledger, receipts, snapshots = copy.deepcopy(evidence)
    ts = ledger["transitions"]
    if mutation == "reorder": ts[-2:] = reversed(ts[-2:])
    elif mutation == "prefix": ts[0]["phase_id"] = "P4.4WRONG"
    elif mutation == "snapshot":
        snap = snapshots[ts[-1]["checkpoint_snapshot_path"]]
        snap["transitions"].pop(); snap["canonical_sha256"] = e.canonical_sha256(snap)
    elif mutation == "missing_receipt": receipts.pop(ts[-1]["evidence_receipt_path"])
    else:
        receipt = receipts[ts[-1]["evidence_receipt_path"]]
        receipt["reviewed_workflow_transition"]["phase_id"] = "CORE-01C"
        receipt["canonical_sha256"] = e.canonical_sha256(receipt)
    with pytest.raises(e.WorkflowEvolutionError):
        e.validate_transition_checkpoints(ts, ledger, receipts=receipts, snapshots=snapshots)


@pytest.mark.parametrize("mutation", ["delivery", "parity", "complete", "blocker", "count14", "port_transition"])
def test_receipt_policy_tamper_rehashed_rejects(monkeypatch, mutation):
    original = a.raw
    value = json.loads(original(a.RECEIPT_PATH))
    expected = copy.deepcopy(value)
    if mutation == "delivery": value["scheduled_shadow_create_share_code"] = True
    elif mutation == "parity": value["legacy_delivery_byte_or_intention_parity_claimed"] = True
    elif mutation == "complete": value["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "blocker": value["blockers"] = []
    elif mutation == "count14": value["evolution"]["transition_count_after"] = 14
    else: value["port02c_forward_context"]["new_port02c_transition"] = True
    a.predecessor.seal(value)
    monkeypatch.setattr(a, "expected_receipt", lambda: expected)
    monkeypatch.setattr(a, "raw", lambda p: a.predecessor.canonical(value) if p == a.RECEIPT_PATH else original(p))
    with pytest.raises(ValueError, match="unreviewed"): a.verified_receipt_path()


@pytest.mark.parametrize("mutation", ["complete", "blocker", "count", "schedule_lane", "delivery", "binding"])
def test_forward_checkpoint_tamper_rehashed_rejects(monkeypatch, mutation):
    original = a.raw
    schedule = json.loads(original(a.RECEIPT_PATH))
    matrix = json.loads(original(a.FORWARD_MATRIX))
    receipt = json.loads(original(a.FORWARD_RECEIPT))
    if mutation == "complete": receipt["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "blocker": receipt["remaining_blocker_ids"] = []
    elif mutation == "count": matrix["trigger_surface_count"] = 58
    elif mutation in {"schedule_lane", "delivery"}:
        row = next(r for r in matrix["workflow_rows"] if r["workflow_path"] == a.CANONICAL)
        surface = next(s for s in row["trigger_surfaces"] if s["trigger_kind"] == "schedule")
        if mutation == "schedule_lane": surface["schedule_lanes"].pop()
        else: surface["schedule_lanes"][1]["create_share_code"] = True
    else: receipt["schedule_ownership_receipt_sha256"] = "0" * 64
    a.predecessor.seal(matrix)
    receipt["workflow_matrix_sha256"] = matrix["canonical_sha256"]
    a.predecessor.seal(receipt)
    monkeypatch.setattr(a, "expected_receipt", lambda: schedule)
    monkeypatch.setattr(a, "raw", lambda p: a.predecessor.canonical(matrix) if p == a.FORWARD_MATRIX else
        a.predecessor.canonical(receipt) if p == a.FORWARD_RECEIPT else original(p))
    with pytest.raises(ValueError, match="forward Checkpoint-E"): a.audit_forward_checkpoint()


@pytest.mark.parametrize("index", range(11))
def test_every_historical_transition_is_immutable(evidence, index):
    from scripts.core_01d_historical_source import historical_bytes
    before = json.loads(historical_bytes(e.LEDGER_PATH.as_posix()))
    current = copy.deepcopy(evidence[0])
    current["transitions"][index]["phase_id"] = "P4.4UNREVIEWED"
    current["canonical_sha256"] = e.canonical_sha256(current)
    with pytest.raises(e.WorkflowEvolutionError, match="historical transition"):
        e.validate_evolution_snapshot_extension(before, current)


def test_historical_prefix_bytes_and_two_exact_new_snapshots(evidence):
    from scripts.core_01d_historical_source import historical_bytes
    ledger, receipts, snapshots = evidence
    before = json.loads(historical_bytes(e.LEDGER_PATH.as_posix()))
    prefix = e.canonical_json_bytes(before["transitions"]).strip()[:-1]
    assert b'"transitions":' + prefix + b"," in a.raw(e.LEDGER_PATH)
    for index in (11, 12):
        t = ledger["transitions"][index]
        snapshot = snapshots[t["checkpoint_snapshot_path"]]
        receipt = receipts[t["evidence_receipt_path"]]
        assert snapshot["transitions"] == ledger["transitions"][:index + 1]
        assert receipt["reviewed_workflow_transition"] == {k: v for k, v in t.items() if k != "evidence_body_sha256"}
        assert receipt["workflow_evolution_ledger_sha256"] == snapshot["canonical_sha256"]
        assert e.source_identity(a.raw(t["historical_before_fixture"]["path"])) == t["before"]


def test_deleting_legacy_email_step_entirely_rejects(monkeypatch):
    original = a.raw
    doc = a.yaml.load(original(a.LEGACY), Loader=a.yaml.BaseLoader)
    steps = doc["jobs"]["current-shadow-all-market"]["steps"]
    steps[:] = [s for s in steps if s["name"] != "Email durable Shadow result when configured"]
    changed = a.yaml.safe_dump(doc).encode()
    monkeypatch.setattr(a, "raw", lambda p: changed if p == a.LEGACY else original(p))
    with pytest.raises(ValueError, match="legacy change"): a.validate_workflow_source()
