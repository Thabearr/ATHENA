#!/usr/bin/env python3
"""Offline, fail-closed audit for P4.4R runtime composition and evidence."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc_runtime
from domain import current_shadow_runtime_bindings as runtime_bindings
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_team_label_compatibility as team_labels
from domain import _current_shadow_quote_binding as quote_binding


BASE_MAIN_SHA = "47326a934aabe34052c804a6941a702e52710b12"
PC_SOURCE_SHA256 = "306e9b37bb749032cae48be100ae7b49f1221fcf3392373a2e2407a8b3c339f5"
PC_RUNTIME_SHA256 = "3cf597440422433e7c7e2246d33de4ece22e55395218f8bc2eb8950a361dd68a"
TEAM_LABEL_SHA256 = "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
IDENTITY_SHA256 = "e8587d1e99cb7aa6214f65b515ca59f1456443a554a762ba27be204506da7569"
BRIDGE_SHA256 = "c3f05e5ea6ce08c392ec13d1b39d40dd8dd177e5a73f3660605c359705719858"
V2_SHA256 = "149b7b61213e33ee85f030d3e567966e5f79df6bea4e138d54d638c76d5e8156"
V2_SEED_SHA256 = "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
RUN_ID = 36285099805
ARTIFACT_ID = 10920404872
ARTIFACT_ZIP_SHA256 = "1e1c1e315d0bafe1cbec5c0fde1be2cba9832cca56e4ce64a582a51b57662ace"
RECEIPT_PATH = Path("artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json")
INVENTORY_PATH = Path("artifacts/architecture/p4_4r_shadow_runtime_composition_inventory_v1.json")
FIXTURE_ROOT = Path("tests/fixtures/p4_4r_run_36285099805_quote_evidence")
PRE_FIX_VERIFIER_FIXTURE = Path(
    "tests/fixtures/p4_4r_pre_fix_quote_context_verifier.py"
)
PRE_FIX_VERIFIER_FIXTURE_SHA256 = (
    "7547f701e025aa6723b7b0fc181c00347292bca2dfe0a15eeeb7a9bb205f2f87"
)
PRE_FIX_VERIFIER_SOURCE_SLICE_SHA256 = (
    "f3a3afc36fee517a776297a6cedd5867379f57877053798e565b4f8548617df1"
)
FIXTURE_SHAS = {
    "initial/event.raw.json": "4e42b9b38e33a2d9d7d839f0f6a36c7849a0f4043d4cdfdce40cad59c9de0bc8",
    "initial/manifest.json": "f2515e5f02682a05b6d3e1cd48f03b08085f0567baf56dfce38244a63e99892e",
    "fresh/event.raw.json": "d4f08a6f7293943e99a4a2db94d545714dee55e3d14335ad593a16f5154ff33a",
    "fresh/manifest.json": "83a0f4b1a6240f2e21ab6d97ef4e4d1863dc7b5ee49953f9efaf9aed64bb5bd6",
    "accepted-source/manifest.json": "17436da36f2e39c3d041cb487160dffbf3a7c68115985ce83576b4e432cf2594",
    "accepted-source/page-001.raw.json": "a525f072d0648a5110e85da1d970f8e773348cee8a15c091969f6bb4452857ea",
    "run-diagnostic/current-shadow-price-stage-diagnostic.json": "af2826dbee57caf9ea1e80d0d82e535c72dabf8676a1300057efe063c7e2e1dd",
}
HISTORICAL_RECEIPT_SHA256 = {
    "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json": "95707fd03a83fa1c20a5128f9ec2b9494c25b24cf8f23c16a77b5fb62d25da15",
    "artifacts/architecture/p4_4i_shadow_supervisor_failure_evidence_v1.json": "699edcdda6f399315d119450fc15fb3021f7653f572b0e54bd170c7521865ee6",
    "artifacts/architecture/p4_4j_shadow_selected_source_issuer_network_control_v1.json": "2cd8aa80af55aef948c383b7a23365113e5a2356a4a8caa7ec11f9a3e48218ec",
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": "88c7c1423b81251515da0ca145fbbfd26040df4966da10b5a5d322aaf44aacb3",
    "artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json": "0cc979b15c7eff7e783563dbed30ea0901bbfc801fec6d419474f1a6f59f6314",
    "artifacts/architecture/p4_4o_pc_upcoming_stable_epoch_recovery_v1.json": "dd225517d2b0c065c55629e1d01e18ce4bcb2fe012a2e637b6f253f941b8c1ed",
    "artifacts/architecture/p4_4p_pc_upcoming_preparse_response_evidence_v1.json": "6b10048d3f62a3b97c6baeff79b74913a519446005ae5829c0d1608f86046077",
    "artifacts/architecture/p4_4q_pc_upcoming_simple_tournament_identity_v1.json": "0bb8f7cc32bc387de49f61f4792e65813ec1933a5030f633488e50e76a13e19c",
}


class P44RError(AssertionError):
    """Raised when P4.4R evidence or runtime composition drifts."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P44RError(message)


