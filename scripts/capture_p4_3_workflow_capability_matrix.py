"""Capture P4.3 workflow capability metadata and read-only GitHub run history.

Default operation is offline and fails closed.  Only the explicit ``--capture``
switch calls the GitHub CLI, using ``gh run list`` read operations only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


BASE_MAIN_SHA = "475f1dcd825cd2ad32c9b9946b4a7ca24817433f"
POLICY_ID = "ATHENA_P4_3_WORKFLOW_CAPABILITY_MATRIX_V1"
WORKFLOW_DIR = ".github/workflows"
RUN_FIELDS = "databaseId,headSha,headBranch,event,status,conclusion,createdAt,updatedAt,url"

ALLOWED_FAMILIES = {
    "TESTS", "ATHENA_RUN", "ATHENA_INGEST_FUTURE", "ATHENA_RETRAIN_FUTURE",
    "ATHENA_BACKTEST_FUTURE", "ATHENA_PR_BRIDGE", "PROTECTED_RESEARCH",
    "RETAIN_PENDING_AUDIT",
}


class WorkflowHistoryAccessError(RuntimeError):
    """Live GitHub run-history query failed; never convert this into no history."""


class MainAdvanceError(RuntimeError):
    """The live capture base is no longer the reviewed main commit."""

PROTECTED_FRESH_HOLDOUT = {
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
}
CURRENT_SHADOW_BLOCKERS = [
    "scheduled SHADOW ownership not migrated",
    "notification/email capability not migrated",
    "persistent identity ancestry still consumes old workflow/artifact history",
    "live canonical SHADOW successor proof not established",
    "issue-comment compatibility still needs disposition",
]
SUPPORTED_ROOTS = {
    ".github/workflows/athena-run.yml",
    ".github/workflows/athena-draft-ready-bridge.yml",
    ".github/workflows/athena-patch-bridge.yml",
    ".github/workflows/tests.yml",
    ".github/workflows/current-shadow-all-market.yml",
    ".github/workflows/current-shadow-history-cache-prime.yml",
    ".github/workflows/current-shadow-sportybet-source-diagnostic.yml",
    ".github/workflows/current-sportybet-accumulator.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml",
    ".github/workflows/verify-fotmob-fresh-holdout-history-pagination.yml",
    ".github/workflows/issue-current-fotmob-reviewed-source.yml",
    ".github/workflows/p3-0-comparison-evidence-capture.yml",
    ".github/workflows/p3-0-e1-owner-dispatch-bridge.yml",
}
DATE_HARDCODED_PATHS = {
    ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml",
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml",
    ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml",
    ".github/workflows/probe-sportybet-direct-20-markets.yml",
    ".github/workflows/prove-sportybet-direct-share-code.yml",
    ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml",
    ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
    ".github/workflows/verify-saturday-competition-review-priority.yml",
}
KNOWN_CONSUMERS: dict[str, list[str]] = {
    ".github/workflows/current-shadow-all-market.yml": [
        ".github/workflows/athena-run.yml",
        ".github/workflows/p3-0-comparison-evidence-capture.yml",
    ],
    ".github/workflows/current-shadow-history-cache-prime.yml": [
        ".github/workflows/athena-run.yml",
        ".github/workflows/current-shadow-all-market.yml",
        ".github/workflows/p3-0-comparison-evidence-capture.yml",
    ],
    ".github/workflows/build-historical-warehouse.yml": [
        ".github/workflows/prepare-canonical-drive-transfer.yml",
    ],
    ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml": [
        ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml",
        ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
        ".github/workflows/verify-saturday-competition-review-priority.yml",
    ],
    ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml": [
        ".github/workflows/verify-fotmob-real-player-context-array-admission.yml",
        ".github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml",
        ".github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml",
    ],
}

SPECIAL_PURPOSE: dict[str, tuple[str, list[str], str, str, bool]] = {
    ".github/workflows/athena-run.yml": (
        "Canonical parameterized RunRequest to AthenaRunService transport.",
        ["canonical manual and scheduled run request transport"], "ATHENA_RUN", "CANONICAL_RETAIN", False,
    ),
    ".github/workflows/tests.yml": (
        "Authoritative hosted syntax and sharded pytest validation.",
        ["syntax validation", "eight test shards", "aggregate test result"], "TESTS", "CANONICAL_RETAIN", False,
    ),
    ".github/workflows/current-shadow-all-market.yml": (
        "Active scheduled and operator-requested Current Shadow multi-market research run.",
        ["scheduled Shadow execution", "issue-comment compatibility", "identity and history artifact ancestry", "optional notification"],
        "ATHENA_RUN", "RETAIN_ACTIVE_PENDING_CANONICAL_SHADOW_MIGRATION", False,
    ),
    ".github/workflows/current-sportybet-accumulator.yml": (
        "Legacy target-only MAIN fail-closed SportyBet request workflow.",
        ["target_size request wrapper", "Phase-6 authority fail-closed response"], "ATHENA_RUN", "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED", True,
    ),
}
PURPOSE_OVERRIDES: dict[str, tuple[str, list[str], str, str, bool]] = {
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml": ("Audits Fresh Holdout Actions run lineage and receipt projections.", ["lineage/run metadata validation", "audit artifact production"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": ("Bridges completed Fresh Holdout runs into continuity receipts.", ["workflow_run completion handling", "continuity receipt binding", "issue-comment compatibility"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
    ".github/workflows/build-historical-warehouse.yml": ("Builds and validates the historical football-data warehouse.", ["historical data ingestion", "warehouse/CSV outputs", "season completeness evidence"], "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST", False),
    ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml": ("Captures the fixed Saturday fixture universe used by later review workflows.", ["fixed-date fixture capture", "source fixture-universe artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/create-saturday-2026-08-22-sportybet-direct-20-code.yml": ("Historical fixed-date direct SportyBet share-code proof workflow.", ["fixed protocol and selections", "direct share-code proof artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/current-shadow-history-cache-prime.yml": ("Produces and validates the durable Current Shadow history-prime artifact.", ["history cache prime", "Current Shadow prerequisite artifact"], "PROTECTED_RESEARCH", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/current-shadow-sportybet-source-diagnostic.yml": ("Runs a bounded Current Shadow SportyBet source diagnostic.", ["operator source diagnostic", "diagnostic evidence artifact"], "PROTECTED_RESEARCH", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml": ("Captures ordinary full-time FotMob source-history evidence.", ["source-history campaign", "run-scoped evidence artifact"], "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST", False),
    ".github/workflows/execute-fotmob-prospective-player-context-campaign.yml": ("Captures a fixed-date prospective player-context source campaign.", ["fixed-date player context capture", "shared campaign artifact"], "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST", False),
    ".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml": ("Runs a bounded UTC-native expected-goals model validation campaign.", ["model validation evidence", "run-scoped validation artifact"], "ATHENA_RETRAIN_FUTURE", "RETAIN_PENDING_FUTURE_RETRAIN", False),
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml": ("Qualifies successor features using the v2 research evidence path.", ["history materialization and feature construction", "v2 qualification evidence"], "ATHENA_RETRAIN_FUTURE", "RETAIN_PENDING_FUTURE_RETRAIN", False),
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml": ("Historical predecessor successor-feature qualification workflow.", ["predecessor feature qualification", "run-scoped qualification artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml": ("Stages v2 primary-time-basis evidence for the PR69 research lane.", ["v2 evidence campaign", "run-scoped staging artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml": ("Stages predecessor primary-time-basis evidence for the PR69 research lane.", ["predecessor evidence campaign", "run-scoped staging artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml": ("Mirrors completed Fresh Holdout receipts into durable release evidence.", ["workflow_run completion receipt mirror", "release/contents write capability"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml": ("Collects the protected prospective UTC-native expected-goals Fresh Holdout.", ["scheduled and explicit continuity collection", "release receipt evidence"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
    ".github/workflows/issue-current-fotmob-reviewed-source.yml": ("Captures reviewed FotMob source evidence for an explicit fixture date.", ["reviewed source capture", "captured match-data artifact"], "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST", False),
    ".github/workflows/p3-0-comparison-evidence-capture.yml": ("Captures paired P3.0 comparison evidence and source diagnostics.", ["comparison evidence capture", "current Shadow/history artifact reads"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/p3-0-e1-owner-dispatch-bridge.yml": ("Enforces the owner-gated P3.0-E1 dispatch bridge.", ["owner authorization gate", "Actions dispatch capability"], "ATHENA_PR_BRIDGE", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/pr258-sportybet-live-transport-proof.yml": ("Historical PR258 SportyBet live-transport proof workflow.", ["live transport proof artifact", "PR/dispatch verification"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/prb-sportybet-semantic-registry-proof.yml": ("Validates SportyBet semantic-registry proof evidence.", ["semantic-registry proof artifact", "PR/dispatch verification"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/prepare-canonical-drive-transfer.yml": ("Prepares chunked historical warehouse data for canonical Drive transfer.", ["warehouse artifact consumption", "transfer manifest and archive chunks"], "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST", False),
    ".github/workflows/probe-sportybet-direct-20-markets.yml": ("Historical fixed-date direct-market probe evidence workflow.", ["fixed-date market probe", "direct-market artifact"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/prove-sportybet-direct-share-code.yml": ("Historical fixed-date direct share-code proof workflow.", ["fixed-date share-code transport proof", "summary/proof artifacts"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/validate-win-either-half-campaign-commitment.yml": ("Validates the Win-Either-Half research commitment and attestation.", ["commitment validation", "run-scoped attestation artifact"], "TESTS", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-competition-review-priority-tests.yml": ("Runs competition-priority review tests for pull requests.", ["focused pytest validation", "dated-fixture test coverage"], "TESTS", "CANONICAL_RETAIN", False),
    ".github/workflows/verify-fotmob-fresh-holdout-history-pagination.yml": ("Verifies bounded pagination behavior for protected Fresh Holdout history.", ["focused history pagination tests"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
    ".github/workflows/verify-fotmob-real-player-context-array-admission.yml": ("Validates source-run player-context array admission evidence.", ["source artifact identity check", "array admission proof"], "TESTS", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-fotmob-real-player-context-authoritative-bridge.yml": ("Validates the authoritative real-player-context bridge.", ["source artifact identity check", "authoritative bridge proof"], "TESTS", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-fotmob-real-player-context-team-strength-handoff.yml": ("Validates the real-player-context team-strength handoff.", ["source artifact handoff validation", "handoff proof artifact"], "TESTS", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-saturday-2026-08-22-fixture-identity-review.yml": ("Verifies a human-reviewed fixed-date fixture identity ledger.", ["fixed artifact/run identity", "decision ledger validation"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml": ("Prepares and verifies a fixed-date reviewed fixture catalog.", ["fixed source artifact identity", "candidate/admission evidence"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/verify-saturday-competition-review-priority.yml": ("Verifies fixed-source Saturday competition-review priority evidence.", ["fixed source run/artifact identity", "priority JSON verification"], "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", False),
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml": ("Monitors protected Fresh Holdout scheduler liveness and continuity.", ["scheduled liveness watchdog", "operator issue-comment continuity dispatch"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False),
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def canonical_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("canonical_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _git(*args: str, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", *args], input=input_bytes, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout


def _at_base(path: str) -> bytes:
    return _git("show", f"{BASE_MAIN_SHA}:{path}")


def _read_text_files_at_base(paths: list[str]) -> dict[str, str]:
    """Read tracked source text from immutable Git blobs, never the worktree."""
    if not paths:
        return {}
    request = b"".join(f"{BASE_MAIN_SHA}:{path}\n".encode("utf-8") for path in paths)
    proc = subprocess.run(["git", "cat-file", "--batch"], input=request, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"git cat-file --batch failed: {proc.stderr.decode('utf-8', 'replace')}")
    output = proc.stdout
    offset = 0
    result: dict[str, str] = {}
    for path in paths:
        end = output.find(b"\n", offset)
        if end < 0:
            raise RuntimeError(f"truncated git cat-file header for {path}")
        header = output[offset:end].decode("ascii")
        offset = end + 1
        parts = header.split(" ")
        if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
            raise RuntimeError(f"invalid git cat-file response for {path}: {header}")
        size = int(parts[2])
        blob = output[offset:offset + size]
        offset += size
        if len(blob) != size or output[offset:offset + 1] != b"\n":
            raise RuntimeError(f"truncated git cat-file body for {path}")
        offset += 1
        try:
            result[path] = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
    if offset != len(output):
        raise RuntimeError("unparsed trailing data from git cat-file --batch")
    return result


def _tracked_workflows() -> list[str]:
    paths = _git("ls-tree", "-r", "--name-only", BASE_MAIN_SHA).decode().splitlines()
    return sorted(p for p in paths if p.startswith(WORKFLOW_DIR + "/") and p.endswith(".yml"))


def _yaml(raw: bytes) -> dict[str, Any]:
    parsed = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(parsed, dict):
        raise RuntimeError("workflow YAML root must be a mapping")
    return parsed


def _trigger_data(doc: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    on = doc.get("on", {})
    if not isinstance(on, dict):
        on = {}
    triggers = sorted(str(k) for k in on)
    crons: list[str] = []
    inputs: dict[str, Any] = {}
    for schedule in on.get("schedule", []) or []:
        if isinstance(schedule, dict) and "cron" in schedule:
            crons.append(str(schedule["cron"]))
    dispatch = on.get("workflow_dispatch", {})
    if isinstance(dispatch, dict) and isinstance(dispatch.get("inputs", {}), dict):
        inputs = dispatch.get("inputs", {})
    return triggers, sorted(crons), inputs


def _job_metadata(doc: dict[str, Any]) -> tuple[list[str], list[int], dict[str, Any]]:
    jobs = doc.get("jobs", {})
    if not isinstance(jobs, dict):
        return [], [], {}
    names: list[str] = []
    timeouts: list[int] = []
    permissions: dict[str, Any] = {}
    for key, value in jobs.items():
        if not isinstance(value, dict):
            continue
        names.append(str(key))
        timeout = value.get("timeout-minutes")
        if isinstance(timeout, str) and timeout.isdigit():
            timeouts.append(int(timeout))
        if isinstance(value.get("permissions"), dict):
            permissions[str(key)] = value["permissions"]
    return sorted(names), sorted(set(timeouts)), permissions


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    jobs = doc.get("jobs", {})
    if isinstance(jobs, dict):
        for job in jobs.values():
            if isinstance(job, dict) and isinstance(job.get("steps"), list):
                out.extend(s for s in job["steps"] if isinstance(s, dict))
    return out


def _string_list(pattern: str, content: str) -> list[str]:
    return sorted(set(re.findall(pattern, content, flags=re.IGNORECASE | re.MULTILINE)))


def _artifacts(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    uploads: list[dict[str, Any]] = []
    downloads: list[dict[str, Any]] = []
    for step in steps:
        uses = str(step.get("uses", ""))
        with_values = step.get("with", {}) if isinstance(step.get("with", {}), dict) else {}
        entry = {
            "step": step.get("name"),
            "name": with_values.get("name"),
            "path": with_values.get("path"),
            "retention_days": with_values.get("retention-days"),
            "run_id": with_values.get("run-id"),
            "workflow": with_values.get("workflow"),
            "command": step.get("run") if "gh run download" in str(step.get("run", "")) else None,
        }
        if "upload-artifact" in uses:
            uploads.append(entry)
        if "download-artifact" in uses or "gh run download" in str(step.get("run", "")):
            downloads.append(entry)
    return uploads, downloads


def _consumer_evidence(path: str, name: str, artifact_names: list[str], tracked_text: dict[str, str]) -> dict[str, Any]:
    stem = Path(path).stem
    identifiers = sorted({x for x in [path, Path(path).name, stem, name, *artifact_names] if isinstance(x, str) and x})
    precise_identifiers = [
        x for x in identifiers
        if x in artifact_names or x.startswith(WORKFLOW_DIR + "/") or len(x) >= 12
    ]
    sources: list[str] = []
    docs: list[str] = []
    tests: list[str] = []
    workflow_refs: list[str] = []
    artifact_reference_sources: list[str] = []
    artifact_refs: list[str] = []
    history_refs: list[str] = []
    source_matches: list[dict[str, Any]] = []
    for source_path, content in tracked_text.items():
        if source_path == path:
            continue
        hits = [identifier for identifier in precise_identifiers if identifier.casefold() in content.casefold()]
        if not hits:
            continue
        sources.append(source_path)
        source_matches.append({"path": source_path, "matched_identifiers": sorted(hits)})
        if source_path.startswith("docs/"):
            docs.append(source_path)
        if source_path.startswith("tests/"):
            tests.append(source_path)
        if source_path.startswith(WORKFLOW_DIR + "/"):
            workflow_refs.append(source_path)
        artifact_hits = [a for a in artifact_names if a and a.casefold() in content.casefold()]
        if artifact_hits:
            artifact_reference_sources.append(source_path)
            download_match = False
            if source_path.startswith(WORKFLOW_DIR + "/") and source_path.endswith((".yml", ".yaml")):
                try:
                    source_doc = _yaml(content.encode("utf-8"))
                    for step in _steps(source_doc):
                        uses = str(step.get("uses", ""))
                        with_values = step.get("with", {}) if isinstance(step.get("with", {}), dict) else {}
                        if "download-artifact" in uses and str(with_values.get("name", "")).casefold() in {a.casefold() for a in artifact_hits}:
                            download_match = True
                        command = str(step.get("run", ""))
                        if "gh run download" in command and any(a.casefold() in command.casefold() for a in artifact_hits):
                            download_match = True
                except (RuntimeError, yaml.YAMLError):
                    download_match = False
            elif source_path.endswith(".py"):
                download_match = "gh run download" in content and any(a.casefold() in content.casefold() for a in artifact_hits)
            if download_match:
                artifact_refs.append(source_path)
        workflow_run_binding = source_path.startswith(WORKFLOW_DIR + "/") and "workflow_run:" in content and name in content
        named_run_lookup = bool(re.search(r"gh\s+run\s+(?:list|download)\b|api\.github\.com/.*/actions/runs", content, re.I)) and any(x.casefold() in content.casefold() for x in precise_identifiers)
        if workflow_run_binding or named_run_lookup:
            history_refs.append(source_path)
    known_consumers = KNOWN_CONSUMERS.get(path, [])
    return {
        "artifact_producer_only": bool(artifact_names) and not (artifact_refs or known_consumers),
        "artifact_consumer_exists": bool(artifact_refs or known_consumers),
        "workflow_history_consumer_exists": bool(history_refs or known_consumers),
        "current_docs_reference": bool(docs),
        "current_test_reference": bool(tests),
        "historical_reference_only": bool(sources) and all(x.startswith(("docs/", "tests/", "artifacts/")) for x in sources),
        "consumer_sources": sorted(set(sources)),
        "source_matches": sorted(source_matches, key=lambda item: (item["path"], item["matched_identifiers"])),
        "artifact_consumer_sources": sorted(set(artifact_refs)),
        "artifact_reference_sources": sorted(set(artifact_reference_sources)),
        "workflow_or_history_consumer_sources": sorted(set(history_refs)),
        "workflow_reference_sources": sorted(set(workflow_refs)),
        "known_workflow_consumers": known_consumers,
    }


def _history_run(run: Any) -> dict[str, Any] | None:
    if not run:
        return None
    if not isinstance(run, dict) or not run.get("databaseId"):
        raise WorkflowHistoryAccessError(f"unexpected gh run list record: {run!r}")
    return {
        "run_id": int(run["databaseId"]),
        "url": run.get("url"),
        "head_sha": run.get("headSha"),
        "head_branch": run.get("headBranch"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("createdAt"),
        "updated_at": run.get("updatedAt"),
    }


def _gh_runs(filename: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    def query(success: bool) -> list[dict[str, Any]]:
        command = ["gh", "run", "list", "--repo", "Thabearr/ATHENA", "--workflow", filename]
        if success:
            command.extend(["--status", "success"])
        command.extend(["--limit", "1", "--json", RUN_FIELDS])
        try:
            proc = subprocess.run(command, capture_output=True, text=True)
        except OSError as exc:
            raise WorkflowHistoryAccessError(f"GitHub CLI could not be executed for {filename}: {exc}") from exc
        if proc.returncode:
            raise WorkflowHistoryAccessError(
                f"GitHub history access failed for {filename} (success={success}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise WorkflowHistoryAccessError(f"invalid gh JSON for {filename}: {exc}") from exc
        if not isinstance(result, list) or (result and not isinstance(result[0], dict)):
            raise WorkflowHistoryAccessError(f"unexpected gh run list response for {filename}: {result!r}")
        return result

    successful = query(True)
    latest = query(False)
    return _history_run(successful[0] if successful else None), _history_run(latest[0] if latest else None)


def _purpose(path: str, name: str, modules: list[str], scripts: list[str]) -> tuple[str, list[str], str, str, bool]:
    if path in SPECIAL_PURPOSE:
        return SPECIAL_PURPOSE[path]
    if path in PURPOSE_OVERRIDES:
        return PURPOSE_OVERRIDES[path]
    basename = Path(path).name
    stem = Path(path).stem
    if path in PROTECTED_FRESH_HOLDOUT or "fresh-holdout" in stem:
        return (f"Protected Fresh Holdout or continuity capability: {name}.", ["Fresh Holdout or continuity research capability; no P4.3A retirement authority"], "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH", False)
    if path == ".github/workflows/athena-draft-ready-bridge.yml" or path == ".github/workflows/athena-patch-bridge.yml":
        return (f"ATHENA pull-request command bridge: {name}.", ["operator issue-comment command compatibility", *scripts], "ATHENA_PR_BRIDGE", "CANONICAL_RETAIN", False)
    if "backtest" in stem:
        family, disposition = "ATHENA_BACKTEST_FUTURE", "RETAIN_PENDING_FUTURE_BACKTEST"
    elif any(x in stem for x in ("warehouse", "source-history", "reviewed-source", "drive-transfer", "history-campaign")):
        family, disposition = "ATHENA_INGEST_FUTURE", "RETAIN_PENDING_FUTURE_INGEST"
    elif any(x in stem for x in ("validation", "qualification", "commitment", "campaign")):
        family, disposition = "ATHENA_RETRAIN_FUTURE", "RETAIN_PENDING_FUTURE_RETRAIN"
    elif any(x in stem for x in ("bridge", "owner-dispatch")):
        family, disposition = "ATHENA_PR_BRIDGE", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT"
    elif "test" in stem or "verify-" in stem:
        family, disposition = "TESTS", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT"
    elif "shadow" in stem:
        family, disposition = "PROTECTED_RESEARCH", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT"
    else:
        family, disposition = "RETAIN_PENDING_AUDIT", "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT"
    unique = [f"workflow-specific capability for {basename}"]
    unique.extend(x for x in [*scripts, *modules] if x not in unique)
    return f"Workflow-specific capability: {name}.", unique, family, disposition, False


def _classify_history(success: dict[str, Any] | None, latest: dict[str, Any] | None) -> str:
    if success:
        return "HAS_SUCCESSFUL_RUN"
    if latest:
        return "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED"
    return "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"


def build_static_row(path: str, raw: bytes, success: dict[str, Any] | None, latest: dict[str, Any] | None, tracked_text: dict[str, str]) -> dict[str, Any]:
    doc = _yaml(raw)
    content = raw.decode("utf-8")
    name = str(doc.get("name", Path(path).stem))
    triggers, crons, inputs = _trigger_data(doc)
    jobs, timeouts, job_permissions = _job_metadata(doc)
    steps = _steps(doc)
    uploads, downloads = _artifacts(steps)
    scripts = sorted(set(re.findall(r"(?:python(?:3(?:\.\d+)?)?\s+)([\w./-]+\.py)", content, flags=re.IGNORECASE)))
    modules = sorted(set(re.findall(r"(?:python(?:3(?:\.\d+)?)?\s+-m\s+)([\w.]+)", content, flags=re.IGNORECASE)))
    external = sorted(set(re.findall(r"(?m)^\s*uses:\s*([^\s]+)", content)))
    external.extend(x for x in ("GitHub CLI (gh)", "GitHub REST API") if re.search(r"\bgh\s+(?:run|api|release)\b|api\.github\.com", content, re.I))
    external = sorted(set(external))
    artifact_names = sorted(set(str(a.get("name")) for a in uploads if a.get("name")))
    upload_paths = sorted(set(str(a.get("path")) for a in uploads if a.get("path")))
    output_receipts = sorted(set(artifact_names + upload_paths))
    purpose, unique, family, disposition, _ = _purpose(path, name, modules, scripts)
    unique = sorted(set(unique + [str(step["name"]) for step in steps if step.get("name")]))
    unique = sorted(set(unique + [str(s["name"]) for s in steps if s.get("name")]))
    history_status = _classify_history(success, latest)
    owner_review = history_status != "HAS_SUCCESSFUL_RUN"
    if history_status == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED" and path not in SPECIAL_PURPOSE:
        disposition = "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"
    elif history_status == "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED" and path not in SPECIAL_PURPOSE:
        disposition = "RETAIN_RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED"
    if path == ".github/workflows/current-sportybet-accumulator.yml" and latest is None and success is None:
        disposition = "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"
    fresh_protected = path in PROTECTED_FRESH_HOLDOUT
    if fresh_protected:
        family, disposition = "PROTECTED_RESEARCH", "RETAIN_PROTECTED_RESEARCH"
    if path == ".github/workflows/current-shadow-all-market.yml":
        family, disposition = "ATHENA_RUN", "RETAIN_ACTIVE_PENDING_CANONICAL_SHADOW_MIGRATION"
        unique = sorted(set(unique + CURRENT_SHADOW_BLOCKERS))
    if path == ".github/workflows/athena-run.yml":
        family, disposition = "ATHENA_RUN", "CANONICAL_RETAIN"
    if path == ".github/workflows/tests.yml":
        family, disposition = "TESTS", "CANONICAL_RETAIN"
    if path == ".github/workflows/current-sportybet-accumulator.yml":
        family = "ATHENA_RUN"
        unique = ["target_size maps to canonical target_legs", "MAIN Phase-6 authority failure remains fail-closed"]
    if family not in ALLOWED_FAMILIES:
        raise RuntimeError(f"bad successor family {family} for {path}")
    if path == ".github/workflows/current-shadow-all-market.yml":
        blockers = CURRENT_SHADOW_BLOCKERS.copy()
    elif history_status == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED":
        blockers = ["NO_RUN_HISTORY", "owner review required; P4.3A authorizes no retirement"]
    elif owner_review:
        blockers = ["NO_SUCCESSFUL_RUN", "owner review required; P4.3A authorizes no retirement"]
    else:
        blockers = ["P4.3A authorizes no retirement"]

    on = doc.get("on", {})
    issue_behavior = "" if not isinstance(on, dict) or "issue_comment" not in on else "issue_comment trigger; see workflow steps for command/comment contract"
    workflow_run = on.get("workflow_run") if isinstance(on, dict) else None
    workflow_run_behavior = "" if workflow_run is None else json.dumps(workflow_run, sort_keys=True, separators=(",", ":"))
    permission_raw = doc.get("permissions", {})
    permissions: Any = permission_raw if isinstance(permission_raw, (dict, str)) else {}
    permission_map = permissions if isinstance(permissions, dict) else {}
    write_permissions = sorted(k for k, v in permission_map.items() if str(v).lower() in {"write", "write-all"})
    for job_name, perms in job_permissions.items():
        write_permissions.extend(f"{job_name}:{k}" for k, v in perms.items() if str(v).lower() == "write")
    secret_refs = sorted(set(re.findall(r"\bsecrets\.([A-Z0-9_]+)\b", content)))
    concurrency = doc.get("concurrency", {})
    concurrency_group = concurrency.get("group") if isinstance(concurrency, dict) else concurrency
    cancel = concurrency.get("cancel-in-progress") if isinstance(concurrency, dict) else None
    if isinstance(cancel, str) and cancel.lower() in {"true", "false"}:
        cancel = cancel.lower() == "true"
    date_hardcoded = path in DATE_HARDCODED_PATHS
    supported = path in SUPPORTED_ROOTS
    consumer = _consumer_evidence(path, name, artifact_names, tracked_text)
    consumer.update({
        "artifact_producer_only": bool(artifact_names) and not consumer["artifact_consumer_exists"],
        "artifact_upload_names": artifact_names,
        "artifact_upload_paths": upload_paths,
        "gh_run_download_references": [s for s in consumer["consumer_sources"] if "gh run download" in tracked_text.get(s, "")],
        "workflow_run_dependency_references": consumer["workflow_or_history_consumer_sources"],
        "release_asset_names": sorted(set(re.findall(r"(?:release|asset)[^\n]{0,100}", content, flags=re.I))),
    })
    return {
        "workflow_path": path,
        "workflow_name": name,
        "git_blob_sha1": _git("rev-parse", f"{BASE_MAIN_SHA}:{path}").decode().strip(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "trigger_types": triggers,
        "schedule_crons": crons,
        "workflow_dispatch_inputs": inputs,
        "issue_comment_behavior": issue_behavior,
        "workflow_run_behavior": workflow_run_behavior,
        "permissions": {"workflow": permissions, "jobs": job_permissions},
        "write_permissions": sorted(set(write_permissions)),
        "secrets_referenced": secret_refs,
        "concurrency_group": concurrency_group,
        "cancel_in_progress": cancel,
        "job_names": jobs,
        "job_timeout_minutes": timeouts,
        "scripts_or_modules_called": sorted(set(scripts + modules)),
        "local_python_entrypoints": scripts + modules,
        "external_tools_called": external,
        "artifact_uploads": uploads,
        "artifact_downloads": downloads,
        "release_assets_read": sorted(set(re.findall(r"(?:gh\s+release\s+download|browser_download_url|releases/download)[^\n]*", content, flags=re.I))),
        "outputs_or_receipts": output_receipts,
        "purpose": purpose,
        "unique_responsibilities": unique,
        "supported_runtime_root": supported,
        "date_hardcoded": date_hardcoded,
        "fresh_holdout_protected": fresh_protected,
        "evidence_only": not supported,
        "last_successful_run": success,
        "latest_run": latest,
        "history_status": history_status,
        "successor_family": family,
        "successor_workflow_path": ".github/workflows/athena-run.yml" if family == "ATHENA_RUN" and path != ".github/workflows/athena-run.yml" else None,
        "capability_mapping": {
            "successor_family": family,
            "mapping": ["target_size -> target_legs", "days=today", "target_total_odds=null", "bookie=sportybet", "profile=main"] if path == ".github/workflows/current-sportybet-accumulator.yml" else [],
            # P4.3A records mapping hints only; a later owner-reviewed retirement proof establishes equivalence.
            "equivalence_claimed": False,
        },
        "disposition": disposition,
        "retirement_candidate": False,
        "retirement_eligible": False,
        "owner_review_required": owner_review,
        "retirement_blockers": blockers,
        "dependency_evidence": consumer,
        "evidence_references": sorted(set([path, *consumer["consumer_sources"], *scripts, *modules])),
    }


def build_matrix(
    *,
    live_history: bool,
    captured_at: str | None = None,
    prior_history: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD").decode().strip()
    if head != BASE_MAIN_SHA:
        if live_history or prior_history is None:
            raise MainAdvanceError(f"capture requires exact base checkout {BASE_MAIN_SHA}; got {head}")
        # Offline static refresh may run on the P4.3A branch, but never against changed workflow YAML.
        if subprocess.run(["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"]).returncode != 0:
            raise MainAdvanceError(f"static refresh branch does not descend from {BASE_MAIN_SHA}")
        if _git("diff", "--name-only", BASE_MAIN_SHA, "HEAD", "--", WORKFLOW_DIR).strip() or _git("diff", "--name-only", BASE_MAIN_SHA, "--", WORKFLOW_DIR).strip():
            raise MainAdvanceError("static refresh requires unchanged workflow YAML")
    paths = _tracked_workflows()
    if len(paths) != 40:
        raise RuntimeError(f"expected 40 tracked workflow YAMLs at base; got {len(paths)}")
    tracked_paths = _git("ls-tree", "-r", "--name-only", BASE_MAIN_SHA).decode().splitlines()
    text_extensions = {".py", ".yml", ".yaml", ".md", ".json", ".sh", ".toml"}
    relevant_prefixes = (
        ".github/workflows/", "scripts/", "tests/", "docs/", "domain/",
        "services/", "api/", "tools/", "config/architecture/",
        "artifacts/architecture/", "workers/", "intelligence/", "engine/",
    )
    tracked_text_paths = [
        source_path for source_path in tracked_paths
        if Path(source_path).suffix.lower() in text_extensions
        and (source_path.startswith(relevant_prefixes) or ("/" not in source_path and source_path.endswith(".py")))
        and (Path(source_path).suffix.lower() != ".json" or source_path.startswith(("config/architecture/", "artifacts/architecture/", "tests/fixtures/architecture/")))
    ]
    tracked_text = _read_text_files_at_base(tracked_text_paths)
    rows: list[dict[str, Any]] = []
    for path in paths:
        raw = _at_base(path)
        if live_history:
            success, latest = _gh_runs(Path(path).name)
        elif prior_history is not None:
            prior = prior_history[path]
            success, latest = prior.get("last_successful_run"), prior.get("latest_run")
        else:
            success, latest = None, None
        rows.append(build_static_row(path, raw, success, latest, tracked_text))
    no_run = [r for r in rows if r["history_status"] == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"]
    no_success = [r for r in rows if r["history_status"] == "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED"]
    date_rows = [r for r in rows if r["date_hardcoded"]]
    supported_date_rows = [r for r in date_rows if r["supported_runtime_root"]]
    protected = [r for r in rows if r["fresh_holdout_protected"]]
    matrix: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_main_sha": BASE_MAIN_SHA,
        "captured_at_utc": captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workflow_count": 40,
        "workflow_rows": sorted(rows, key=lambda r: r["workflow_path"]),
        "date_hardcoded_workflow_count": len(date_rows),
        "supported_date_hardcoded_workflow_count": len(supported_date_rows),
        "supported_date_hardcoded_workflows": [r["workflow_path"] for r in supported_date_rows],
        "no_run_history_owner_review_required": [
            {"workflow_path": r["workflow_path"], "workflow_name": r["workflow_name"], "current_purpose": r["purpose"], "successor_candidate": r["successor_family"], "reason": "no run history; owner review required"}
            for r in no_run
        ],
        "run_history_without_success_owner_review_required": [
            {"workflow_path": r["workflow_path"], "workflow_name": r["workflow_name"], "current_purpose": r["purpose"], "successor_candidate": r["successor_family"], "reason": "run history has no successful run; owner review required"}
            for r in no_success
        ],
        "no_successful_run_count": len(no_run) + len(no_success),
        "successful_run_count": sum(r["history_status"] == "HAS_SUCCESSFUL_RUN" for r in rows),
        "protected_research_workflow_count": len(protected),
        "protected_research_workflows": [r["workflow_path"] for r in protected],
        "canonical_sha256": "",
    }
    matrix["canonical_sha256"] = canonical_sha256(matrix)
    return matrix


def validate_static_snapshot(matrix: dict[str, Any]) -> None:
    if matrix.get("policy_id") != POLICY_ID or matrix.get("repository_main_sha") != BASE_MAIN_SHA:
        raise RuntimeError("matrix policy/base SHA mismatch")
    rows = matrix.get("workflow_rows")
    paths = _tracked_workflows()
    if not isinstance(rows, list) or len(rows) != 40:
        raise RuntimeError("matrix must contain exactly 40 rows")
    row_paths = [r.get("workflow_path") for r in rows]
    if row_paths != sorted(paths) or len(set(row_paths)) != 40:
        raise RuntimeError("matrix workflow rows do not match the exact base workflow set")
    if canonical_sha256(matrix) != matrix.get("canonical_sha256"):
        raise RuntimeError("matrix canonical SHA mismatch")
    for row in rows:
        raw = _at_base(row["workflow_path"])
        if row.get("git_blob_sha1") != _git("rev-parse", f"{BASE_MAIN_SHA}:{row['workflow_path']}").decode().strip():
            raise RuntimeError(f"blob SHA mismatch: {row['workflow_path']}")
        if row.get("source_sha256") != hashlib.sha256(raw).hexdigest():
            raise RuntimeError(f"source SHA mismatch: {row['workflow_path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--capture", action="store_true", help="perform read-only gh run list queries and write matrix")
    group.add_argument("--check-static", action="store_true", help="offline validation of captured matrix")
    group.add_argument("--refresh-static", action="store_true", help="offline rebuild of static fields from base blobs, preserving captured run history")
    parser.add_argument("--output", required=True, help="matrix JSON path")
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        if args.capture:
            matrix = build_matrix(live_history=True)
            validate_static_snapshot(matrix)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(canonical_json_bytes(matrix))
            print(f"captured {len(matrix['workflow_rows'])} workflows; sha256={matrix['canonical_sha256']}")
            return 0
        if args.refresh_static:
            prior = json.loads(output.read_text(encoding="utf-8"))
            validate_static_snapshot(prior)
            history = {
                row["workflow_path"]: {
                    "last_successful_run": row["last_successful_run"],
                    "latest_run": row["latest_run"],
                }
                for row in prior["workflow_rows"]
            }
            matrix = build_matrix(
                live_history=False,
                captured_at=prior["captured_at_utc"],
                prior_history=history,
            )
            output.write_bytes(canonical_json_bytes(matrix))
            print(f"refreshed static matrix from base blobs; preserved {len(history)} captured histories; sha256={matrix['canonical_sha256']}")
            return 0
        if not args.check_static:
            raise RuntimeError("default is offline/fail-closed; specify --capture, --refresh-static or --check-static")
        matrix = json.loads(output.read_text(encoding="utf-8"))
        validate_static_snapshot(matrix)
        print(f"matrix static check passed; sha256={matrix['canonical_sha256']}")
        return 0
    except WorkflowHistoryAccessError as exc:
        print(f"P4_3A_BLOCKED_BY_WORKFLOW_HISTORY_ACCESS: {exc}", file=sys.stderr)
        return 1
    except MainAdvanceError as exc:
        print(f"P4_3A_BLOCKED_BY_MAIN_ADVANCE: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"P4_3A_CAPTURE_OR_MATRIX_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
