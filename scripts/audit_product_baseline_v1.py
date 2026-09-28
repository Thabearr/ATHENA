#!/usr/bin/env python3
"""Offline integrity and schema audit for the frozen ATHENA product baseline.

The default audit validates the historical snapshot and immutable receipt bytes.
It does not compare mutable runtime source files with the snapshot, so later
authorized roadmap work does not invalidate BASE-00. ``--exact-head`` performs
that optional static reproduction check and reports a skip if source has moved.
``--freeze`` is restricted to the exact baseline source commit and writes the
initial JSON and Markdown snapshot without importing ATHENA runtime modules.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_JSON = "artifacts/product/product_baseline_v1.json"
BASELINE_MARKDOWN = "docs/product/athena_product_baseline_v1.md"
BASELINE_ID = "ATHENA_PRODUCT_BASELINE_V1"
POLICY_ID = "ATHENA_PRODUCT_BASELINE_POLICY_V1"
REPOSITORY = "Thabearr/ATHENA"
BASE_COMMIT = "eae938a268707f07db3da2d551ea589782902b1c"
BASE_TREE = "c00e98b0a4b2d5c5f211e6c4f929a08b8e79639b"

CLASSIFICATIONS = {
    "CANONICAL_SUPPORTED", "RETAINED_COMPATIBILITY", "DIAGNOSTIC_RESEARCH_ONLY",
    "BLOCKED", "OBSOLETE_CANDIDATE", "UNKNOWN",
}
CAPABILITY_STATES = {
    "VERIFIED_AVAILABLE", "AVAILABLE_RETAINED_COMPATIBILITY", "RESEARCH_ONLY",
    "BLOCKED_BY_AUTHORITY", "BLOCKED_BY_IMPLEMENTATION", "NOT_IMPLEMENTED",
    "NOT_AUTHORIZED", "UNKNOWN",
}
EXTERNAL_EFFECT_STATES = {"YES", "NO", "CONDITIONAL", "UNKNOWN"}
MISSION_IDS = {
    "BASE-00", "AUTH-01A", "AUTH-01B", "AUTH-01C", "AUTH-01D", "PORT-01",
    "PORT-02", "CORE-01", "APP-01", "DATA-01", "RUN-01", "RUN-02", "UX-01",
    "INT-01", "PKG-WINDOWS", "PKG-LINUX", "REL-01",
}

CORE_SOURCE_PATHS = (
    "run_desktop.py", "api/server.py", "api/athenizer.py", "api/export.py",
    "ui/index.html", "ui/app.js", "services/athena_run_service.py",
    "services/athena_run_workflow_request.py", "services/athena_run_request_parser.py",
    "scripts/resolve_athena_run_workflow_request.py", "scripts/execute_athena_run_workflow.py",
    "scripts/execute_current_shadow_request.py", "scripts/execute_current_shadow_daily.py",
    "scripts/execute_current_shadow_all_market.py",
    "scripts/execute_current_shadow_all_market_summary_reuse.py",
    "scripts/execute_current_shadow_all_market_fresh_reprice.py",
    "scripts/execute_current_shadow_all_market_fresh_reprice_bound.py",
    ".github/workflows/athena-run.yml", ".github/workflows/current-shadow-all-market.yml",
    "domain/current_shadow_all_market_runner.py",
    "domain/current_shadow_canonical_core_adapter.py",
    "domain/current_shadow_runtime_bindings.py", "domain/run_contracts.py",
    "database/schema.sql", "database/database.py",
    "docs/architecture/runtime_reachability.md",
    "docs/architecture/workflow_capability_matrix.md",
    "docs/architecture/athena_run_workflow.md", "requirements.txt",
)

SOURCE_DOCUMENTS = [
    {
        "source_document_id": "SRC-ARCH-REMEDIATION-MASTER-V2",
        "title": "ATHENA Architecture Remediation Master Implementation Specification v2",
        "sha256": "f308628f007c748d90be9bec1d693a411994c5d3562edd50533309863883efbd",
        "identity_class": "OWNER_SUPPLIED_HASH_REPORTED",
        "repository_file": None,
        "content_used_as": "Controlling architecture invariants, authority separation, evidence discipline, bounded PR doctrine, reread cadence.",
    },
    {
        "source_document_id": "SRC-SIX-DOCUMENT-BLUEPRINT",
        "title": "ATHENA: Six-Document Product and Implementation Blueprint",
        "sha256": "caa4f737912d78dbd3f42ff540e3f888f7de60519935e42d7bdbc8a4c842e6df",
        "identity_class": "OWNER_SUPPLIED_HASH_REPORTED",
        "repository_file": None,
        "content_used_as": "Target product requirements, UI/UX intent, target application architecture, release scope.",
    },
    {
        "source_document_id": "SRC-PRODUCT-IMPLEMENTATION-MASTER-V1",
        "title": "ATHENA Product Implementation Master Specification v1",
        "sha256": "fbcfca9e34b43e05ac810623d09ec82983ae118825161987cf8123a9f35566f9",
        "identity_class": "OWNER_SUPPLIED_HASH_REPORTED",
        "repository_file": None,
        "content_used_as": "Dependency-ordered product implementation missions; BASE-00 records AUTH-01A as next, not authorized.",
    },
    {
        "source_document_id": "SRC-COMPETITION-HIERARCHY-V1",
        "title": "Athena Football Competition Hierarchy v1",
        "sha256": "242f5d0a78bccf16f3dbb81eb020a5be7c81d5964ab81a4da28feb43cb5b4b66",
        "identity_class": "SUPPLIED_ATTACHMENT_SHA256_VERIFIED",
        "repository_file": None,
        "content_used_as": "Competition hierarchy reference. Identity verified from the supplied PDF attachment; it is not represented as a repository file.",
    },
    {
        "source_document_id": "SRC-PRODUCT-ARCH-WINDOWS-LINUX-GUIDE",
        "title": "ATHENA Product Architecture and Windows/Linux Implementation Guide",
        "sha256": "146fe226487bf0518e60d4d9bc622ba0d15bdafdb0ac6a97a164b508a3ca7dc0",
        "identity_class": "SUPPLIED_ATTACHMENT_SHA256_VERIFIED",
        "repository_file": None,
        "content_used_as": "Supplementary product and Windows/Linux implementation guidance; repository source controls current state.",
    },
]

KNOWN_LIVE_RUN = {
    "run_id": 36345657852,
    "workflow_name": "ATHENA Canonical Run",
    "workflow_path": ".github/workflows/athena-run.yml",
    "event": "workflow_dispatch",
    "attempt": 1,
    "head_sha": BASE_COMMIT,
    "status": "completed",
    "conclusion": "success",
    "artifact_id": 10940728036,
    "artifact_name": "athena-run-36345657852",
    "artifact_sha256": "f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a",
    "artifact_digest_class": "GITHUB_ARTIFACT_API_DIGEST_VERIFIED",
    "request_sha256": "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4",
    "run_receipt_sha256": "a8ce4f163432ebead90ee649c7297115acba0a852ceeac2beeb5ef0bdc0d4b6d",
    "inner_current_shadow_receipt_sha256": "80ce47a0965562cffd11d8dbd847740fbf57e36b8f1b173020827ea19a18b258",
    "stabilization_receipt_sha256": "a16860bd03f03a99087f030ed91474a57233ef3e619a36a20494c615bb15e1c7",
    "source_manifest_canonical_sha256": "fb5412845dbed85d00396ea8f11a9343e1145dc4cba07664d54be69b260b449f",
    "business_status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
    "classification": "POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalized_source_bytes(path: Path) -> bytes:
    """Canonicalize text checkout EOLs so source identity is host-independent."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalized_source_sha256(path: Path) -> str:
    return sha256_bytes(normalized_source_bytes(path))


def relative_path(value: str) -> str:
    """Validate canonical repository-relative POSIX paths; reject traversal."""
    if type(value) is not str or not value or "\\" in value or re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"non-normalized repository path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe repository path: {value!r}")
    if path.as_posix() != value:
        raise ValueError(f"non-canonical repository path: {value!r}")
    return value


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value or "UNNAMED"


def _read(root: Path, rel: str) -> bytes:
    return (root / relative_path(rel)).read_bytes()


def _line_evidence(root: Path, rel: str, tokens: list[str], role: str) -> list[dict[str, Any]]:
    lines = _read(root, rel).decode("utf-8", errors="strict").splitlines()
    result = []
    for token in tokens:
        hits = [(i, line) for i, line in enumerate(lines, 1) if token in line]
        result.append({
            "path": rel,
            "symbol_or_literal": token,
            "role": role,
            "match_count": len(hits),
            "line": hits[0][0] if hits else None,
            "line_sha256": sha256_bytes(hits[0][1].encode("utf-8")) if hits else None,
        })
    return result


def _documented_cli(root: Path) -> tuple[list[dict[str, Any]], set[str]]:
    command_re = re.compile(r"\bpython(?:\.exe)?\s+(?:-m\s+)?(scripts(?:[/.][A-Za-z0-9_.-]+)+)")
    docs = []
    for base in (root / "docs",):
        if base.exists():
            docs.extend(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".rst", ".txt"})
    docs.extend(p for p in root.glob("README*") if p.is_file())
    candidates: dict[str, dict[str, Any]] = {}
    referenced_docs: set[str] = set()
    for doc in sorted(set(docs)):
        rel_doc = doc.relative_to(root).as_posix()
        text = doc.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in command_re.finditer(line):
                target = match.group(1).replace("\\", "/")
                if target.startswith("scripts."):
                    target = "scripts/" + target[len("scripts."):].replace(".", "/")
                if not target.endswith(".py"):
                    target = target.replace(".", "/") + ".py" if "/" not in target else target + ".py"
                relative_path(target)
                entry = candidates.setdefault(target, {"docs": [], "commands": 0})
                entry["docs"].append({
                    "path": rel_doc,
                    "line": line_no,
                    "line_sha256": sha256_bytes(line.encode("utf-8")),
                })
                entry["commands"] += 1
                referenced_docs.add(rel_doc)
    records = []
    for target, details in sorted(candidates.items()):
        exists = (root / target).is_file()
        name = Path(target).stem
        diagnostic = bool(re.search(r"audit|verify|validate|replay|assess|qualify|inspect", name, re.I))
        has_external_signal = False
        if exists:
            text = _read(root, target).decode("utf-8", errors="replace")
            has_external_signal = bool(re.search(r"requests\.|httpx\.|urlopen|FotMobAdvancedScraper|SportyBet|provider_transport|execute-live-network|execute-reviewed-protocol", text, re.I))
        records.append({
            "entrypoint_id": "EP-DOC-CLI-" + _slug(name),
            "display_name": f"Documented script command: {target}",
            "kind": "CLI",
            "source_path": target,
            "symbol_or_trigger": "Python module/script entrypoint referenced by repository documentation; not imported during census.",
            "caller_surface": sorted({item["path"] for item in details["docs"]}),
            "downstream_targets": [target] if exists else [],
            "external_side_effects": ["CONDITIONAL: static source contains provider/network signal; inspect that command's own reviewed contract before use."] if has_external_signal else ["UNKNOWN: documentation reference alone does not prove the full side-effect boundary."],
            "authority_profile_behavior": "Script-specific; a documented command is not blanket owner authorization.",
            "current_classification": "DIAGNOSTIC_RESEARCH_ONLY" if diagnostic else ("RETAINED_COMPATIBILITY" if exists else "BLOCKED"),
            "support_status": "DOCUMENTED_COMMAND_CANDIDATE" if exists else "DOCUMENTED_TARGET_MISSING_AT_BASELINE",
            "source_evidence": [{"path": target, "sha256": normalized_source_sha256(root / target), "hash_kind":"LF_NORMALIZED_SOURCE_SHA256", "role": "SCRIPT_SOURCE"}] if exists else [],
            "documentation_evidence": details["docs"],
            "documented_command_occurrence_count": details["commands"],
            "notes": "Captured from a repository-wide static scan of Markdown/RST/TXT command examples. Command arguments and payload values are intentionally not copied.",
        })
    return records, referenced_docs


