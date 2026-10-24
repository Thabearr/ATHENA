"""Temporary, one-run GitHub-hosted repair assembler. Never retained in candidate."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BRANCH="athena/one-time-checkpoint-holdout-20261024"
WORKFLOW=Path(".github/workflows/athena-one-time-offline-workspace.yml")
SELF=Path(".github/athena_one_time_checkpoint_candidate.py")
EXPECTED="20d01d50f121be79ee07f1b2126d22735ea812e5"
TARGET=".github/workflows/tests.yml"

def command(*args, check=True, capture_output=False):
    return subprocess.run(list(args),cwd=ROOT,text=True,check=check,
                          capture_output=capture_output)

def replace_exact(path, before, after):
    file=ROOT/path
    raw=file.read_text(encoding="utf-8")
    if raw.count(before)!=1:
        raise RuntimeError("Patch anchor not unique: "+path)
    file.write_text(raw.replace(before,after),encoding="utf-8",newline="\n")

def main():
    assert command("git","branch","--show-current",capture_output=True).stdout.strip()==BRANCH
    assert command("git","merge-base","--is-ancestor",EXPECTED,"HEAD").returncode==0
    assert command("git","status","--porcelain",capture_output=True).stdout==""
    checkpoint="scripts/audit_checkpoint_e_workflows.py"
    anchor="        elif path in PASS_A_HISTORICAL_SOURCE_FIXTURES:\n"
    insert='''        elif path == ".github/workflows/tests.yml":
            # Historical Pass-1 compares its fixed V1 workflow identity, not
            # the separately approved and authenticated live shard-balance.
            from scripts import audit_phase_a_pass_a_tests_source_successor as tests_view
            from scripts import audit_tests_shard_balance_successor as tests_shards
            predecessor = tests_view.historical_workflow_source()
            before_identity = {"mode": "100644",
                               "git_blob_sha1": tests_shards.BEFORE["git_blob_sha1"]}
            after_identity = {"mode": "100644",
                              "git_blob_sha1": tests_shards.AFTER["git_blob_sha1"]}
            require(
                identity == before_identity and current.get(path) == after_identity
                and hashlib.sha1(
                    b"blob " + str(len(predecessor)).encode("ascii") + b"\\0" + predecessor
                ).hexdigest() == before_identity["git_blob_sha1"],
                "Pass-1 exact historical Tests workflow successor drift",
            )
            pass1_forward_predecessor_blobs[path] = before_identity["git_blob_sha1"]
            if path in value["scan_paths"]:
                pass1_forward_predecessor_sources[path] = predecessor
'''
    replace_exact(checkpoint,anchor,insert+anchor)
    v2="scripts/audit_core_01d_checkpoint_e_completion_v2.py"
    raw=(ROOT/v2).read_text()
    prefix,sep,tail=raw.partition("def a2_historical_projection(raw):")
    if not sep:
        raise RuntimeError("A2 historical projection missing")
    marker="  elif path in RUN_02A_PRE_PREDECESSOR_BLOBS:\n"
    if tail.count(marker)!=1:
        raise RuntimeError("A2 historical tests projection anchor changed")
    insert2='''  elif path=='.github/workflows/tests.yml':
   # Preserve the immutable Pass-A/V1 Git-tree identity, but only after the
   # actual head and current A2/shard receipt have been authenticated.
   from scripts import audit_phase_a_pass_a_tests_source_successor as tests_view
   from scripts import audit_tests_shard_balance_successor as tests_shards
   predecessor=tests_view.historical_workflow_source()
   review.require(
    hashlib.sha1(b'blob '+str(len(predecessor)).encode()+b'\\0'+predecessor).hexdigest()
       == tests_shards.BEFORE['git_blob_sha1']
    and tests_shards.AFTER['git_blob_sha1']!=tests_shards.BEFORE['git_blob_sha1'],
    'Checkpoint-E historical Tests predecessor identity drift')
   line=('100644 blob '+tests_shards.BEFORE['git_blob_sha1']+'\\t'+path+'\\n').encode()
'''
    (ROOT/v2).write_text(prefix+sep+tail.replace(marker,insert2+marker),encoding="utf-8",newline="\n")
    # The candidate MUST exclude this one-time workflow and its runner helper.
    (ROOT/WORKFLOW).unlink()
    (ROOT/SELF).unlink()
    command("git","config","user.name","github-actions[bot]")
    command("git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com")
    command("git","add","-A")
    command("git","diff","--cached","--check")
    command("git","commit","-m","fix: authenticate Checkpoint-E historical Tests shard predecessor")
    # All current source bytes now exist at HEAD, and immutable V1-V359 are
    # unchanged. The project's own reviewed A2 generator must derive V360.
    generated=command("python","-m","scripts.audit_core_01d_ci_offline_transport_boundary",
                      "--emit-successor-inventory",capture_output=True)
    document=json.loads(generated.stdout)
    assert document["generation"]==360
    assert document["predecessor_inventory"]["generation"]==359
    assert document["predecessor_inventory"]["rewritten"] is False
    output=ROOT/"tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v360.json"
    output.write_text(generated.stdout,encoding="utf-8",newline="\n")
    command("git","add",str(output.relative_to(ROOT)))
    command("git","diff","--cached","--check")
    command("git","commit","-m","chore: append exact-current A2 V360 inventory for Checkpoint-E")
    # Catch incorrect current-A2 identity before any remote candidate push.
    command("python","-m","scripts.audit_core_01d_ci_offline_transport_boundary","--check")
    print("CANDIDATE_HEAD="+command("git","rev-parse","HEAD",capture_output=True).stdout.strip())
    print("A2_V360_SHA256="+document["canonical_sha256"])
    print("CHANGED_PATHS="+command("git","diff","--name-only",EXPECTED+"..HEAD",capture_output=True).stdout.strip().replace("\n",","))
    print("EXACT_CANDIDATE_READY_TO_PUSH")
    # Do not mutate PR #465. Publish to the separately authorized temporary
    # branch only after the source-bound inventory check succeeds.
    command("git","push","origin","HEAD:refs/heads/"+BRANCH)
    print("PUSHED_CANDIDATE_TEMP_BRANCH="+BRANCH)

if __name__=="__main__":
    main()
