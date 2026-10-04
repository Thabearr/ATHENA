"""Authenticate the source-bound B2 review of the warehouse/transfer triggers.

The audit consumes committed GitHub metadata and repository source only. It does
not dispatch workflows, download artifacts, or contact historical data sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
BASE_MAIN = "3c09b1ed8fdc95eaced229dc2ff98021d0bcea6d"
BASE_TREE = "b017b93609063645f38977f869222571ec4adb4f"
WORKFLOW_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
EVOLUTION_SHA = "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
RETIREMENT_SHA = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
COMPLETION_V4_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json"
COMPLETION_V4_SHA = "adb23d8ca4802c95298ddf90b7c07e75d2a8179bebe0592db309140871e1490c"
B1_RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json"
B1_RECEIPT_SHA = "bf38f7ef6bc43efa96ff36152b71308fafe5b21d581fd7921fc6f1ba2b4b06cc"
A2_V1_SHA = "ca8c07c071538298ffb293027e7a0be1c5766e8a943b3d2b605627f9ffe922dd"
A2_V2_SHA = "c7b12447b7f671b2ece76d1207b404cd4555cc45d2e2ec88451682d6e0b4f14e"
A2_V3_SHA = "f7646fd5008d12cc7c5b0379455c384742b893a26cac00fa55df19f28c8a8017"
A2_RECEIPT_SHA = "5d0385f77463d3e7a9f804b431df7e2c2c9c4908c266326bf35b05a50086f8e2"
BRIDGE_RECEIPT_SHA = "6ba76fc9362db44df9c901784b7bdea0ab9284c0db763e8168eefc83ab2e3a8d"
COMPLETION_V3_SHA = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
MATRIX_V2_SHA = "3c3cfec8b37e55161b24185941e72c3e096a00f38456a2c07a9072b62e31e5b7"
RETAINED_V5_SHA = "c90d71a04f54c29ed094b262f0aef6cad9067316c6d548227f1c4c289a4abebf"
SOURCE_INVENTORY_PATH = "tests/fixtures/core_01d/historical-warehouse-transfer-authority-b2-source-inventory-v1.json"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-historical-warehouse-transfer-authority-b2-v1.json"
POLICY_ID = "ATHENA_CORE_01D_HISTORICAL_WAREHOUSE_TRANSFER_AUTHORITY_B2_V1"
SOURCE_INVENTORY_POLICY_ID = "ATHENA_CORE_01D_HISTORICAL_WAREHOUSE_TRANSFER_AUTHORITY_B2_SOURCE_INVENTORY_V1"

WAREHOUSE = ".github/workflows/build-historical-warehouse.yml"
TRANSFER = ".github/workflows/prepare-canonical-drive-transfer.yml"
TARGET_KEYS = (
    (WAREHOUSE, "pull_request"),
    (WAREHOUSE, "push"),
    (WAREHOUSE, "workflow_dispatch"),
    (TRANSFER, "push"),
    (TRANSFER, "workflow_dispatch"),
)

# Current exact-main source identities. These pins make an evidence refresh
# insufficient to bless a workflow/runtime change as the same B2 review.
SOURCE_PINS = {
    ".github/workflows/build-historical-warehouse.yml": ("6b9968bae3167bb61a853952a19da91028338d57", "b76ec29d62aa345d562c592171e232aaee17b50ab03295e2de4d974ea7227315"),
    ".github/workflows/prepare-canonical-drive-transfer.yml": ("f863d6c19696a519e9706c99f4b6effd6a182525", "bbf0dda03803ca1484069e086eefa50df370a378e8a0520cdb0d6a7af9c7d5f2"),
    "scripts/run_with_fast_history_quality.py": ("7a8a55a9d62293acf6bfe748e048fb7e40065cb6", "5859bca479fb95190c983cae6925e072a193528a3bdb46ad2e4344fee0d624a2"),
    "scripts/import_current_soccer_datalake.py": ("8ff47b9104e32ef524334b0c7322d0aff9643005", "8e36b13d49a4adf0b6f2d2fab2f5c158fbe37366cd9951e805b63f4f118c8549"),
    "scripts/register_datalake_team_aliases.py": ("d51d20cd22e17e0e3e1b54f7e436556559b53138", "5dba0266fe9830edd8e26f1dadf08784370154e740214903d408a8cc2cfcdb0e"),
    "scripts/import_global_football_backbone.py": ("ed7de32b9ce46bc787644af32cfa7fb050b7f6b9", "d231bc291443f1bb828cabeaddf1186b1f1ba025fef0e27d1d20b619d4cc7269"),
    "scripts/build_historical_warehouse.py": ("e1eb169b96e7abd8f3db9cc39ac883d99392d641", "0c685fc42ef744b857b73161e8990134cfca4ec8875d4966c47837b3991f37db"),
    "scripts/import_football_data_history.py": ("186f8e8c874801687fb8cf4ba48c43caf3a5f56d", "bce238b8a853cc4a713ae320b477d08accfe2e33077ca6670ae23070606a59d3"),
    "scripts/import_openfootball_history.py": ("6e155308af45d11f7ac56f77459da59174d76a0c", "33d4bafeebf9f32c64fa235e3576d74b89ff13c065820a05ff157780ee35bf13"),
    "scripts/enrich_schochastics_goal_events.py": ("9f09bb33e1cf672109c07d2ba7c684439a633e3b", "bdffdefd1e7ea45e145a34d2018ed53602d0f65793c26a073eb81ca19d83938e"),
    "scripts/enrich_statsbomb_history.py": ("19cbc28640f7731490fe2297cb348ab070d77111", "019abb511d861e937166ccec6a661110153c5944dc6d4f987927b40bb243d5b8"),
    "scripts/normalize_historical_score_periods.py": ("c8c1aea22de858330997ef696ba205a080cd8dd4", "46ef48636a9006a2bc234a4de80c1b95352b57e6cebe64d23c45082d7273232d"),
    "scripts/audit_historical_hierarchy_coverage.py": ("bd23dda00020a9b1bf748a99cef15dd656c44373", "b8fb9f5deb7208103fdd63e2dc085afa0333306ed1feb14709b66803fdde6e98"),
    "scripts/audit_historical_season_completeness.py": ("efc2f5eb78599c9ef3e7f2ec315010742cdc4283", "2800fcdfeff60f4dcd539e37e4df6cb3fa6fc667d62fc2bf17873005976ca69e"),
    "scripts/audit_historical_data_integrity.py": ("b71d59eba2825602307560a8b3d4355729407ae7", "eba3e44f0eabba223c070ab199b450c6c1d06cc0a9f53f8dc6b93bfe3120ea40"),
    "scripts/historical_quality.py": ("a0dfb64c1905ff08687817697e362fb1214b9740", "6eae47da94424066643f490ff2a83b857cceea725b8faa82469c685fe706fa11"),
    "domain/historical_competitions.py": ("1ce7df56b12ecf943a499906a73cf4a7fd8a5695", "33e7857ff3fc2737d9da47519e23299bc82d69a843247c4f0375c010445fbd81"),
    "database/historical_warehouse_schema.sql": ("c9f02eb696256670124c7cf1b8dc36fc21064300", "d5a3b545a639c43a2b35fb18529a429ba2572d2861ac52c638cce42a8141306f"),
    "tests/test_historical_warehouse.py": ("7933f0ce2e90b75071f09b4de16e0f6540b69e62", "8a88ec0789ee49db71b1151d4011e2a36a9a7853b30550ed0d99e2e118ed9e25"),
    "tests/test_historical_hierarchy_freshness.py": ("d93797ea0243ea0bbdf06a5c016615f36eb5933f", "ee60d24b1e9c80c1101ad5f443b4ded1a361bdc5b7d49ecfa310bf85fbf96c86"),
    "tests/test_historical_season_completeness.py": ("249c6301055d2d15b7cc03bd0bf11c3f020d7b70", "34fbf48cceb07b7a2a95be3354a9fe23709e91d558958d38a026391d71d79984"),
    "tests/test_global_backbone_retention.py": ("d42dd4d1c497365264ee926acaba31200e1f9051", "bf8890b92fa2f30f106e00362b2699dc95c9a9daf9e051f0351ae8d9f9293d7e"),
    "tests/test_historical_quality_refresh.py": ("902cefe2132f9efb76e560cd363f4a8f271cc2bf", "9726400a7be1f62e57b1aeea5a28eae35fbbd53337d1d0c910ddde7c83763df2"),
    "tests/test_historical_data_integrity.py": ("4923e971cd08849e2bf6c0582b127a1fd419fcf2", "b760eade371ee2cea56051ce0b8228ff96a2738cb86b43e263bbc76827941f0e"),
}
SOURCE_PATHS = tuple(SOURCE_PINS)

V1_INVENTORY_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v1.json"
V2_INVENTORY_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v2.json"
V3_INVENTORY_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v3.json"
V4_INVENTORY_PATH = "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json"
A2_V4_SHA = "82c440deb06d760d13bf73d914c5ec9181e568ba388f844a3fc6fa49976ab50f"

OBSERVED_AT = "2026-10-03T19:46:48Z"
POST_440_TESTS = {
    "run_id": 37147658828,
    "workflow": "Tests",
    "event": "push",
    "branch": "main",
    "head_sha": BASE_MAIN,
    "status": "completed",
    "conclusion": "success",
    "syntax": "success",
    "shards": {str(index): "success" for index in range(1, 9)},
    "aggregate": "success",
    "source_endpoint": "GET /repos/Thabearr/ATHENA/actions/runs/37147658828 and /jobs",
    "read_only": True,
    "observed_at_utc": OBSERVED_AT,
}

# Minimum historical GitHub metadata captured for the producer/consumer lineage.
HISTORICAL_RUNS = [
    {"run_id": 33541247244, "run_number": 66, "workflow_path": WAREHOUSE, "event": "push", "head_branch": "main", "head_sha": "5c0ccfd21e421c432217bf229ca94ab71f783a1f", "run_attempt": 1, "status": "completed", "conclusion": "success", "created_at": "2026-09-01T18:01:59Z", "updated_at": "2026-09-01T19:22:56Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/33541247244"},
    {"run_id": 32628985683, "run_number": 56, "workflow_path": WAREHOUSE, "event": "pull_request", "head_branch": "feat/historical-season-completeness-v3", "head_sha": "3cd4ad85e0894c440026a205f143cf9eb7cc1add", "run_attempt": 1, "status": "completed", "conclusion": "success", "created_at": "2026-08-23T08:42:40Z", "updated_at": "2026-08-23T09:58:58Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32628985683", "historical_transfer_source": True},
    {"run_id": 32632678889, "run_number": 57, "workflow_path": WAREHOUSE, "event": "push", "head_branch": "main", "head_sha": "24c18222d170834b1dae2e430ab016fe5bb9fca2", "run_attempt": 1, "status": "completed", "conclusion": "success", "created_at": "2026-08-23T10:02:47Z", "updated_at": "2026-08-23T11:24:15Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32632678889"},
    {"run_id": 32635585415, "run_number": 3, "workflow_path": TRANSFER, "event": "push", "head_branch": "main", "head_sha": "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa", "run_attempt": 1, "status": "completed", "conclusion": "success", "created_at": "2026-08-23T11:06:04Z", "updated_at": "2026-08-23T11:07:16Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32635585415", "historical_transfer_success": True},
    {"run_id": 32635488809, "run_number": 2, "workflow_path": TRANSFER, "event": "push", "head_branch": "main", "head_sha": "b2121814be0619b8bafcd2c1f5b183ca22b1a598", "run_attempt": 1, "status": "completed", "conclusion": "failure", "created_at": "2026-08-23T11:04:00Z", "updated_at": "2026-08-23T11:06:12Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32635488809"},
    {"run_id": 32633019191, "run_number": 1, "workflow_path": TRANSFER, "event": "push", "head_branch": "main", "head_sha": "a642927fa854286c9b7f4bb107b6264f60e28725", "run_attempt": 1, "status": "completed", "conclusion": "failure", "created_at": "2026-08-23T10:10:12Z", "updated_at": "2026-08-23T10:14:29Z", "url": "https://github.com/Thabearr/ATHENA/actions/runs/32633019191"},
]
CURRENT_ARTIFACT_LISTINGS = [
    {"run_id": run_id, "expected_artifact": expected, "state": "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY", "total_count": 0, "source_endpoint": f"GET /repos/Thabearr/ATHENA/actions/runs/{run_id}/artifacts", "read_only": True, "payload_downloaded": False, "disappearance_cause_inferred": False, "observed_at_utc": OBSERVED_AT}
    for run_id, expected in ((33541247244, "athena-history-sqlite"), (32628985683, "athena-history-sqlite"), (32632678889, "athena-history-sqlite"), (32635585415, "athena-canonical-manifest and 23 part artifacts"))
]

ARCHIVE = {
    "name": "athena-history-canonical.zip",
    "bytes": 2149256220,
    "sha256": "a783886d0906e357e26851fcb3eb182bb06bdcc184d21f2b6578bb3d1fa61511",
    "source_run_id_default": "32628985683",
    "source_artifact_id_default": "9491418446",
    "part_count": 23,
    "pointer_branch": "automation/canonical-drive-transfer-pointer",
}

PUBLIC_DATA_SOURCES = [
    {"source_file": "scripts/import_current_soccer_datalake.py", "category": "PUBLIC_HISTORICAL_AND_CURRENT_FOOTBALL_DATASET_HTTP_READ", "endpoint": "https://huggingface.co/datasets/eatpizzanot/soccer-dataset/resolve/main", "notes": "Reads public dataset files; some fields originate from API-Football datasets, but no direct API-Football service call is present."},
    {"source_file": "scripts/import_global_football_backbone.py", "category": "PUBLIC_HISTORICAL_BACKBONE_HTTP_READ", "endpoint": "https://raw.githubusercontent.com/schochastics/football-data/master/data/results/games.parquet"},
    {"source_file": "scripts/import_football_data_history.py", "category": "PUBLIC_HISTORICAL_DATA_HTTP_READ", "endpoint": "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"},
    {"source_file": "scripts/build_historical_warehouse.py", "category": "PUBLIC_HISTORICAL_DATA_HTTP_READ", "endpoints": ["https://raw.githubusercontent.com/martj42/international_results/master/{results.csv,goalscorers.csv,shootouts.csv}", "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv", "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv", "https://github.com/openfootball/{repo}/archive/refs/heads/master.zip"]},
    {"source_file": "scripts/import_openfootball_history.py", "category": "PUBLIC_HISTORICAL_DATA_HTTP_READ", "endpoint": "https://github.com/openfootball/{repo}/archive/refs/heads/master.zip"},
    {"source_file": "scripts/enrich_schochastics_goal_events.py", "category": "PUBLIC_HISTORICAL_DATA_HTTP_READ", "endpoint": "https://raw.githubusercontent.com/schochastics/football-data/master/data/goals_time/{csv}"},
    {"source_file": "scripts/enrich_statsbomb_history.py", "category": "PUBLIC_OPEN_DATA_HTTP_READ", "endpoint": "https://raw.githubusercontent.com/statsbomb/open-data/master/data/{competitions,matches,events,lineups}.json"},
]

WAREHOUSE_SCRIPTS = [
    "scripts/run_with_fast_history_quality.py",
    "scripts/import_current_soccer_datalake.py",
    "scripts/register_datalake_team_aliases.py",
    "scripts/import_global_football_backbone.py",
    "scripts/build_historical_warehouse.py",
    "scripts/import_football_data_history.py",
    "scripts/import_openfootball_history.py",
    "scripts/enrich_schochastics_goal_events.py",
    "scripts/enrich_statsbomb_history.py",
    "scripts/normalize_historical_score_periods.py",
    "scripts/audit_historical_hierarchy_coverage.py",
    "scripts/audit_historical_season_completeness.py",
    "scripts/audit_historical_data_integrity.py",
]

ZERO_ACTIONS = {
    "provider_or_historical_source_calls_during_review": 0,
    "sportsbook_calls": 0,
    "workflow_dispatch": 0,
    "workflow_rerun": 0,
    "workflow_cancel": 0,
    "artifact_payload_download": 0,
    "warehouse_execution": 0,
    "transfer_execution": 0,
    "pointer_branch_write": 0,
    "drive_or_external_storage_write": 0,
    "release_mutation": 0,
    "email_or_smtp": 0,
    "share_code": 0,
    "login_or_cookies": 0,
    "wallet_or_stake_or_wager": 0,
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def canonical(value: object) -> bytes:
    return boundary.canonical(value)


def seal(value: dict[str, object]) -> dict[str, object]:
    return boundary.seal(value)


def read_json(path: str) -> dict[str, object]:
    return boundary.read(path)


def lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def source_identity(path: str) -> dict[str, str]:
    raw = (ROOT / path).read_bytes()
    normalized = lf(raw)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    expected_blob, expected_sha = SOURCE_PINS[path]
    require(blob == expected_blob, "B2 base Git blob identity drift: " + path)
    digest = hashlib.sha256(normalized).hexdigest()
    require(digest == expected_sha, "B2 normalized source identity drift: " + path)
    return {"path": path, "git_blob_sha1": blob, "normalized_source_sha256": digest}


def parse_yaml(path: str) -> dict[str, object]:
    value = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    require(isinstance(value, dict), "workflow YAML root is not a mapping: " + path)
    return value


def _step_contract(step: dict[str, object], source_lines: list[str]) -> dict[str, object]:
    name = str(step.get("name", "unnamed"))
    uses = step.get("uses")
    run = step.get("run")
    compact = " ".join(str(run).split()) if run is not None else ""
    line_index = next((i for i, line in enumerate(source_lines) if line.strip() == "- name: " + name), -1)
    require(line_index >= 0, "step line not found: " + name)
    return {
        "name": name,
        "line": line_index + 1,
        "uses": uses,
        "if": step.get("if"),
        "run_sha256": hashlib.sha256(compact.encode()).hexdigest() if compact else None,
        "run_references": re.findall(r"(?:python(?:\s+-m)?|bash|sh)\s+(scripts/[A-Za-z0-9_./-]+\.py)", compact),
        "with": step.get("with", {}),
        "env": step.get("env", {}),
    }


def trigger_contract(path: str, event: str) -> dict[str, object]:
    workflow = parse_yaml(path)
    events = workflow.get("on", {})
    require(isinstance(events, dict) and event in events, "target trigger missing: " + path + "#" + event)
    jobs = workflow.get("jobs", {})
    expected_job = "build-history" if path == WAREHOUSE else "prepare-drive-transfer"
    require(expected_job in jobs, "target job missing: " + path)
    job = jobs[expected_job]
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    steps = [_step_contract(step, lines) for step in job.get("steps", [])]
    return {
        "event": event,
        "trigger_declaration": events[event],
        "workflow_permissions": workflow.get("permissions", {}),
        "job_name": expected_job,
        "job_if": job.get("if"),
        "job_permissions": job.get("permissions", {}),
        "runs_on": job.get("runs-on"),
        "timeout_minutes": job.get("timeout-minutes"),
        "workflow_concurrency": workflow.get("concurrency", {}),
        "steps": steps,
        "event_dependent_conditions": [
            {"step": step["name"], "condition": step["if"]}
            for step in steps if step["if"] is not None
        ],
        "workflow_env": workflow.get("env", {}),
    }


def discover_repository_callers() -> list[dict[str, str]]:
    """Find in-repository reusable-workflow/API dispatch callers, not prose."""
    raw_paths = subprocess.check_output(["git", "ls-files", ".github/workflows", "scripts"], cwd=ROOT)
    callers: list[dict[str, str]] = []
    trigger_line = re.compile(r"(?:uses\s*:|workflow_run\s*:|gh\s+workflow\s+run|createWorkflowDispatch|repository_dispatch)", re.I)
    targets = {WAREHOUSE, TRANSFER, Path(WAREHOUSE).name, Path(TRANSFER).name,
               "Build Historical Football Warehouse", "Prepare Canonical Database Drive Transfer"}
    for rel in raw_paths.decode().splitlines():
        if rel in {WAREHOUSE, TRANSFER, "scripts/audit_core_01d_historical_warehouse_transfer_authority_b2.py"}:
            continue
        path = ROOT / rel
        if not path.is_file() or path.suffix not in {".yml", ".yaml", ".py", ".sh"}:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if trigger_line.search(line) and any(target in line for target in targets):
                callers.append({"path": rel, "line": str(line_no), "source_line": line.strip()})
    return callers


def build_source_inventory() -> dict[str, object]:
    boundary.authenticate_predecessors()
    chain = boundary.load_inventory_generations()
    generations = list(range(1, len(chain) + 1))
    require(generations in ([1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4, 5]),
            "A2 inventory chain is not contiguous through the reviewed V3/V4/V5 generations")
    v3 = chain[2][1]
    require(v3["canonical_sha256"] == A2_V3_SHA,
            "A2 V3 predecessor identity drift")
    if len(chain) >= 4:
        v4 = chain[3][1]
        require(v4["canonical_sha256"] == A2_V4_SHA and v4["generation"] == 4,
                "immutable A2 V4 identity drift")
        require(v4["predecessor_inventory"] == {"path": V3_INVENTORY_PATH,
                                                  "canonical_sha256": A2_V3_SHA,
                                                  "generation": 3, "rewritten": False},
                "A2 V4 does not bind the exact immutable V3 predecessor")
        if len(chain) == 5:
            require(chain[4][1]["predecessor_inventory"] == {"path": V4_INVENTORY_PATH,
                                                              "canonical_sha256": A2_V4_SHA,
                                                              "generation": 4, "rewritten": False},
                    "A2 V5 does not bind the exact immutable V4 predecessor")
    parent = read_json(COMPLETION_V4_PATH)
    require(parent["canonical_sha256"] == COMPLETION_V4_SHA, "immutable Completion V4 identity drift")
    b1 = read_json(B1_RECEIPT_PATH)
    require(b1["canonical_sha256"] == B1_RECEIPT_SHA, "immutable B1 receipt identity drift")
    inherited = {(row["workflow_path"], row["trigger_kind"]) for row in parent["unreviewed_authority_surfaces"]}
    require(len(parent["unreviewed_authority_surfaces"]) == 25 and set(TARGET_KEYS) <= inherited
            and parent["workflow_count"] == 39 and parent["trigger_surface_count"] == 57,
            "B2 targets differ from the authenticated Completion V4 unresolved set")
    contracts = {f"{path}#{event}": trigger_contract(path, event) for path, event in TARGET_KEYS}
    transfer_steps = contracts[TRANSFER + "#workflow_dispatch"]["steps"]
    transfer_names = [row["name"] for row in transfer_steps]
    required_order = ["Checkout repository", "Publish run pointer",
                      "Download canonical artifact archive exactly as stored by GitHub",
                      "Split archive into Drive-safe parts and build manifest",
                      "Upload transfer manifest", "Upload canonical part 000",
                      "Upload canonical part 022", "Mark run pointer completed"]
    require([transfer_names.index(name) for name in required_order] ==
            sorted(transfer_names.index(name) for name in required_order),
            "transfer pointer/download/split/upload/completion order drift")
    edges = {
        "warehouse_execution_chain": [
            {"from": WAREHOUSE, "to": script, "classification": "WORKFLOW_RUNS_SOURCE_BOUND_LOCAL_PYTHON_ENTRYPOINT"}
            for script in WAREHOUSE_SCRIPTS
        ],
        "transfer_execution_chain": [
            {"step": "Checkout repository", "classification": "SOURCE_CHECKOUT_WITH_PERSISTED_GITHUB_TOKEN"},
            {"step": "Publish run pointer", "classification": "FORCE_PUSH_FIXED_POINTER_BRANCH_STATUS_STARTED_BEFORE_ARTIFACT_VALIDATION"},
            {"step": "Download canonical artifact archive exactly as stored by GitHub", "classification": "GITHUB_ACTIONS_ARTIFACT_ZIP_READ_BY_ARTIFACT_ID_WITH_GITHUB_TOKEN"},
            {"step": "Split archive into Drive-safe parts and build manifest", "classification": "LOCAL_SPLIT_AND_HASH_AFTER_EXACT_BYTES_AND_SHA_GATE"},
            {"step": "Upload transfer manifest and canonical parts 000-022", "classification": "RUN_SCOPED_GITHUB_ACTIONS_ARTIFACT_WRITE_RETENTION_30_DAYS"},
            {"step": "Mark run pointer completed", "classification": "FORCE_PUSH_FIXED_POINTER_BRANCH_AFTER_SUCCESSFUL_PRECEDING_STEPS_ONLY"},
        ],
    }
    source_ids = [source_identity(path) for path in SOURCE_PATHS]
    require(discover_repository_callers() == [], "unexpected in-repository workflow dispatch/reuse caller found")
    return seal({
        "schema_version": 1,
        "policy_id": SOURCE_INVENTORY_POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA,
        "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "predecessors": {
            "completion_v4": {"path": COMPLETION_V4_PATH, "canonical_sha256": COMPLETION_V4_SHA, "rewritten": False},
            "b1_receipt": {"path": B1_RECEIPT_PATH, "canonical_sha256": B1_RECEIPT_SHA, "rewritten": False},
            "a2_v1_sha256": A2_V1_SHA,
            "a2_v2_sha256": A2_V2_SHA,
            "a2_v3_sha256": A2_V3_SHA,
            "a2_receipt_sha256": A2_RECEIPT_SHA,
            "a2_bridge_receipt_sha256": BRIDGE_RECEIPT_SHA,
            "completion_v3_sha256": COMPLETION_V3_SHA,
            "capability_matrix_v2_sha256": MATRIX_V2_SHA,
            "retained_workflow_v5_sha256": RETAINED_V5_SHA,
            "latest_a2_generation_before_b2": 3,
            "successor_required": "V4",
        },
        "scope": {"target_surface_count": 5, "target_keys": [[path, event] for path, event in TARGET_KEYS],
                  "workflow_count": 2, "out_of_scope_surface_count": 20},
        "source_identities": source_ids,
        "trigger_contracts": contracts,
        "dynamic_reachability_edges": edges,
        "public_data_sources": PUBLIC_DATA_SOURCES,
        "repository_caller_discovery": {
            "method": "SOURCE_SCAN_OF_TRACKED_WORKFLOW_AND_SCRIPT_FILES_FOR_LOCAL_REUSABLE_WORKFLOW_USES_WORKFLOW_RUN_GH_WORKFLOW_RUN_CREATEWORKFLOWDISPATCH_AND_REPOSITORY_DISPATCH_TARGETS",
            "current_repository_callers": [],
            "result": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
            "external_or_manual_github_dispatch_authority": "NOT_NEGATED_BY_ABSENCE_OF_REPOSITORY_CALLERS",
        },
        "source_review_boundary": {
            "github_metadata_reads_only": True,
            "workflow_execution": 0,
            "artifact_payload_download": 0,
            "historical_source_network_calls": 0,
            "workflow_yaml_edits": 0,
            "trigger_edits": 0,
        },
    })


def _authority_for(path: str, event: str) -> dict[str, str]:
    if path == WAREHOUSE:
        return {
            "historical_data_acquisition_authority": "PUBLIC_HISTORICAL_DATASET_HTTP_READ_AND_LOCAL_IMPORT",
            "current_provider_acquisition_authority": "NONE_NO_DIRECT_FOTMOB_API_OR_CURRENT_PROVIDER_CAPTURE; PUBLIC_DATASET_READS_REMAIN_ENABLED",
            "sportsbook_read_authority": "NONE",
            "share_code_authority": "NONE",
            "wager_authority": "NONE",
            "delivery_authority": "NONE_NO_USER_FACING_DELIVERY",
            "notification_authority": "NONE_EXPLICIT; ACTIONS_RUN_STATUS_LOGS_AND_RUN_SCOPED_ARTIFACTS_ONLY",
            "github_artifact_read_authority": "NONE",
            "github_artifact_write_authority": "RUN_SCOPED_HISTORICAL_SQLITE_CSV_AND_COMPLETENESS_DIAGNOSTIC_ARTIFACTS_RETENTION_30_DAYS",
            "github_branch_write_authority": "NONE_CONTENTS_READ_ONLY",
            "github_release_write_authority": "NONE",
            "external_storage_write_authority": "NONE",
            "local_runner_database_write_authority": "LOCAL_RUNNER_DATABASE_ATHENA_HISTORY_DB_SQLITE_AND_LOCAL_EXPORTS",
            "persistent_canonical_database_write_authority": "NONE; RUNNER_LOCAL_SQLITE_IS_PUBLISHED_ONLY_AS_ACTIONS_ARTIFACT",
            "network_authority_summary": "PUBLIC_HUGGINGFACE_DATASET_GITHUB_RAW_FOOTBALL_DATA_OPENFOOTBALL_STATSBOMB_OPEN_DATA_AND_PYPI_READS; NO_FOTMOB_OR_SPORTSBOOK_TRANSPORT",
            "model_or_research_execution_authority": "HISTORICAL_DATASET_BUILD_AND_QUALITY_AUDIT_ONLY; NO_MODEL_TRAINING_OR_PRODUCTION_SELECTION",
        }
    return {
        "historical_data_acquisition_authority": "NONE_NO_HISTORICAL_SOURCE_FETCH_IN_TRANSFER_WORKFLOW",
        "current_provider_acquisition_authority": "NONE_NO_PROVIDER_ENDPOINT",
        "sportsbook_read_authority": "NONE",
        "share_code_authority": "NONE",
        "wager_authority": "NONE",
        "delivery_authority": "GITHUB_ACTIONS_TRANSFER_PREPARATION_ARTIFACTS_ONLY; NO_DRIVE_DELIVERY",
        "notification_authority": "NONE_EXPLICIT; GITHUB_POINTER_BRANCH_STATUS_ONLY",
        "github_artifact_read_authority": "ACTIONS_ARTIFACT_ZIP_READ_BY_INPUT_ARTIFACT_ID_WITH_GITHUB_TOKEN; EXPECTED_ARCHIVE_BYTES_AND_SHA256_CHECKED_AFTER_STARTED_POINTER_PUSH",
        "github_artifact_write_authority": "RUN_SCOPED_MANIFEST_AND_23_PART_ARTIFACTS_RETENTION_30_DAYS_AFTER_ARCHIVE_HASH_GATE",
        "github_branch_write_authority": "FORCE_PUSH_ONLY_FIXED_BRANCH_AUTOMATION_CANONICAL_DRIVE_TRANSFER_POINTER; STARTED_POINTER_BEFORE_ARTIFACT_VALIDATION_AND_COMPLETED_POINTER_AFTER_SUCCESS",
        "github_release_write_authority": "NONE",
        "external_storage_write_authority": "NONE_NO_DRIVE_API_OR_EXTERNAL_STORAGE_CALL",
        "local_runner_database_write_authority": "TEMPORARY_DOWNLOADED_ARCHIVE_SPLIT_AND_MANIFEST_FILES_ONLY",
        "persistent_canonical_database_write_authority": "NONE",
        "network_authority_summary": "GITHUB_ACTIONS_ARTIFACT_DOWNLOAD_VIA_GITHUB_TOKEN_AND_FORCE_PUSH_TO_FIXED_GITHUB_BRANCH; ACTIONS_ARTIFACT_UPLOAD; NO_DRIVE_OR_OTHER_EXTERNAL_STORAGE_NETWORK",
        "model_or_research_execution_authority": "NONE_TRANSFER_PACKAGING_ONLY",
    }


def _reachability(path: str, event: str) -> dict[str, object]:
    if path == WAREHOUSE and event == "pull_request":
        return {"status": "CONDITIONALLY_REACHABLE", "event_condition": "PULL_REQUEST_TARGETS_MAIN_AND_MATCHES_DECLARED_PATH_FILTER", "event_specific_execution": "SHARED_BUILD_JOB_RUNS; STATS_BOMB_STEP_RUNS_FOR_NON_DISPATCH_EVENTS", "manual_authority": False}
    if path == WAREHOUSE and event == "push":
        return {"status": "CONDITIONALLY_REACHABLE", "event_condition": "PUSH_TO_MAIN_AND_MATCHES_DECLARED_PATH_FILTER", "event_specific_execution": "SHARED_BUILD_JOB_RUNS; STATS_BOMB_STEP_RUNS_FOR_NON_DISPATCH_EVENTS", "manual_authority": False}
    if path == WAREHOUSE:
        return {"status": "MANUALLY_REACHABLE", "event_condition": "GITHUB_WORKFLOW_DISPATCH_WITH_DECLARED_INPUTS", "event_specific_execution": "INCLUDE_STATSBOMB_INPUT_GATES_ONLY_STATSBOMB_STEP; YEAR_INPUTS_AFFECT_FOOTBALL_DATA_RANGE", "manual_authority": True}
    if path == TRANSFER and event == "push":
        return {"status": "CONDITIONALLY_REACHABLE", "event_condition": "PUSH_TO_MAIN_WHEN_THE_TRANSFER_WORKFLOW_YAML_PATH_CHANGES", "event_specific_execution": "B2_HAS_ZERO_WORKFLOW_YAML_DIFF_AND_DOES_NOT_TRIGGER_THIS_SURFACE", "manual_authority": False}
    return {"status": "MANUALLY_REACHABLE", "event_condition": "GITHUB_WORKFLOW_DISPATCH_WITH_SOURCE_RUN_AND_ARTIFACT_STRING_INPUTS", "event_specific_execution": "INPUTS_ARE_NOT_BOUND_TO_A_RUN_OR_ARTIFACT_NAME; ARCHIVE_SIZE_AND_SHA256_GATE_OCCURS_AFTER_STARTED_POINTER_PUSH", "manual_authority": True}


def _review_row(key: tuple[str, str], inventory: dict[str, object]) -> dict[str, object]:
    path, event = key
    contract = inventory["trigger_contracts"][path + "#" + event]
    source = next(row for row in inventory["source_identities"] if row["path"] == path)
    if path == WAREHOUSE:
        authority = _authority_for(path, event)
        input_contract = contract["trigger_declaration"]
        trigger_summary = {
            "branch_filter": input_contract.get("branches", []),
            "path_filter": input_contract.get("paths", []),
            "inputs": input_contract.get("inputs", {}),
            "concurrency": contract["workflow_concurrency"],
            "event_dependent_conditions": contract["event_dependent_conditions"],
        }
        dynamic = {
            "entrypoint_chain": WAREHOUSE_SCRIPTS,
            "public_data_sources": PUBLIC_DATA_SOURCES,
            "local_writes": ["database/athena_history.db", "data/history_exports", "run-scoped temporary cache"],
            "actions_artifacts": ["athena-history-sqlite", "athena-history-csv", "athena-history-season-completeness"],
            "branch_or_release_or_external_storage_writes": [],
            "current_repository_callers": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
        }
        interpretation = "CURRENT_LIVE_HISTORICAL_DATASET_BUILD_TRIGGER; SOURCE_AND_PATH_FILTERS_DO_NOT_DISABLE_PUBLIC_DATA_ACQUISITION"
    else:
        authority = _authority_for(path, event)
        input_contract = contract["trigger_declaration"]
        trigger_summary = {
            "branch_filter": input_contract.get("branches", []),
            "path_filter": input_contract.get("paths", []),
            "inputs": input_contract.get("inputs", {}),
            "concurrency": contract["workflow_concurrency"],
            "event_dependent_conditions": contract["event_dependent_conditions"],
        }
        dynamic = {
            "step_edges": inventory["dynamic_reachability_edges"]["transfer_execution_chain"],
            "source_artifact_run_id_default": ARCHIVE["source_run_id_default"],
            "source_artifact_id_default": ARCHIVE["source_artifact_id_default"],
            "source_run_id_cross_validation": "NONE_SOURCE_RUN_ID_IS_POINTER_METADATA_ONLY",
            "artifact_name_or_run_provenance_validation": "NONE_ARTIFACT_ENDPOINT_LOOKUP_IS_BY_ARTIFACT_ID; EXACT_ARCHIVE_BYTES_AND_SHA256_CHECKED",
            "pointer_branch_write_precedes_validation": True,
            "pointer_branch": ARCHIVE["pointer_branch"],
            "current_repository_callers": "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN",
        }
        interpretation = "PHYSICALLY_DECLARED_CURRENT_TRANSFER_PREPARATION_SURFACE; RETAINED_HISTORICAL_PRODUCT_STATUS_DOES_NOT_DISABLE_GITHUB_TRIGGER_AUTHORITY"
    return {
        "workflow_path": path,
        "trigger_kind": event,
        "source_identity": source,
        "trigger_contract": trigger_summary,
        "permissions_and_credentials": {
            "workflow": contract["workflow_permissions"],
            "job": contract["job_permissions"],
            "credential_surface": (
                "CHECKOUT_IMPLICIT_GITHUB_TOKEN_CONTENTS_READ_ONLY; NO_SECRETS_REFERENCE"
                if path == WAREHOUSE else
                "CHECKOUT_PERSISTED_GITHUB_TOKEN_CONTENTS_WRITE_AND_EXPLICIT_SECRETS_GITHUB_TOKEN_FOR_ACTIONS_ARTIFACT_READ"
            ),
            "secret_references": sorted(set(re.findall(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)", (ROOT / path).read_text(encoding="utf-8")))),
        },
        "current_reachability": _reachability(path, event),
        "retained_product_disposition": (
            "CURRENT_HISTORICAL_DATASET_PRODUCER; NO_RETAINED_NONEXECUTABLE_CLASSIFICATION"
            if path == WAREHOUSE else
            "RETAINED_NONEXECUTABLE_HISTORICAL_TRANSFER_PRODUCT_DISPOSITION_FROM_PASS_3; PHYSICAL_TRIGGER_REACHABILITY_REMAINS_SEPARATELY_CURRENT"
        ),
        "historical_guarded_capability": authority,
        "current_declared_trigger_authority": dict(authority),
        "dynamic_reachability": dynamic,
        "interpretation": interpretation,
        "review": {"status": "RESOLVED", "blocker": None},
    }


def build_receipt() -> dict[str, object]:
    # B2 is immutable historical evidence. Later A2 generations supersede V4
    # as the current corpus head, so authenticate B2 against its exact V4
    # predecessor snapshot while the current A2 chain remains separately
    # authenticated by the active pass auditor.
    a2_v4 = boundary.read(V4_INVENTORY_PATH)
    require(a2_v4["generation"] == 4
            and a2_v4["canonical_sha256"] == A2_V4_SHA
            and a2_v4["predecessor_inventory"] == {"path": V3_INVENTORY_PATH,
                                                     "canonical_sha256": A2_V3_SHA,
                                                     "generation": 3, "rewritten": False},
            "immutable B2 A2 V4 source inventory predecessor drift")
    chain = boundary.load_inventory_generations()
    require(len(chain) >= 4 and chain[3][1] == a2_v4,
            "A2 generation chain no longer contains the exact B2 V4 inventory")
    required_python = {
        "scripts/audit_core_01d_historical_warehouse_transfer_authority_b2.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v5.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v2.py",
        "scripts/audit_checkpoint_e_workflows.py",
        "tests/test_core_01d_historical_warehouse_transfer_authority_b2.py",
        "tests/test_core_01d_checkpoint_e_completion_v5.py",
    }
    require(required_python <= {row["path"] for row in a2_v4["source_identities"]},
            "A2 V4 does not authenticate the complete B2 Python change set")
    inventory = read_json(SOURCE_INVENTORY_PATH)
    validate_source_inventory(inventory)
    parent = read_json(COMPLETION_V4_PATH)
    b1 = read_json(B1_RECEIPT_PATH)
    require(parent["canonical_sha256"] == COMPLETION_V4_SHA and b1["canonical_sha256"] == B1_RECEIPT_SHA,
            "B2 predecessor evidence identity drift")
    inherited = {(row["workflow_path"], row["trigger_kind"]) for row in parent["unreviewed_authority_surfaces"]}
    require(len(inherited) == 25 and set(TARGET_KEYS) <= inherited, "B2 predecessor unknown set drift")
    rows = [_review_row(key, inventory) for key in TARGET_KEYS]
    require(all(row["review"]["status"] == "RESOLVED" for row in rows), "B2 source review contains an unresolved target")
    remain = [row for row in parent["unreviewed_authority_surfaces"] if (row["workflow_path"], row["trigger_kind"]) not in TARGET_KEYS]
    require(len(remain) == 20, "B2 scope must leave the other 20 inherited surfaces unchanged")
    return seal({
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": BASE_MAIN,
        "base_tree_sha": BASE_TREE,
        "predecessors": {
            "completion_v4": {"path": COMPLETION_V4_PATH, "canonical_sha256": COMPLETION_V4_SHA, "rewritten": False},
            "b1_receipt": {"path": B1_RECEIPT_PATH, "canonical_sha256": B1_RECEIPT_SHA, "rewritten": False},
            "completion_v3_sha256": COMPLETION_V3_SHA,
            "a2_v1_inventory_sha256": A2_V1_SHA,
            "a2_v2_inventory_sha256": A2_V2_SHA,
            "a2_v3_inventory_sha256": A2_V3_SHA,
            "a2_receipt_sha256": A2_RECEIPT_SHA,
            "a2_bridge_receipt_sha256": BRIDGE_RECEIPT_SHA,
        },
        "source_inventory": {"path": SOURCE_INVENTORY_PATH, "canonical_sha256": inventory["canonical_sha256"]},
        "a2_inventory_successor": {"path": V4_INVENTORY_PATH, "generation": 4,
                                   "canonical_sha256": a2_v4["canonical_sha256"],
                                   "predecessor_path": V3_INVENTORY_PATH,
                                   "predecessor_canonical_sha256": A2_V3_SHA,
                                   "predecessor_rewritten": False},
        "workflow_tree_sha1": WORKFLOW_TREE,
        "workflow_evolution_ledger_sha256": EVOLUTION_SHA,
        "transition_count": 14,
        "retirement_ledger_sha256": RETIREMENT_SHA,
        "retired_workflow_count": 3,
        "workflow_count": parent["workflow_count"],
        "trigger_surface_count": parent["trigger_surface_count"],
        "scope": {"target_surface_count": 5, "reviewed_workflow_count": 2,
                  "resolved_count": len(rows), "partial_count": 0,
                  "global_unknown_before": 25, "global_unknown_after": len(remain),
                  "remaining_unknown_keys": [[row["workflow_path"], row["trigger_kind"]] for row in remain]},
        "post_440_tests": POST_440_TESTS,
        "historical_github_run_metadata": {"observed_at_utc": OBSERVED_AT, "source_endpoint": "GET /repos/Thabearr/ATHENA/actions/runs/{run_id}", "read_only": True, "runs": HISTORICAL_RUNS},
        "historical_run_interpretation": "SUCCESSFUL_TRANSFER_RUN_PROVES_HISTORICAL_COMPLETION_ONLY; IT_DOES_NOT_DISABLE_OR_AUTHORIZE_CURRENT_TRIGGER_EXECUTION",
        "current_actions_artifact_listings": {"observed_at_utc": OBSERVED_AT, "records": CURRENT_ARTIFACT_LISTINGS,
                                               "empty_listing_does_not_infer_disappearance_cause": True},
        "canonical_archive_contract": ARCHIVE,
        "review_rows": rows,
        "out_of_scope_surface_keys_preserved": [[row["workflow_path"], row["trigger_kind"]] for row in remain],
        "retention_blockers_A_B_C_D": "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
        "live_missing_artifact_relation_count": 0,
        "historical_missing_artifact_relation_count": 14,
        "actions": ZERO_ACTIONS,
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "protected_model_router_portfolio_semantic_delta": 0,
        "source_review_counter_while_open": "1/5",
        "source_review_counter_if_owner_merges": "2/5",
        "mandatory_governing_source_reread_after_b2_merge": False,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "criterion_11": False,
        "criterion_14": False,
        "terminal": "CORE_01D_HISTORICAL_WAREHOUSE_TRANSFER_AUTHORITY_B2_REVIEW_READY_5_RESOLVED_DO_NOT_MERGE",
    })


def validate_source_inventory(value: dict[str, object]) -> None:
    require(value == build_source_inventory(), "B2 source inventory differs from current source/predecessor identities")
    require((ROOT / SOURCE_INVENTORY_PATH).read_bytes() == canonical(value), "B2 source inventory is not canonical")


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None) -> None:
    require((ROOT / RECEIPT_PATH).read_bytes() == canonical(value), "B2 receipt is not canonical")
    require(value == (build_receipt() if expected is None else expected), "B2 receipt differs from independently derived source review")
    require(value["scope"]["target_surface_count"] == 5 and value["scope"]["resolved_count"] == 5,
            "B2 must resolve exactly five reviewed surfaces")
    require(value["scope"]["global_unknown_before"] == 25 and value["scope"]["global_unknown_after"] == 20,
            "B2 unresolved count is not source-derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
            and value["criterion_11"] is False and value["criterion_14"] is False,
            "B2 cannot close global Checkpoint-E authority criteria")
    require(value["actions"] == ZERO_ACTIONS and value["workflow_edit_count"] == value["trigger_edit_count"] == 0,
            "B2 live-action or workflow mutation sentinel changed")


def audit() -> dict[str, object]:
    value = read_json(RECEIPT_PATH)
    validate_receipt(value)
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"],
            "target_count": value["scope"]["target_surface_count"], "resolved_count": value["scope"]["resolved_count"],
            "global_unknown_after": value["scope"]["global_unknown_after"],
            "checkpoint_e": value["checkpoint_e_status"], "p4_4": value["p4_4_status"], "terminal": value["terminal"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-source-inventory", action="store_true")
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    if args.write_source_inventory:
        value = build_source_inventory()
        (ROOT / SOURCE_INVENTORY_PATH).write_bytes(canonical(value))
        print(value["canonical_sha256"])
    elif args.write_receipt:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