def _workflow_parse(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="strict")
    name_match = re.search(r"(?m)^name:\s*[\"']?([^\r\n\"']+)", text)
    name = name_match.group(1).strip() if name_match else path.stem
    lines = text.splitlines()
    on_idx = next((i for i, line in enumerate(lines) if re.fullmatch(r"on:\s*", line)), None)
    events: list[str] = []
    event_blocks: dict[str, list[str]] = {}
    if on_idx is not None:
        end = len(lines)
        for i in range(on_idx + 1, len(lines)):
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*$", lines[i]):
                end = i
                break
        current = None
        for line in lines[on_idx + 1:end]:
            event_match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", line)
            if event_match:
                current = event_match.group(1)
                events.append(current)
                event_blocks[current] = [line]
            elif current is not None:
                event_blocks[current].append(line)
    crons = sorted(set(re.findall(r"(?m)^\s+-\s+cron:\s*[\"']([^\"']+)", "\n".join(event_blocks.get("schedule", [])))))
    dispatch_block = "\n".join(event_blocks.get("workflow_dispatch", []))
    inputs = re.findall(r"(?m)^      ([A-Za-z0-9_-]+):\s*$", dispatch_block)
    group = None
    if "concurrency:" in text:
        section = text.split("concurrency:", 1)[1].split("\njobs:", 1)[0]
        gm = re.search(r"(?m)^\s+group:\s*(.+)$", section)
        group = gm.group(1).strip() if gm else None
    jobs = []
    if "jobs:" in text:
        job_text = text.split("jobs:", 1)[1]
        jobs = re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", job_text)
    artifact_names = []
    for index, line in enumerate(lines):
        if re.match(r"^\s{8}uses:\s*actions/upload-artifact@", line):
            for candidate in lines[index + 1:]:
                if re.match(r"^\s{6}-\s", candidate):
                    break
                artifact_match = re.match(r"^\s{10}name:\s*(.+?)\s*$", candidate)
                if artifact_match:
                    artifact_names.append(artifact_match.group(1).strip().strip("\"'"))
                    break
    artifact_names = sorted(set(artifact_names))
    restore_refs = sorted(set(re.findall(r"(?m)['\"]((?:\.cache|artifacts|data)/[^'\"]+)['\"]", text)))
    restore_refs = [value.replace("\\", "/") for value in restore_refs]
    known_live = {
        "athena-run.yml": 36345657852,
        "verify-saturday-2026-08-22-reviewed-fixture-catalog.yml": 36344862576,
        "tests.yml": 36344862612,
    }
    core = path.name in {"athena-run.yml", "current-shadow-all-market.yml"}
    test_like = path.name in {"tests.yml", "verify-saturday-2026-08-22-reviewed-fixture-catalog.yml"} or path.name.startswith(("verify-", "audit-"))
    provider_signal = bool(re.search(r"sportybet|fotmob|pcUpcoming|provider", text, re.I))
    provider_active_signal = bool(re.search(r"capture|acquir|probe|execute|source|fetch|dispatch", text, re.I))
    provider_effect = "NO" if test_like else ("CONDITIONAL" if provider_signal and provider_active_signal else ("UNKNOWN" if provider_signal else "NO"))
    delivery_signal = bool(re.search(r"share[_ -]?code|create[_ -]?code|delivery|export_code|transport-roundtrip", text, re.I))
    delivery_effect = "CONDITIONAL" if delivery_signal and not test_like else ("NO" if not delivery_signal or test_like else "UNKNOWN")
    email_signal = bool(re.search(r"gmail|smtp|send[_ -]?email|email delivery", text, re.I))
    email_effect = "CONDITIONAL" if email_signal and not test_like else "NO"
    if path.name == "athena-run.yml":
        profile = "workflow_dispatch profile choices main/shadow (default main); schedule resolves main; SHADOW requires explicit dispatch input and remains delivery-coupled by request parser/service."
        provider_effect, delivery_effect, email_effect = "CONDITIONAL", "CONDITIONAL", "NO"
        classification = "CANONICAL_SUPPORTED"
        successor = None
        retained_reason = "Canonical RunRequest -> AthenaRunService boundary; MAIN executor remains target-only, explicit SHADOW dispatch reaches the bounded Current Shadow supervisor."
    elif path.name == "current-shadow-all-market.yml":
        profile = "Legacy Current Shadow path; schedule, manual inputs, and owner issue-comment command all execute the Current Shadow request chain."
        provider_effect, delivery_effect, email_effect = "CONDITIONAL", "CONDITIONAL", "CONDITIONAL"
        classification = "RETAINED_COMPATIBILITY"
        successor = ".github/workflows/athena-run.yml"
        retained_reason = "Scheduled/on-demand/issue-comment ownership, identity/history artifact ancestry, and optional post-core email are not yet migrated; retirement is not authorized."
    elif test_like:
        profile = "Test/catalog verification only; guarded live/provider jobs are expected to remain skipped."
        provider_effect = "NO"
        delivery_effect = email_effect = "NO"
        classification = "DIAGNOSTIC_RESEARCH_ONLY"
        successor = None
        retained_reason = "CI/verification evidence."
    else:
        profile = "Workflow-specific; no common canonical MAIN/SHADOW profile inferred from its filename."
        classification = "DIAGNOSTIC_RESEARCH_ONLY" if provider_signal else "UNKNOWN"
        successor = None
        retained_reason = "Specialized research/evidence workflow; current operational state must be read from its own trigger and job contract."
    issue_guard = None
    if "issue_comment" in events:
        im = re.search(r"(?m)^\s*if:\s*(.+issue\.number.+)$", text)
        issue_guard = im.group(1).strip() if im else "Issue-comment trigger exists; authorization predicate is in workflow source."
    return {
        "workflow_id": "WF-" + _slug(path.stem),
        "name": name,
        "path": rel,
        "source_sha256": normalized_source_sha256(path),
        "trigger_kinds": events,
        "schedule_cron_utc": crons,
        "workflow_dispatch_inputs": inputs,
        "issue_comment_guard": issue_guard,
        "concurrency_group_expression": group,
        "job_ids": jobs,
        "authority_profile_behavior": profile,
        "provider_acquisition": provider_effect,
        "delivery": delivery_effect,
        "email_notification": email_effect,
        "artifact_names_or_roles": artifact_names,
        "restored_historical_dependencies": restore_refs,
        "canonical_successor": successor,
        "retained_reason": retained_reason,
        "retirement_eligibility": False,
        "latest_relevant_successful_run_id": known_live.get(path.name),
        "entrypoint_id": "EP-WF-" + _slug(path.stem),
        "current_classification": classification,
        "support_status": "SOURCE_INSPECTED_TRIGGER_CENSUS",
        "side_effect_assessment": "Static workflow-source indicators; no workflow was dispatched by BASE-00.",
    }


def _core_entrypoint_definitions() -> list[dict[str, Any]]:
    return [
        {"id":"EP-DESKTOP-LEGACY","name":"Legacy pywebview desktop launcher","kind":"DESKTOP","path":"run_desktop.py","symbol":"__main__ startup","tokens":["uvicorn.run(app, host=\"127.0.0.1\", port=8500)","threading.Thread(target=start_server, daemon=True)","webview.create_window("],"caller":"Local operator launches Python script","downstream":["api.server:app","ui/index.html","127.0.0.1:8500/api/status"],"effects":["Local loopback HTTP listener; it may adopt any responding process on fixed port 8500."],"authority":"No authenticated per-launch process/session handshake is visible at this boundary.","class":"RETAINED_COMPATIBILITY","status":"Developer/repository-relative shell; not a qualified installed runtime.","notes":"Polls a static health route, launches daemon server thread if absent, loads repository-relative UI file."},
        {"id":"EP-API-ROOT","name":"Legacy desktop UI root","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /","tokens":["@app.get(\"/\")"],"caller":"Browser or desktop webview","downstream":["ui/index.html"],"effects":["Local file response."],"authority":"Legacy API boundary; no canonical RunRequest authorization envelope.","class":"RETAINED_COMPATIBILITY","status":"Static legacy UI route.","notes":""},
        {"id":"EP-API-UI","name":"Legacy static UI mount","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"mount /ui","tokens":["app.mount(\"/ui\", StaticFiles"],"caller":"Browser or desktop webview","downstream":["ui/*"],"effects":["Local static file serving when repository-relative UI directory exists."],"authority":"None in route; server CORS and responder identity limitations apply.","class":"RETAINED_COMPATIBILITY","status":"Conditional static mount.","notes":""},
        {"id":"EP-API-STATUS","name":"Legacy status/readiness route","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /api/status","tokens":["@app.get(\"/api/status\")","weights_path = \"config/model_weights.json\""],"caller":"Desktop shell and legacy UI","downstream":["get_status"],"effects":["Local status response."],"authority":"A response and model-weight existence are not canonical engine or source readiness proof.","class":"RETAINED_COMPATIBILITY","status":"Static/superficial status semantics.","notes":""},
        {"id":"EP-API-LEAGUES","name":"Legacy upcoming leagues browsing","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /api/leagues","tokens":["@app.get(\"/api/leagues\")","scraper = FotMobAdvancedScraper()","matches = scraper.fetch_upcoming_matches(days_ahead=days)"],"caller":"Legacy UI","downstream":["_get_cached_fixtures","workers.fotmob_advanced_scraper.FotMobAdvancedScraper"],"effects":["Conditional FotMob/provider fixture acquisition on cache miss."],"authority":"Legacy route without canonical provider evidence envelope.","class":"RETAINED_COMPATIBILITY","status":"Provider-backed legacy browsing route.","notes":"Cache TTL does not turn a cache miss into offline operation."},
        {"id":"EP-API-FIXTURES","name":"Legacy upcoming fixture browsing","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /api/fixtures","tokens":["@app.get(\"/api/fixtures\")","matches = _get_cached_fixtures(days)"],"caller":"Legacy UI","downstream":["_get_cached_fixtures","FotMobAdvancedScraper"],"effects":["Conditional FotMob/provider fixture acquisition on cache miss."],"authority":"Legacy route without canonical provider evidence envelope.","class":"RETAINED_COMPATIBILITY","status":"Provider-backed legacy browsing route.","notes":""},
        {"id":"EP-API-GENERATE","name":"Legacy accumulator generation API","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"POST /api/generate","tokens":["@app.post(\"/api/generate\")","from services.legacy_acca_builder_compat import AccaBuilder","builder = AccaBuilder()"],"caller":"Legacy UI Generate button","downstream":["services.legacy_acca_builder_compat.AccaBuilder.build"],"effects":["Legacy source/provider work may occur through retained pipeline."],"authority":"Not the canonical RunRequest/AthenaRunService product boundary.","class":"RETAINED_COMPATIBILITY","status":"Legacy builder endpoint; migration required before representing it as canonical product API.","notes":""},
        {"id":"EP-API-STYLES","name":"Legacy stylesheet route","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /styles.css","tokens":["@app.get(\"/styles.css\")"],"caller":"Legacy UI root","downstream":["ui/styles.css"],"effects":["Local file response."],"authority":"None.","class":"RETAINED_COMPATIBILITY","status":"Static asset route.","notes":""},
        {"id":"EP-API-JS","name":"Legacy application JavaScript route","kind":"HTTP_ROUTE","path":"api/server.py","symbol":"GET /app.js","tokens":["@app.get(\"/app.js\")"],"caller":"Legacy UI root","downstream":["ui/app.js"],"effects":["Local file response."],"authority":"None.","class":"RETAINED_COMPATIBILITY","status":"Static asset route.","notes":""},
        {"id":"EP-API-ATHENIZER-VET","name":"Legacy booking-code vet route","kind":"HTTP_ROUTE","path":"api/athenizer.py","symbol":"POST /vet","tokens":["@router.post(\"/vet\")"],"caller":"Legacy UI Athenizer tab","downstream":["vet_booking_code"],"effects":["Booking-code/provider behavior is conditional on route implementation."],"authority":"Legacy compatibility surface; not canonical product API.","class":"RETAINED_COMPATIBILITY","status":"Retained route; no new capability inferred.","notes":""},
        {"id":"EP-API-ATHENIZER-SPLIT","name":"Legacy booking-code split route","kind":"HTTP_ROUTE","path":"api/athenizer.py","symbol":"POST /split","tokens":["@router.post(\"/split\")"],"caller":"Legacy UI Athenizer tab","downstream":["split_booking_code"],"effects":["Booking-code/provider behavior is conditional on route implementation."],"authority":"Legacy compatibility surface; not canonical product API.","class":"RETAINED_COMPATIBILITY","status":"Retained route; no new capability inferred.","notes":""},
        {"id":"EP-API-ATHENIZER-MERGE","name":"Legacy booking-code merge route","kind":"HTTP_ROUTE","path":"api/athenizer.py","symbol":"POST /merge","tokens":["@router.post(\"/merge\")"],"caller":"Legacy UI Athenizer tab","downstream":["merge_booking_codes"],"effects":["Booking-code/provider behavior is conditional on route implementation."],"authority":"Legacy compatibility surface; not canonical product API.","class":"RETAINED_COMPATIBILITY","status":"Retained route; no new capability inferred.","notes":""},
        {"id":"EP-API-EXPORT","name":"Legacy export route","kind":"HTTP_ROUTE","path":"api/export.py","symbol":"POST /api/export","tokens":["@router.post(\"/api/export\")"],"caller":"Legacy UI export controls","downstream":["prepare_bookmaker_export"],"effects":["Local export preparation response; not delivery proof."],"authority":"No canonical delivery lineage asserted by this baseline.","class":"RETAINED_COMPATIBILITY","status":"Export route is included by api.server.","notes":""},
        {"id":"EP-API-EXPORT-CODE","name":"Deprecated legacy export-code route","kind":"HTTP_ROUTE","path":"api/export.py","symbol":"POST /api/export_code","tokens":["@router.post(\"/api/export_code\", deprecated=True)"],"caller":"Legacy clients, if still present","downstream":["prepare_bookmaker_export"],"effects":["Local export preparation response; not delivery proof."],"authority":"Deprecated compatibility route.","class":"RETAINED_COMPATIBILITY","status":"Deprecated, still source-reachable.","notes":""},
        {"id":"EP-CANONICAL-SERVICE","name":"Canonical AthenaRunService boundary","kind":"SERVICE","path":"services/athena_run_service.py","symbol":"AthenaRunService.execute","tokens":["class _MainFailClosedExecutor","class _ShadowSupervisorExecutor","_SOURCE_CONTROLLED_EXECUTORS"],"caller":"scripts.execute_athena_run_workflow via persisted RunRequest","downstream":["MainFailClosedExecutor","ShadowSupervisorExecutor","scripts.execute_current_shadow_request"],"effects":["MAIN is target-only/fail-closed; SHADOW supervisor can perform conditional provider acquisition and delivery under its current coupled manifest; wager remains false."],"authority":"Immutable MAIN/SHADOW profiles; _manifest_for currently requires SHADOW research_shadow with create_share_code=true; MAIN request couples create_share_code=false and target-only executor.","class":"CANONICAL_SUPPORTED","status":"Canonical service boundary exists; MAIN production analysis/delivery authority is not implemented.","notes":"Control-plane receipt success and business result are separate."},
        {"id":"EP-CANONICAL-REQUEST-RESOLVER","name":"Canonical workflow request resolution","kind":"CLI","path":"scripts/resolve_athena_run_workflow_request.py","symbol":"module CLI","tokens":["AthenaRunWorkflowRequest"],"caller":".github/workflows/athena-run.yml resolve_request step","downstream":["services.athena_run_workflow_request","services.athena_run_request_parser","domain.run_contracts.RunRequest"],"effects":["No provider acquisition in resolver; resolved request drives later workflow execution."],"authority":"Schedule defaults MAIN; dispatch selects profile; parser sets SHADOW create_share_code=true and MAIN false.","class":"CANONICAL_SUPPORTED","status":"Pure request-resolution boundary.","notes":""},
        {"id":"EP-CANONICAL-WORKFLOW-EXECUTOR","name":"Canonical persisted-request executor","kind":"CLI","path":"scripts/execute_athena_run_workflow.py","symbol":"execute_persisted_request","tokens":["def execute_persisted_request("],"caller":"Canonical workflow execute_request step","downstream":["services.athena_run_service.AthenaRunService"],"effects":["Conditional per resolved authority manifest."],"authority":"Consumes persisted exact request and expected checkout/ref lineage.","class":"CANONICAL_SUPPORTED","status":"Canonical workflow/service handoff.","notes":""},
        {"id":"EP-SHADOW-REQUEST","name":"Current Shadow request supervisor CLI","kind":"CLI","path":"scripts/execute_current_shadow_request.py","symbol":"module CLI and worker dispatch","tokens":["WORKER_MODULE = \"scripts.execute_current_shadow_request\"","execute_current_shadow"],"caller":"Canonical SHADOW service executor and legacy Current Shadow workflow","downstream":["execute_current_shadow_daily","execute_current_shadow_all_market_fresh_reprice_bound","Current Shadow runner"],"effects":["Current Shadow provider acquisition; delivery may be coupled by canonical service binding."],"authority":"SHADOW research path only; no MAIN elevation.","class":"CANONICAL_SUPPORTED","status":"Canonical adapter plus retained Current Shadow supervisor.","notes":""},
        {"id":"EP-SHADOW-DAILY","name":"Current Shadow daily wrapper","kind":"WORKER","path":"scripts/execute_current_shadow_daily.py","symbol":"worker and daily scope resolver","tokens":["SCOPE_TODAY = \"today\"","WORKER_MODULE = \"scripts.execute_current_shadow_daily\""],"caller":"Current Shadow request wrapper","downstream":["all-market CLI","fresh-reprice bound worker"],"effects":["Provider activity when actual SHADOW request executes."],"authority":"Retained SHADOW only.","class":"RETAINED_COMPATIBILITY","status":"Daily/three-day wrapper ownership not cut over.","notes":""},
        {"id":"EP-SHADOW-ALL-MARKET","name":"Current Shadow all-market compatibility CLI","kind":"CLI","path":"scripts/execute_current_shadow_all_market.py","symbol":"module CLI","tokens":["build_parser(","execute_current_shadow_all_market"],"caller":"Daily/request/fresh-reprice wrappers","downstream":["domain.current_shadow_all_market_runner"],"effects":["Provider acquisition and downstream reviewed SHADOW path."],"authority":"SHADOW compatibility path.","class":"RETAINED_COMPATIBILITY","status":"Retained CLI compatibility owner.","notes":""},
        {"id":"EP-SHADOW-SUMMARY-REUSE","name":"Current Shadow summary-reuse wrapper","kind":"WORKER","path":"scripts/execute_current_shadow_all_market_summary_reuse.py","symbol":"module supervisor","tokens":["subprocess.run("],"caller":"Fresh-reprice path","downstream":["Current Shadow runner summary reuse"],"effects":["Conditional provider activity according to selected worker mode."],"authority":"SHADOW only.","class":"RETAINED_COMPATIBILITY","status":"Wrapper remains as compatibility/supervision code.","notes":""},
        {"id":"EP-SHADOW-FRESH-REPRICE","name":"Current Shadow fresh-reprice wrapper","kind":"WORKER","path":"scripts/execute_current_shadow_all_market_fresh_reprice.py","symbol":"_execute_worker","tokens":["def _execute_worker(args, *, runtime_bindings=None)","fresh_reprice_current_shadow_runtime_bindings"],"caller":"Canonical/retained SHADOW reprice path","downstream":["summary-reuse wrapper","Price-all","Router","Portfolio"],"effects":["Fresh direct provider observation when path reaches refresh."],"authority":"Explicit fresh runtime binding; SHADOW only.","class":"RETAINED_COMPATIBILITY","status":"P4.4R first-class fresh reprice; no live reproof after P4.4S.","notes":""},
        {"id":"EP-SHADOW-BOUND-WORKER","name":"Current Shadow timeout-bound worker","kind":"WORKER","path":"scripts/execute_current_shadow_all_market_fresh_reprice_bound.py","symbol":"timeout supervisor","tokens":["def _write_timeout_receipt(","subprocess.run("],"caller":"Daily/fresh-reprice supervisor","downstream":["fresh-reprice worker"],"effects":["No new authority beyond supervised inner SHADOW execution."],"authority":"Timeout/finalization boundary.","class":"RETAINED_COMPATIBILITY","status":"Retained bounded wrapper.","notes":""},
        {"id":"EP-SHADOW-RUNNER","name":"Current Shadow all-market runner","kind":"RUNNER","path":"domain/current_shadow_all_market_runner.py","symbol":"execute_current_shadow_all_market","tokens":["def execute_current_shadow_all_market(","resolve_shadow_canonical_core"],"caller":"Current Shadow supervisor","downstream":["canonical-core adapter","source/reconciliation/Price-all/Router/Portfolio"],"effects":["Conditional provider acquisition and SHADOW delivery boundary."],"authority":"Profile-specific SHADOW runtime binding.","class":"CANONICAL_SUPPORTED","status":"Canonical SHADOW runtime runner; successor proof remains noncompliant.","notes":""},
        {"id":"EP-SHADOW-CORE-ADAPTER","name":"Current Shadow canonical-core adapter","kind":"SERVICE","path":"domain/current_shadow_canonical_core_adapter.py","symbol":"resolve_shadow_canonical_core","tokens":["def resolve_shadow_canonical_core(","def build_current_shadow_price_context_from_reconciliation("],"caller":"Current Shadow runner","downstream":["registered canonical components and retained implementations"],"effects":["No independent acquisition; downstream owners act within bound authority."],"authority":"Resolves SHADOW-eligible registered components; does not grant MAIN authority.","class":"CANONICAL_SUPPORTED","status":"P4.4S adapter ownership fix is merged.","notes":""},
        {"id":"EP-SHADOW-RUNTIME-BINDINGS","name":"Current Shadow runtime bindings","kind":"SERVICE","path":"domain/current_shadow_runtime_bindings.py","symbol":"CurrentShadowRuntimeBindings","tokens":["class CurrentShadowRuntimeBindings"],"caller":"Canonical SHADOW execution context","downstream":["Price-all","Router","Portfolio","fresh-reprice verification"],"effects":["No standalone external operation."],"authority":"Source-controlled immutable execution composition; SHADOW only.","class":"CANONICAL_SUPPORTED","status":"P4.4R composition owner.","notes":""},
    ]


