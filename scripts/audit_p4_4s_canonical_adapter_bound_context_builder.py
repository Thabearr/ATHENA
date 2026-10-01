from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from domain import _current_shadow_quote_binding as quote_binding
from domain import current_shadow_all_market_price_all as price_all
from domain import current_shadow_canonical_core_adapter as adapter


BASE_MAIN_SHA = "adc7ee762cb7479a41184863c76fd5d0696ad7e9"
POLICY_ID = "ATHENA_P4_4S_CANONICAL_ADAPTER_BOUND_CONTEXT_BUILDER_V1"
RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json"
)
P4_4R_RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json"
)
P4_4R_RECEIPT_SHA256 = (
    "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552"
)
P4_4S_RECEIPT_SHA256 = "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3"
QUOTE_BINDING_BEFORE_SHA256 = (
    "2706d8e1b689be153cf6b0de545cfed00f7ee953707a7094f70e6df1344557de"
)
QUOTE_BINDING_AFTER_SHA256 = (
    "689193a9b9f50229b38e7a024189f6aaa9a5c85235e5575895bb398a535e76ff"
)
ADAPTER_BEFORE_SHA256 = (
    "777ab4b88ae0c761f17e96d6904e74e94b61deffaf50a51861dcb8162a47cc71"
)
ADAPTER_AFTER_SHA256 = (
    "bf1a9acff635a378f81bafa73f8274a4b9806e34d8d7c3ca13bad1729e205ce2"
)
# Current-source forward only: explicit verified release-resource resolution.
# The historical P4.4S transition identities above and receipt remain immutable.
PORT02C_ADAPTER_SUCCESSOR_SHA256 = (
    "518f0c08022650b7adcf8869e870e6574552e42e8d6bda4abab8a65112f2dff3"
)


class P44SError(AssertionError):
    """Raised when P4.4S adapter ownership evidence drifts."""


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
        raise P44SError(message)