def _read_json(root: Path, relative: str | Path) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44RError(f"required P4.4R evidence is unavailable: {relative}") from exc
    _require(type(value) is dict, f"P4.4R JSON must be an object: {relative}")
    return value


def _verify_self_hash(value: dict[str, Any], label: str) -> str:
    semantic = dict(value)
    actual = semantic.pop("canonical_sha256", None)
    expected = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(type(actual) is str and actual == expected, f"{label} canonical SHA mismatch")
    return expected


def verify_receipt(value: dict[str, Any]) -> None:
    _verify_self_hash(value, "P4.4R receipt")
    _require(value.get("schema_version") == 1, "P4.4R receipt schema drifted")
    _require(value.get("policy_id") == "ATHENA_P4_4R_SHADOW_RUNTIME_COMPOSITION_STABILIZATION_V1",
             "P4.4R receipt policy identity drifted")
    _require(value.get("repository") == "Thabearr/ATHENA" and value.get("base_main_sha") == BASE_MAIN_SHA,
             "P4.4R base/repository identity drifted")
    trigger = value.get("trigger")
    _require(type(trigger) is dict
             and trigger.get("run_id") == RUN_ID
             and trigger.get("artifact_id") == ARTIFACT_ID
             and trigger.get("artifact_name") == f"athena-run-{RUN_ID}"
             and trigger.get("artifact_zip_sha256") == ARTIFACT_ZIP_SHA256
             and trigger.get("canonical_run_receipt_sha256") == "ac61df7db771239adaee2468ba6e5ae36152aa24b9dff53290f792048a3bc612"
             and trigger.get("inner_current_shadow_receipt_sha256") == "01ea33d43138e178079b4279c983eb2bb46b91bc05a7247ee9e33f988dfb1718",
             "P4.4R triggering run/artifact/receipt identity drifted")
    _require(value.get("source_review_counter_while_unmerged") == "3/5",
             "P4.4R source-review counter is not 3/5 while unmerged")
    _require(value.get("p4_4_complete") is False
             and value.get("architecture_checkpoint_e_complete") is False
             and value.get("canonical_shadow_successor_proof_complete") is False,
             "P4.4R must not close P4.4, Checkpoint E, or the live proof")
    _require(value.get("evidence_classification") == (
        "REAL_RETAINED_PROVIDER_EVIDENCE_PLUS_SYNTHETIC_MODEL_HISTORY_COMPOSITION"
    ), "P4.4R evidence classification drifted")
    _require(value.get("offline_only_authority") == {
        "provider_acquisition_during_implementation": 0,
        "workflow_dispatches_during_implementation": 0,
        "live_retries": 0,
        "share_code_network_actions": 0,
        "email_network_actions": 0,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
        "main_authority_expansion": False,
        "caller_migration": False,
        "workflow_retirement": False,
        "next_live_proof_authorized": False,
    }, "P4.4R authority/counter boundary drifted")
    pre = value.get("pre_fix_offline_replay")
    _require(type(pre) is dict
             and pre.get("result") == "REPRODUCED"
             and pre.get("same_live_failure_class") == "ShadowPriceError: unknown current Shadow source-context mode"
             and pre.get("live_boundary", {}).get("fixture_identity") == "FOTMOB:5071393"
             and pre.get("live_boundary", {}).get("provider_event_id") == "sr:match:66299604",
             "P4.4R pre-fix integration reproduction evidence is incomplete")
    _require(pre.get("historical_verifier_source_sha256") == (
                 "7f793abebe899c0a05eaf50a56dce6b97a5cb866039993d1e793a39bc97813c1"
             )
             and pre.get("historical_verifier_fixture_path") == PRE_FIX_VERIFIER_FIXTURE.as_posix()
             and pre.get("historical_verifier_fixture_sha256") == PRE_FIX_VERIFIER_FIXTURE_SHA256
             and pre.get("historical_verifier_fixture_source_slice_sha256") == PRE_FIX_VERIFIER_SOURCE_SLICE_SHA256
             and pre.get("historical_verifier_fixture_provenance") == (
                 "VERIFIED_SOURCE_SLICE_FROM_EXACT_BASE_MAIN; LF_TERMINATOR_NORMALIZED"
             )
             and pre.get("historical_verifier_loaded_from_pinned_source_fixture") is True
             and "historical_verifier_loaded_from_exact_base_git_object" not in pre,
             "P4.4R pre-fix verifier fixture provenance is incomplete or overclaimed")
    post = value.get("post_fix_offline_replay")
    _require(type(post) is dict
             and post.get("result") == "ADVANCED_THROUGH_PORTFOLIO_BOUNDARY"
             and post.get("network_sentinel") == "PASS_ZERO_OUTBOUND_CALLS"
             and post.get("same_live_fixture_event") == ["FOTMOB:5071393", "sr:match:66299604"],
             "P4.4R post-fix replay result is incomplete")
    deterministic = value.get("determinism")
    _require(type(deterministic) is dict
             and deterministic.get("replay_count") == 2
             and deterministic.get("canonical_outputs_byte_identical") is True
             and deterministic.get("terminal_internal_classification_identical") is True,
             "P4.4R deterministic replay evidence is incomplete")
    _require(value.get("composition_inventory_path") == INVENTORY_PATH.as_posix(),
             "P4.4R composition inventory path drifted")
    corrections = value.get("review_corrections")
    _require(corrections == {
        "reviewed_head_before_correction": "61c711cfbe8f543251970d6e257531f450a149f9",
        "legacy_builder_preserves_explicit_runtime_binding": True,
        "legacy_bridge_exact_replay_regression": True,
        "mode_correct_verifier_policy_memo_identity": True,
        "policy_mismatch_rejected_before_memo": True,
        "unknown_mode_fails_closed_before_memo": True,
        "binding_identity_remains_a_memo_key_dimension": True,
        "source_controlled_runtime_binding_policy_unchanged": True,
    }, "P4.4R corrective review evidence is incomplete")