def _entrypoint_record(root: Path, definition: dict[str, Any], evidence_ids: dict[str, str]) -> dict[str, Any]:
    path = definition["path"]
    found = _line_evidence(root, path, definition["tokens"], definition["id"])
    return {
        "entrypoint_id": definition["id"],
        "display_name": definition["name"],
        "kind": definition["kind"],
        "source_path": path,
        "symbol_or_trigger": definition["symbol"],
        "caller_surface": definition["caller"],
        "downstream_targets": definition["downstream"],
        "external_side_effects": definition["effects"],
        "authority_profile_behavior": definition["authority"],
        "current_classification": definition["class"],
        "support_status": definition["status"],
        "source_evidence": found,
        "evidence_ids": [evidence_ids[path]],
        "notes": definition["notes"],
    }


def _capabilities() -> list[dict[str, Any]]:
    rows = [
        ("CAP-OFFLINE-REPLAY","Retained evidence replay","VERIFIED_AVAILABLE","SHADOW/research","Local deterministic replay/audits","Source-specific replay/auditor scripts","EVID-P4-4R-RECEIPT","Live/provider reads are excluded; each replay contract is bounded.","OFFLINE_ONLY","NO","AUTH-01A"),
        ("CAP-PROVIDER-ACQUISITION","Current provider acquisition","AVAILABLE_RETAINED_COMPATIBILITY","SHADOW; legacy routes also expose browsing","FotMob and SportyBet facts/quotes","Canonical SHADOW runner and retained legacy paths","EVID-RUN-36345657852","Actual run acquired 223 provider events; each future acquisition requires separate owner authorization.","EXTERNAL_READ","YES","AUTH-01C"),
        ("CAP-FIXTURE-BROWSING","Fixture browsing","AVAILABLE_RETAINED_COMPATIBILITY","Legacy UI","GET leagues and upcoming fixtures","/api/leagues and /api/fixtures","EVID-SOURCE-API-SERVER-PY","Cache misses construct FotMobAdvancedScraper; not offline browsing.","EXTERNAL_READ","YES","APP-01"),
        ("CAP-SHADOW-ANALYSIS","SHADOW analysis","VERIFIED_AVAILABLE","SHADOW/research_shadow","Reconcile, Price-all, Router and Portfolio analysis","AthenaRunService to Current Shadow supervisor","EVID-RUN-36345657852","Internal analysis reached terminal shortfall; run had unauthorized delivery side effect.","PROVIDER_READ","YES","AUTH-01D"),
        ("CAP-SHADOW-DELIVERY","SHADOW share-code delivery","AVAILABLE_RETAINED_COMPATIBILITY","SHADOW/research_shadow","Create/reload/verify anonymous share code","Current Shadow delivery boundary","EVID-RUN-36345657852","Technically available and coupled to SHADOW request; capability did not intersect invocation intent in the latest run.","EXTERNAL_WRITE","YES","AUTH-01A"),
        ("CAP-SHADOW-NO-DELIVERY","SHADOW analysis without delivery","BLOCKED_BY_AUTHORITY","SHADOW/research_shadow","Analysis-only request with create_share_code=false","RunRequest/AuthorityManifest and service","EVID-SOURCE-SERVICES-ATHENA-RUN-SERVICE-PY","Current service requires create_share_code=true for SHADOW; explicit no-delivery request is rejected.","NONE_UNTIL_AUTHORIZED","YES","AUTH-01A"),
        ("CAP-MAIN-LIVE-ANALYSIS","MAIN live analysis","BLOCKED_BY_AUTHORITY","MAIN/main_application","Production MAIN analysis request","MainFailClosedExecutor","EVID-SOURCE-SERVICES-ATHENA-RUN-SERVICE-PY","Production executor is target-only and returns MAIN_PHASE6_AUTHORITY_REQUIRED.","NONE","YES","CORE-01"),
        ("CAP-MAIN-DELIVERY","MAIN delivery","NOT_AUTHORIZED","MAIN","Create external delivery","No production MAIN delivery executor","EVID-SOURCE-SERVICES-ATHENA-RUN-SERVICE-PY","No MAIN delivery authority in current canonical service.","PROHIBITED","YES","CORE-01"),
        ("CAP-EMAIL-NOTIFICATION","Email/notification","AVAILABLE_RETAINED_COMPATIBILITY","Legacy Current Shadow workflow","Optional post-core email when configured","current-shadow-all-market.yml","EVID-WF-CURRENT-SHADOW-ALL-MARKET","Owned by retained legacy workflow; not migrated to canonical post-core consumer.","EXTERNAL_WRITE","YES","INT-01"),
        ("CAP-HISTORY-VIEW","Retained history viewing","AVAILABLE_RETAINED_COMPATIBILITY","SHADOW/research","Read retained identity/history artifacts","Canonical workflow historical artifact restoration","EVID-WF-ATHENA-RUN","History is restored from prior legacy workflow artifacts; persistent ancestry cutover remains open.","LOCAL_READ","NO","INT-01"),
        ("CAP-EXPORT","Export","AVAILABLE_RETAINED_COMPATIBILITY","Legacy UI","Prepare bookmaker export payload","api.export router","EVID-SOURCE-API-EXPORT-PY","Export response does not prove delivery and is not canonical lineage.","LOCAL_RESPONSE","NO","UX-01"),
        ("CAP-BACKUP-RESTORE","Application backup/restore","NOT_IMPLEMENTED","Desktop product target","Verified app-data backup and restore","No reviewed product-level store/backup journey","EVID-SOURCE-DATABASE-SCHEMA-SQL","Future app persistence and recovery need additive schema and verified backup implementation.","LOCAL_DATA","NO","DATA-01"),
        ("CAP-DESKTOP-INSTALLED","Installed desktop runtime","BLOCKED_BY_IMPLEMENTATION","Windows/Linux target","Run without checkout/Git/system Python","run_desktop.py currently repo-relative developer shell","EVID-SOURCE-RUN-DESKTOP-PY","No qualified signed installed application runtime at baseline.","LOCAL_PROCESS","NO","PORT-02"),
        ("CAP-WINDOWS-QUALIFICATION","Windows qualification","BLOCKED_BY_IMPLEMENTATION","Windows 11 x86-64 target","Build/runtime/path/byte qualification","Reported Windows CRLF/canonical fixture failures","EVID-SOURCE-DOMAIN-RUN-CONTRACTS-PY","10 Windows CRLF/canonical-fixture failures reported in PR #414 remain unresolved.","BUILD_AND_LOCAL_IO","NO","PORT-01"),
        ("CAP-LINUX-QUALIFICATION","Linux qualification","BLOCKED_BY_IMPLEMENTATION","Ubuntu 24.04 LTS x86-64 target","Installed artifact runtime qualification","Hosted Linux tests only","EVID-POSTMERGE-TESTS","CI green is not a no-checkout installed artifact test.","BUILD_AND_LOCAL_IO","NO","PKG-LINUX"),
        ("CAP-SCHEDULED-RUN","Scheduled execution","AVAILABLE_RETAINED_COMPATIBILITY","Canonical schedule defaults MAIN; legacy Shadow schedule also exists","Daily GitHub schedule","athena-run.yml and current-shadow-all-market.yml","EVID-WF-ATHENA-RUN","Two workflow families coexist; schedule ownership and date parity are unresolved.","CONDITIONAL_EXTERNAL","YES","INT-01"),
        ("CAP-ISSUE-COMMENT","Issue-comment compatibility","AVAILABLE_RETAINED_COMPATIBILITY","Legacy Current Shadow","Owner-only /athena-shadow command","current-shadow-all-market.yml issue_comment trigger","EVID-WF-CURRENT-SHADOW-ALL-MARKET","Grammar and workflow owner check remain a separate compatibility surface.","CONDITIONAL_EXTERNAL","YES","INT-01"),
        ("CAP-WAGER","Wager placement","NOT_AUTHORIZED","All","Submit stake or wager","Canonical RunRequest and AuthorityManifest deny wagering","EVID-SOURCE-DOMAIN-RUN-CONTRACTS-PY","place_wager and wager_placed remain false in canonical evidence.","PROHIBITED","YES","NONE"),
        ("CAP-ACCOUNT-ACCESS","Login/cookies/wallet/staking","NOT_AUTHORIZED","Canonical MAIN/SHADOW","Authenticate or access account/wallet","Canonical authority contract explicitly denies sensitive capabilities","EVID-SOURCE-DOMAIN-RUN-CONTRACTS-PY","Legacy source is not treated as proof of a supported account capability.","PROHIBITED","YES","NONE"),
    ]
    return [{"capability_id":r[0],"name":r[1],"state":r[2],"profile":r[3],"operation":r[4],"controlling_source":r[5],"evidence_ids":[r[6]],"blocker_or_reason":r[7],"side_effect_class":r[8],"owner_approval_required":r[9]=="YES","next_roadmap_mission":r[10]} for r in rows]


