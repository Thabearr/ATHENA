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
P43C_LEDGER_SNAPSHOT_PATH = Path(
    "artifacts/architecture/p4_3_retirement_ledger_snapshots/p4_3c_workflow_retirement_ledger_v1.json"
)
MATRIX_SHA256 = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
P43A_RECEIPT_SHA256 = "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b"
P43B_RECEIPT_SHA256 = "cf2371c7ec2747256f23599e7a43dd2d9e46ff61dda2c478a746d8bd8a49e72a"
P43C_RECEIPT_SHA256 = "c4afd0d0052c7b14d643f7868d7eac85344042da20a9d7aa0e8bf3b59ab9bd24"
P43C_LEDGER_SNAPSHOT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
P43D_RETIREMENT_LEDGER_SHA256 = P43C_LEDGER_SNAPSHOT_SHA256
BASELINE_WORKFLOW_COUNT = 40
WORKFLOW_DIR = Path(".github/workflows")
LEDGER_FIELDS = {
    "schema_version", "policy_id", "baseline_matrix_sha256",
    "baseline_p4_3a_receipt_sha256", "baseline_workflow_count", "retirements",
    "current_retired_workflow_count", "current_live_workflow_count",
    "retired_workflow_paths", "canonical_sha256",
}
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


def _retirement_entries_by_path(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = ledger.get("retirements")
    if not isinstance(entries, list):
        raise RetirementLedgerError("retirement ledger entries must be a list")
    paths = [entry.get("workflow_path") if isinstance(entry, dict) else None for entry in entries]
    if any(type(path) is not str for path in paths) or len(paths) != len(set(paths)):
        raise RetirementLedgerError("retirement ledger paths must be unique strings")
    return {entry["workflow_path"]: entry for entry in entries}


def _validate_ledger_arithmetic(ledger: dict[str, Any], *, label: str) -> tuple[list[str], list[str]]:
    if not isinstance(ledger, dict) or set(ledger) != LEDGER_FIELDS:
        raise RetirementLedgerError(f"{label} schema fields mismatch")
    if ledger.get("schema_version") != 1 or ledger.get("policy_id") != POLICY_ID:
        raise RetirementLedgerError(f"{label} schema/policy mismatch")
    if canonical_sha256(ledger) != ledger.get("canonical_sha256"):
        raise RetirementLedgerError(f"{label} canonical SHA mismatch")
    if (
        ledger.get("baseline_matrix_sha256") != MATRIX_SHA256
        or ledger.get("baseline_p4_3a_receipt_sha256") != P43A_RECEIPT_SHA256
        or ledger.get("baseline_workflow_count") != BASELINE_WORKFLOW_COUNT
    ):
        raise RetirementLedgerError(f"{label} baseline identity mismatch")
    by_path = _retirement_entries_by_path(ledger)
    retired_paths = sorted(by_path)
    if ledger.get("retired_workflow_paths") != retired_paths:
        raise RetirementLedgerError(f"{label} retired path set mismatch")
    retired_count = len(retired_paths)
    live_count = BASELINE_WORKFLOW_COUNT - retired_count
    if (
        ledger.get("current_retired_workflow_count") != retired_count
        or ledger.get("current_live_workflow_count") != live_count
        or live_count < 0
    ):
        raise RetirementLedgerError(f"{label} workflow count arithmetic mismatch")
    return retired_paths, sorted(set(_baseline_paths()) - set(retired_paths))


def _baseline_paths() -> list[str]:
    matrix, _census = load_baseline()
    return [row["workflow_path"] for row in matrix["workflow_rows"]]


def validate_historical_snapshot_extension(
    snapshot: dict[str, Any], current: dict[str, Any]
) -> None:
    """Require the current ledger to monotonically extend a frozen phase snapshot.

    Old retirement records are immutable. Later reviewed phases may append rows,
    but may not rewrite an earlier source, fixture, phase, receipt, or successor.
    """
    snapshot_paths, _snapshot_live = _validate_ledger_arithmetic(snapshot, label="historical ledger snapshot")
    current_paths, _current_live = _validate_ledger_arithmetic(current, label="current retirement ledger")
    baseline_fields = (
        "baseline_matrix_sha256",
        "baseline_p4_3a_receipt_sha256",
        "baseline_workflow_count",
    )
    if any(snapshot.get(field) != current.get(field) for field in baseline_fields):
        raise RetirementLedgerError("current ledger changed the historical baseline")

    snapshot_entries = _retirement_entries_by_path(snapshot)
    current_entries = _retirement_entries_by_path(current)
    matrix_paths = set(_baseline_paths())
    if not set(current_paths).issubset(matrix_paths):
        raise RetirementLedgerError("current ledger retires a path absent from the P4.3A baseline")
    if not set(snapshot_paths).issubset(current_entries):
        raise RetirementLedgerError("current ledger removed a historical retirement")
    for path, entry in snapshot_entries.items():
        if current_entries.get(path) != entry:
            raise RetirementLedgerError(f"current ledger rewrote historical retirement metadata: {path}")

    snapshot_retired = len(snapshot_paths)
    current_retired = len(current_paths)
    snapshot_live = snapshot["current_live_workflow_count"]
    current_live = current["current_live_workflow_count"]
    if current_retired < snapshot_retired or current_live > snapshot_live:
        raise RetirementLedgerError("current ledger is not a monotonic retirement extension")
    if BASELINE_WORKFLOW_COUNT - snapshot_retired != snapshot_live:
        raise RetirementLedgerError("historical snapshot count arithmetic mismatch")
    if BASELINE_WORKFLOW_COUNT - current_retired != current_live:
        raise RetirementLedgerError("current ledger count arithmetic mismatch")


def validate_reviewed_retirement_entries(
    snapshot: dict[str, Any],
    current: dict[str, Any],
    *,
    expected_entries: list[dict[str, Any]],
) -> None:
    """Check a current ledger against an explicit, phase-reviewed entry set.

    The caller supplies ``expected_entries`` only after the corresponding phase
    evidence has been reviewed. This pure check is useful for testing a future
    reviewed extension without granting authority to the on-disk current ledger.
    Source fixtures and receipt bindings are still verified by
    :func:`validate_retirement_history`.
    """
    validate_historical_snapshot_extension(snapshot, current)
    if not isinstance(expected_entries, list):
        raise RetirementLedgerError("reviewed retirement entries must be a list")
    expected = sorted(expected_entries, key=lambda entry: entry.get("workflow_path", ""))
    actual = current.get("retirements")
    if actual != expected:
        raise RetirementLedgerError("cumulative ledger retirement entries do not match reviewed evidence")
    matrix, _ = load_baseline()
    rows = {row["workflow_path"]: row for row in matrix["workflow_rows"]}
    for entry in expected:
        path = entry.get("workflow_path")
        row = rows.get(path)
        if row is None:
            raise RetirementLedgerError(f"reviewed retirement is absent from the P4.3A baseline: {path}")
        if (
            entry.get("git_blob_sha1") != row.get("git_blob_sha1")
            or entry.get("source_sha256") != row.get("source_sha256")
        ):
            raise RetirementLedgerError(f"reviewed retirement source identity differs from baseline: {path}")


def _load_p43c_ledger_snapshot() -> dict[str, Any]:
    try:
        snapshot = json.loads(P43C_LEDGER_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementLedgerError("frozen P4.3C retirement ledger snapshot is unreadable") from exc
    if (
        snapshot.get("canonical_sha256") != P43C_LEDGER_SNAPSHOT_SHA256
        or canonical_sha256(snapshot) != P43C_LEDGER_SNAPSHOT_SHA256
    ):
        raise RetirementLedgerError("immutable P4.3C ledger snapshot identity changed")
    retired_paths, _live_paths = _validate_ledger_arithmetic(snapshot, label="P4.3C ledger snapshot")
    if len(retired_paths) != 3 or snapshot.get("current_live_workflow_count") != 37:
        raise RetirementLedgerError("P4.3C historical ledger snapshot must remain 3 retired / 37 live")
    return snapshot


def resolve_reviewed_workflow_source(
    path: str, *, ledger: dict[str, Any] | None = None
) -> bytes:
    """Resolve a P4.3A workflow from its live YAML or ledger-backed fixture.

    Passing ``ledger`` avoids recursive validation while ``validate_ledger`` is
    checking each row. Direct callers validate the current ledger first.
    """
    matrix, _census = load_baseline()
    row = next((item for item in matrix["workflow_rows"] if item.get("workflow_path") == path), None)
    if row is None:
        raise RetirementLedgerError(f"workflow path is absent from the frozen P4.3A matrix: {path}")
    if ledger is None:
        ledger = validate_ledger()
    entries = _retirement_entries_by_path(ledger)
    entry = entries.get(path)
    if entry is not None:
        if Path(path).exists():
            raise RetirementLedgerError(f"retired executable workflow unexpectedly exists: {path}")
        fixture_path = entry.get("fixture_path")
        try:
            raw = Path(fixture_path).read_bytes()
        except (TypeError, OSError) as exc:
            raise RetirementLedgerError(f"retired workflow fixture missing: {path}") from exc
        if (
            entry.get("git_blob_sha1") != row.get("git_blob_sha1")
            or entry.get("source_sha256") != row.get("source_sha256")
            or _git_blob_sha1(raw) != row.get("git_blob_sha1")
            or _sha256(raw) != row.get("source_sha256")
        ):
            raise RetirementLedgerError(f"retired workflow fixture identity differs from baseline: {path}")
        return raw

    try:
        raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    except OSError as exc:
        raise RetirementLedgerError(f"live workflow unexpectedly missing: {path}") from exc
    if (
        _git_blob_sha1(raw) != row.get("git_blob_sha1")
        or _sha256(raw) != row.get("source_sha256")
        or _git_blob_at_head(path) != row.get("git_blob_sha1")
    ):
        raise RetirementLedgerError(f"live workflow identity differs from baseline: {path}")
    return raw


def validate_retirement_history(ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify frozen P4.3 retirement evidence without granting current-tree authority."""
    matrix, _census = load_baseline()
    if ledger is None:
        try:
            ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetirementLedgerError("cumulative retirement ledger is unreadable") from exc
    retired_paths, _current_survivors = _validate_ledger_arithmetic(ledger, label="current retirement ledger")
    checkpoint = _load_p43c_ledger_snapshot()
    validate_historical_snapshot_extension(checkpoint, ledger)
    if checkpoint.get("canonical_sha256") != P43D_RETIREMENT_LEDGER_SHA256:
        raise RetirementLedgerError("P4.3D retirement checkpoint identity changed")
    # This exact reviewed-entry inventory advances only when a later P4.3
    # retirement phase adds its own audited fixture and receipt binding.
    expected_entries = _expected_entries()
    validate_reviewed_retirement_entries(checkpoint, ledger, expected_entries=expected_entries)
    entries = ledger.get("retirements")

    rows = matrix["workflow_rows"]
    matrix_paths = [row["workflow_path"] for row in rows]
    if not set(retired_paths).issubset(matrix_paths):
        raise RetirementLedgerError("ledger contains a retired workflow absent from the baseline matrix")
    by_row = {row["workflow_path"]: row for row in rows}
    for entry in entries:
        path = entry["workflow_path"]
        try:
            raw = Path(entry["fixture_path"]).read_bytes()
        except OSError as exc:
            raise RetirementLedgerError(f"retired workflow fixture missing: {path}") from exc
        row = by_row[path]
        if (
            _git_blob_sha1(raw) != row["git_blob_sha1"]
            or _sha256(raw) != row["source_sha256"]
            or entry["git_blob_sha1"] != row["git_blob_sha1"]
            or entry["source_sha256"] != row["source_sha256"]
        ):
            raise RetirementLedgerError(f"retired workflow fixture identity differs from baseline: {path}")

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
    if (
        p43c.get("canonical_sha256") != P43C_RECEIPT_SHA256
        or canonical_sha256(p43c) != P43C_RECEIPT_SHA256
    ):
        raise RetirementLedgerError("immutable P4.3C receipt identity changed")
    if p43c.get("retirement_ledger_sha256") != checkpoint.get("canonical_sha256"):
        raise RetirementLedgerError("P4.3C receipt does not bind its frozen historical ledger snapshot")
    if p43c_receipt_evidence_sha256(p43c) != next(
        entry["retirement_receipt_evidence_sha256"] for entry in entries if entry["retirement_phase"] == "P4.3C"
    ):
        raise RetirementLedgerError("P4.3C receipt evidence body does not match ledger entry")
    return ledger


def validate_ledger(
    ledger: dict[str, Any] | None = None,
    *,
    workflow_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Verify P4.3 history and delegate today's tree to the evolution ledger."""
    history = validate_retirement_history(ledger)
    from scripts import audit_p4_workflow_evolution_ledger as evolution_audit

    evolution_audit.validate_current_state(retirement_ledger=history, workflow_paths=workflow_paths)
    return history


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
