"""Offline validator for cumulative P4.3 workflow retirement state."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable


POLICY_ID = "ATHENA_P4_3_WORKFLOW_RETIREMENT_LEDGER_V1"
MATRIX_PATH = Path("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json")
P43A_RECEIPT_PATH = Path("artifacts/architecture/p4_3a_workflow_capability_census_v1.json")
P43B_RECEIPT_PATH = Path("artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json")
P43C_RECEIPT_PATH = Path("artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json")
LEDGER_PATH = Path("artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json")
MATRIX_SHA256 = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
P43A_RECEIPT_SHA256 = "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b"
P43B_RECEIPT_SHA256 = "cf2371c7ec2747256f23599e7a43dd2d9e46ff61dda2c478a746d8bd8a49e72a"
BASELINE_WORKFLOW_COUNT = 40
WORKFLOW_DIR = Path(".github/workflows")
RETIRED = {
    ".github/workflows/current-sportybet-accumulator.yml": {
        "git_blob_sha1": "21400f2615a033c0b9df5dd943f469c0cae4c3e0",
        "source_sha256": "839925e6ad0ceee2452ef008da13d481bc34d445290444b30d6f0278510542c1",
        "fixture_path": "tests/fixtures/architecture/retired_workflows/current-sportybet-accumulator.yml",
        "retirement_phase": "P4.3B",
        "receipt_path": "artifacts/architecture/p4_3b_current_sportybet_workflow_retirement_v1.json",
        "receipt_sha256": P43B_RECEIPT_SHA256,
        "successor_workflow_path": ".github/workflows/athena-run.yml",
    },
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml": {
        "git_blob_sha1": "9f159f77e58f20082b5ecb0b092c1d7dab831897",
        "source_sha256": "f48cdda138081e2453896e3f94496c4744d9ed360c0b7e6a86fb14bc7fa58c63",
        "fixture_path": "tests/fixtures/architecture/retired_workflows/execute-fotmob-utc-native-successor-feature-qualification.yml",
        "retirement_phase": "P4.3C",
        "receipt_path": "artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json",
        "successor_workflow_path": ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
    },
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml": {
        "git_blob_sha1": "04c6f1d3c709acb2c90d69e39733b2297caa7e8a",
        "source_sha256": "39e961b07586a6de46ceb78c4281b189f783e15a8fc5023b08e2b5b6f03d416e",
        "fixture_path": "tests/fixtures/architecture/retired_workflows/execute-pr69-primary-time-basis-evidence-campaign.yml",
        "retirement_phase": "P4.3C",
        "receipt_path": "artifacts/architecture/p4_3c_spent_v1_evidence_workflow_retirement_v1.json",
        "successor_workflow_path": ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml",
    },
}
PROTECTED_LIVE = {
    ".github/workflows/athena-run.yml",
    ".github/workflows/current-shadow-all-market.yml",
    ".github/workflows/current-shadow-history-cache-prime.yml",
    ".github/workflows/athena-draft-ready-bridge.yml",
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
}


class RetirementLedgerError(AssertionError):
    """Raised when cumulative retirement evidence is inconsistent."""


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_sha256(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("canonical_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _git_blob_at_head(path: str) -> str:
    result = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], capture_output=True, text=True)
    if result.returncode:
        raise RetirementLedgerError(f"live workflow is not present in HEAD: {path}")
    return result.stdout.strip()


def p43c_receipt_evidence_sha256(receipt: dict[str, Any]) -> str:
    """Hash the P4.3C receipt body excluding its ledger backlink and self-hash.

    The cumulative ledger and P4.3C receipt bind one another without a cyclic hash:
    the ledger binds this evidence-body hash; the receipt binds the final ledger hash.
    """
    unsigned = dict(receipt)
    unsigned.pop("canonical_sha256", None)
    unsigned.pop("retirement_ledger_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def load_baseline() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        census = json.loads(P43A_RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementLedgerError("frozen P4.3A matrix/receipt is unreadable") from exc
    if matrix.get("canonical_sha256") != MATRIX_SHA256 or canonical_sha256(matrix) != MATRIX_SHA256:
        raise RetirementLedgerError("immutable P4.3A matrix identity changed")
    if census.get("canonical_sha256") != P43A_RECEIPT_SHA256 or canonical_sha256(census) != P43A_RECEIPT_SHA256:
        raise RetirementLedgerError("immutable P4.3A receipt identity changed")
    rows = matrix.get("workflow_rows")
    if matrix.get("workflow_count") != BASELINE_WORKFLOW_COUNT or not isinstance(rows, list) or len(rows) != BASELINE_WORKFLOW_COUNT:
        raise RetirementLedgerError("P4.3A baseline must remain exactly 40 workflows")
    return matrix, census


def _expected_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    p43c_receipt: dict[str, Any] | None = None
    if P43C_RECEIPT_PATH.exists():
        try:
            p43c_receipt = json.loads(P43C_RECEIPT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RetirementLedgerError("P4.3C receipt is unreadable") from exc
    for path, identity in RETIRED.items():
        entry = {
            "workflow_path": path,
            "git_blob_sha1": identity["git_blob_sha1"],
            "source_sha256": identity["source_sha256"],
            "fixture_path": identity["fixture_path"],
            "retirement_phase": identity["retirement_phase"],
            "retirement_receipt_path": identity["receipt_path"],
            "successor_workflow_path": identity["successor_workflow_path"],
        }
        if identity["retirement_phase"] == "P4.3B":
            entry["retirement_receipt_sha256"] = identity["receipt_sha256"]
        elif p43c_receipt is not None:
            entry["retirement_receipt_evidence_sha256"] = p43c_receipt_evidence_sha256(p43c_receipt)
        entries.append(entry)
    return sorted(entries, key=lambda entry: entry["workflow_path"])


def build_ledger(p43c_receipt_core: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path, identity in RETIRED.items():
        entry = {
            "workflow_path": path,
            "git_blob_sha1": identity["git_blob_sha1"],
            "source_sha256": identity["source_sha256"],
            "fixture_path": identity["fixture_path"],
            "retirement_phase": identity["retirement_phase"],
            "retirement_receipt_path": identity["receipt_path"],
            "successor_workflow_path": identity["successor_workflow_path"],
        }
        if identity["retirement_phase"] == "P4.3B":
            entry["retirement_receipt_sha256"] = identity["receipt_sha256"]
        else:
            entry["retirement_receipt_evidence_sha256"] = p43c_receipt_evidence_sha256(p43c_receipt_core)
        entries.append(entry)
    entries.sort(key=lambda entry: entry["workflow_path"])
    ledger: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "baseline_matrix_sha256": MATRIX_SHA256,
        "baseline_p4_3a_receipt_sha256": P43A_RECEIPT_SHA256,
        "baseline_workflow_count": BASELINE_WORKFLOW_COUNT,
        "retirements": entries,
        "current_retired_workflow_count": len(RETIRED),
        "current_live_workflow_count": BASELINE_WORKFLOW_COUNT - len(RETIRED),
        "retired_workflow_paths": sorted(RETIRED),
        "canonical_sha256": "",
    }
    ledger["canonical_sha256"] = canonical_sha256(ledger)
    return ledger


def _source_for_row(row: dict[str, Any]) -> bytes:
    path = row["workflow_path"]
    if path in RETIRED:
        fixture = Path(RETIRED[path]["fixture_path"])
        try:
            return fixture.read_bytes()
        except OSError as exc:
            raise RetirementLedgerError(f"retired workflow fixture missing: {fixture}") from exc
    try:
        return Path(path).read_bytes().replace(b"\r\n", b"\n")
    except OSError as exc:
        raise RetirementLedgerError(f"unretired workflow missing: {path}") from exc


def validate_ledger(
    ledger: dict[str, Any] | None = None,
    *,
    workflow_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    matrix, _census = load_baseline()
    if ledger is None:
        try:
            ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetirementLedgerError("cumulative retirement ledger is unreadable") from exc
    if ledger.get("schema_version") != 1 or ledger.get("policy_id") != POLICY_ID:
        raise RetirementLedgerError("retirement ledger schema/policy mismatch")
    if canonical_sha256(ledger) != ledger.get("canonical_sha256"):
        raise RetirementLedgerError("retirement ledger canonical SHA mismatch")
    if (
        ledger.get("baseline_matrix_sha256") != MATRIX_SHA256
        or ledger.get("baseline_p4_3a_receipt_sha256") != P43A_RECEIPT_SHA256
        or ledger.get("baseline_workflow_count") != BASELINE_WORKFLOW_COUNT
    ):
        raise RetirementLedgerError("retirement ledger baseline identity mismatch")
    expected_entries = _expected_entries()
    entries = ledger.get("retirements")
    if entries != expected_entries:
        raise RetirementLedgerError("cumulative ledger retirement entries do not match reviewed evidence")
    retired_paths = sorted(RETIRED)
    if ledger.get("retired_workflow_paths") != retired_paths:
        raise RetirementLedgerError("cumulative ledger retired path set mismatch")
    if (
        ledger.get("current_retired_workflow_count") != len(RETIRED)
        or ledger.get("current_live_workflow_count") != BASELINE_WORKFLOW_COUNT - len(RETIRED)
    ):
        raise RetirementLedgerError("cumulative ledger workflow count mismatch")

    rows = matrix["workflow_rows"]
    matrix_paths = [row["workflow_path"] for row in rows]
    if not set(RETIRED).issubset(matrix_paths):
        raise RetirementLedgerError("ledger contains a retired workflow absent from the baseline matrix")
    for row in rows:
        raw = _source_for_row(row)
        path = row["workflow_path"]
        identity = RETIRED.get(path)
        expected_blob = identity["git_blob_sha1"] if identity else row["git_blob_sha1"]
        expected_sha = identity["source_sha256"] if identity else row["source_sha256"]
        if _git_blob_sha1(raw) != expected_blob or _sha256(raw) != expected_sha:
            raise RetirementLedgerError(f"workflow source identity differs from baseline: {path}")
        if not identity and _git_blob_at_head(path) != row["git_blob_sha1"]:
            raise RetirementLedgerError(f"live workflow Git blob differs from baseline: {path}")
        if identity and Path(path).exists():
            raise RetirementLedgerError(f"retired executable workflow still exists: {path}")

    current = sorted(path.as_posix() for path in WORKFLOW_DIR.glob("*.yml"))
    expected_current = sorted(set(matrix_paths) - set(retired_paths))
    supplied = sorted(workflow_paths) if workflow_paths is not None else current
    if supplied != expected_current or current != expected_current:
        unexpected = sorted(set(supplied) ^ set(expected_current))
        raise RetirementLedgerError(f"live workflow set is not baseline minus the three reviewed retirements: {unexpected}")
    if len(current) != 37:
        raise RetirementLedgerError("current live workflow count must be exactly 37")
    for path in PROTECTED_LIVE:
        if path not in current:
            raise RetirementLedgerError(f"protected/canonical workflow is not live: {path}")

    try:
        p43b = json.loads(P43B_RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementLedgerError("immutable P4.3B receipt is unreadable") from exc
    if p43b.get("canonical_sha256") != P43B_RECEIPT_SHA256 or canonical_sha256(p43b) != P43B_RECEIPT_SHA256:
        raise RetirementLedgerError("immutable P4.3B receipt identity changed")
    try:
        p43c = json.loads(P43C_RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementLedgerError("P4.3C receipt is unreadable") from exc
    if p43c.get("canonical_sha256") != canonical_sha256(p43c):
        raise RetirementLedgerError("P4.3C receipt canonical SHA mismatch")
    if p43c.get("retirement_ledger_sha256") != ledger.get("canonical_sha256"):
        raise RetirementLedgerError("P4.3C receipt does not bind the cumulative ledger")
    if p43c_receipt_evidence_sha256(p43c) != next(
        entry["retirement_receipt_evidence_sha256"] for entry in entries if entry["retirement_phase"] == "P4.3C"
    ):
        raise RetirementLedgerError("P4.3C receipt evidence body does not match ledger entry")
    return ledger


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate current cumulative state offline")
    args = parser.parse_args()
    validate_ledger()
    print(f"P4.3 retirement ledger passed; sha256={json.loads(LEDGER_PATH.read_text(encoding='utf-8'))['canonical_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