def _debts() -> list[dict[str, Any]]:
    rows = [
        ("DEBT-LEGACY-ACCA-BUILDER-API","POST /api/generate calls legacy AccaBuilder compatibility layer.","api/server.py","Legacy generated accumulator is presented as product journey while canonical run service exists separately.","Two competing orchestration surfaces obscure source and authority ownership.","HIGH","APP-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-UI-STATIC-ENGINE-ONLINE","Status UI treats process/weights file as engine readiness.","api/server.py","Operator may mistake superficial liveness for capability/readiness.","Readiness has no capability manifest or evidence freshness.","HIGH","APP-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-UI-FULLPROOF-LANGUAGE","Fullproof/guaranteed-like labels remain in desktop UI and window title.","ui/index.html","Overstates research output reliability.","Product truth diverges from shortfall and evidence-gated behavior.","HIGH","UX-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-UI-UNSUPPORTED-STAKE-RISK","Stake/risk elements are shown in legacy result UI without reviewed product authority.","ui/index.html","Can suggest a staking recommendation that the canonical product does not authorize.","Confuses analysis and wagering capability.","HIGH","UX-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-UI-LONG-BLOCKING-RUN","Legacy JS uses a 300000ms request timeout for generation.","ui/app.js","Long waits and ambiguous retry behavior; no durable job progress journey.","No durable desktop job ownership/recovery boundary.","MEDIUM","RUN-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-SHELL-FIXED-PORT","Legacy shell assumes 127.0.0.1:8500.","run_desktop.py","Port collisions and accidental attachment to another responder.","Fixed-port process identity is not bound to the launching process.","HIGH","APP-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-API-WILDCARD-CORS","API config uses wildcard origins/methods/headers with credentials enabled.","api/server.py","Weak same-origin/local API trust boundary.","Local API lacks trusted per-launch origin/session design.","HIGH","APP-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-SHELL-UNTRUSTED-RESPONDER","Launcher accepts an existing HTTP status responder on fixed port.","run_desktop.py","UI may connect to a process not created by this launch.","No signed nonce/session handshake proves process ownership.","HIGH","APP-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-INSTALLED-RUNTIME-GIT","Canonical service/component identity currently relies on Git/repository state.","services/athena_run_service.py","Installed app may fail outside a checkout.","Release identity must replace mutable Git context without inventing SHA.","HIGH","PORT-02","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-REPO-RELATIVE-RESOURCES","Legacy UI/config/resource paths rely on repository layout/cwd.","run_desktop.py","Installed launch may resolve wrong or missing assets.","No canonical resource root/release manifest for installed payload.","MEDIUM","PORT-02","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-WINDOWS-CANONICAL-BYTES","10 Windows CRLF/canonical-fixture failures were reported in PR #414.","P4.4S merge/test evidence; source identity hashes","Windows test result cannot be inferred from Hosted Linux CI.","Byte-level evidence portability is not qualified.","HIGH","PORT-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-WORKFLOW-DUPLICATION","Canonical and legacy Current Shadow workflow families coexist.",".github/workflows/athena-run.yml; .github/workflows/current-shadow-all-market.yml","Multiple schedules/triggers can initiate similar research paths.","Ownership/caller/notification migration is incomplete.","HIGH","INT-01","RETIREMENT_NOT_AUTHORIZED"),
        ("DEBT-SCHEDULED-SHADOW-OWNERSHIP","Legacy workflow retains scheduled SHADOW execution.",".github/workflows/current-shadow-all-market.yml","Scheduled work can continue outside canonical workflow request surface.","P4.4 scheduled ownership/cutover gate remains open.","HIGH","INT-01","RETIREMENT_NOT_AUTHORIZED"),
        ("DEBT-PERSISTENT-IDENTITY-ANCESTRY","Canonical workflow restores historical legacy Current Shadow identity artifacts.",".github/workflows/athena-run.yml","State lineage depends on artifacts from another workflow family.","Persistent identity/history ancestry has not cut over.","HIGH","INT-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-NOTIFICATION-EMAIL-OWNERSHIP","Legacy workflow owns optional post-core email behavior.",".github/workflows/current-shadow-all-market.yml","Notification behavior is coupled to legacy workflow execution.","Post-core consumer ownership not migrated.","MEDIUM","INT-01","RETIREMENT_NOT_AUTHORIZED"),
        ("DEBT-ISSUE-COMMENT-COMPAT","Owner-only /athena-shadow grammar remains active on issue comments.",".github/workflows/current-shadow-all-market.yml","A legacy command surface remains in user/operator use.","Needs explicit compatibility disposition before retirement.","MEDIUM","INT-01","RETIREMENT_NOT_AUTHORIZED"),
        ("DEBT-LAGOS-UTC-DATE-PARITY","Canonical and legacy date handling/cutover require fail-closed parity.","services/athena_run_request_parser.py; .github/workflows/current-shadow-all-market.yml","Requested calendar day must not silently shift across UTC/Lagos behavior.","Date-policy parity is a separate migration gate.","HIGH","INT-01","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-SHADOW-DELIVERY-COUPLING","SHADOW request parser maps research_shadow to create_share_code=true and service requires it.","services/athena_run_request_parser.py; services/athena_run_service.py","User intent to analyze without delivery cannot currently be represented in canonical SHADOW request.","Capability was not intersected with owner intent in latest run.","HIGH","AUTH-01A","CHANGE_REQUIRES_REVIEW"),
        ("DEBT-AUTHORIZATION-PREFLIGHT","Run 36345657852 executed share-code create/reload despite owner prohibition.","GitHub artifact 10940728036; owner authorization context; resolved request","Unauthorized external delivery side effect occurred despite correct workflow control-plane success.","Invocation intent and operation capability are not intersected before execution.","HIGH","AUTH-01A","CHANGE_REQUIRES_REVIEW"),
    ]
    return [{"debt_id":r[0],"description":r[1],"source_evidence":[r[2]],"evidence_ids":["EVID-RUN-36345657852" if r[0] in {"DEBT-AUTHORIZATION-PREFLIGHT","DEBT-SHADOW-DELIVERY-COUPLING"} else "EVID-SOURCE-API-SERVER-PY"],"user_impact":r[3],"architecture_impact":r[4],"severity":r[5],"owning_future_mission":r[6],"delete_or_change_authorization":r[7]} for r in rows]


def _gates() -> list[dict[str, Any]]:
    rows = [
        ("GATE-AUTH-01","OPEN","Owner intent and operation capability are not independent; the last SHADOW request forced delivery and the run performed it despite explicit owner prohibition.",["AUTH-01A","AUTH-01B","AUTH-01C","AUTH-01D"],["A source-controlled intent envelope, capability set, explicit intersection, and offline tests proving denied operations are unreachable."],["Treating SHADOW profile as owner intent; dispatching before preview; interpreting `place_wager=false` as delivery authorization."]),
        ("GATE-PORT-01","OPEN","Windows canonical byte/path parity is unresolved; 10 CRLF/canonical-fixture failures were reported.",["PORT-01"],["Repeatable Windows 11 byte-level tests and artifact parity evidence on the exact build."],["Calling green Linux CI Windows qualification; normalizing bytes without reviewed contract."]),
        ("GATE-PORT-02","OPEN","Installed runtime still relies on Git/repository-relative resources.",["PORT-02"],["Installed Windows/Linux runtime tests without Git, system Python, checkout, or expected cwd."],["Inventing a commit SHA when Git is absent; silently falling back to checkout resources."]),
        ("GATE-P4_4-CLEAN-SUCCESSOR","OPEN","Run 36345657852 reached terminal internal analysis but includes owner-prohibited share-code side effect.",["AUTH-01A","AUTH-01D"],["One separately authorized successor proof after authorization semantics are corrected, with exact request/artifact/receipt ancestry and no unauthorized delivery."],["Calling workflow success a clean business proof; retrying prior run; inferring authorization from internal result."]),
        ("GATE-P4_4-CALLER-MIGRATION","NOT_AUTHORIZED","P4.4 remains incomplete and the clean successor proof has not been established.",["INT-01"],["Owner authorization plus capability parity, schedule/date/history/notification/issue-comment dispositions and source evidence."],["Migrating callers before gate closure; deleting legacy surface early."]),
        ("GATE-CHECKPOINT-E","OPEN","Workflow consolidation criteria and legacy ownership cutover remain incomplete.",["INT-01"],["Evidence for ownership, caller compatibility, history ancestry, notification and retirement prerequisites."],["Retiring workflow based only on PR merge or a green run."]),
        ("GATE-APP-01","OPEN","Legacy server uses fixed port and permissive CORS; responder identity is not bound to its launcher.",["APP-01"],["Same-origin API design, per-launch nonce/session handshake, trusted process ownership, and native integration tests."],["Assuming localhost or random port alone establishes trust."]),
        ("GATE-DATA-01","OPEN","The proposed application-owned data/persistence and additive migrations are not implemented.",["DATA-01"],["Versioned additive migration, transactional constraints, backup/restore and corruption tests."],["Destructive schema rewrite; treating evidence blobs as mutable application rows."]),
        ("GATE-RUN-01-02","OPEN","Durable job ownership/recovery and an external side-effect ledger tied to owner authorization and exact evidence are not implemented.",["RUN-01","RUN-02","AUTH-01D"],["Persistent job/attempt/event lifecycle, idempotency and restart recovery tests plus operation rows with intent/capability decision, request digest, result evidence and replay-safe transitions."],["Blindly retrying a POST after timeout; equating UI timeout with worker cancellation; replaying delivery without a fresh authorization check."]),
        ("GATE-UX-01","OPEN","Legacy UI does not present an end-to-end truthful research-preview journey.",["UX-01"],["Truthful readiness, explicit request preview, durable progress, evidence-linked result, shortfall and recovery screens."],["Fullproof/guarantee language; hiding unknowns or converting missing data to zero."]),
        ("GATE-PKG-WINDOWS","OPEN","No qualified native Windows 11 x86-64 installer/runtime.",["PKG-WINDOWS","REL-01"],["Signed, installable, updateable build tested with Unicode/locked/read-only paths and no Git/Python."],["Using the developer checkout as release qualification."]),
        ("GATE-PKG-LINUX","OPEN","No qualified native Ubuntu 24.04 LTS x86-64 installer/runtime.",["PKG-LINUX","REL-01"],["Signed native package and installed runtime tested outside checkout/system Python assumptions."],["Treating Hosted Tests as packaged application qualification."]),
        ("GATE-REL","OPEN","Signing, release manifest, update/rollback and support ownership are not qualified.",["REL-01"],["Signed artifact manifest, verified update, rollback and documented support/release owner."],["Installing unsigned/unverified payload; destructive update or rollback without retained data."]),
    ]
    return [{"gate_id":r[0],"current_state":r[1],"exact_blocker":r[2],"dependencies":r[3],"evidence_required_to_close":r[4],"prohibited_shortcuts":r[5],"evidence_ids":["EVID-RUN-36345657852"] if r[0]=="GATE-P4_4-CLEAN-SUCCESSOR" else ["EVID-POSTMERGE-TESTS"]} for r in rows]