def _read_json(root: Path, path: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44SError(f"required P4.4S architecture evidence missing: {path}") from exc
    _require(type(value) is dict, f"P4.4S evidence must be an object: {path}")
    return value


def _verify_self_hash(value: dict[str, Any], label: str) -> str:
    semantic = dict(value)
    claimed = semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(type(claimed) is str and claimed == actual, f"{label} canonical SHA mismatch")
    return actual


def _lf_source_sha256(root: Path, relative: str) -> str:
    try:
        data = (root / relative).read_bytes()
    except OSError as exc:
        raise P44SError(f"source file missing: {relative}") from exc
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def verify_receipt(value: dict[str, Any], *, root: Path | None = None) -> str:
    digest = _verify_self_hash(value, "P4.4S receipt")
    _require(digest == P4_4S_RECEIPT_SHA256, "P4.4S receipt identity is not pinned")
    _require(value.get("schema_version") == 1, "P4.4S schema drifted")
    _require(value.get("policy_id") == POLICY_ID, "P4.4S policy identity drifted")
    _require(
        value.get("repository") == "Thabearr/ATHENA"
        and value.get("base_main_sha") == BASE_MAIN_SHA,
        "P4.4S repository/base identity drifted",
    )
    trigger = value.get("trigger")
    _require(
        type(trigger) is dict
        and trigger.get("run_id") == 36336675870
        and trigger.get("artifact_id") == 10937532097
        and trigger.get("artifact_name") == "athena-run-36336675870"
        and trigger.get("artifact_zip_sha256")
        == "78498c5eea46dfaedb0376822360f0afe8585e68a5c98a7547b9ac658b27f623"
        and trigger.get("head_sha") == BASE_MAIN_SHA
        and trigger.get("attempt") == 1
        and trigger.get("artifact_digest_verified_from_github") is True
        and trigger.get("canonical_run_receipt_sha256")
        == "6085ade6250030f8edc0488fa147db2818da6d6e9e5c2e9bd2f2dfc08db33b2f"
        and trigger.get("failure_diagnostic_sha256")
        == "54f9c2d57be2b0890f628a66fa10b659e7815f827c573a96580cec7ec4969598"
        and trigger.get("pc_upcoming_stabilization_sha256")
        == "919ff6feb9c654515982056e4b1773d743df93cc69b7562486484687a6030984"
        and trigger.get("fixture_identity") == "FOTMOB:5071387"
        and trigger.get("provider_event_id") == "sr:match:66299608"
        and trigger.get("failure_stage") == "CONTEXT_BUILD_STARTED"
        and trigger.get("supervisor_return_code") == 1
        and trigger.get("terminal_receipt_accepted") is False
        and trigger.get("wager_placed") is False,
        "P4.4S trigger-run provenance or failure classification drifted",
    )
    retained = trigger.get("retained_artifact_file_sha256")
    _require(
        type(retained) is dict
        and retained.get("athena-run-workflow/resolved-run-request.json")
        == "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"
        and retained.get(
            "athena-runs/0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4/athena-run-receipt.json"
        )
        == trigger.get("canonical_run_receipt_sha256")
        and retained.get(
            "athena-runs/0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4/current-shadow/current-shadow-price-stage-diagnostic.json"
        )
        == trigger.get("failure_diagnostic_sha256")
        and retained.get(
            "athena-run-workflow/source-evidence/current-shadow-sportybet-pc-upcoming-discovery/runtime-capture-stabilization.json"
        )
        == trigger.get("pc_upcoming_stabilization_sha256"),
        "retained artifact file hash ancestry drifted",
    )
    transition = value.get("source_transition")
    _require(
        type(transition) is dict
        and transition.get("context_verifier_source_before_sha256")
        == QUOTE_BINDING_BEFORE_SHA256
        and transition.get("context_verifier_source_after_sha256")
        == QUOTE_BINDING_AFTER_SHA256
        and transition.get("canonical_adapter_source_before_sha256")
        == ADAPTER_BEFORE_SHA256
        and transition.get("canonical_adapter_source_after_sha256")
        == ADAPTER_AFTER_SHA256
        and transition.get("runtime_binding_policy_changed") is False
        and transition.get("price_all_source_changed") is False
        and transition.get("provider_or_reconciliation_semantics_changed") is False
        and transition.get("workflow_yaml_changed") is False,
        "P4.4S source transition or authority boundary drifted",
    )
    authority = value.get("authority_and_governance")
    _require(
        type(authority) is dict
        and authority.get("provider_acquisition_during_implementation") == 0
        and authority.get("workflow_dispatches_during_implementation") == 0
        and authority.get("live_retries") == 0
        and authority.get("share_code_network_actions") == 0
        and authority.get("wager_placed") is False
        and authority.get("source_review_counter_while_unmerged") == "4/5"
        and authority.get("p4_4_complete") is False
        and authority.get("architecture_checkpoint_e_complete") is False
        and authority.get("canonical_shadow_successor_proof_complete") is False
        and authority.get("next_live_proof_authorized") is False
        and authority.get("caller_migration_authorized") is False
        and authority.get("workflow_retirement_authorized") is False,
        "P4.4S authority/governance boundary drifted",
    )
    if root is not None:
        _require(
            _lf_source_sha256(root, "domain/_current_shadow_quote_binding.py")
            == QUOTE_BINDING_AFTER_SHA256
            and _lf_source_sha256(root, "domain/current_shadow_canonical_core_adapter.py")
            == PORT02C_ADAPTER_SUCCESSOR_SHA256,
            "P4.4S current source differs from exact PORT-02C installed-resource successor",
        )
    return digest


def verify_adapter_wiring() -> None:
    signature = inspect.signature(
        quote_binding.build_current_shadow_price_context_from_reconciliation
    )
    runtime_parameter = signature.parameters.get("runtime_bindings")
    _require(
        runtime_parameter is not None
        and runtime_parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and runtime_parameter.default is None,
        "public direct context builder lacks optional keyword-only runtime_bindings",
    )
    builder_source = inspect.getsource(
        quote_binding.build_current_shadow_price_context_from_reconciliation
    )
    builder_tree = ast.parse(builder_source)
    bound_calls = [
        node
        for node in ast.walk(builder_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_build_current_shadow_price_context_from_reconciliation_bound"
    ]
    _require(
        len(bound_calls) == 1
        and any(
            item.arg == "runtime_bindings"
            and isinstance(item.value, ast.Name)
            and item.value.id == "runtime_bindings"
            for item in bound_calls[0].keywords
        ),
        "public builder does not forward the supplied reviewed runtime binding",
    )

    adapter_source = inspect.getsource(
        adapter.build_current_shadow_price_context_from_reconciliation
    )
    adapter_tree = ast.parse(adapter_source)
    bad_private_lookups = [
        node
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "_build_current_shadow_price_context_from_reconciliation_bound"
    ]
    _require(not bad_private_lookups, "canonical adapter reaches across private helper ownership")
    public_delegations = [
        node
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "build_current_shadow_price_context_from_reconciliation"
        and isinstance(node.value, ast.Name)
        and node.value.id == "_legacy_price"
    ]
    _require(len(public_delegations) == 1, "canonical adapter does not delegate through public builder")
    _require(
        not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"setattr", "monkeypatch"}
            for node in ast.walk(adapter_tree)
        ),
        "canonical adapter reintroduced a runtime monkeypatch seam",
    )
    _require(
        not hasattr(price_all, "_build_current_shadow_price_context_from_reconciliation_bound"),
        "Price-all exported the private quote-binding helper to satisfy the adapter",
    )


