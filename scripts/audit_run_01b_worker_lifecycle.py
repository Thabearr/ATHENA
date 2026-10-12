"""Audit immutable E1/E2 lineage and the RUN-01B evidence candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = "artifacts/product/run_01b_worker_lifecycle_v1.json"
E1_RECEIPT_SHA256 = "de2222e7f1c472d7a336f8a4c9c7bec84c2e6ed533b8f568689a3857adaf4f71"
D5_RECEIPT_SHA256 = "c9be3cc4c74fea16c9f97c0db3fe7b54d9e12373fc5787d46677f36276f7441d"
D5_PORTABILITY_SHA256 = "f85937fae092981c655b0fa66756527633549b867209bb731171ab7d6e1e6a97"
MAIN_SHA = "ba5e868d2fb1e44d8939489559958d2fda5815d3"
MAIN_TREE_SHA = "89a045b1867c4c5714d53218931a51a668bad487"
ORIGINAL_BRANCH_POINT = "8b1af2d3fb14eb9915b31f4cd7d5c59c06820387"
SYNC_MERGE = "9b9d8ada06324bcd6ea0b2bce990e2e01fe89e3a"
A2_PREDECESSOR_SHA256 = "fff805f9b3482054d41a25e800ea398c33471bb5d30e38d292eca07d9a5cb381"
A2_V125_CANONICAL_SHA256 = "5a328d356aa7995612d60e5473ea6c92f2655c39ec1dd9dce81e90026938a605"
A2_V126_CANONICAL_SHA256 = "e518d4ec0db08d85430a6e04b5650b49be8d5dfdc6ece91612f61087d9cf1396"
A2_V127_CANONICAL_SHA256 = "d6896bfa45293a4d8407e9273ea5c56c6276a602a256a6535de4eaab60c083cf"
A2_V128_CANONICAL_SHA256 = "a1d6c095d13619c64a1242bf44ab58a67f43cbecf6ab099bd85b6d7301f3050b"
A2_V129_CANONICAL_SHA256 = "7433ba55126df49196668eb162625335fa57edc7793fc51c297071c183d76daf"
A2_V130_CANONICAL_SHA256 = "e57e42257e922e401ee3a40a5291ab8e8018cbf488653306cc1baef6790b9edc"
A2_V131_CANONICAL_SHA256 = "71e347caa69c7f42cb471611503fe1524cb430e74034c8e1195ea069b588baaa"
A2_V132_CANONICAL_SHA256 = "00af46c7c89932956b752a42c21ed6bd40d2d12e95e02f98d8a2046466c55c9d"
A2_V133_CANONICAL_SHA256 = "e01f9b23074076846522056a45514d2a34f78a85c3bc6c89383c33e1b81e69e7"
A2_V134_CANONICAL_SHA256 = "85107818034b50495157e36bde9bc277a4b181136b9bfeced846e7a6de2eb289"
A2_V135_CANONICAL_SHA256 = "be33b12c9149c6c8b645adadbe5770484ac25814269a2fb93c78b2666d37f91e"
A2_V136_CANONICAL_SHA256 = "daa5e71f17e9aedadabd4919022620f7625d8bef7e6133f98b487e1d372e2c78"
A2_V137_CANONICAL_SHA256 = "3eeb4869444ca4728fa763ccd79d9bb756693286f01624248c80942e417f6989"
SUCCESSOR_RUNTIME_SHA256 = "9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba"
LEGACY_RUNTIME_SHA256 = "3cf597440422433e7c7e2246d33de4ece22e55395218f8bc2eb8950a361dd68a"
INCIDENT_RECEIPT_PATH = (
    "tests/fixtures/core_01d/inc_20261010/"
    "inc_20261010_pc_upcoming_bounded_epoch_stabilization_v1.json"
)
INCIDENT_RECEIPT_SHA256 = "deb03d899324249bd62a7e132f7947cc574828d926d1cd77b9c98117050627a2"

_A2_RAW_SHA256 = {
    116: "00a9cf3f6e1e9c20da2089c021791a30b1785e2c373aa4eecbcff131829d991c",
    117: "acffd3d84ff62ac61fc864a464272c7ef00e0e972695e8bfa1b49bf56c03c5c7",
    118: "bfc9d2b82cf91617ce702e61c3cc32dbca5bb291206811c83c82fab3c94a254b",
    119: "bd3b1fcc199d4997b53086bc48f31bc648f05276a0735357f16ae612e2057410",
    120: "6476517e2c341cd4207b0bc1a2ae6af9b6b10e096119b317fe62e723708dc55f",
    121: "f30be3c2ed2751a030420b354b734e68a8ce6f42a93340bd619410e64b342981",
    122: "f06e072ce27cc8ae025fc8f406828c0372566dab734eaa5f363d37c62cc3d7bb",
    123: "c1726acb7ed1737a0c8d062fd3051a93a30663d13bda0f7248d44e8d27abc6b7",
    124: "6b4fa6f8b0dbef4baeb3df19034f41e72b6ca795a3c2620661e3248b6c57d4bb",
    125: "d46e46fad2e489cb491164dd81e08730e9f9513227d833a6c80c873ee8dc4a1d",
    126: "ddc97daca3d418a48b02650ebda6c39f81bb144047070db4193f6dc236a6abab",
    127: "5637210541c4ce6af247b9590373cbc86d273e32a841d66396daafc21247c33c",
    128: "59b088624d113599029c38695f2ab485aee1b93fd9eac5cf9c043bcf3f3e9165",
    129: "51dbe3a6cdaa6e7f935a6e3d1233dc46c55249035b0d9336c6e3c69620e24de7",
    130: "a6def3e67316785a8aefa1a5282b678cfc540cd06beb8195937ff6519962a933",
    131: "07f312fd709d6afe8b14f199f39695fb5fe9b04dd5dd861d53290e4a773087c9",
    132: "e78e4aa2c0cbed963b21165246656202a23e9a66dbcf46749bee09b98d0baf7d",
    133: "4fdbec5febe1ed46fa2c53e1e3daab2163871ae2d7ff5b7b0bb3712b01221c39",
    134: "3a104f2ebfb22960abf449cedb6364426cdfead64b599626a930d22eb3a59a94",
    135: "d4e7c1528168becb4065e4f08d2109bd8c03cae5c3d86d6c182685e5ae0e13a3",
    136: "7357e350e7cdb88aca627e79e0f35b8f213b0adfe13f699a20e846d7e7fd3417",
    137: "d0959930ebab04c7963bf249c2979d29973bba759ea1764d2fe9e9be9f06d2a8",
}
_SOURCE_PATHS = (
    "api/schemas.py",
    "database/run_repository.py",
    "runtime/worker_launcher.py",
    "scripts/audit_run_01a_durable_admission.py",
    "scripts/audit_run_01b_worker_lifecycle.py",
    "services/athena_job_service.py",
    "services/athena_read_service.py",
    "services/worker_coordinator.py",
    "tests/test_run_01a_forward_successor_pr457.py",
    "tests/test_run_01b_worker_lifecycle.py",
    "tests/native/test_run_01b_worker_coordinator_native.py",
)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def seal(value):
    value = dict(value)
    value.pop("canonical_sha256", None)
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def _read_canonical(path, *, trailing_newline=True):
    raw = (ROOT / path).read_bytes()
    value = json.loads(raw)
    expected = canonical(value)
    if not trailing_newline:
        expected = expected[:-1]
    semantic = dict(value) if type(value) is dict else {}
    embedded = semantic.pop("canonical_sha256", None)
    self_bytes = canonical(semantic)
    if not trailing_newline:
        self_bytes = self_bytes[:-1]
    if (type(value) is not dict or raw != expected
            or embedded != hashlib.sha256(self_bytes).hexdigest()):
        raise AssertionError("canonical evidence drift: " + path)
    return value


def _lf_sha(path):
    raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _source_map(rows):
    return {row["path"]: row["lf_source_sha256"] for row in rows}


def build_receipt():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    from scripts import audit_run_01a_durable_admission as e1
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime

    latest = a2.authenticate_inventory()
    if latest.get("generation") != 138:
        raise AssertionError("RUN-01B requires the V138 successor from immutable V137")
    chain = a2.load_inventory_generations()
    if len(chain) != 138:
        raise AssertionError("A2 generation sequence is not contiguous through V138")
    predecessor_path, predecessor = chain[-2]
    if (predecessor_path != a2.inventory_generation_path(137)
            or predecessor.get("canonical_sha256") != A2_V137_CANONICAL_SHA256):
        raise AssertionError("V137 predecessor identity changed")
    if latest.get("predecessor_inventory") != {
        "path": a2.inventory_generation_path(137),
        "canonical_sha256": A2_V137_CANONICAL_SHA256,
        "generation": 137,
        "rewritten": False,
    }:
        raise AssertionError("V137 predecessor binding drift")
    v137_path, v137 = chain[-2]
    if (v137_path != a2.inventory_generation_path(137)
            or v137.get("canonical_sha256") != A2_V137_CANONICAL_SHA256):
        raise AssertionError("immutable V137 identity changed")
    v136_path, v136 = chain[-3]
    if (v136_path != a2.inventory_generation_path(136)
            or v136.get("canonical_sha256") != A2_V136_CANONICAL_SHA256):
        raise AssertionError("immutable V136 identity changed")
    v135_path, v135 = chain[-4]
    if (v135_path != a2.inventory_generation_path(135)
            or v135.get("canonical_sha256") != A2_V135_CANONICAL_SHA256):
        raise AssertionError("immutable V135 identity changed")
    v134_path, v134 = chain[-5]
    if (v134_path != a2.inventory_generation_path(134)
            or v134.get("canonical_sha256") != A2_V134_CANONICAL_SHA256):
        raise AssertionError("immutable V134 identity changed")
    v133_path, v133 = chain[-6]
    if (v133_path != a2.inventory_generation_path(133)
            or v133.get("canonical_sha256") != A2_V133_CANONICAL_SHA256):
        raise AssertionError("immutable V133 identity changed")
    v132_path, v132 = chain[-7]
    if (v132_path != a2.inventory_generation_path(132)
            or v132.get("canonical_sha256") != A2_V132_CANONICAL_SHA256):
        raise AssertionError("immutable V132 identity changed")
    v131_path, v131 = chain[-8]
    if (v131_path != a2.inventory_generation_path(131)
            or v131.get("canonical_sha256") != A2_V131_CANONICAL_SHA256):
        raise AssertionError("immutable V131 identity changed")
    v130_path, v130 = chain[-9]
    if (v130_path != a2.inventory_generation_path(130)
            or v130.get("canonical_sha256") != A2_V130_CANONICAL_SHA256):
        raise AssertionError("immutable V130 identity changed")
    v129_path, v129 = chain[-10]
    if (v129_path != a2.inventory_generation_path(129)
            or v129.get("canonical_sha256") != A2_V129_CANONICAL_SHA256):
        raise AssertionError("immutable V129 identity changed")
    v128_path, v128 = chain[-11]
    if (v128_path != a2.inventory_generation_path(128)
            or v128.get("canonical_sha256") != A2_V128_CANONICAL_SHA256):
        raise AssertionError("immutable V128 identity changed")
    v127_path, v127 = chain[-12]
    if (v127_path != a2.inventory_generation_path(127)
            or v127.get("canonical_sha256") != A2_V127_CANONICAL_SHA256):
        raise AssertionError("immutable V127 identity changed")
    v126_path, v126 = chain[-13]
    if (v126_path != a2.inventory_generation_path(126)
            or v126.get("canonical_sha256") != A2_V126_CANONICAL_SHA256):
        raise AssertionError("immutable V126 identity changed")
    v125_path, v125 = chain[-14]
    if (v125_path != a2.inventory_generation_path(125)
            or v125.get("canonical_sha256") != A2_V125_CANONICAL_SHA256):
        raise AssertionError("immutable V125 identity changed")
    v124_path, v124 = chain[-15]
    if (v124_path != a2.inventory_generation_path(124)
            or v124.get("canonical_sha256") != A2_PREDECESSOR_SHA256):
        raise AssertionError("immutable V124 identity changed")

    for generation, expected_raw_sha in _A2_RAW_SHA256.items():
        path = a2.inventory_generation_path(generation)
        raw = (ROOT / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_raw_sha:
            raise AssertionError("historical A2 inventory bytes changed: " + path)

    e1._verify_immutable_receipt()
    e1.authenticate_successor()
    e1_raw = (ROOT / e1.RECEIPT).read_bytes()
    if e1_raw != e1.canonical(e1.build_receipt()):
        raise AssertionError("E1 historical reconstruction changed")
    e1_value = _read_canonical(e1.RECEIPT)
    if e1_value.get("canonical_sha256") != E1_RECEIPT_SHA256:
        raise AssertionError("E1 canonical receipt identity changed")

    d5 = _read_canonical("artifacts/product/data_01c_app_store_complete_v1.json")
    portability = _read_canonical("artifacts/product/data_01c_restore_portability_v1.json")
    if d5.get("canonical_sha256") != D5_RECEIPT_SHA256:
        raise AssertionError("D5 receipt identity changed")
    if portability.get("canonical_sha256") != D5_PORTABILITY_SHA256:
        raise AssertionError("D5 portability identity changed")

    incident = _read_canonical(INCIDENT_RECEIPT_PATH, trailing_newline=False)
    if incident.get("canonical_sha256") != INCIDENT_RECEIPT_SHA256:
        raise AssertionError("PR457 incident receipt identity changed")
    if (runtime.calculate_policy_sha256() != SUCCESSOR_RUNTIME_SHA256
            or runtime.PINNED_POLICY_SHA256 != SUCCESSOR_RUNTIME_SHA256
            or runtime.LEGACY_RUNTIME_POLICY_SHA256 != LEGACY_RUNTIME_SHA256):
        raise AssertionError("PR457 runtime policy identities changed")

    a2_sources = _source_map(latest["source_identities"])
    source_identities = []
    for path in _SOURCE_PATHS:
        if path not in a2_sources or _lf_sha(path) != a2_sources[path]:
            raise AssertionError("RUN-01B source differs from A2 V138: " + path)
        source_identities.append({"path": path, "lf_sha256": a2_sources[path]})
    doc_path = "docs/product/run_01b_worker_lifecycle.md"
    if not (ROOT / doc_path).is_file():
        raise AssertionError("RUN-01B review document is missing")

    value = {
        "schema_version": 1,
        "policy_id": "ATHENA_RUN_01B_OWNED_WORKER_LIFECYCLE_V1",
        "original_branch_point": ORIGINAL_BRANCH_POINT,
        "reconciled_main": {"commit_sha": MAIN_SHA, "tree_sha": MAIN_TREE_SHA},
        "branch_synchronization_merge_commit": SYNC_MERGE,
        "a2_successor": {
            "generation": 138,
            "canonical_sha256": latest["canonical_sha256"],
            "predecessor_path": predecessor_path,
            "predecessor_canonical_sha256": A2_V137_CANONICAL_SHA256,
            "predecessor_rewritten": False,
            "v116_v137_raw_sha256": {str(k): v for k, v in _A2_RAW_SHA256.items() if k <= 137},
        },
        "immutable_history": {
            "e1_receipt_path": e1.RECEIPT,
            "e1_receipt_canonical_sha256": E1_RECEIPT_SHA256,
            "d5_receipt_path": "artifacts/product/data_01c_app_store_complete_v1.json",
            "d5_receipt_canonical_sha256": D5_RECEIPT_SHA256,
            "d5_portability_canonical_sha256": D5_PORTABILITY_SHA256,
            "incident_receipt_path": INCIDENT_RECEIPT_PATH,
            "incident_receipt_canonical_sha256": INCIDENT_RECEIPT_SHA256,
            "e1_historical_source_identities_reconstructed": True,
        },
        "runtime_compatibility": {
            "pr457_successor_policy_sha256": SUCCESSOR_RUNTIME_SHA256,
            "legacy_two_epoch_policy_sha256": LEGACY_RUNTIME_SHA256,
            "pr457_semantics_preserved": True,
        },
        "source_identities": source_identities,
        "document_lf_sha256": _lf_sha(doc_path),
        "worker_contract": {
            "root_wide_single_unfinished_attempt": "DURABLE_SQLITE_BEGIN_IMMEDIATE_FENCED_CLAIM",
            "queued_capacity_loser": "DURABLY_QUEUED_NO_AUTOMATIC_DRAIN",
            "worker_process_locator": ["WINDOWS_PROCESS_GROUP", "POSIX_PROCESS_GROUP"],
            "heartbeat_and_lease_fencing": "MATCHED_CURRENT_LEASE_AUTHENTICATES_EVIDENCE_BEFORE_FINISHED_ATTEMPT_FENCE",
            "progress_source": "CANONICAL_TYPED_CURRENT_SHADOW_STAGE_AND_PROGRESS_FILES_ONLY",
            "progress_order_and_dedupe": "MONOTONIC_STAGE_AND_COUNTS_CANONICAL_EVIDENCE_SHA256",
            "last_proven_stage": "LATEST_AUTHENTICATED_TYPED_OBSERVATION",
            "missing_counts": "UNAVAILABLE_NONE_UNTIL_TYPED_EVIDENCE_PROVES_VALUE",
            "terminal_authority": "CANONICAL_RUN_RECEIPT_PRODUCER_REQUEST_ENVELOPE_RELEASE_AND_ATTEMPT_BOUND",
            "projection_order": "PUBLISH_RECEIPT_BEFORE_TERMINAL_DATABASE_PROJECTION",
            "projection_gap": "REPAIR_FROM_EXACT_RETAINED_RECEIPT_ONLY_NO_BUSINESS_RERUN",
            "child_exit_without_receipt": "INTERRUPTED_INTERNAL_LAST_PROVEN_STAGE_NO_RETRY",
            "cancel_intent": "E3_DEFERRED_503_CANCEL_STORE_UNAVAILABLE_NON_MUTATING",
            "installed_producer_provenance": "BLOCKED_UNTIL_AUTHENTICATED_PRODUCER_EXISTS",
        },
        "restricted_action_counts": dict.fromkeys((
            "provider", "live_current_shadow", "fresh_holdout", "share_code",
            "delivery", "login", "cookie", "wallet", "stake", "wager",
            "email", "manual_workflow_dispatch", "manual_workflow_rerun",
            "manual_workflow_cancel",
        ), 0),
        "e3_e4": "UNSTARTED",
        "source_review_counter_while_unmerged": "2/5",
        "pr458_merge_authorized": False,
        "hosted_exact_head_tests": "REQUIRED_AND_RECORDED_IN_PR_BODY_AFTER_FINAL_PUSH",
        "hosted_port_02c_windows_linux": "REQUIRED_IF_NATURALLY_TRIGGERED_BY_FINAL_PATHS",
        "review_ready": False,
    }
    return seal(value)


def audit():
    value = _read_canonical(RECEIPT_PATH)
    if value != build_receipt():
        raise AssertionError("RUN-01B receipt differs from its current source/evidence reconstruction")
    return {"result": "PASS", "receipt_canonical_sha256": value["canonical_sha256"],
            "a2_generation": value["a2_successor"]["generation"],
            "merge_authorized": False, "review_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    value = build_receipt()
    path = ROOT / RECEIPT_PATH
    if args.write:
        path.write_bytes(canonical(value))
    elif path.read_bytes() != canonical(value):
        raise AssertionError("RUN-01B evidence receipt drift")
    print(json.dumps({"result": "RUN_01B_SOURCE_EVIDENCE_OK",
                      "canonical_sha256": value["canonical_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