def _workflow_inventory(root: Path) -> list[dict[str, Any]]:
    return [_workflow_parse(root, path) for path in sorted((root / ".github/workflows").glob("*.yml"))]


def _source_inventory(root: Path, cli_records: list[dict[str, Any]], workflow_records: list[dict[str, Any]], docs_refs: set[str]) -> list[dict[str, Any]]:
    paths = set(CORE_SOURCE_PATHS)
    paths.update(w["path"] for w in workflow_records)
    paths.update(docs_refs)
    paths.update(r["source_path"] for r in cli_records if (root / r["source_path"]).is_file())
    missing = sorted(path for path in paths if not (root / path).is_file())
    if missing:
        # Missing optional documentation/CLI candidates remain explicitly represented,
        # but core source paths and discovered workflow paths must exist.
        required = set(CORE_SOURCE_PATHS) | {w["path"] for w in workflow_records}
        absent_required = sorted(set(missing) & required)
        if absent_required:
            raise ValueError("required source paths missing: " + ", ".join(absent_required))
        paths.difference_update(missing)
    result = []
    for rel in sorted(paths):
        path = root / relative_path(rel)
        role = "WORKFLOW_SOURCE" if rel.startswith(".github/workflows/") else ("DOCUMENTED_CLI_SOURCE" if rel.startswith("scripts/") else "BASELINE_SOURCE");
        normalized = normalized_source_bytes(path)
        result.append({"evidence_id":"EVID-SOURCE-" + _slug(rel),"path":rel,"normalized_byte_count":len(normalized),"sha256":sha256_bytes(normalized),"hash_kind":"LF_NORMALIZED_SOURCE_SHA256","evidence_class":"SOURCE_CONTROLLED_AT_BASELINE","role":role})
    return result


def _receipt_anchors(root: Path) -> dict[str, Any]:
    names = {
        "p4_4r_inventory": "artifacts/architecture/p4_4r_shadow_runtime_composition_inventory_v1.json",
        "p4_4r_receipt": "artifacts/architecture/p4_4r_shadow_runtime_composition_stabilization_v1.json",
        "p4_4s_receipt": "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json",
    }
    result = {}
    for key, rel in names.items():
        raw = _read(root, rel)
        parsed = json.loads(raw)
        result[key] = {"path":rel,"file_sha256":sha256_bytes(raw),"canonical_sha256":parsed.get("canonical_sha256"),"policy_id":parsed.get("policy_id"),"evidence_class":"SOURCE_CONTROLLED_HISTORICAL_RECEIPT"}
    transition = json.loads(_read(root, names["p4_4s_receipt"])).get("source_transition", {})
    result["p4_4s_source_transition"] = transition
    return result


def _static_assertions(root: Path) -> list[dict[str, Any]]:
    text = {p: _read(root, p).decode("utf-8", errors="strict") for p in CORE_SOURCE_PATHS if (root / p).is_file()}
    checks = [
        ("ASSERT-API-LEGACY-ACCA","api/server.py",["from services.legacy_acca_builder_compat import AccaBuilder","@app.post(\"/api/generate\")","builder = AccaBuilder()"]),
        ("ASSERT-API-WILDCARD-CORS","api/server.py",["allow_origins=[\"*\"]","allow_credentials=True","allow_methods=[\"*\"]","allow_headers=[\"*\"]"]),
        ("ASSERT-API-PROVIDER-BROWSING","api/server.py",["@app.get(\"/api/leagues\")","@app.get(\"/api/fixtures\")","FotMobAdvancedScraper()","fetch_upcoming_matches(days_ahead=days)"]),
        ("ASSERT-DESKTOP-TRUST","run_desktop.py",["port=8500","daemon=True","wait_for_server()","webview.create_window(","os.path.join(os.path.dirname(__file__), \"ui\", \"index.html\")"]),
        ("ASSERT-UI-LEGACY-SEMANTICS","ui/app.js",["http://127.0.0.1:8500","REQUEST_TIMEOUT_MS = 300000"]),
        ("ASSERT-UI-PRODUCT-CLAIMS","ui/index.html",["Fullproof","Stake:","Risk:"]),
        ("ASSERT-CANONICAL-AND-LEGACY-WORKFLOWS",".github/workflows/athena-run.yml",["schedule:","workflow_dispatch:","profile:","default: main","current-shadow-all-market"]),
        ("ASSERT-LEGACY-COMMENT-AND-EMAIL",".github/workflows/current-shadow-all-market.yml",["issue_comment:","/athena-shadow target=","Email durable Shadow result when configured"]),
        ("ASSERT-REQUEST-SHADOW-DELIVERY-COUPLING","services/athena_run_request_parser.py",["return \"SHADOW\", \"research_shadow\", True","create_share_code=True"]),
        ("ASSERT-SERVICE-MANIFEST-COUPLING","services/athena_run_service.py",["(\"SHADOW\", \"research_shadow\", \"sportybet\", True)","request.create_share_code is not True","MAIN_PHASE6_AUTHORITY_REQUIRED"]),
    ]
    return [{"assertion_id":key,"path":path,"expected_literals":tokens,"result":"PASS" if all(t in text.get(path,"") for t in tokens) else "FAIL"} for key,path,tokens in checks]


