"""Batch 0001 (PH-A): the three Phase A successors admitted by PR #470.

Immutable once merged: later missions add NEW batch files and never edit this one
(tests/test_source_successor_registry.py proves it against the A2 generations).
Entries are copied exactly from PHASE_A_SUCCESSORS as merged in PR #470.
"""
from scripts.source_successor_registry import Successor

SEQUENCE = 1
MISSION = "PH-A"
PREVIOUS_BATCH_SHA256 = ""

REASON = "Phase A pcUpcoming retention (rebuild of PR #465 Phase A)"

# The Phase A workflow delta: one copy-list line and the trailing verify block.
COPY_LINE = b"            '.cache/athena-research/current-shadow-sportybet-pc-upcoming-discovery' \\\n"
VERIFY_BLOCK = (
    b"          # Verify copied raw pages, manifests and capture epochs against the\n"
    b"          # exact source tree and the completed run receipt before artifact upload.\n"
    b"          # Runs last so a verification failure cannot skip the identity-state copy.\n"
    b"          python -m scripts.verify_current_shadow_pc_upcoming_archive\n"
    b"\n"
)
# The F1 one-call hook in scripts/core_01d_historical_source.py.
HISTORICAL_SOURCE_HOOK = (
    b"        from scripts import audit_phase_a_workflow_successor as phase_a\n"
    b"        live_identity = phase_a.project_source_identity(str(path), live, live_identity)\n"
)
# The one-call hook in retained_workflow_status_v3._source_identity (Amendment 3 R2).
RETAINED_STATUS_V3_HOOK = (
    b"    from scripts import audit_phase_a_workflow_successor as phase_a\n"
    b"    blob, normalized = phase_a.project_source_bytes(path, blob, normalized)\n"
)

ENTRIES = (
    Successor(
        path=".github/workflows/current-shadow-all-market.yml",
        before_blob="a06a3166322ccb92b0bc3c05c87c5b3ca17298e1",
        before_sha256="755cca90021183bbadf82ccb4ba3c90222eb088702f2e780aad8be9cebfe2c9c",
        after_blob="62dd84da0c426b0b03729cca5d9d7b4294fb0472",
        after_sha256="0ac54f9a5d2958e57d589f3e2489a0a7b505f6acc978a568906993960803c1e5",
        hunks=(COPY_LINE, VERIFY_BLOCK),
        reason=REASON,
    ),
    Successor(
        path="scripts/core_01d_historical_source.py",
        before_blob="7548914b31ceb832b55818e66c19b8a9bd606927",
        before_sha256="5c46e7b5011de91c540fbbff9b7c06f15a81c87097ef07838d045123ae948865",
        after_blob="83913347db213e0972948113f1ce8dfb2600fe15",
        after_sha256="de26bbae44894704399d9f520da478749739ca7b055b42bc5305c4f39213fd2b",
        hunks=(HISTORICAL_SOURCE_HOOK,),
        reason=REASON + ": one-call projection hook for the workflow successor",
    ),
    Successor(
        path="scripts/audit_core_01d_retained_workflow_status_v3.py",
        before_blob="6121d896de477c4384bcdb41a3d55f691227d2fd",
        before_sha256="c55e244adb14979b7da384ad46e9fdf7958f15ec03dfa4250747a8091088d600",
        after_blob="db9f14c86a78ec2314c746163506757956d4a65c",
        after_sha256="0ef7a91bb52ceba90db9ac93e16ba6983933b2632d3bd04c3a2840d192b3ef51",
        hunks=(RETAINED_STATUS_V3_HOOK,),
        reason=REASON + ": one-call source-identity hook (L1; D5 app-store admission)",
    ),
)