def _verify_historical_receipts_from_p4_4s_receipt(
    root: Path, receipt: dict[str, Any]
) -> dict[str, str]:
    evidence = receipt.get("historical_receipt_immutability")
    _require(
        type(evidence) is dict
        and evidence.get("base_main_sha") == BASE_MAIN_SHA
        and evidence.get("compared_receipt_count") == 31,
        "P4.4S historical-receipt baseline identity drifted",
    )
    expected = evidence.get("sha256_by_path")
    _require(
        type(expected) is dict
        and len(expected) == 31
        and all(
            type(path) is str
            and path.startswith("artifacts/architecture/")
            and type(digest) is str
            and len(digest) == 64
            for path, digest in expected.items()
        ),
        "P4.4S historical-receipt SHA inventory is malformed",
    )
    candidates = {
        path.relative_to(root).as_posix()
        for path in (root / "artifacts/architecture").rglob("*.json")
        if ("p4_4" in path.name or path.name.startswith("post_p4_4"))
        and "p4_4r" not in path.name
        and "p4_4s" not in path.name
    }
    _require(
        candidates == set(expected),
        "P4.4S historical-receipt inventory differs from exact base-main set",
    )
    actual: dict[str, str] = {}
    for relative, expected_sha in expected.items():
        try:
            content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        except OSError as exc:
            raise P44SError(f"historical P4.4 receipt disappeared: {relative}") from exc
        actual_sha = hashlib.sha256(content).hexdigest()
        _require(
            actual_sha == expected_sha,
            f"historical P4.4 receipt was rewritten: {relative}",
        )
        actual[relative] = actual_sha
    return actual


def audit(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path.cwd()).resolve()
    receipt = _read_json(root, RECEIPT_PATH)
    receipt_sha = verify_receipt(receipt, root=root)
    verify_adapter_wiring()

    p4_4r_receipt = _read_json(root, P4_4R_RECEIPT_PATH)
    p4_4r_sha = _verify_self_hash(p4_4r_receipt, "historical P4.4R receipt")
    _require(p4_4r_sha == P4_4R_RECEIPT_SHA256, "historical P4.4R receipt changed")
    _require(
        p4_4r_receipt.get("before_after_contracts", {})
        .get("context_verifier_source", {})
        .get("sha256_after")
        == receipt["source_transition"]["context_verifier_source_before_sha256"],
        "P4.4S does not begin at the historical P4.4R context-verifier source",
    )

    # Reuse P4.4R's exact source-supersession verifier. The immutable historical
    # receipt inventory is pinned in this self-hashed P4.4S receipt so this
    # forward audit also works in hosted shallow checkouts lacking the base tree.
    from scripts import audit_p4_4r_shadow_runtime_composition_stabilization as p4_4r_audit

    current_verifier_sha = _lf_source_sha256(
        root, "domain/_current_shadow_quote_binding.py"
    )
    _require(
        p4_4r_audit.verify_context_verifier_source_supersession(
            root, p4_4r_receipt, current_verifier_sha
        ),
        "P4.4R source transition was not superseded by P4.4S",
    )
    historical_receipts = _verify_historical_receipts_from_p4_4s_receipt(root, receipt)
    return {
        "status": "PASS",
        "receipt_sha256": receipt_sha,
        "historical_p4_4r_receipt_sha256": p4_4r_sha,
        "context_verifier_source_sha256": QUOTE_BINDING_AFTER_SHA256,
        "canonical_adapter_source_sha256": PORT02C_ADAPTER_SUCCESSOR_SHA256,
        "historical_canonical_adapter_source_sha256": ADAPTER_AFTER_SHA256,
        "current_source_forward_classification": "PORT02C_EXPLICIT_VERIFIED_RELEASE_RESOURCE_RESOLUTION_ONLY",
        "p4_4r_historical_receipt_count": len(historical_receipts),
        "network_provider_share_wager_actions": 0,
    }


def main() -> int:
    print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