def build_baseline(root: Path = ROOT) -> dict[str, Any]:
    if not (root / "artifacts/architecture/p4_4s_canonical_adapter_bound_context_builder_v1.json").is_file():
        raise ValueError("not an ATHENA baseline source tree")
    workflow_records = _workflow_inventory(root)
    cli_records, docs_refs = _documented_cli(root)
    sources = _source_inventory(root, cli_records, workflow_records, docs_refs)
    by_path = {row["path"]:row["evidence_id"] for row in sources}
    core_entries = [_entrypoint_record(root, row, by_path) for row in _core_entrypoint_definitions()]
    workflow_entries = []
    for wf in workflow_records:
        workflow_entries.append({
            "entrypoint_id":wf["entrypoint_id"],"display_name":wf["name"],"kind":"WORKFLOW","source_path":wf["path"],
            "symbol_or_trigger":wf["trigger_kinds"],"caller_surface":"GitHub Actions event/schedule/dispatch/issue-comment surface.",
            "downstream_targets":wf["job_ids"],"external_side_effects":[f"provider={wf['provider_acquisition']}",f"delivery={wf['delivery']}",f"email={wf['email_notification']}"],
            "authority_profile_behavior":wf["authority_profile_behavior"],"current_classification":wf["current_classification"],
            "support_status":wf["support_status"],"source_evidence":[{"path":wf["path"],"sha256":wf["source_sha256"],"hash_kind":"LF_NORMALIZED_SOURCE_SHA256","role":"WORKFLOW_SOURCE"}],
            "evidence_ids":[by_path[wf["path"]]],"notes":wf["retained_reason"],
        })
    evidence_records = [{"evidence_id":s["evidence_id"],"kind":"SOURCE_FILE","path":s["path"],"sha256":s["sha256"],"evidence_class":s["evidence_class"]} for s in sources]
    evidence_records.extend([
        {"evidence_id":"EVID-POSTMERGE-TESTS","kind":"GITHUB_WORKFLOW_RUN","run_id":36344862612,"head_sha":BASE_COMMIT,"status":"completed","conclusion":"success","jobs":{"syntax":"success","test shard 1 of 8":"success","test shard 2 of 8":"success","test shard 3 of 8":"success","test shard 4 of 8":"success","test shard 5 of 8":"success","test shard 6 of 8":"success","test shard 7 of 8":"success","test shard 8 of 8":"success","test":"success"},"evidence_class":"LIVE_GITHUB_API_VERIFIED"},
        {"evidence_id":"EVID-POSTMERGE-CATALOG","kind":"GITHUB_WORKFLOW_RUN","run_id":36344862576,"head_sha":BASE_COMMIT,"status":"completed","conclusion":"success","evidence_class":"LIVE_GITHUB_API_VERIFIED"},
        {"evidence_id":"EVID-RUN-36345657852","kind":"GITHUB_ARTIFACT_AND_RUN","run_id":36345657852,"artifact_id":10940728036,"artifact_name":"athena-run-36345657852","artifact_sha256":"f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a","head_sha":BASE_COMMIT,"attempt":1,"conclusion":"success","request_sha256":"0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4","run_receipt_sha256":"a8ce4f163432ebead90ee649c7297115acba0a852ceeac2beeb5ef0bdc0d4b6d","inner_receipt_sha256":"80ce47a0965562cffd11d8dbd847740fbf57e36b8f1b173020827ea19a18b258","evidence_class":"GITHUB_ARTIFACT_DIGEST_AND_MEMBER_HASH_VERIFIED"},
        {"evidence_id":"EVID-ISSUE-REREAD-5859231125","kind":"GITHUB_ISSUE_COMMENT","issue_number":337,"comment_id":5859231125,"fact":"Mandatory post-5/5 architecture/source reread recorded complete; counter reset to 0/5.","evidence_class":"LIVE_GITHUB_COMMENT_VERIFIED"},
    ])
    evidence_records.extend({
        "evidence_id":"EVID-WF-"+_slug(w["path"].split("/")[-1].removesuffix(".yml")),
        "kind":"WORKFLOW_SOURCE","path":w["path"],"sha256":w["source_sha256"],"hash_kind":"LF_NORMALIZED_SOURCE_SHA256","evidence_class":"SOURCE_CONTROLLED_AT_BASELINE_COMMIT",
    } for w in workflow_records)
    receipts = _receipt_anchors(root)
    for key, item in receipts.items():
        if key == "p4_4s_source_transition":
            continue
        evidence_records.append({"evidence_id":"EVID-"+_slug(key),"kind":"HISTORICAL_ARCHITECTURE_RECEIPT","path":item["path"],"file_sha256":item["file_sha256"],"canonical_sha256":item["canonical_sha256"],"policy_id":item["policy_id"],"evidence_class":"SOURCE_CONTROLLED_HISTORICAL_RECEIPT"})
    entrypoints = sorted(core_entries + workflow_entries + cli_records,key=lambda r:r["entrypoint_id"])
    debts = _debts()
    gates = _gates()
    capabilities = _capabilities()
    mission_map = {
        "DEBT-LEGACY-ACCA-BUILDER-API":"APP-01","DEBT-UI-STATIC-ENGINE-ONLINE":"APP-01","DEBT-UI-FULLPROOF-LANGUAGE":"UX-01","DEBT-UI-UNSUPPORTED-STAKE-RISK":"UX-01","DEBT-UI-LONG-BLOCKING-RUN":"RUN-01","DEBT-SHELL-FIXED-PORT":"APP-01","DEBT-API-WILDCARD-CORS":"APP-01","DEBT-SHELL-UNTRUSTED-RESPONDER":"APP-01","DEBT-INSTALLED-RUNTIME-GIT":"PORT-02","DEBT-REPO-RELATIVE-RESOURCES":"PORT-02","DEBT-WINDOWS-CANONICAL-BYTES":"PORT-01","DEBT-WORKFLOW-DUPLICATION":"INT-01","DEBT-SCHEDULED-SHADOW-OWNERSHIP":"INT-01","DEBT-PERSISTENT-IDENTITY-ANCESTRY":"INT-01","DEBT-NOTIFICATION-EMAIL-OWNERSHIP":"INT-01","DEBT-ISSUE-COMMENT-COMPAT":"INT-01","DEBT-LAGOS-UTC-DATE-PARITY":"INT-01","DEBT-SHADOW-DELIVERY-COUPLING":"AUTH-01A","DEBT-AUTHORIZATION-PREFLIGHT":"AUTH-01A",
    }
    crosswalk = [{"baseline_item_id":d["debt_id"],"item_kind":"PRODUCT_DEBT","expected_mission_ids":[mission_map[d["debt_id"]]],"sequence_status":"PLANNED_NOT_STARTED"} for d in debts]
    gate_missions = {"GATE-AUTH-01":["AUTH-01A","AUTH-01B","AUTH-01C","AUTH-01D"],"GATE-PORT-01":["PORT-01"],"GATE-PORT-02":["PORT-02"],"GATE-P4_4-CLEAN-SUCCESSOR":["AUTH-01D"],"GATE-P4_4-CALLER-MIGRATION":["INT-01"],"GATE-CHECKPOINT-E":["INT-01"],"GATE-APP-01":["APP-01"],"GATE-DATA-01":["DATA-01"],"GATE-RUN-01-02":["RUN-01","RUN-02","AUTH-01D"],"GATE-UX-01":["UX-01"],"GATE-PKG-WINDOWS":["PKG-WINDOWS","REL-01"],"GATE-PKG-LINUX":["PKG-LINUX","REL-01"],"GATE-REL":["REL-01"]}
    crosswalk.extend({"baseline_item_id":g["gate_id"],"item_kind":"UNRESOLVED_GATE","expected_mission_ids":gate_missions[g["gate_id"]],"sequence_status":"PLANNED_NOT_STARTED"} for g in gates)
    source_inventory_digest = sha256_bytes(canonical_bytes(sources))
    static = _static_assertions(root)
    if any(item["result"] != "PASS" for item in static):
        failed = [item["assertion_id"] for item in static if item["result"] != "PASS"]
        raise ValueError("exact baseline static source assertions failed: " + ", ".join(failed))
    run = dict(KNOWN_LIVE_RUN)
    run.update({
        "request": {"authority_profile":"SHADOW","mode":"research_shadow","date":["2026-09-27"],"target_legs":20,"target_total_odds":None,"bookie":"sportybet","create_share_code":True,"place_wager":False},
        "counts": {"provider_event_count":223,"reviewed_fixture_count":3,"reconciled_fixture_count":3,"priced_fixture_count":3,"router_selected_count":3,"router_no_bet_count":0,"selected_leg_count":3,"reserve_leg_count":0,"target_legs":20,"shortfall":17},
        "source_capture": {"accepted_attempt_index":1,"attempt_count":1,"final_state":"ACCEPTED_ATTEMPT_1","provider_page_count":3,"page_event_counts":[100,100,23],"workflow_retry":False,"per_page_transport_retry":False,"fallback":False,"cross_epoch_event_merge":False,"non_totalnum_parse_failure_fresh_epoch":False},
        "delivery": {"share_code_operation_attempted":True,"share_code_result_verified":True,"raw_code_or_url_stored":False,"owner_authorized_share_code_action":False},
        "safety": {"login":False,"cookies":False,"wallet":False,"staking":False,"bet":False,"place_wager":False,"wager_placed":False},
        "interpretation": "GitHub workflow success is control-plane/evidence-upload success. Internal SHADOW analysis reached a terminal shortfall result, but create_share_code=true was persisted and share-code create/reload verification occurred despite owner prohibition. This is not clean successor evidence and authorizes neither caller migration nor workflow retirement.",
    })
    data = {
        "schema_version":1,"baseline_id":BASELINE_ID,"policy_id":POLICY_ID,"repository":REPOSITORY,
        "baseline_source_commit_sha":BASE_COMMIT,"baseline_source_tree_sha":BASE_TREE,
        "baseline_branch_at_capture":"main","implementation_branch":"feat/base-00-product-capability-closure-baseline",
        "implementation_review":{"pull_request_number":None,"head_sha_at_pr_creation":None,"state_at_capture":"NOT_CREATED_AT_BASELINE_FREEZE"},
        "authority_statement":{"baseline_is_descriptive_evidence":True,"grants_provider_authority":False,"grants_delivery_authority":False,"grants_main_authority":False,"grants_workflow_cutover_authority":False,"grants_wager_authority":False,"provider_acquisition_during_base00":False,"workflow_dispatch_during_base00":False,"live_retry_during_base00":False,"share_code_operation_during_base00":False,"wager_action_during_base00":False},
        "source_precedence":["CURRENT_VERIFIED_REPOSITORY_SOURCE_AND_IMMUTABLE_EVIDENCE","ARCHITECTURE_REMEDIATION_MASTER_V2","SIX_DOCUMENT_PRODUCT_AND_IMPLEMENTATION_BLUEPRINT","PRODUCT_IMPLEMENTATION_MASTER_V1","ISSUE_337_AND_SOURCE_CONTROLLED_ARCHITECTURE_RECEIPTS"],
        "source_documents":SOURCE_DOCUMENTS,
        "governance":{"source_review_counter":"0/5","mandatory_5_of_5_reread_completed":True,"reread_issue_337_comment_id":5859231125,"p4_4":"INCOMPLETE","architecture_checkpoint_e":"INCOMPLETE","clean_canonical_shadow_successor_proof":"INCOMPLETE","next_live_proof":"NOT_AUTHORIZED","caller_migration":"NOT_AUTHORIZED","workflow_retirement":"NOT_AUTHORIZED","next_mission":"AUTH-01A","next_mission_authorized":False},
        "postmerge_gates":[{"gate_id":"EVID-POSTMERGE-TESTS","run_id":36344862612,"head_sha":BASE_COMMIT,"status":"completed","conclusion":"success","required_jobs":"all successful"},{"gate_id":"EVID-POSTMERGE-CATALOG","run_id":36344862576,"head_sha":BASE_COMMIT,"status":"completed","conclusion":"success"}],
        "latest_live_evidence":run,
        "source_snapshot":{"evidence_class":"SOURCE_CONTROLLED_AT_BASELINE_COMMIT","source_commit_sha":BASE_COMMIT,"source_tree_sha":BASE_TREE,"files":sources,"canonical_sha256":source_inventory_digest,"source_hash_policy":"UTF-8 source text hashes use LF-normalized bytes so the same Git content has identical Windows/Linux snapshot identity; historical receipt hashes remain raw byte hashes.","reproduction":{"method":"static source inspection; Python AST/text/YAML-source parsing only; no application/provider modules imported","assertions":static,"result":"PASS","reproduction_sha256":sha256_bytes(canonical_bytes(static)),"future_safe_rule":"Historical audit verifies stored snapshot integrity; current source comparison is optional and skips when any pinned source file changes."}},
        "evidence_records":evidence_records,"entrypoints":entrypoints,"workflows":workflow_records,"capabilities":capabilities,"product_debt":debts,"unresolved_gates":gates,
        "platform_debt":[
            {"platform_debt_id":"PLAT-WINDOWS-11-X64","target":"Windows 11 x86-64","state":"NOT_QUALIFIED","details":"10 Windows CRLF/canonical-fixture failures were reported in PR #414; no exact-head Windows qualification is recorded.","evidence_ids":["EVID-P4-4S-RECEIPT"],"next_mission":"PORT-01 / PKG-WINDOWS"},
            {"platform_debt_id":"PLAT-UBUNTU-24-04-X64","target":"Ubuntu 24.04 LTS x86-64","state":"NOT_QUALIFIED_AS_INSTALLED_PRODUCT","details":"Hosted Linux Tests passed; no Git-free installed product package/runtime qualification is recorded.","evidence_ids":["EVID-POSTMERGE-TESTS"],"next_mission":"PKG-LINUX"},
            {"platform_debt_id":"PLAT-NO-GIT","target":"Windows and Linux installed mode","state":"OPEN","details":"No Git-free release identity/runtime proof; current service binds to exact Git HEAD.","evidence_ids":["EVID-SOURCE-SERVICES-ATHENA-RUN-SERVICE-PY"],"next_mission":"PORT-02"},
            {"platform_debt_id":"PLAT-NO-SYSTEM-PYTHON","target":"Windows and Linux installed mode","state":"OPEN","details":"Bundled dependency/runtime package has not been qualified independently of system Python.","evidence_ids":["EVID-SOURCE-REQUIREMENTS-TXT"],"next_mission":"PKG-WINDOWS / PKG-LINUX"},
            {"platform_debt_id":"PLAT-RESOURCE-CWD","target":"Windows and Linux installed mode","state":"OPEN","details":"Repository-relative resources, unrelated working directory and read-only install paths need qualification.","evidence_ids":["EVID-SOURCE-RUN-DESKTOP-PY"],"next_mission":"PORT-02"},
            {"platform_debt_id":"PLAT-UNICODE-LOCKED-PATH","target":"Windows and Linux installed mode","state":"OPEN","details":"Unicode paths and locked-file install/update recovery are not qualified.","evidence_ids":["EVID-SOURCE-RUN-DESKTOP-PY"],"next_mission":"PKG-WINDOWS / REL-01"},
        ],
        "evidence_anchors":[
            {"evidence_id":"EVID-P4-4R-INVENTORY","path":receipts["p4_4r_inventory"]["path"],"file_sha256":receipts["p4_4r_inventory"]["file_sha256"],"canonical_sha256":None,"evidence_class":"SOURCE_CONTROLLED"},
            {"evidence_id":"EVID-P4-4R-RECEIPT","path":receipts["p4_4r_receipt"]["path"],"file_sha256":receipts["p4_4r_receipt"]["file_sha256"],"canonical_sha256":receipts["p4_4r_receipt"]["canonical_sha256"],"evidence_class":"SOURCE_CONTROLLED_HISTORICAL"},
            {"evidence_id":"EVID-P4-4S-RECEIPT","path":receipts["p4_4s_receipt"]["path"],"file_sha256":receipts["p4_4s_receipt"]["file_sha256"],"canonical_sha256":receipts["p4_4s_receipt"]["canonical_sha256"],"evidence_class":"SOURCE_CONTROLLED_HISTORICAL"},
            {"evidence_id":"EVID-P4-4S-CONTEXT-SOURCE-BEFORE","path":"domain/_current_shadow_quote_binding.py","sha256":receipts["p4_4s_source_transition"]["context_verifier_source_before_sha256"],"evidence_class":"SOURCE_HASH_BOUND_BY_P4_4S_RECEIPT"},
            {"evidence_id":"EVID-P4-4S-CONTEXT-SOURCE-AFTER","path":"domain/_current_shadow_quote_binding.py","sha256":receipts["p4_4s_source_transition"]["context_verifier_source_after_sha256"],"evidence_class":"SOURCE_HASH_BOUND_BY_P4_4S_RECEIPT"},
            {"evidence_id":"EVID-P4-4S-ADAPTER-SOURCE-BEFORE","path":"domain/current_shadow_canonical_core_adapter.py","sha256":receipts["p4_4s_source_transition"]["canonical_adapter_source_before_sha256"],"evidence_class":"SOURCE_HASH_BOUND_BY_P4_4S_RECEIPT"},
            {"evidence_id":"EVID-P4-4S-ADAPTER-SOURCE-AFTER","path":"domain/current_shadow_canonical_core_adapter.py","sha256":receipts["p4_4s_source_transition"]["canonical_adapter_source_after_sha256"],"evidence_class":"SOURCE_HASH_BOUND_BY_P4_4S_RECEIPT"},
            {"evidence_id":"EVID-RUN-REQUEST","path":"athena-run-workflow/resolved-run-request.json","sha256":"0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4","evidence_class":"GITHUB_ARTIFACT_MEMBER_VERIFIED","artifact_id":10940728036},
            {"evidence_id":"EVID-RUN-RECEIPT","path":"athena-run-receipt.json","sha256":"a8ce4f163432ebead90ee649c7297115acba0a852ceeac2beeb5ef0bdc0d4b6d","evidence_class":"GITHUB_ARTIFACT_MEMBER_VERIFIED","artifact_id":10940728036},
            {"evidence_id":"EVID-INNER-SHADOW-RECEIPT","path":"current-shadow-all-market-run-receipt.json","sha256":"80ce47a0965562cffd11d8dbd847740fbf57e36b8f1b173020827ea19a18b258","evidence_class":"GITHUB_ARTIFACT_MEMBER_VERIFIED","artifact_id":10940728036},
            {"evidence_id":"EVID-PCUPCOMING-STABILIZATION","path":"runtime-capture-stabilization.json","sha256":"a16860bd03f03a99087f030ed91474a57233ef3e619a36a20494c615bb15e1c7","evidence_class":"GITHUB_ARTIFACT_MEMBER_VERIFIED","artifact_id":10940728036},
            {"evidence_id":"EVID-PCUPCOMING-SOURCE-MANIFEST","path":"manifest.json","sha256":"fb5412845dbed85d00396ea8f11a9343e1145dc4cba07664d54be69b260b449f","hash_kind":"canonical_payload_sha256","evidence_class":"GITHUB_ARTIFACT_CANONICAL_MANIFEST_IDENTITY"},
        ],
        "historical_receipt_immutability":[receipts[k] for k in ("p4_4r_inventory","p4_4r_receipt","p4_4s_receipt")],
        "superseded_plans":[
            {"plan_id":"PLAN-P4_4T-STANDALONE","status":"SUPERSEDED_BY_AUTH_01_SERIES","reason":"Its no-delivery work is absorbed into AUTH-01A, AUTH-01B, AUTH-01C and AUTH-01D; do not run the standalone prompt unchanged."},
            {"plan_id":"P4_4R_AND_P4_4S_RECEIPTS","status":"RETAINED_IMMUTABLE_HISTORY","reason":"Historical evidence remains immutable; BASE-00 records current state separately."},
            {"plan_id":"ARCHITECTURE-MASTER-V2","status":"CONTROLLING_ARCHITECTURE","reason":"Controls architecture invariants and evidence discipline."},
            {"plan_id":"SIX-DOCUMENT-BLUEPRINT","status":"TARGET_PRODUCT_SPECIFICATION","reason":"Controls target product requirements and UX intent."},
            {"plan_id":"PRODUCT-IMPLEMENTATION-MASTER-V1","status":"DELIVERY_SEQUENCE","reason":"Controls dependency order; future missions remain unstarted until authorized."},
        ],
        "roadmap_missions":[{"mission_id":x,"status":"CURRENT_BASELINE_ONLY" if x=="BASE-00" else "NOT_STARTED"} for x in ["BASE-00","AUTH-01A","AUTH-01B","AUTH-01C","AUTH-01D","PORT-01","PORT-02","CORE-01","APP-01","DATA-01","RUN-01","RUN-02","UX-01","INT-01","PKG-WINDOWS","PKG-LINUX","REL-01"]],
        "roadmap_crosswalk":crosswalk,
        "next_mission":"AUTH-01A",
        "next_mission_status":"NOT_STARTED_NOT_AUTHORIZED_BY_BASE_00",
        "severity_scale":{"HIGH":"Authority, security, evidence-integrity or product-truth failure with direct user impact.","MEDIUM":"Material journey, lifecycle, ownership or portability gap without an observed unauthorized external write."},
        "historical_run_classification":KNOWN_LIVE_RUN["classification"],
        "canonical_sha256":"",
    }
    data["canonical_sha256"] = sha256_bytes(canonical_bytes({k:v for k,v in data.items() if k!="canonical_sha256"}))
    return data


