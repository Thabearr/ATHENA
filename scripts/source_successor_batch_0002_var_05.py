"""Batch 0002 (VAR-05): registers the new files this mission adds; no successor entries.

Immutable once merged: later missions add NEW batch files and never edit this one
(tests/test_source_successor_registry.py proves it against the A2 generations).
The balanced-shard change to .github/workflows/tests.yml is deferred (it needs a
root-pinned edit), so this batch has no ENTRIES. ADDED_PATHS lets the additive
allowlist and the exact B1 census read the new files from here.
"""

SEQUENCE = 2
MISSION = "VAR-05"
PREVIOUS_BATCH_SHA256 = "e13bc44a6a4788b6c121127290c14c8c8a487bc35d0bd3fb2f04ba6e24c8ddcb"

ENTRIES = ()

# New files this mission adds; the additive allowlist and the B1 census read them.
ADDED_PATHS = (
    "scripts/ci_select_test_shard.py",
    "scripts/source_successor_batch_0002_var_05.py",
    "tests/test_var_05_ci_guardrails.py",
)
FIRST_GENERATION = 351
