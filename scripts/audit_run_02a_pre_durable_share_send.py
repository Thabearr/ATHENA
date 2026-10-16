"""Non-writing prerequisite source/evidence audit; no execution authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = "artifacts/product/run_02a_pre_durable_share_send_v1.json"
BASE = "4125624948deb314278004df5f13a627d31f8fd2"
V142_SHA = "ea45174c6c5d6203ee9fab78f589c87ea86000871e4dd8b746e172befdd62b56"
SOURCES = (
    "database/run_repository.py", "runtime/worker_entry.py",
    "scripts/sportybet_direct_share_bridge.py", "services/athena_job_service.py",
    "services/durable_share_code_transport.py", "scripts/audit_run_01b_worker_lifecycle.py",
    "scripts/audit_core_01d_checkpoint_e_completion_v2.py", "scripts/audit_checkpoint_e_workflows.py",
    "scripts/audit_core_01d_checkpoint_e_completion.py",
    "scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py",
    "scripts/audit_core_01d_exact_pr_trigger_disposition_b1.py",
    "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
    "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py",
    "scripts/audit_data_01c_app_store_complete.py",
    "scripts/audit_lg_a_worker_launch_failure_remediation.py",
    "scripts/audit_run_02a_pre_durable_share_send.py", "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
    "tests/test_lg_a_worker_entry_historical_projection.py",
    "tests/test_run_02a_pre_durable_share_send.py", "tests/native/test_run_02a_pre_share_send_publication.py",
)
HISTORY = {
    "artifacts/product/run_01a_durable_admission_v1.json": "de2222e7f1c472d7a336f8a4c9c7bec84c2e6ed533b8f568689a3857adaf4f71",
    "artifacts/product/run_01b_worker_lifecycle_v1.json": "e0e76d6fa375028ca4f248134ae61fb2717fd7333104ae8a696544931febc203",
}
TRANSPORT_PREDECESSORS = {
    "scripts/audit_auth_01_analysis_only_shadow_worker_boundary.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/auth-worker-boundary-predecessor.py.txt",
        "07ce59ed824d40ef1be12686537c4e355e565c30",
        "27cc08cb019f649721ebe0b91021553420e442d530cda329ec3d3fcd26c48c64"),
    "runtime/worker_entry.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-predecessor.py.txt",
        "77d8888a4b007f9bb0967409a23e826f97338c90",
        "feaf4a9364fd064f081c9a4d086b65fdc31620075f0071ae1385bcbfa5cdaf94"),
    "scripts/sportybet_direct_share_bridge.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/direct-share-predecessor.py.txt",
        "681ce2a043a334dcb8523c81d092369d6540e6d5",
        "452a83426077ca758afef1f5e2a4d2e5100a1ef2401824cab733a4d31e0513cd"),
}


RETAINED_RECEIPT_SHA = "a62a8847dad208f1ed1c9bcd8cdcb36cf21b576b8528d2aaf6ca23209db5c22e"
RETAINED_GENERATION = 154
RETAINED_INVENTORY_SHA = "1dcf6a62d1e22c7e432c62bcadef824204466298c881741abe57edf709796230"
RETAINED_AUDIT_PREDECESSORS = {'scripts/audit_checkpoint_e_workflows.py': ('tests/fixtures/core_01d/fresh_holdout_20261014/checkpoint-workflows-predecessor.py.txt',
                                             '54d1af95d7aaebe99292fc33da5bd4d24db4462e',
                                             '502d20abe4155277fc671466fb2e759fc265201b116b76ef740cb69148313ffd'),
 'scripts/audit_core_01d_checkpoint_e_completion.py': ('tests/fixtures/core_01d/fresh_holdout_20261014/checkpoint-completion-predecessor.py.txt',
                                                       'a3906ff8c6189e09f2106ae0ed03ddef929dec2b',
                                                       'bd848f32e9311a3aba49cf024d89b5089f70abcb877913fabb0a401b5ecd31ee'),
 'scripts/audit_core_01d_checkpoint_e_completion_v2.py': ('tests/fixtures/core_01d/fresh_holdout_20261014/checkpoint-completion-v2-predecessor.py.txt',
                                                          'f427baed805abe41894d7c66d7492247aa82a9b2',
                                                          '2e0e6bb6dc6ba27f35a04066d4a29fb8a8e265998be8fa29719b2943eb30801b'),
 'scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py': ('tests/fixtures/core_01d/run_02a_pre_historical/b4-trigger-authority-predecessor.py.txt',
                                                                     '28e4963c668ab5992cd5760b499c0f69fd6f14db',
                                                                     'b10036a6fc5d56c9d718db3e14d0a998cffad3c3050530e28ed4e21630e2ac2b'),
 'scripts/audit_run_02a_pre_durable_share_send.py': ('tests/fixtures/core_01d/fresh_holdout_20261014/share-prerequisite-predecessor.py.txt',
                                                     '35617b52e020e9350b6de422dfd74171243990c6',
                                                     'eb2e8dbc6fcb464ab1dead01c0db3096ed85db0110e96e8c0c23a2f69d9d7974'),
 'tests/test_core_01d_exact_pr_trigger_disposition_b1.py': ('tests/fixtures/core_01d/fresh_holdout_20261014/b1-tests-predecessor.py.txt',
                                                            '36f784e7902f9f2317da5bcf9a95e2c90a206f56',
                                                            '9b68157609e03eb3ca0bf2e0a29729a23998ff0f1a3c8f9f35921773b91e4705'),
 'scripts/audit_data_01c_app_store_complete.py': ('tests/fixtures/core_01d/run_02a_pre_historical/app-store-complete-v154.py.txt',
                                                  'f8fc830dfd3ab9a487d8245d6bf545ff2408cacf',
                                                  'c44aecd7405ba13d4f4156e400fe8de15cba89bfc4b4f4e48b0ad34833d3cffd')}
RUN_02A_CURRENT_SOURCE_PREDECESSORS = {
    "database/run_repository.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/run-repository-pr463-base.py.txt",
        "103bcbf4e06a90ef768a122408235b9d9267fe6b",
        "abcce798ddcdfc9b650aadf9f369408831573e51e65d99afb96294e043e2e03f"),
    "services/athena_job_service.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/athena-job-service-pr463-base.py.txt",
        "d0291cc9a25b1372d86464e2fb54ac97f1fc7f98",
        "439c97a9b4d22e2e61724e349f20cad8e365787047f306af00f4d4690d60876d"),
    "runtime/worker_entry.py": (
        "tests/fixtures/core_01d/run_02a_pre_historical/worker-entry-pr463-base.py.txt",
        "113acdf1ece29ca2977e4e3d2d84576a31fe7828",
        "98d5b1d7cfbc524be876f7000f9e605caac013039893d4f028ac2452216a2a61"),
}


def historical_prerequisite_source_bytes(path, *, latest=None):
    """Exact retained audit/test predecessors; never runtime execution authority."""
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_core_01d_authority_reachability_review_a as review
    predecessors = {**RETAINED_AUDIT_PREDECESSORS, **RUN_02A_CURRENT_SOURCE_PREDECESSORS}
    if path not in predecessors or ROOT != review.ROOT or ROOT != a2.ROOT:
        raise AssertionError("unclassified retained prerequisite source/root")
    latest = a2.authenticate_inventory() if latest is None else latest
    retained = a2.read_generation(a2.inventory_generation_path(RETAINED_GENERATION))
    if retained["canonical_sha256"] != RETAINED_INVENTORY_SHA:
        raise AssertionError("retained prerequisite A2 identity drift")
    fixture, blob, digest = predecessors[path]
    for logical in (path, fixture):
        candidate = ROOT / logical
        if not candidate.is_file() or any(p.is_symlink() for p in (candidate, *candidate.parents)):
            raise AssertionError("retained prerequisite requires regular source/fixture")
    live = review._tracked_payloads(((path, (ROOT / path).read_bytes()),))[path]
    current = {r["path"]:r["lf_source_sha256"] for r in latest["source_identities"]}
    if hashlib.sha256(live.replace(b"\r\n", b"\n")).hexdigest() != current.get(path):
        raise AssertionError("current prerequisite source differs from authenticated A2")
    review._tracked_payloads(((fixture, (ROOT / fixture).read_bytes()),))
    raw = (ROOT / fixture).read_bytes().replace(b"\r\n", b"\n")
    retained_sources = {r["path"]:r["lf_source_sha256"] for r in retained["source_identities"]}
    if (hashlib.sha256(raw).hexdigest() != digest or retained_sources.get(path) != digest
            or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != blob):
        raise AssertionError("retained prerequisite predecessor fixture drift")
    return raw


def historical_transport_bytes(path, *, root=None):
    """Exact historical audit evidence; this grants no live execution authority."""
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    root = ROOT if root is None else root
    latest = a2.authenticate_inventory()
    v142 = a2.read_generation(a2.inventory_generation_path(142))
    if v142["canonical_sha256"] != V142_SHA:
        raise AssertionError("transport predecessor V142 changed")
    current = {row["path"]:row["lf_source_sha256"] for row in latest["source_identities"]}
    live = (root / path).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(live).hexdigest() != current.get(path):
        raise AssertionError("current transport differs from authenticated A2: " + path)
    fixture, blob, digest = TRANSPORT_PREDECESSORS[path]
    raw = (root / fixture).read_bytes().replace(b"\r\n", b"\n")
    old_sources = {row["path"]:row["lf_source_sha256"] for row in v142["source_identities"]}
    if (hashlib.sha256(raw).hexdigest() != digest or old_sources.get(path) != digest
            or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != blob):
        raise AssertionError("exact transport predecessor bytes changed: " + path)
    return raw


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def seal(value):
    value = dict(value)
    value.pop("canonical_sha256", None)
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def build_receipt(source_head, *, retained=False):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as policy
    latest = a2.authenticate_inventory()
    chain = a2.load_inventory_generations()
    if latest["generation"] < 143 or chain[141][1]["canonical_sha256"] != V142_SHA:
        raise AssertionError("prerequisite requires append-only successor from V142")
    for path, expected in HISTORY.items():
        value = json.loads((ROOT / path).read_bytes())
        if seal(value) != value or value["canonical_sha256"] != expected:
            raise AssertionError("historical receipt changed: " + path)
    if policy.calculate_policy_sha256() != "9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba":
        raise AssertionError("PR457 runtime policy changed")
    current = {row["path"]:row["lf_source_sha256"] for row in latest["source_identities"]}
    for path in TRANSPORT_PREDECESSORS:
        historical_transport_bytes(path)
    identities = {}
    for path in SOURCES:
        digest = hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if current.get(path) != digest:
            raise AssertionError("source differs from authenticated A2: " + path)
        if retained and path in (set(RETAINED_AUDIT_PREDECESSORS)
                                 | set(RUN_02A_CURRENT_SOURCE_PREDECESSORS)):
            digest = hashlib.sha256(historical_prerequisite_source_bytes(path, latest=latest)).hexdigest()
        identities[path] = digest
    if (type(source_head) is not str or len(source_head) != 40
            or any(c not in "0123456789abcdef" for c in source_head)):
        raise AssertionError("invalid source commit identity")
    evidence_inventory = latest
    if retained:
        evidence_inventory = a2.read_generation(a2.inventory_generation_path(RETAINED_GENERATION))
        if evidence_inventory["canonical_sha256"] != RETAINED_INVENTORY_SHA:
            raise AssertionError("retained prerequisite inventory changed")
    return seal({
        "schema_version": 1, "policy_id": "ATHENA_RUN_02A_PRE_DURABLE_SHARE_SEND_V1",
        "base_main": BASE, "source_head": source_head,
        "final_head_binding": "PR_AND_NATURAL_HOSTED_EXACT_HEAD_ATTESTATION_WITH_EXACT_SOURCE_HASHES",
        "source_identities": identities,
        "document_lf_sha256": hashlib.sha256((ROOT / "docs/product/run_02a_pre_durable_share_send.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "a2": {"generation": evidence_inventory["generation"], "canonical_sha256": evidence_inventory["canonical_sha256"],
               "immutable_predecessor_generation": 142, "immutable_predecessor_canonical_sha256": V142_SHA,
               "predecessor_rewritten": False},
        "history": HISTORY,
        "operation_kind": "SPORTYBET_SHARE_CODE_CREATE_V1",
        "write_ahead": "PREPARED_FULL_COMMIT_THEN_SENT_FULL_COMMIT_THEN_ONE_POST_MAXIMUM",
        "intent": "EXACT_ADMITTED_RUN_REQUEST_ENVELOPE_RELEASE_AUTHORITY_AND_CANONICAL_POST_BODY",
        "response": "IMMUTABLE_LOSSLESS_RAW_BYTES_STATUS_SHA_BYTE_COUNT_RUN_OPERATION_METHOD_AND_INTENT_BINDING",
        "classification": {"before_sent": "FAILED_ONLY_WITH_SHARE_CREATE_NEVER_SENT_AND_ZERO_POST",
                           "retained_success": "HTTP_200_BIZCODE_10000_RECOGNIZED_CODE_TO_CONFIRMED",
                           "post_sent_unproven": "OUTCOME_UNKNOWN_NEVER_FAILED",
                           "provider_proven_failed": "UNSUPPORTED_NO_REVIEWED_NO_CREATE_CONTRACT_OUTCOME_UNKNOWN_ACCEPTED"},
        "no_resend": "SERIALIZED_RUN_KIND_INTENT_CHECK_ALL_STATES_ALL_ATTEMPTS_ALL_IDEMPOTENCY_KEYS",
        "reload": "EXPLICIT_GET_ONLY_FROM_RETAINED_CONFIRMED_CREATE_CODE_NO_SECOND_POST",
        "authority": "REAUTHENTICATED_ADMITTED_CAPABILITY_NO_ACCOUNT_OR_WAGER_AUTHORITY",
        "product_delivery": "BLOCKED_NO_WORKER_INTEGRATION",
        "migration": "NONE_EXISTING_BEGIN_IMMEDIATE_SERIALIZATION",
        "run_02a": "BLOCKED_UNSTARTED_PENDING_PREREQUISITE_MERGE_AND_INDEPENDENT_ACCEPTANCE",
        "e4_e5": "UNSTARTED", "source_review_counter_while_unmerged": "3/5",
        "restricted_action_counts": dict.fromkeys(("provider_acquisition", "live_current_shadow", "fresh_holdout",
            "real_share_code_create", "delivery", "login", "cookies", "wallet", "stake", "wager", "email",
            "manual_workflow_dispatch", "manual_workflow_rerun", "manual_workflow_cancel"), 0),
        "review_ready": False, "merge_authorized": False,
        "residual_blocker": "NONE_CONSERVATIVE_POST_SENT_UNKNOWN_IS_ACCEPTED; PROVIDER_PROVEN_FAILED_UNSUPPORTED_WITHOUT_REVIEWED_NO_CREATE_CONTRACT",
        "hosted_gates": "NATURAL_EXACT_HEAD_TESTS_AND_PORT02C_REQUIRED_RECORDED_IN_PR_BODY",
    })


def audit():
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    value = json.loads(raw)
    if (raw != canonical(value) or value.get("canonical_sha256") != RETAINED_RECEIPT_SHA
            or value != build_receipt(value["source_head"], retained=True)):
        raise AssertionError("prerequisite source/evidence drift")
    return {"result": "PASS", "canonical_sha256": value["canonical_sha256"],
            "a2_generation": value["a2"]["generation"], "review_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        raise SystemExit("retained PR #459 receipt is immutable; reviewed successor evidence is required")
    print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