def _md_escape(value: Any) -> str:
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out.extend("| " + " | ".join(_md_escape(item) for item in row) + " |" for row in rows)
    return out


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# ATHENA product baseline v1", "",
        f"**Baseline:** `{data['baseline_id']}` · **Policy:** `{data['policy_id']}` · **Repository:** `{data['repository']}`", "",
        "## A. Purpose and non-authority", "",
        "This is a descriptive, versioned snapshot of ATHENA at the start of the product-delivery roadmap. It records evidence and closure work; it does not grant provider, delivery, MAIN, workflow-cutover or wager authority. BASE-00 changes no runtime behavior. Current source and immutable evidence control the current-state description.", "",
        "## B. Source precedence", "",
        "1. Current verified repository source and immutable evidence.  2. Architecture Remediation Master v2.  3. Six-Document Product and Implementation Blueprint.  4. Product Implementation Master v1.  5. Issue #337 and source-controlled architecture receipts.", "",
        *_table(["Source ID","Document","SHA-256","Identity class","Role"],[[s['source_document_id'],s['title'],s['sha256'],s['identity_class'],s['content_used_as']] for s in data['source_documents']]), "",
        "Owner-supplied PDF identities without an available source file are recorded as reported; the two supplied attachment PDFs were locally hash-verified. No source PDF is represented as an ATHENA repository file.", "",
        "## C. Repository identity and gates", "",
        *_table(["Field","Frozen value"],[["Main source commit",data['baseline_source_commit_sha']],["Main tree",data['baseline_source_tree_sha']],["Branch at baseline capture",data['baseline_branch_at_capture']],["Implementation branch",data['implementation_branch']],["Open PRs at preflight","0"],["BASE-00 PR number",str(data['implementation_review']['pull_request_number'] or "NOT_CREATED_AT_FREEZE")],["PR head when first opened",data['implementation_review']['head_sha_at_pr_creation'] or "NOT_CREATED_AT_FREEZE"],["PR state when review metadata was bound",data['implementation_review']['state_at_capture']],["Post-merge Tests", "36344862612: completed/success; syntax, shards 1–8, aggregate all success"],["Reviewed Fixture Catalog","36344862576: completed/success"]]), "",
        "The main commit/tree remain the frozen product source identity. PR metadata is a later review annotation: `head_sha_at_pr_creation` records the exact branch head when the single BASE-00 PR was first opened, not a self-referential final head hash.", "",
        "## D. Governance snapshot", "",
        *_table(["Item","State"],[["SOURCE_REVIEW_COUNTER","0/5; mandatory reread after the previous 5/5 completed (comment 5859231125)"],["P4.4","INCOMPLETE"],["Architecture Checkpoint E","INCOMPLETE"],["Clean canonical SHADOW successor proof","INCOMPLETE"],["Next live proof","NOT_AUTHORIZED"],["Caller migration","NOT_AUTHORIZED"],["Workflow retirement","NOT_AUTHORIZED"],["Next mission","AUTH-01A — NOT STARTED and not authorized by BASE-00"]]), "",
        "## E. Entrypoint inventory", "",
        "Static census includes canonical service/workflow paths, legacy desktop HTTP routes and every Python CLI command referenced by repository Markdown/RST/TXT. Source evidence stores repository-relative paths, line identities and LF-normalized source SHA-256 values for cross-platform identity; historical receipt hashes remain byte-exact. Entrypoints were not executed.", "",
        *_table(["ID","Kind / path","Caller → downstream","External effects / authority","Class / limitation"],[[e['entrypoint_id'],e['kind']+" · "+e['source_path'],str(e['caller_surface'])+" → "+str(e['downstream_targets']),str(e['external_side_effects'])+" · "+e['authority_profile_behavior'],e['current_classification']+" · "+e['support_status']] for e in data['entrypoints']]), "",
        "The legacy API defines `/`, `/ui`, `/styles.css`, `/app.js`, `/api/status`, `/api/leagues`, `/api/fixtures`, `/api/generate`, `/vet`, `/split`, `/merge`, `/api/export`, and deprecated `/api/export_code`. `/api/generate` imports and invokes `legacy_acca_builder_compat.AccaBuilder`; fixture routes acquire FotMob on cache misses. Wildcard CORS is configured with credentials. The legacy route inventory is not the canonical product API.", "",
        "`run_desktop.py` launches a pywebview shell on fixed `127.0.0.1:8500`, starts a daemon server thread, polls `/api/status`, and loads the UI from the repository-relative path. It does not prove the responder belongs to that launch. `/api/status` reports basic liveness/weights-file status, not canonical source/model readiness.", "",
        "## F. Capability matrix", "",
        *_table(["Capability","State / profile","Operation and source","Evidence / blocker","Side effect · approval · next mission"],[[c['capability_id'],c['state']+" · "+c['profile'],c['operation']+" · "+str(c['controlling_source']),str(c['evidence_ids'])+" · "+c['blocker_or_reason'],c['side_effect_class']+" · owner approval="+str(c['owner_approval_required'])+" · "+c['next_roadmap_mission']] for c in data['capabilities']]), "",
        "Capability (what code can do), invocation intent (what an owner asked for), authorization (the permitted intersection), execution (what happened), business result (analysis), and delivery result (external delivery) are distinct. BASE-00 documents this distinction; AUTH-01 implements it.", "",
        "## G. Product debt", "",
        *_table(["Debt ID","Description / source","User impact / architecture impact","Severity","Future owner / authorization"],[[d['debt_id'],d['description']+" Source: "+str(d['source_evidence']),d['user_impact']+" / "+d['architecture_impact'],d['severity'],d['owning_future_mission']+" / "+d['delete_or_change_authorization']] for d in data['product_debt']]), "",
        "Severity definitions: HIGH means an authority, security, evidence-integrity or product-truth failure with direct user impact. MEDIUM means a material journey, lifecycle, ownership or portability gap without an observed unauthorized external write.", "",
        "## H. Unresolved gates", "",
        *_table(["Gate","State / blocker","Dependencies","Closure evidence","Prohibited shortcut"],[[g['gate_id'],g['current_state']+" · "+g['exact_blocker'],g['dependencies'],g['evidence_required_to_close'],g['prohibited_shortcuts']] for g in data['unresolved_gates']]), "",
        "## I. Platform debt", "",
        *_table(["Platform debt","Target / state","Details","Evidence / next mission"],[[p['platform_debt_id'],p['target']+" / "+p['state'],p['details'],", ".join(p['evidence_ids'])+" / "+p['next_mission']] for p in data['platform_debt']]), "",
        "Targets are Windows 11 x86-64 and Ubuntu 24.04 LTS x86-64. Hosted Linux Tests are not Windows qualification. Git-free runtime, no system Python, unrelated cwd, read-only install, Unicode path and locked-file update/rollback behavior are not qualified.", "",
        "## J. Evidence anchors", "",
        *_table(["Evidence ID","Path / identity","SHA-256","Class"],[[e['evidence_id'],e.get('path',''),e.get('file_sha256',e.get('sha256','')),e['evidence_class']] for e in data['evidence_anchors']]), "",
        "The actual share code and URL are intentionally excluded. The latest artifact contains those values; only non-secret evidence hashes and boolean presence/action facts are recorded here.", "",
        "## K. Latest run classification", "",
        f"Run `{data['latest_live_evidence']['run_id']}` on `{data['latest_live_evidence']['head_sha']}` completed at GitHub Actions level. Its request resolved to SHADOW, one Lagos date, target 20, no total-odds objective, SportyBet, `create_share_code=true`, `place_wager=false`. It acquired {data['latest_live_evidence']['counts']['provider_event_count']} provider events; reviewed/reconciled/priced counts were {data['latest_live_evidence']['counts']['reviewed_fixture_count']}/{data['latest_live_evidence']['counts']['reconciled_fixture_count']}/{data['latest_live_evidence']['counts']['priced_fixture_count']}; selected {data['latest_live_evidence']['counts']['selected_leg_count']}/20, reserve 0, shortfall 17. The internal analysis reached a terminal result and share-code verification occurred. Because the owner prohibited that delivery action, classification is `{data['latest_live_evidence']['classification']}`. This is not clean successor proof and cannot authorize caller migration or workflow retirement. Wager, login, cookies, wallet and stake remain false.", "",
        "P4.4/P4.4S, latest artifact, request, RunReceipt, inner receipt, stabilization and source-manifest identities are in the machine-readable evidence anchors. Run artifact digest was checked against the GitHub Actions artifact API; the artifact was downloaded for offline, read-only review once.", "",
        "## L. Roadmap crosswalk", "",
        *_table(["Baseline item","Kind","Expected mission(s)","Status"],[[x['baseline_item_id'],x['item_kind'],x['expected_mission_ids'],x['sequence_status']] for x in data['roadmap_crosswalk']]), "",
        "Sequence anchor: A1 BASE-00 → A2 AUTH-01A → A3 AUTH-01B → A4 AUTH-01C → A5 AUTH-01D, then PORT / CORE / APP / DATA / RUN / UX / INT / PKG / REL per Product Implementation Master v1. Later missions have not started.", "",
        "## M. Superseded and retained plans", "",
        *_table(["Plan / source","Status","Meaning"],[[x['plan_id'],x['status'],x['reason']] for x in data['superseded_plans']]), "",
        "The standalone P4.4T prompt is superseded by AUTH-01A–D. Do not run it unchanged.", "",
        "## N. Next mission and change boundary", "",
        "Next mission: `AUTH-01A`. BASE-00 does not authorize or start it; it becomes eligible only after BASE-00 merges and post-merge gates are reviewed.", "",
        "This PR may change only the product baseline Markdown/JSON, its offline audit, and focused tests. It does not change runtime, provider, model, pricing, Router, Portfolio, workflow, caller, delivery or account behavior.", "",
        f"**Snapshot canonical SHA-256:** `{data['canonical_sha256']}`",
        "",
        f"**Static source-inventory canonical SHA-256:** `{data['source_snapshot']['canonical_sha256']}`",
        "**Governance:** SOURCE_REVIEW_COUNTER 0/5 while unmerged; P4.4 and Checkpoint E incomplete; no live proof, migration or retirement authorized.", "",
    ]
    return "\n".join(lines)


def _walk_strings(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, str):
        yield value


