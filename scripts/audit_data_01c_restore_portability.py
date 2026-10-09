"""Exact PORT-02C second source successor and offline native evidence audit."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from scripts.qualify_data_01c_restore_portability import canonical, NODEIDS, PHASES, validate_receipt

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/port-02c-native-runtime.yml"
PREDECESSOR_HEAD = "942f4a3820b5521d0595fcf36154283b19379c6a"
PREDECESSOR_TREE = "9b08653f1a12bb1b3d964fbd910396ff955740da"
SNAPSHOT = "tests/fixtures/core_01d/data_01c_portability/predecessor_sources_v5.json"
SNAPSHOT_SHA = "78615dfee7cd52cc85b5e5ee128b7f5711e216201b95ae240f8348d46dd65c76"
RECEIPT = "artifacts/product/data_01c_restore_portability_v1.json"
FROZEN_EVIDENCE = {
    "artifacts/architecture/port_02c_native_runtime_workflow_add_v1.json": "5065031917a1e2c78ff9f6ec047ea9debbb2df593fb708cc595140fbe8c8c9b4",
    "artifacts/architecture/p4_workflow_evolution_snapshots/port_02c_native_runtime_slice_v1.json": "da2a00e6ba5ae10d04b44fe91c48328038f615e4acabcb0c24278d319ddf58fc",
    "artifacts/architecture/p4_workflow_evolution_ledger_v1.json": "886e6aa5f82c137158346f520553969550008a1bffdb243a77875334041a53d7",
}
STEP = '''      - name: D5 native restore portability (offline, four cases)
        env:
          D5_PR_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}
        run: |
          python scripts/qualify_data_01c_restore_portability.py --runner-temp "${{ runner.temp }}"

'''
UPLOAD = "            ${{ runner.temp }}/data01c-restore-portability.json\n"
HISTORICAL_A2_SOURCE_FIXTURES = {
    "tests/offline_transport.py": "tests/fixtures/core_01d/a2-v1-offline-transport.txt",
    "scripts/audit_core_01d_ci_offline_transport_boundary.py":
        "tests/fixtures/core_01d/a2-v1-ci-offline-transport-boundary.py.txt",
    "scripts/audit_p4_workflow_evolution_ledger.py":
        "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-ledger.py.txt",
    "tests/native/test_port_02c_audit_source_forward.py":
        "tests/fixtures/core_01d/a2-v1-port02c-source-forward-test.py.txt",
    "tests/test_p4_4a_workflow_evolution_guard.py":
        "tests/fixtures/core_01d/a2-v1-p4-workflow-evolution-guard-test.py.txt",
}


def identity(raw):
    return {"git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
            "source_sha256": hashlib.sha256(raw).hexdigest()}


def snapshot():
    raw = (ROOT / SNAPSHOT).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA:
        raise ValueError("D5 portability predecessor snapshot drift")
    return json.loads(raw)


def predecessor_source(path):
    row = snapshot()["sources"][path]
    raw = base64.b64decode(row["base64"], validate=True)
    if identity(raw) != {"git_blob_sha1": row["git_blob_sha1"], "source_sha256": row["byte_sha256"]}:
        raise ValueError("retained portability predecessor bytes drift")
    return raw


def expected_workflow():
    raw = predecessor_source(WORKFLOW)
    anchor = b"      - name: Require variant semantic equality\n"
    upload = b"            ${{ runner.temp }}/port02c-out-locked/\n"
    if raw.count(anchor) != 1 or raw.count(upload) != 1:
        raise ValueError("ambiguous bounded PORT-02C source-forward anchors")
    return raw.replace(anchor, STEP.encode() + anchor).replace(upload, upload + UPLOAD.encode())


def tree_identity(entries):
    body = b"".join(row["mode"].encode() + b" " + row["name"].encode() + b"\0" + bytes.fromhex(row["blob"])
                    for row in entries)
    return hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()


def successor_context():
    entries = snapshot()["workflow_entries"]
    if tree_identity(entries) != PREDECESSOR_TREE:
        raise ValueError("retained PORT-02C predecessor workflow tree drift")
    after = identity(expected_workflow())
    changed = [dict(row, blob=after["git_blob_sha1"]) if row["name"] == "port-02c-native-runtime.yml"
               else row for row in entries]
    return after, tree_identity(changed)


def authenticate_workflow():
    for path, digest in FROZEN_EVIDENCE.items():
        if hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest:
            raise ValueError("frozen PORT-02C historical evidence drift: " + path)
    expected = expected_workflow()
    raw = (ROOT / WORKFLOW).read_bytes().replace(b"\r\n", b"\n")
    if raw != expected:
        raise ValueError("PORT-02C change exceeds the exact D5 offline qualification delta")
    after, tree = successor_context()
    entries = snapshot()["workflow_entries"]
    directory = ROOT / ".github/workflows"
    if sorted(p.name for p in directory.iterdir()) != sorted(row["name"] for row in entries):
        raise ValueError("D5 successor changed the workflow set")
    for row in entries:
        source = (directory / row["name"]).read_bytes().replace(b"\r\n", b"\n")
        expected_blob = after["git_blob_sha1"] if row["name"] == "port-02c-native-runtime.yml" else row["blob"]
        if identity(source)["git_blob_sha1"] != expected_blob:
            raise ValueError("unrelated workflow changed in D5 successor: " + row["name"])
    return after, tree


def historical_workflow_tree(observed_tree):
    if observed_tree == PREDECESSOR_TREE:
        return observed_tree
    _, tree = authenticate_workflow()
    if observed_tree != tree:
        raise ValueError("unknown PORT-02C source-forward workflow tree")
    return PREDECESSOR_TREE


def historical_a2_source_blob_identity(path):
    """Return a Git blob ID only for exact source bytes authenticated by A2 V1."""
    fixture_path = HISTORICAL_A2_SOURCE_FIXTURES.get(path)
    if fixture_path is None:
        return None
    fixture = ROOT / fixture_path
    if not fixture.is_file() or fixture.is_symlink():
        raise ValueError("pinned A2 historical source fixture is unavailable: " + path)
    raw = fixture.read_bytes().replace(b"\r\n", b"\n")
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    if hashlib.sha256(raw).hexdigest() != a2.pinned_historical_identity(path):
        raise ValueError("pinned A2 historical source fixture identity mismatch: " + path)
    return identity(raw)["git_blob_sha1"]


def project_historical_inventory(raw):
    """Authenticate the current source corpus before projecting fixed predecessor blobs."""
    from scripts import audit_data_01c_app_store_complete as data01c
    data01c.authenticate_successor()
    authenticate_workflow()
    sources = snapshot()["sources"]
    lines = []
    for line in raw.splitlines(keepends=True):
        meta, sep, path = line.partition(b"\t")
        name = path.strip().decode()
        historical = historical_a2_source_blob_identity(name)
        if name in sources:
            current = identity((ROOT / name).read_bytes().replace(b"\r\n", b"\n"))["git_blob_sha1"]
            allowed = {current.encode(), sources[name]["git_blob_sha1"].encode()}
            if historical is not None:
                allowed.add(historical.encode())
            if meta.rsplit(b" ", 1)[-1] not in allowed:
                raise ValueError("portability source inventory identity does not match authenticated current bytes: " + name)
            meta = meta.rsplit(b" ", 1)[0] + b" " + sources[name]["git_blob_sha1"].encode()
        elif historical is not None:
            current = identity((ROOT / name).read_bytes().replace(b"\r\n", b"\n"))["git_blob_sha1"]
            if meta.rsplit(b" ", 1)[-1] not in {current.encode(), historical.encode()}:
                raise ValueError("portability historical source identity is not pinned: " + name)
            meta = meta.rsplit(b" ", 1)[0] + b" " + historical.encode()
        line = meta + sep + path
        lines.append(line)
    return b"".join(lines)


def build_receipt():
    after, tree = authenticate_workflow()
    paths = list(FROZEN_EVIDENCE)
    frozen = {path: identity((ROOT / path).read_bytes()) for path in paths}
    value = {"schema_version": 1, "policy_id": "ATHENA_DATA_01C_PORT02C_EXACT_SOURCE_FORWARD_V1",
             "base_main_sha": "57e632f1e150cd1429ce00005a3cdf9ef3673ff2",
             "predecessor_head": PREDECESSOR_HEAD,
             "mechanism": "EXACT_EXISTING_SUCCESSOR_CONTEXT_EXTENSION_NO_NEW_WORKFLOW_TRANSITION",
             "retained_predecessor_snapshot": {"path": SNAPSHOT, "sha256": SNAPSHOT_SHA},
             "historical_add": {"git_blob_sha1": "cb7374cbf4d1d35a39964d123e75367996983d6c",
                                "source_sha256": "d4630d7904b464f83ddee4ea9f935da84e81a073d9d20565d79df4247918989e"},
             "predecessor_source": identity(predecessor_source(WORKFLOW)),
             "successor_source": after, "predecessor_workflow_tree": PREDECESSOR_TREE,
             "successor_workflow_tree": tree, "historical_evidence": frozen,
             "pytest_nodeids": NODEIDS, "crash_phases": PHASES,
             "hosted_proof": "SEPARATE_EXACT_FINAL_HEAD_UPLOADED_NATIVE_RECEIPTS_REQUIRED",
             "source_review_counter": "2/5", "merge_authorized": False}
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def audit():
    expected = build_receipt()
    if (ROOT / RECEIPT).read_bytes() != canonical(expected):
        raise ValueError("D5 portability source receipt drift")
    return expected


def audit_native_pair(windows, linux, head, jobs_metadata):
    values = []
    for path in (windows, linux):
        raw = Path(path).read_bytes()
        value = json.loads(raw)
        if raw != canonical(value):
            raise ValueError("native qualification receipt is not canonical")
        values.append(validate_receipt(value, head))
    if [v["host_os"] for v in values] != ["Windows", "Linux"] or values[0]["run_id"] != values[1]["run_id"]:
        raise ValueError("native receipts do not share the exact final PR run")
    metadata = json.loads(Path(jobs_metadata).read_bytes())
    if (metadata.get("head_sha") != head or metadata.get("event") != "pull_request"
            or metadata.get("conclusion") != "success" or metadata.get("run_attempt") != 1
            or metadata.get("id") != values[0]["run_id"]
            or any(value.get("run_attempt") != 1 for value in values)):
        raise ValueError("native jobs are not natural successful exact-final-head evidence")
    jobs = metadata.get("jobs", [])
    qualified = []
    for host in ("windows", "linux"):
        matches = [job for job in jobs if job.get("name") == "native slice (" + host + ")"]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError("native qualification job is absent or unsuccessful")
        job = matches[0]
        for name in ("D5 native restore portability (offline, four cases)", "Upload qualification evidence"):
            steps = [step for step in job.get("steps", []) if step.get("name") == name]
            if len(steps) != 1 or steps[0].get("conclusion") != "success":
                raise ValueError("native qualification or evidence upload failed")
        cases = [step for step in job.get("steps", []) if step.get("name", "").startswith("CASE ")]
        if len(cases) != 5 or any(step.get("conclusion") != "success" for step in cases):
            raise ValueError("existing PORT-02C cases did not all pass")
        qualified.append({"host_os": host, "job_id": job["id"]})
    evidence = {"schema_version": 1, "policy_id": "ATHENA_DATA_01C_NATIVE_RESTORE_ACCEPTANCE_V1",
                "final_pr_head": head, "run_id": metadata["id"], "run_attempt": 1,
                "source_receipt_sha256": audit()["canonical_sha256"],
                "jobs": qualified, "native_receipts": values,
                "metadata_byte_sha256": hashlib.sha256(Path(jobs_metadata).read_bytes()).hexdigest(),
                "qualification": "WINDOWS_NTFS_AND_UBUNTU_24_04_EXT4_PROVEN",
                "merge_authorized": False}
    evidence["canonical_sha256"] = hashlib.sha256(canonical(evidence)).hexdigest()
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--windows-receipt")
    parser.add_argument("--linux-receipt")
    parser.add_argument("--head")
    parser.add_argument("--jobs-metadata")
    parser.add_argument("--write-native-evidence")
    args = parser.parse_args()
    if args.write:
        (ROOT / RECEIPT).write_bytes(canonical(build_receipt()))
    else:
        audit()
    if args.windows_receipt or args.linux_receipt or args.head:
        if not all((args.windows_receipt, args.linux_receipt, args.head, args.jobs_metadata)):
            parser.error("both native receipts, job metadata and final head are required")
        evidence = audit_native_pair(args.windows_receipt, args.linux_receipt, args.head, args.jobs_metadata)
        if args.write_native_evidence:
            with Path(args.write_native_evidence).open("xb") as stream:
                stream.write(canonical(evidence))
    print("DATA_01C_RESTORE_PORTABILITY_SOURCE_OK")


if __name__ == "__main__":
    main()