def _verify_fixture_files(root: Path, expected_shas: dict[str, str] | None = None) -> None:
    for relative, expected in (expected_shas or FIXTURE_SHAS).items():
        path = root / FIXTURE_ROOT / relative
        try:
            # Git's core.autocrlf may materialize these reviewed text fixtures
            # with CRLF on Windows. Their pinned identities are over the LF
            # Git/source bytes, so normalize only checkout line endings before
            # checking the historical source identity.
            fixture_bytes = path.read_bytes().replace(b"\r\n", b"\n")
            actual = hashlib.sha256(fixture_bytes).hexdigest()
        except OSError as exc:
            raise P44RError(f"retained P4.4R fixture is missing: {relative}") from exc
        _require(actual == expected, f"retained P4.4R fixture SHA drifted: {relative}")


def _historical_paths_from_base(root: Path) -> list[tuple[str, str]]:
    try:
        output = subprocess.check_output(
            ["git", "ls-tree", "-r", "-z", BASE_MAIN_SHA, "--", "artifacts/architecture"],
            cwd=root,
        )
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        raise P44RError("P4.4R historical receipt base is not available in local Git") from exc
    rows: list[tuple[str, str]] = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        metadata, path_bytes = entry.split(b"\t", 1)
        _mode, _kind, object_id = metadata.decode("ascii").split()
        relative = path_bytes.decode("utf-8")
        if (
            relative.endswith(".json")
            and ("p4_4" in Path(relative).name or Path(relative).name.startswith("post_p4_4"))
            and "p4_4r" not in Path(relative).name
        ):
            rows.append((relative, object_id))
    return rows