def _walk_sha_fields(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            if isinstance(key, str) and key.endswith("sha256") and item is not None:
                yield item_path, item
            yield from _walk_sha_fields(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_sha_fields(item, f"{path}[{index}]")


def validate_baseline(data: dict[str, Any], root: Path = ROOT, *, verify_receipts: bool = True) -> list[str]:
    errors: list[str] = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)
    require(type(data) is dict, "baseline root must be an object")
    if type(data) is not dict:
        return errors
    require(data.get("schema_version") == 1 and type(data.get("schema_version")) is int, "unsupported schema_version")
    require(data.get("baseline_id") == BASELINE_ID, "baseline_id mismatch")
    require(data.get("policy_id") == POLICY_ID, "policy_id mismatch")
    require(data.get("repository") == REPOSITORY, "repository mismatch")
    require(data.get("baseline_source_commit_sha") == BASE_COMMIT, "baseline commit mismatch")
    require(data.get("baseline_source_tree_sha") == BASE_TREE, "baseline tree mismatch")
    review = data.get("implementation_review", {})
    if review.get("state_at_capture") == "NOT_CREATED_AT_BASELINE_FREEZE":
        require(review.get("pull_request_number") is None and review.get("head_sha_at_pr_creation") is None, "uncreated PR metadata must remain empty")
    elif review.get("state_at_capture") == "OPEN_UNMERGED_AT_REVIEW_BIND":
        require(type(review.get("pull_request_number")) is int and review["pull_request_number"] > 0, "invalid BASE-00 PR number")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", str(review.get("head_sha_at_pr_creation", "")))), "invalid BASE-00 PR creation head")
    else:
        errors.append("unknown BASE-00 implementation review state")
    claimed = data.get("canonical_sha256")
    canonical = sha256_bytes(canonical_bytes({k:v for k,v in data.items() if k!="canonical_sha256"}))
    require(claimed == canonical, "baseline canonical_sha256 mismatch")
    path_records = data.get("source_snapshot", {}).get("files", [])
    require(type(path_records) is list and len(path_records)>0, "source snapshot files missing")
    for record in path_records:
        try: relative_path(record["path"])
        except (KeyError, ValueError) as exc: errors.append(f"unsafe snapshot path: {exc}"); continue
        require(bool(re.fullmatch(r"[0-9a-f]{64}",str(record.get("sha256","")))), f"invalid source sha256: {record.get('path')}")
        require(record.get("hash_kind") == "LF_NORMALIZED_SOURCE_SHA256", f"source hash kind is not portable/explicit: {record.get('path')}")
    require(data.get("source_snapshot",{}).get("canonical_sha256")==sha256_bytes(canonical_bytes(path_records)),"source inventory canonical hash mismatch")
    for field, value in _walk_sha_fields(data):
        require(type(value) is str and bool(re.fullmatch(r"[0-9a-f]{64}", value)), f"malformed SHA-256 field: {field}")
    for source in data.get("source_documents",[]):
        require(bool(re.fullmatch(r"[0-9a-f]{64}",str(source.get("sha256","")))),f"invalid source-document SHA: {source.get('source_document_id')}")
        require(source.get("repository_file") is None,"external source document incorrectly claims repository path")
    for field, records, key in (
        ("source_documents", data.get("source_documents", []), "source_document_id"),
        ("evidence_records", data.get("evidence_records", []), "evidence_id"),
        ("evidence_anchors", data.get("evidence_anchors", []), "evidence_id"),
    ):
        values = [record.get(key) for record in records]
        require(len(values) == len(set(values)), f"duplicate stable IDs in {field}")
    for field, records, id_key, allowed in [
        ("entrypoints",data.get("entrypoints",[]),"entrypoint_id",CLASSIFICATIONS),
        ("workflows",data.get("workflows",[]),"workflow_id",None),
        ("capabilities",data.get("capabilities",[]),"capability_id",None),
        ("product_debt",data.get("product_debt",[]),"debt_id",None),
        ("unresolved_gates",data.get("unresolved_gates",[]),"gate_id",None),
        ("platform_debt",data.get("platform_debt",[]),"platform_debt_id",None),
    ]:
        ids = [record.get(id_key) for record in records]
        require(all(type(x) is str and re.fullmatch(r"[A-Z0-9_-]+",x) for x in ids),f"invalid IDs in {field}")
        require(len(ids)==len(set(ids)),f"duplicate IDs in {field}")
        if allowed:
            require(all(record.get("current_classification") in allowed for record in records),"unknown entrypoint classification")
    require(all(c.get("state") in CAPABILITY_STATES for c in data.get("capabilities",[])),"unknown capability state")
    require(all(w.get(k) in EXTERNAL_EFFECT_STATES for w in data.get("workflows",[]) for k in ("provider_acquisition","delivery","email_notification")),"unknown workflow side-effect state")
    evidence_ids={e.get("evidence_id") for e in data.get("evidence_records",[])} | {e.get("evidence_id") for e in data.get("evidence_anchors",[])}
    # All source records are included in evidence_records, and directly referenced by IDs.
    evidence_ids |= {record.get("evidence_id") for record in data.get("source_snapshot",{}).get("files",[])}
    source_evidence_by_path = {record.get("path"): record for record in data.get("source_snapshot",{}).get("files",[])}
    for entry in data.get("entrypoints", []):
        try: relative_path(entry.get("source_path"))
        except (TypeError, ValueError) as exc: errors.append(f"unsafe entrypoint path: {exc}")
        refs = entry.get("evidence_ids", [])
        ref_ids = [ref.get("evidence_id") if isinstance(ref, dict) else ref for ref in refs]
        source_refs = entry.get("source_evidence", []) + entry.get("documentation_evidence", [])
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                errors.append(f"{entry.get('entrypoint_id')} has malformed source evidence")
                continue
            try: relative_path(source_ref.get("path"))
            except (TypeError, ValueError) as exc: errors.append(f"unsafe entrypoint evidence path: {exc}"); continue
            source_record = source_evidence_by_path.get(source_ref.get("path"))
            require(source_record is not None, f"{entry.get('entrypoint_id')} cites unpinned source evidence")
            if source_record is not None:
                ref_ids.append(source_record.get("evidence_id"))
                if source_ref.get("hash_kind") == "LF_NORMALIZED_SOURCE_SHA256":
                    require(source_ref.get("sha256") == source_record.get("sha256"), f"{entry.get('entrypoint_id')} source evidence hash mismatch")
        require(bool(ref_ids) and all(ref in evidence_ids for ref in ref_ids), f"{entry.get('entrypoint_id')} lacks valid source evidence")
    for workflow in data.get("workflows", []):
        try: relative_path(workflow.get("path"))
        except (TypeError, ValueError) as exc: errors.append(f"unsafe workflow path: {exc}")
    for collection, id_key in ((data.get("capabilities",[]),"capability_id"),(data.get("product_debt",[]),"debt_id"),(data.get("unresolved_gates",[]),"gate_id")):
        for item in collection:
            refs=item.get("evidence_ids",[])
            require(bool(refs) or (item.get("blocker_or_reason") or item.get("exact_blocker")),f"{item.get(id_key)} lacks evidence or blocked reason")
            require(all(ref in evidence_ids for ref in refs),f"{item.get(id_key)} references unknown evidence ID")
    known_ids={r.get(k) for k,records in [("debt_id",data.get("product_debt",[])),("gate_id",data.get("unresolved_gates",[])),("capability_id",data.get("capabilities",[]))] for r in records}
    crosswalk=data.get("roadmap_crosswalk",[])
    require({x.get("baseline_item_id") for x in crosswalk}=={d["debt_id"] for d in data.get("product_debt",[])}|{g["gate_id"] for g in data.get("unresolved_gates",[])},"roadmap crosswalk does not cover every debt and gate")
    known_missions={x.get("mission_id") for x in data.get("roadmap_missions",[])}
    for row in crosswalk:
        require(row.get("baseline_item_id") in known_ids,"crosswalk references unknown baseline item")
        require(bool(row.get("expected_mission_ids")) and all(m in known_missions and m in MISSION_IDS for m in row.get("expected_mission_ids",[])),"crosswalk references unknown mission")
    for value in _walk_strings(data):
        require(not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[^\\]+\\",value,re.I),"absolute path found in baseline")
        require(not re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{16,}|AKIA[0-9A-Z]{16})",value),"secret-like value found")
    forbidden_keys={"share_code_value","share_code_url","sharecode","shareurl","access_token","cookie_value","raw_cookie","password_value"}
    def inspect_keys(value):
        if isinstance(value,dict):
            for key,item in value.items():
                require(key.lower() not in forbidden_keys,f"forbidden secret-bearing field: {key}")
                inspect_keys(item)
        elif isinstance(value,list):
            for item in value:inspect_keys(item)
    inspect_keys(data)
    run=data.get("latest_live_evidence",{})
    require(run.get("run_id")==36345657852 and run.get("classification")=="POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT","latest run classification drift")
    require(run.get("delivery",{}).get("raw_code_or_url_stored") is False,"share-code value storage must be false")
    require(run.get("request",{}).get("create_share_code") is True and run.get("request",{}).get("place_wager") is False,"latest request intent evidence drift")
    gov=data.get("governance",{})
    require(gov.get("source_review_counter")=="0/5","source review counter drift")
    require(gov.get("p4_4")=="INCOMPLETE" and gov.get("architecture_checkpoint_e")=="INCOMPLETE","P4.4 governance state drift")
    require(gov.get("clean_canonical_shadow_successor_proof")=="INCOMPLETE","clean successor must remain incomplete")
    require(gov.get("caller_migration")=="NOT_AUTHORIZED" and gov.get("workflow_retirement")=="NOT_AUTHORIZED" and gov.get("next_live_proof")=="NOT_AUTHORIZED","authorization state drift")
    require(data.get("next_mission")=="AUTH-01A" and data.get("next_mission_status")=="NOT_STARTED_NOT_AUTHORIZED_BY_BASE_00","next mission drift")
    require(any(p.get("plan_id")=="PLAN-P4_4T-STANDALONE" and p.get("status")=="SUPERSEDED_BY_AUTH_01_SERIES" for p in data.get("superseded_plans",[])),"standalone P4.4T supersession absent")
    require(len(data.get("workflows",[]))==38,"workflow census count differs from frozen source snapshot")
    workflow_paths={w.get("path") for w in data.get("workflows",[])}
    require(".github/workflows/athena-run.yml" in workflow_paths and ".github/workflows/current-shadow-all-market.yml" in workflow_paths,"canonical/legacy workflow missing")
    for gate in data.get("postmerge_gates",[]):
        require(gate.get("head_sha")==BASE_COMMIT and gate.get("conclusion")=="success","postmerge gate identity/status mismatch")
    reread=next((x for x in data.get("evidence_records",[]) if x.get("evidence_id")=="EVID-ISSUE-REREAD-5859231125"),None)
    require(reread is not None,"mandatory reread evidence missing")
    if verify_receipts:
        for receipt in data.get("historical_receipt_immutability",[]):
            try:
                rel=relative_path(receipt["path"]); actual=file_sha256(root/rel)
                require(actual==receipt.get("file_sha256"),f"historical receipt bytes changed: {rel}")
            except (OSError,KeyError,ValueError) as exc:errors.append(f"historical receipt unavailable/unsafe: {exc}")
    return errors


def exact_head_reproduction(data: dict[str, Any], root: Path = ROOT) -> tuple[str, list[str]]:
    mismatches=[]
    for item in data.get("source_snapshot",{}).get("files",[]):
        path=root/relative_path(item["path"])
        if not path.is_file() or normalized_source_sha256(path)!=item["sha256"]:
            mismatches.append(item["path"])
    if mismatches:
        return "SKIP_SOURCE_MOVED",mismatches
    failed=[r["assertion_id"] for r in _static_assertions(root) if r["result"]!="PASS"]
    if failed:
        return "FAIL",failed
    return "PASS",[]


def freeze(root: Path = ROOT) -> dict[str, Any]:
    data=build_baseline(root)
    errors=validate_baseline(data,root,verify_receipts=True)
    if errors:raise ValueError("baseline validation failed: "+"; ".join(errors))
    (root/BASELINE_JSON).write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    (root/BASELINE_MARKDOWN).write_text(render_markdown(data),encoding="utf-8",newline="\n")
    return data


def bind_review(root: Path, pr_number: int, head_sha: str) -> dict[str, Any]:
    """Bind the single opened PR's creation identity without changing baseline source identity."""
    if type(pr_number) is not int or pr_number <= 0 or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("invalid PR number or creation head SHA")
    path = root / BASELINE_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_baseline(data, root, verify_receipts=False)
    if errors:
        raise ValueError("cannot bind PR metadata to an invalid baseline: " + "; ".join(errors))
    if data["implementation_review"]["state_at_capture"] != "NOT_CREATED_AT_BASELINE_FREEZE":
        raise ValueError("BASE-00 PR metadata is already bound; refusing replacement")
    data["implementation_review"] = {
        "pull_request_number": pr_number,
        "head_sha_at_pr_creation": head_sha,
        "state_at_capture": "OPEN_UNMERGED_AT_REVIEW_BIND",
    }
    data["canonical_sha256"] = sha256_bytes(canonical_bytes({key:value for key,value in data.items() if key!="canonical_sha256"}))
    errors = validate_baseline(data, root, verify_receipts=False)
    if errors:
        raise ValueError("bound BASE-00 PR metadata failed validation: " + "; ".join(errors))
    path.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    (root / BASELINE_MARKDOWN).write_text(render_markdown(data),encoding="utf-8",newline="\n")
    return data


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",action="store_true",help="Create the initial BASE-00 JSON and Markdown; source commit is fixed by this audit.")
    parser.add_argument("--exact-head",action="store_true",help="Optionally reproduce pinned source assertions when source files remain unchanged.")
    parser.add_argument("--bind-review-pr",type=int,help="Record the sole BASE-00 PR number after opening it.")
    parser.add_argument("--bind-review-head",help="40-hex PR branch head at the moment the PR was first opened.")
    args=parser.parse_args(argv)
    try:
        if (args.bind_review_pr is None) != (args.bind_review_head is None):
            parser.error("--bind-review-pr and --bind-review-head must be supplied together")
        if args.bind_review_pr is not None:
            if args.freeze or args.exact_head:
                parser.error("PR review binding cannot be combined with --freeze or --exact-head")
            data=bind_review(ROOT,args.bind_review_pr,args.bind_review_head)
            print(json.dumps({"result":"PR_REVIEW_IDENTITY_BOUND","pull_request_number":args.bind_review_pr,"head_sha_at_pr_creation":args.bind_review_head,"canonical_sha256":data["canonical_sha256"]},sort_keys=True))
            return 0
        if args.freeze:
            data=freeze()
            print(json.dumps({"result":"BASELINE_FROZEN","canonical_sha256":data["canonical_sha256"],"entrypoints":len(data["entrypoints"]),"workflows":len(data["workflows"]),"capabilities":len(data["capabilities"]),"debts":len(data["product_debt"]),"gates":len(data["unresolved_gates"]),"source_files":len(data["source_snapshot"]["files"])},sort_keys=True))
            return 0
        data=json.loads((ROOT/BASELINE_JSON).read_text(encoding="utf-8"))
        errors=validate_baseline(data,ROOT,verify_receipts=True)
        if errors:
            print("BASELINE_AUDIT_FAILED")
            for error in errors:print("- "+error)
            return 1
        result={"result":"BASELINE_SNAPSHOT_INTEGRITY_PASS","canonical_sha256":data["canonical_sha256"],"workflow_count":len(data["workflows"]),"entrypoint_count":len(data["entrypoints"]),"historical_receipts_verified":len(data["historical_receipt_immutability"]),"network":"NOT_USED"}
        if args.exact_head:
            reproduction,detail=exact_head_reproduction(data,ROOT)
            result["exact_head_reproduction"]={"result":reproduction,"details":detail}
            if reproduction=="FAIL":return 1
        print(json.dumps(result,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        print(f"BASELINE_AUDIT_FAILED: {exc}")
        return 1


if __name__=="__main__":
    raise SystemExit(main())
