#!/usr/bin/env python3
"""Forward-safe AUTH-01D no-delivery proof for the PORT-02B worker boundary."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_auth_01_analysis_only_shadow as historical_audit


POLICY_ID = "ATHENA_AUTH_01_ANALYSIS_ONLY_SHADOW_WORKER_BOUNDARY_V1"
ARTIFACT_PATH = Path("artifacts/architecture/auth_01_analysis_only_shadow_worker_boundary_v1.json")
IMPLEMENTATION_BASE_MAIN_SHA = "235fd86a1de26732473e7e839b5147b50bcfcd86"
HISTORICAL_ARTIFACT_SHA256 = "7b09adb4882d49749c33efecbce0b1c8985a2d3bdec52417f7b02f8f335f4a86"
HISTORICAL_REPLAY_SHA256 = "3b792193ef813f4aab79d7c3f9d48550270f3ae008265cc9ceb9c3d629e974f5"
FALSE_REQUEST_SHA256 = "2206abcefa58a28b3ec162b8a735e20ee2b18203b832837c8da9cf2735a5b276"
TRUE_REQUEST_SHA256 = "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"
SOURCE_PATHS = (
    "services/athena_run_service.py",
    "runtime/worker_launcher.py",
    "runtime/worker_entry.py",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    if type(value) is not dict:
        raise ValueError(f"expected JSON object: {path}")
    return value


def _current_head_sha() -> str:
    head = subprocess.check_output(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise AssertionError("current DevelopmentCheckout HEAD is not a canonical Git SHA-1")
    return head


def _source_identities() -> list[dict[str, str]]:
    records = []
    for relative_path in SOURCE_PATHS:
        blob_sha1 = subprocess.check_output(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", f"HEAD:{relative_path}"],
            text=True,
        ).strip()
        payload = subprocess.check_output(
            ["git", "-C", str(REPOSITORY_ROOT), "show", f"HEAD:{relative_path}"]
        )
        if relative_path == "services/athena_run_service.py" and blob_sha1 != "16d54ff599bffc70cdd66498a440647cf8e8b131":
            # Preserve the immutable receipt's source identities, but replay the
            # real current worker boundary below. Only the sealed LG-A successor
            # is permitted; no historical source or no-delivery proof is repinned.
            from scripts.audit_lg_a_worker_launch_failure_remediation import historical_source
            payload, identity = historical_source(relative_path, root=REPOSITORY_ROOT)
            if identity.git_blob_sha1 != "16d54ff599bffc70cdd66498a440647cf8e8b131":
                raise AssertionError("AUTH-01D/LG-A historical service fixture differs")
            blob_sha1 = identity.git_blob_sha1
        records.append(
            {
                "path": relative_path,
                "git_blob_sha1": blob_sha1,
                "git_blob_payload_sha256": _sha256(payload),
            }
        )
    return records


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    value = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )
    if value is None:
        raise AssertionError(f"reviewed worker boundary function is missing: {name}")
    return value


def _assigned_literal(tree: ast.Module, name: str) -> Any:
    node = next(
        (
            item for item in tree.body
            if isinstance(item, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in item.targets)
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"reviewed worker boundary constant is missing: {name}")
    if (
        isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id in {"set", "frozenset"}
        and len(node.value.args) == 1
    ):
        return set(ast.literal_eval(node.value.args[0]))
    return ast.literal_eval(node.value)


def _has_exact_bool_projection(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.IfExp):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Attribute)
            and isinstance(test.value, ast.Name)
            and test.value.id == "request"
            and test.attr == "create_share_code"
        ):
            continue
        if (
            isinstance(node.body, ast.Constant)
            and node.body.value == "true"
            and isinstance(node.orelse, ast.Constant)
            and node.orelse.value == "false"
        ):
            return True
    return False


def _worker_boundary_static_checks() -> None:
    service_path = REPOSITORY_ROOT / SOURCE_PATHS[0]
    launcher_path = REPOSITORY_ROOT / SOURCE_PATHS[1]
    entry_path = REPOSITORY_ROOT / SOURCE_PATHS[2]
    service_tree = ast.parse(service_path.read_text(encoding="utf-8"))
    launcher_tree = ast.parse(launcher_path.read_text(encoding="utf-8"))
    entry_tree = ast.parse(entry_path.read_text(encoding="utf-8"))

    service_helper = _function(service_tree, "_run_reviewed_shadow_worker")
    service_names = {node.id for node in ast.walk(service_helper) if isinstance(node, ast.Name)}
    if not {"WorkerCommand", "WorkerLauncher"}.issubset(service_names):
        raise AssertionError("AthenaRunService does not use the reviewed WorkerCommand/WorkerLauncher")
    if any(arg.arg in {"module", "function", "argv", "environment", "cwd"} for arg in service_helper.args.args + service_helper.args.kwonlyargs):
        raise AssertionError("AthenaRunService worker helper exposes arbitrary dispatch inputs")
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        for node in ast.walk(service_helper)
    ):
        raise AssertionError("AthenaRunService still starts a direct subprocess in the worker helper")

    operations = _assigned_literal(launcher_tree, "WORKER_OPERATIONS")
    if tuple(operations) != ("CURRENT_SHADOW_REQUEST", "OFFLINE_IDENTITY_PROBE"):
        raise AssertionError("worker operation allowlist changed")
    command_fields = set(_assigned_literal(launcher_tree, "_COMMAND_FIELDS"))
    expected_fields = {
        "schema_version", "policy_id", "operation", "mode", "run_directory",
        "request_artifact_id", "envelope_artifact_id", "release_identity_kind",
        "release_identity_id",
    }
    if command_fields != expected_fields or command_fields.intersection({"module", "function", "argv", "environment", "cwd"}):
        raise AssertionError("WorkerCommand schema gained arbitrary execution fields")
    launch_method = next(
        (
            node for node in ast.walk(launcher_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "launch"
        ),
        None,
    )
    if launch_method is None:
        raise AssertionError("WorkerLauncher.launch is missing")
    spawn_calls = [
        node for node in ast.walk(launch_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_spawn_process"
    ]
    if len(spawn_calls) != 1 or not any(
        keyword.arg == "shell"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in spawn_calls[0].keywords
    ):
        raise AssertionError("WorkerLauncher must use exactly one shell=False OS spawn seam")
    for tree in (launcher_tree, entry_tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "system" and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    raise AssertionError("worker launch path uses os.system")
                if any(
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                ):
                    raise AssertionError("worker launch path enables shell=True")

    current_shadow = _function(entry_tree, "_run_current_shadow")
    if not _has_exact_bool_projection(current_shadow):
        raise AssertionError("worker_entry does not serialize exact true/false request intent")
    constants = {node.value for node in ast.walk(current_shadow) if isinstance(node, ast.Constant)}
    if "--create-share-code" not in constants:
        raise AssertionError("worker_entry omitted the explicit Current Shadow delivery argument")
    if not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "main"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "execute_current_shadow_request"
        for node in ast.walk(current_shadow)
    ):
        raise AssertionError("worker_entry does not call the reviewed Current Shadow parser/entry")
    execute_command = _function(entry_tree, "execute_worker_command")
    execute_names = [node.id for node in ast.walk(execute_command) if isinstance(node, ast.Name)]
    if "read_bound_request" not in execute_names:
        raise AssertionError("worker_entry does not validate the exact bound RunRequest before dispatch")

    request_source = (REPOSITORY_ROOT / "services/athena_run_request_parser.py").read_text(encoding="utf-8")
    service_source = service_path.read_text(encoding="utf-8")
    if "share_code = True, request.create_share_code" not in service_source:
        raise AssertionError("SHADOW share-code capability is not request-bound")
    if "getattr(" in request_source and "create_share_code" in request_source and "getattr(request, \"create_share_code\", True)" in request_source:
        raise AssertionError("canonical request path contains a hidden true delivery default")


def _semantic_continuity_projection(replay: dict[str, Any]) -> dict[str, Any]:
    request = replay["request"]
    current = replay["current_shadow"]
    side_effects = replay["side_effects"]
    return {
        "request_canonical_sha256": request["canonical_sha256"],
        "authority_profile": request["authority_profile"],
        "mode": request["mode"],
        "bookie": request["bookie"],
        "create_share_code": request["create_share_code"],
        "place_wager": request["place_wager"],
        "business_status": current["status"],
        "selected_leg_count": current["selected_leg_count"],
        "target_legs": current["target_legs"],
        "shortfall": current["shortfall"],
        "reserve_leg_count": current["reserve_leg_count"],
        "selected_leg_identity_order": current["selected_leg_identity_order"],
        "authority_manifest": replay["authority_manifest"],
        "request_policy_delivery_intent": current["request_policy_delivery_intent"],
        "inner_delivery_intent": current["inner_delivery_intent"],
        "share_receipt_present": current["share_receipt_present"],
        "share_code_present": current["share_code_present"],
        "share_url_present": current["share_url_present"],
        "wager_placed": current["wager_placed"],
        "provider_network_call_count": side_effects["provider_network"],
        "share_transport_call_count": side_effects["share_transport"],
        "email_login_cookies_wallet_stake_wager_call_count": sum(
            side_effects[key]
            for key in ("email", "login", "cookies", "wallet", "stake", "wager")
        ),
    }


def _semantic_continuity_sha256(projection: dict[str, Any]) -> str:
    return _sha256(_canonical(projection))


def _build_artifact(replay: dict[str, Any]) -> dict[str, Any]:
    projection = _semantic_continuity_projection(replay)
    command = replay["worker_boundary"]["command"]
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "implementation_base_main_sha": IMPLEMENTATION_BASE_MAIN_SHA,
        "historical_predecessor": {
            "policy_id": historical_audit.POLICY_ID,
            "canonical_sha256": HISTORICAL_ARTIFACT_SHA256,
            "deterministic_replay_sha256": HISTORICAL_REPLAY_SHA256,
            "false_request_sha256": FALSE_REQUEST_SHA256,
            "true_request_sha256": TRUE_REQUEST_SHA256,
            "rewritten": False,
        },
        "current_worker_boundary": {
            "worker_command_policy_id": command["policy_id"],
            "worker_command_schema_version": command["schema_version"],
            "operation": command["operation"],
            "mode": command["mode"],
            "request_artifact_id": command["request_artifact_id"],
            "envelope_artifact_id": command["envelope_artifact_id"],
            "run_directory_bound_to_request_sha": replay["worker_boundary"]["run_directory_bound_to_request_sha"],
            "arbitrary_module": False,
            "arbitrary_function": False,
            "arbitrary_argv": False,
            "arbitrary_environment": False,
            "arbitrary_cwd": False,
            "shell": False,
            "delivery_argument": ["--create-share-code", "false"],
            "parsed_create_share_code": False,
            "retained_offline_worker_chain_executed": True,
        },
        "current_request_contract": {
            "authority_profile": "SHADOW",
            "mode": "research_shadow",
            "bookie": "sportybet",
            "create_share_code": False,
            "place_wager": False,
            "false_request_sha256": replay["request"]["canonical_sha256"],
            "true_compatibility_request_sha256": replay["adapter_request_byte_equality"]["true"]["canonical_sha256"],
        },
        "current_release_identity_contract": {
            "identity_kind": "DEVELOPMENT_CHECKOUT",
            "worker_command_identity": "EXACT_VERIFIED_CURRENT_HEAD",
            "worker_entry_reverification": "EXACT_VERIFIED_CURRENT_HEAD",
            "run_receipt_exact_commit_sha": "EXACT_VERIFIED_CURRENT_HEAD",
            "commit_sha_pinned_in_artifact": False,
        },
        "semantic_continuity": {
            "projection": projection,
            "semantic_continuity_sha256": _semantic_continuity_sha256(projection),
            "historical_full_run_receipt_sha_compared": False,
        },
        "network_sentinels": dict(replay["side_effects"]),
        "side_effects": {
            "provider_acquisition": 0,
            "worker_os_processes": 0,
            "share_code_create_reload": 0,
            "email": 0,
            "login": 0,
            "cookies": 0,
            "wallet": 0,
            "stake": 0,
            "wager": 0,
        },
        "source_identities": _source_identities(),
        "governance": {
            "source_review_counter_while_unmerged": "4/5",
            "source_review_counter_if_merged": "5/5",
            "reread_required_before_port_02c": True,
            "PORT_02C": "NOT_STARTED",
            "LG_A": "NOT_RUN_NOT_AUTHORIZED",
            "P4_4": "INCOMPLETE",
            "architecture_checkpoint_E": "INCOMPLETE",
            "clean_successor_proof": "INCOMPLETE",
            "caller_migration": "NOT_AUTHORIZED",
            "workflow_retirement": "NOT_AUTHORIZED",
        },
    }
    artifact["canonical_sha256"] = _sha256(_canonical(artifact))
    return artifact


def _clean_process_pair() -> tuple[dict[str, Any], bytes, bytes]:
    outputs: list[bytes] = []
    for order in ("forward", "reverse"):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--replay-json", "--import-order", order],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            timeout=600,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"current worker-boundary replay ({order}) failed: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        if completed.stderr:
            raise AssertionError(
                f"current worker-boundary replay ({order}) wrote unexpected stderr: "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        outputs.append(completed.stdout)
    if outputs[0] != outputs[1]:
        raise AssertionError("forward/reverse current worker-boundary replay bytes differ")
    replay = json.loads(outputs[0], object_pairs_hook=_strict_object)
    if _canonical(replay) != outputs[0]:
        raise AssertionError("current worker-boundary replay output is not canonical JSON")
    return replay, outputs[0], outputs[1]


def _verify_replay(replay: dict[str, Any], current_head: str) -> None:
    worker = replay["worker_boundary"]
    command = worker["command"]
    if worker["current_head_sha"] != current_head:
        raise AssertionError("worker boundary replay did not use current verified HEAD")
    if worker["run_receipt_exact_commit_sha"] != current_head:
        raise AssertionError("RunReceipt did not bind the exact current verified HEAD")
    if (
        command["operation"] != "CURRENT_SHADOW_REQUEST"
        or command["mode"] != "research_shadow"
        or command["request_artifact_id"] != FALSE_REQUEST_SHA256
        or command["envelope_artifact_id"] is not None
        or command["release_identity_kind"] != "DEVELOPMENT_CHECKOUT"
        or command["release_identity_id"] != current_head
        or worker["worker_entry_release_identity_id"] != current_head
    ):
        raise AssertionError("WorkerCommand or worker_entry did not bind exact current request/release identity")
    if worker["arbitrary_module"] or worker["arbitrary_function"] or worker["arbitrary_argv"]:
        raise AssertionError("worker boundary enabled arbitrary module/function/argv dispatch")
    if worker["parsed_create_share_code"] is not False:
        raise AssertionError("real Current Shadow parser did not receive exact false delivery intent")
    request = replay["request"]
    current = replay["current_shadow"]
    if request["canonical_sha256"] != FALSE_REQUEST_SHA256 or request["create_share_code"] is not False:
        raise AssertionError("current no-delivery RunRequest identity or intent changed")
    if replay["adapter_request_byte_equality"]["true"]["canonical_sha256"] != TRUE_REQUEST_SHA256:
        raise AssertionError("current true-compatibility RunRequest identity changed")
    if current["request_policy_delivery_intent"] is not False or current["inner_delivery_intent"] is not False:
        raise AssertionError("Current Shadow request policy or inner receipt lost false intent")
    if current["share_receipt_present"] or current["share_code_present"] or current["share_url_present"]:
        raise AssertionError("no-delivery worker proof contains share evidence")
    if current["wager_placed"] is not False:
        raise AssertionError("no-delivery worker proof contains wager evidence")
    if any(value != 0 for value in replay["side_effects"].values()):
        raise AssertionError("current worker-boundary proof reached a forbidden external operation")


def check_artifact() -> dict[str, Any]:
    _worker_boundary_static_checks()
    historical = historical_audit.check_artifact()
    if (
        historical.get("result") != "SKIP_SOURCE_MOVED"
        or historical.get("historical_integrity") != "PASS"
        or historical.get("historical_replay_reexecuted") is not False
        or historical.get("artifact_canonical_sha256") != HISTORICAL_ARTIFACT_SHA256
    ):
        raise AssertionError("AUTH-01D v1 historical integrity/forward-skip result is not exact")
    artifact = _read_json(REPOSITORY_ROOT / ARTIFACT_PATH)
    claimed = artifact.get("canonical_sha256")
    unsigned = dict(artifact)
    unsigned.pop("canonical_sha256", None)
    if type(claimed) is not str or _sha256(_canonical(unsigned)) != claimed:
        raise AssertionError("current worker-boundary evidence self-hash mismatch")
    if claimed != artifact.get("canonical_sha256"):
        raise AssertionError("current worker-boundary evidence canonical identity is malformed")
    predecessor = artifact.get("historical_predecessor", {})
    expected_predecessor = {
        "policy_id": historical_audit.POLICY_ID,
        "canonical_sha256": HISTORICAL_ARTIFACT_SHA256,
        "deterministic_replay_sha256": HISTORICAL_REPLAY_SHA256,
        "false_request_sha256": FALSE_REQUEST_SHA256,
        "true_request_sha256": TRUE_REQUEST_SHA256,
        "rewritten": False,
    }
    if predecessor != expected_predecessor:
        raise AssertionError("current evidence historical predecessor pins changed")
    current_head = _current_head_sha()
    replay, forward, reverse = _clean_process_pair()
    _verify_replay(replay, current_head)
    projection = _semantic_continuity_projection(replay)
    expected = _build_artifact(replay)
    if artifact != expected:
        raise AssertionError("committed worker-boundary evidence differs from exact current replay")
    if forward != reverse:
        raise AssertionError("current full replay bytes are not deterministic across import orders")
    return {
        "result": "PASS",
        "policy_id": POLICY_ID,
        "historical_predecessor_integrity": "PASS",
        "current_head_sha": current_head,
        "current_run_receipt_sha256": replay["canonical_run_receipt"]["canonical_bytes_sha256"],
        "current_full_replay_sha256": _sha256(forward),
        "run_receipt_exact_commit_sha": replay["canonical_run_receipt"]["exact_commit_sha"],
        "worker_command": replay["worker_boundary"]["command"],
        "worker_entry_release_identity_id": replay["worker_boundary"]["worker_entry_release_identity_id"],
        "worker_final_delivery_argument": replay["worker_boundary"]["final_delivery_argument"],
        "worker_parser_create_share_code": replay["worker_boundary"]["parsed_create_share_code"],
        "worker_request_policy_create_share_code": replay["current_shadow"]["request_policy_delivery_intent"],
        "worker_inner_receipt_create_share_code": replay["current_shadow"]["inner_delivery_intent"],
        "worker_share_receipt_present": replay["current_shadow"]["share_receipt_present"],
        "worker_share_code_present": replay["current_shadow"]["share_code_present"],
        "worker_share_url_present": replay["current_shadow"]["share_url_present"],
        "worker_wager_placed": replay["current_shadow"]["wager_placed"],
        "semantic_continuity_sha256": _semantic_continuity_sha256(projection),
        "clean_process_count": 2,
        "forward_reverse_semantic_bytes_equal": _canonical(_semantic_continuity_projection(replay))
        == _canonical(_semantic_continuity_projection(json.loads(reverse, object_pairs_hook=_strict_object))),
        "forward_reverse_full_replay_bytes_equal": forward == reverse,
        "provider_network_calls": replay["side_effects"]["provider_network"],
        "share_transport_calls": replay["side_effects"]["share_transport"],
        "account_wager_calls": sum(
            replay["side_effects"][key] for key in ("login", "cookies", "wallet", "stake", "wager")
        ),
        "historical_replay_sha256": HISTORICAL_REPLAY_SHA256,
        "historical_full_receipt_sha_compared": False,
    }


def _write_artifact() -> dict[str, Any]:
    _worker_boundary_static_checks()
    current_head = _current_head_sha()
    replay, forward, reverse = _clean_process_pair()
    _verify_replay(replay, current_head)
    if forward != reverse:
        raise AssertionError("current full replay bytes are not deterministic across import orders")
    artifact = _build_artifact(replay)
    path = REPOSITORY_ROOT / ARTIFACT_PATH
    payload = json.dumps(artifact, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise FileExistsError("refusing to overwrite a contradictory worker-boundary evidence artifact")
    else:
        path.write_text(payload, encoding="utf-8", newline="\n")
    return artifact


def _replay_json(import_order: str) -> int:
    _worker_boundary_static_checks()
    current_head = _current_head_sha()
    replay = historical_audit._build_replay(import_order, exact_release_sha=current_head)
    _verify_replay(replay, current_head)
    sys.stdout.buffer.write(_canonical(replay))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--print-artifact", action="store_true")
    action.add_argument("--replay-json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--import-order", choices=("forward", "reverse"), default="forward")
    args = parser.parse_args(argv)
    try:
        if args.replay_json:
            return _replay_json(args.import_order)
        if args.print_artifact:
            artifact = _write_artifact()
            sys.stdout.write(json.dumps(artifact, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n")
            return 0
        result = check_artifact()
    except Exception as exc:
        print(f"AUTH-01D worker-boundary audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