def _verify_historical_receipts_unchanged(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    paths = _historical_paths_from_base(root)
    _require(paths, "historical P4.4 receipts were not found at base main")
    for relative, object_id in paths:
        try:
            before = subprocess.check_output(["git", "cat-file", "blob", object_id], cwd=root)
            after = (root / relative).read_bytes()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise P44RError(f"historical P4.4 receipt disappeared: {relative}") from exc
        # Windows checkout may normalize JSON line endings; all other bytes,
        # including embedded canonical hashes and semantic fields, stay exact.
        _require(
            before.replace(b"\r\n", b"\n") == after.replace(b"\r\n", b"\n"),
            f"historical P4.4 receipt was rewritten: {relative}",
        )
        hashes[relative] = hashlib.sha256(before).hexdigest()
    for relative, expected in HISTORICAL_RECEIPT_SHA256.items():
        if expected:
            _require(hashes.get(relative) == expected, f"historical receipt SHA mismatch: {relative}")
    return hashes


def _function_source(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
            return item
    raise P44RError(f"required runtime function is missing: {name}")


def _verify_runtime_composition(root: Path) -> None:
    builder_parameters = inspect.signature(
        quote_binding.build_current_shadow_price_context
    ).parameters
    _require(
        "runtime_bindings" in builder_parameters
        and builder_parameters["runtime_bindings"].default is None,
        "legacy context builder must preserve an optional reviewed runtime binding",
    )
    mode_policies = {
        quote_binding.LEGACY_PR253_FIXTURE_BRIDGE: quote_binding.SOURCE_CONTEXT_POLICY_ID,
        quote_binding.CURRENT_RECONCILIATION_DIRECT: (
            quote_binding.CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID
        ),
        quote_binding.FRESH_REPRICE_MODE: quote_binding.FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    }
    for mode, expected_policy in mode_policies.items():
        _require(
            runtime_bindings._expected_verifier_policy_id(SimpleNamespace(
                source_context_mode=mode,
                source_context_policy_id=expected_policy,
            )) == expected_policy,
            f"runtime binding uses an incorrect verifier policy identity for {mode}",
        )
    try:
        runtime_bindings._expected_verifier_policy_id(SimpleNamespace(
            source_context_mode="UNKNOWN_REVIEWED_MODE",
            source_context_policy_id="unreviewed",
        ))
    except Exception as exc:
        _require(
            type(exc).__name__ == "ShadowPriceError"
            and "unknown current Shadow source-context mode" in str(exc),
            "unknown source-context mode no longer fails closed with the reviewed error",
        )
    else:
        raise P44RError("unknown source-context mode gained memo policy authority")

    try:
        verifier_fixture = (root / PRE_FIX_VERIFIER_FIXTURE).read_bytes().replace(
            b"\r\n", b"\n"
        )
    except OSError as exc:
        raise P44RError("pinned P4.4R pre-fix verifier source slice is missing") from exc
    _require(
        hashlib.sha256(verifier_fixture).hexdigest() == PRE_FIX_VERIFIER_FIXTURE_SHA256,
        "pinned P4.4R pre-fix verifier source slice SHA drifted",
    )
    try:
        old_tree = ast.parse(verifier_fixture.decode("utf-8"))
    except (UnicodeError, SyntaxError) as exc:
        raise P44RError("pinned P4.4R pre-fix verifier source slice is invalid") from exc
    old_verifier = _function_source(old_tree, "verify_current_shadow_price_context")
    old_strings = {
        node.value for node in ast.walk(old_verifier)
        if isinstance(node, ast.Constant) and type(node.value) is str
    }
    old_names = {
        node.id for node in ast.walk(old_verifier) if isinstance(node, ast.Name)
    }
    _require(
        "unknown current Shadow source-context mode" in old_strings
        and "LEGACY_PR253_FIXTURE_BRIDGE" in old_names
        and "CURRENT_RECONCILIATION_DIRECT" in old_names
        and "PRF_CURRENT_RECONCILIATION_FRESH_REPRICE" not in old_strings,
        "pinned P4.4R verifier slice no longer represents the pre-fix mode gate",
    )

    relevant = {
        "scripts/execute_current_shadow_all_market_fresh_reprice.py": {
            "_install_fresh_reprice_worker", "issued_contexts",
        },
        "scripts/execute_current_shadow_all_market_fresh_reprice_bound.py": {
            "verify_current_shadow_price_context",
        },
        "scripts/execute_current_shadow_all_market.py": {
            "_install_price_context_verification_reuse", "_install_portfolio_reconciliation_dispatch",
        },
        "domain/current_shadow_canonical_core_adapter.py": {
            "_with_price_context_verifier", "_with_portfolio_reconciliation",
        },
    }
    for relative, forbidden in relevant.items():
        try:
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise P44RError(f"cannot inspect P4.4R runtime source: {relative}") from exc
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        _require(not (forbidden & (names | attrs)),
                 f"removed semantic mutation/relay remains in {relative}")

    for relative, function in (
        ("domain/current_shadow_all_market_price_all.py", "price_all_shadow_fixture"),
        ("domain/current_shadow_all_market_router.py", "route_shadow_price_results"),
        ("domain/current_shadow_all_market_portfolio.py", "build_shadow_portfolio_router_input"),
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=relative)
        node = _function_source(tree, function)
        identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        _require("runtime_bindings_for_context" in identifiers,
                 f"{relative}:{function} does not select the stable runtime binding")

    bindings = runtime_bindings.policy_payload(composition=runtime_bindings.FRESH_REPRICE_COMPOSITION)
    fresh = bindings["fresh_reprice_contract"]
    _require(bindings["semantic_correctness_depends_on_monkeypatch_install_order"] is False
             and fresh["fresh_observation_strictly_newer_than_reconciliation_and_prior_quote"] is True
             and fresh["evaluation_time_equals_fresh_observation"] is True
             and fresh["worker_local_issued_context_registry_is_authority"] is False,
             "source-controlled fresh-reprice binding semantic contract drifted")


def verify_context_verifier_source_supersession(
    root: Path,
    receipt: dict[str, Any],
    current_source_sha256: str,
) -> bool:
    """Accept a later verifier source only through exact P4.4S ancestry."""

    historical_sha256 = receipt["before_after_contracts"]["context_verifier_source"][
        "sha256_after"
    ]
    if historical_sha256 == current_source_sha256:
        return False
    supersession = _read_json(
        root,
        "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json",
    )
    _verify_self_hash(supersession, "P4.4S forward supersession")
    source_transition = supersession.get("source_transition")
    p4_4r_supersession = supersession.get("p4_4r_supersession")
    _require(
        supersession.get("policy_id")
        == "ATHENA_P4_4S_CANONICAL_ADAPTER_BOUND_CONTEXT_BUILDER_V1"
        and supersession.get("base_main_sha")
        == "adc7ee762cb7479a41184863c76fd5d0696ad7e9"
        and type(source_transition) is dict
        and source_transition.get("context_verifier_source_before_sha256")
        == historical_sha256
        and source_transition.get("context_verifier_source_after_sha256")
        == current_source_sha256
        and type(p4_4r_supersession) is dict
        and p4_4r_supersession.get("receipt_canonical_sha256")
        == receipt.get("canonical_sha256")
        and p4_4r_supersession.get("historical_receipt_rewritten") is False,
        "P4.4R current verifier source differs without the exact P4.4S supersession",
    )
    return True


def audit(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path.cwd()).resolve()
    receipt = _read_json(root, RECEIPT_PATH)
    verify_receipt(receipt)
    inventory = _read_json(root, INVENTORY_PATH)
    inventory_sha = _verify_self_hash(inventory, "P4.4R composition inventory")
    _require(receipt.get("composition_inventory_sha256") == inventory_sha,
             "P4.4R receipt does not bind the exact composition inventory")
    _require(inventory.get("base_main_sha") == BASE_MAIN_SHA
             and inventory.get("post_refactor_composition", {}).get("fresh_context_mode") == "PRF_CURRENT_RECONCILIATION_FRESH_REPRICE",
             "P4.4R composition inventory identity/current path drifted")
    disposition = inventory["post_refactor_composition"]["runtime_mutation_disposition"]
    _require(set(disposition["removed_semantic_mutations"]) == {
        "bound.stale-verifier-relay",
        "fresh.quote-verifier-and-issued-context-registry",
        "fresh.portfolio-builder-override",
        "fresh.acquire-router-inputs-override",
        "all-market.price-context-verification-cache",
        "all-market-portfolio-reconciliation-facade",
        "canonical-adapter-price-verifier-relay",
        "canonical-adapter-portfolio-reconciliation-relay",
    }, "P4.4R composition inventory does not enumerate removed semantic mutations")
    _verify_fixture_files(root)
    _verify_runtime_composition(root)

    source_sha = pc_source.calculate_policy_sha256()
    current_runtime_sha = pc_runtime.calculate_policy_sha256()
    if current_runtime_sha != PC_RUNTIME_SHA256:
        from scripts import audit_inc_20261010_pc_upcoming_bounded_epoch_stabilization as pc_successor
        successor = pc_successor.audit_current(root)
        _require(
            successor.get("runtime_policy_sha256") == current_runtime_sha,
            "P4.4R current pcUpcoming runtime lacks reviewed successor ancestry",
        )
    _require(source_sha == PC_SOURCE_SHA256
             and current_runtime_sha in {PC_RUNTIME_SHA256, pc_runtime.PINNED_POLICY_SHA256}
             and team_labels.EXPECTED_POLICY_SHA256 == TEAM_LABEL_SHA256
             and identity_compatibility.EXPECTED_POLICY_SHA256 == IDENTITY_SHA256
             and bridge.PINNED_POLICY_SHA256 == BRIDGE_SHA256
             and identity_v2.REGISTRY_SHA256 == V2_SHA256
             and identity_v2.SEED_REGISTRY_SHA256 == V2_SEED_SHA256,
             "P4.4R changed a frozen provider/identity source policy")
    contracts = receipt["before_after_contracts"]
    verifier_sha = hashlib.sha256(
        (root / "domain/_current_shadow_quote_binding.py")
        .read_bytes()
        .replace(b"\r\n", b"\n")
    ).hexdigest()
    verify_context_verifier_source_supersession(root, receipt, verifier_sha)
    _require(contracts["runtime_binding_policy"]["policy_id"] == runtime_bindings.POLICY_ID
             and contracts["runtime_binding_policy"]["sha256_after_standard"] == runtime_bindings.policy_sha256(
                 composition=runtime_bindings.STANDARD_COMPOSITION
             )
             and contracts["runtime_binding_policy"]["sha256_after_fresh_reprice"] == runtime_bindings.policy_sha256(
                 composition=runtime_bindings.FRESH_REPRICE_COMPOSITION
             ), "P4.4R runtime binding policy hash drifted")
    try:
        base_workflow = subprocess.check_output(
            ["git", "show", f"{BASE_MAIN_SHA}:.github/workflows/athena-run.yml"], cwd=root
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise P44RError("exact-main workflow bytes are unavailable") from exc
    base_workflow = base_workflow.replace(b"\r\n", b"\n")
    canonical_workflow = receipt["before_after_contracts"]["canonical_workflow"]
    _require(
        hashlib.sha256(base_workflow).hexdigest()
        == canonical_workflow.get("base_main_git_blob_sha256")
        == canonical_workflow.get("after_git_blob_sha256")
        and canonical_workflow.get("unchanged") is True,
        "P4.4R exact-base workflow evidence differs from its immutable receipt",
    )
    workflow_paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", ".github/workflows"], cwd=root
    ).decode("utf-8").splitlines()
    _require(len([item for item in workflow_paths if item.endswith((".yml", ".yaml"))]) == 39,
             "P4.4R changed the workflow count")
    from scripts import audit_p4_workflow_evolution_ledger as evolution
    try:
        ledger = evolution.validate_current_state()
    except evolution.WorkflowEvolutionError as exc:
        raise P44RError("current workflow evolution is not authenticated") from exc
    _require(ledger.get("current_live_workflow_count") == 39
             and ledger.get("current_p4_3_retired_workflow_count") == 3,
             "P4.4R changed workflow/retirement governance counts")
    try:
        evolved_workflow = evolution.resolve_reviewed_transition_after_source(
            ".github/workflows/athena-run.yml",
            "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1",
        )
    except evolution.WorkflowEvolutionError as exc:
        raise P44RError("historical P4.4M workflow revision is not authenticated") from exc
    _require(
        hashlib.sha256(evolved_workflow).hexdigest()
        == canonical_workflow.get("base_main_git_blob_sha256"),
        "P4.4R base workflow no longer chains through the reviewed evolution history",
    )
    historical = _verify_historical_receipts_unchanged(root)
    _require(receipt.get("historical_receipt_immutability") == {
        "verified": True,
        "compared_receipt_count": len(historical),
        "base_main_sha": BASE_MAIN_SHA,
    }, "P4.4R historical receipt immutability result drifted")
    return {
        "status": "PASS",
        "receipt_sha256": receipt["canonical_sha256"],
        "inventory_sha256": inventory_sha,
        "fixture_count": len(FIXTURE_SHAS),
        "historical_receipt_count": len(historical),
        "runtime_binding_standard_sha256": runtime_bindings.policy_sha256(
            composition=runtime_bindings.STANDARD_COMPOSITION
        ),
        "runtime_binding_fresh_sha256": runtime_bindings.policy_sha256(
            composition=runtime_bindings.FRESH_REPRICE_COMPOSITION
        ),
        "network_provider_live_side_effects": 0,
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
