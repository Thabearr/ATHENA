# ATHENA Repository Architecture Inventory (P0.2)

## Purpose

`scripts/audit_repository_architecture.py` produces a deterministic,
machine-generated, read-only inventory of the ATHENA repository at a
specific Git ref. It replaces anecdotal architecture claims with
reproducible, multi-signal evidence.

The inventory answers:

- What Python modules exist at a given commit?
- Which local modules statically import which other modules?
- Which modules are imported by tests only?
- Which modules have zero static inbound edges?
- Which modules contain dynamic import indicators?
- Which modules are referenced by GitHub Actions workflows?
- Which scripts/modules are invoked via subprocess/CLI string literals?
- Which files appear to be executable entrypoints?
- Which CLI frameworks are present?
- Which current workflows invoke which scripts/modules?
- Which architecture generations/families coexist?
- Which "supported roots" can statically reach which modules?
- What exact Git commit was inventoried?

The resulting artifacts are the factual input for subsequent remediation
waves (P0.3 boundary CI, P0.4 runtime instrumentation, etc.).

---

## Schema version

**Schema version: 1**  
**Policy ID: `ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_V1`**

---

## Critical distinctions

### Static imports vs. supported reachability

**Static import edge** — `module A` contains `import B` or `from B import x`.
This is a structural fact about source code.

**Supported reachability** — there exists a chain of static import edges from
a *supported root* to a module.

These are not the same thing. A module can have many static inbound edges and
still be unreachable from any supported root. Conversely, a module referenced
only by tests has static inbound edges but no supported-root reachability.

### Why zero static inbound ≠ obsolete

A module with `zero_static_inbound = true` has no known static importers at the
inventoried commit. That is one signal only.

It does **NOT** mean:

- The module is dead.
- The module is safe to delete.
- The module is not called at runtime.

Modules can be alive and necessary via:
- GitHub Actions workflow invocations (`python -m module` / `python script.py`).
- Dynamic imports (`importlib.import_module(...)`, `__import__(...)`).
- Subprocess calls from other Python files.
- Entry points in `setup.py` / `pyproject.toml`.
- CLI invocation by users or CI scripts not tracked by static analysis.
- Historical contract preservation (module must remain importable by name).

**Policy:** `zero_static_inbound = true` is a flag for investigation.
It never, by itself, authorises deletion.

### Dynamic import limitations

The tool detects `importlib.import_module(...)` and `__import__(...)` by
static AST inspection only. If the target is a literal string, it is
recorded as-is. If it is a variable or expression, it is recorded as
`DYNAMIC_IMPORT_NON_LITERAL`. The tool **does not execute** the module to
resolve dynamic targets.

This means the inventory may undercount reachability through dynamic import.

### Workflow/subprocess reference handling

Workflow YAML files are read as text. The tool extracts literal
`python script.py` and `python -m package.module` patterns using regex.
It does **not** execute workflow steps or shell commands.

References are evidence that a module is invoked by CI, not proof of
production deployment.

---

## Deterministic `--ref` behaviour

The tool resolves the supplied `--ref` using:

```
git rev-parse --verify <ref>^{commit}
```

This fails closed: any invalid ref, non-existent SHA, or non-commit object
causes an immediate fatal error.

File bytes are read from:

```
git show <resolved_sha>:<path>
```

No checkout of the target ref is required. The tool works entirely from the
Git object store.

The `source_commit` field in the JSON artifact always contains the 40-character
resolved SHA, not the human-readable ref string.

Because:
- all output is sorted deterministically,
- no wall-clock time is embedded in canonical output,
- no machine hostname, path, or UUID is included,

two runs of the tool against the same commit and same policy produce
byte-identical JSON and CSV.

---

## How to regenerate the baseline artifact

```bash
git pull --ff-only && \
PYTHONPATH=. python -m scripts.audit_repository_architecture \
  --ref e04cbbeaeff999a1e5dd3ff7891857b4813a7fac \
  --json-output artifacts/architecture/repository-architecture-inventory-v1.json \
  --csv-output artifacts/architecture/repository-architecture-modules-v1.csv
```

On Windows (PowerShell):

```powershell
git pull --ff-only; `
$env:PYTHONPATH="."; python -m scripts.audit_repository_architecture `
  --ref e04cbbeaeff999a1e5dd3ff7891857b4813a7fac `
  --json-output artifacts/architecture/repository-architecture-inventory-v1.json `
  --csv-output artifacts/architecture/repository-architecture-modules-v1.csv
```

To verify determinism (run twice, compare SHA-256):

```bash
PYTHONPATH=. python -m scripts.audit_repository_architecture \
  --ref e04cbbeaeff999a1e5dd3ff7891857b4813a7fac \
  --json-output /tmp/inv-a.json \
  --csv-output /tmp/inv-a.csv

PYTHONPATH=. python -m scripts.audit_repository_architecture \
  --ref e04cbbeaeff999a1e5dd3ff7891857b4813a7fac \
  --json-output /tmp/inv-b.json \
  --csv-output /tmp/inv-b.csv

sha256sum /tmp/inv-a.json /tmp/inv-b.json
sha256sum /tmp/inv-a.csv /tmp/inv-b.csv
```

Required: both SHA-256 pairs must be identical.

---

## What P0.2 does NOT authorise

P0.2 generates evidence only. It does not:

- Assign `DELETE`, `ARCHIVE`, `MIGRATE_THEN_DELETE`, or `KEEP` to any module.
- Promote any architecture generation as canonical.
- Demote any architecture generation as obsolete.
- Authorise deletion of any file.
- Authorise migration of any caller.
- Authorise removal of any workflow.
- Modify any runtime behaviour.
- Create any runtime code path.
- Trigger any provider acquisition.
- Execute Current Shadow.
- Create or reload a SportyBet share code.

All `disposition` values in the P0.2 artifact are `"UNCLASSIFIED"`.

Actual `KEEP` / `MIGRATE_THEN_DELETE` / `ARCHIVE_OR_RETIRE` / `DELETE`
classification belongs to later reviewed remediation waves, each requiring
human review and a merged PR.

---

## How later remediation waves use the artifact

| Wave | How this artifact is used |
|------|--------------------------|
| P0.3 Architecture boundary CI | Import graph edges become CI rules — if a caller imports a module it should not (e.g. legacy into canonical), CI fails. Boundaries derived from P0.2 evidence. |
| P0.4 Runtime reachability instrumentation | P0.2 static roots and edges become starting points for runtime coverage annotation. |
| Checkpoint A | P0.2 + P0.3 + P0.4 together constitute the complete inventory. |
| P1 Canonical orchestration/interfaces | P0.2 identifies which callers must be migrated before canonical interface can be locked. |
| P2–P3 Migration waves | P0.2 provides the list of static importers that must be updated for each migration. |
| P5/P6 Retirement/deletion | P0.2 evidence (static inbound, workflow refs, dynamic refs, subprocess refs) is a required input for any deletion PR. A deletion PR must show that all signals are zero or migrated. |

---

## Cleanup classifications (future waves only)

| Classification | Meaning |
|----------------|---------|
| `KEEP` | Canonical, actively maintained. |
| `MIGRATE_THEN_DELETE` | Has canonical replacement; all callers must be migrated first. |
| `ARCHIVE_OR_RETIRE` | No active callers; safe to archive, requires multi-signal evidence. |
| `DELETE` | Fully superseded; all callers migrated; evidence reviewed by human. |

**No item receives `DELETE` authority merely because `zero_static_inbound = true`.**

Multi-signal evidence required for any deletion decision:
static inbound count + dynamic/workflow/subprocess references + contract review
+ historical usage.

---

## Signals exposed per module

| Signal | Meaning |
|--------|---------|
| `static_inbound_count` | Number of local modules that statically import this module |
| `non_test_static_inbound_count` | Same, excluding test modules |
| `static_outbound_count` | Number of local modules this module imports |
| `zero_static_inbound` | True if no local static importers (NOT equivalent to "dead") |
| `referenced_by_tests` | True if any test module statically imports this module |
| `test_reference_count` | Count of test modules importing this module |
| `workflow_refs` | Direct workflow YAML references (python file or -m invocation) |
| `dynamic_import_indicators` | importlib / __import__ calls detected |
| `execution_refs` | subprocess.run / os.system / Popen calls in this file |
| `reachable_from_supported_static_root` | True if reachable via BFS from a supported root |
| `supported_static_roots` | List of supported roots that can reach this module |
| `disposition` | Always `"UNCLASSIFIED"` in P0.2 |

---

## Supported roots vs. candidate entrypoints

**Supported root** — a module/script with concrete evidence of active use:
- Directly invoked by a current hosted GitHub Actions workflow, OR
- Declared as a `console_scripts` entry point in `setup.py`.

Evidence basis values: `CURRENT_HOSTED_WORKFLOW`, `PACKAGING_ENTRYPOINT`,
`USER_FACING_CLI`.

**Candidate entrypoint** — a module/script that has indicators of being an
entrypoint (main guard, CLI framework, workflow reference) but lacks evidence
of active supported invocation.

If support cannot be proven: module is classified `CANDIDATE`, not `SUPPORTED`.

---

## JSON artifact structure

Top-level keys (alphabetically sorted, canonical JSON):

```json
{
  "schema_version": 1,
  "policy_id": "ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_V1",
  "source_commit": "<40-char SHA>",
  "generator_semantics": { ... },
  "summary": { ... },
  "supported_roots": [ ... ],
  "candidate_entrypoints": [ ... ],
  "python_modules": [ ... ],
  "static_import_edges": [ ... ],
  "workflow_inventory": [ ... ],
  "workflow_references": [ ... ],
  "dynamic_import_indicators": [ ... ],
  "execution_indicators": [ ... ],
  "authority_families": [ ... ],
  "diagnostics": [ ... ]
}
```

All lists are sorted deterministically. All maps have sorted keys.

---

## Security and side-effect guarantees

The inventory tool is **read-only** with respect to ATHENA runtime state. It:

- Does NOT import repository business modules.
- Does NOT run provider code.
- Does NOT make network requests.
- Does NOT read secrets, cookies, or wallet data.
- Does NOT create SportyBet codes.
- Does NOT invoke Current Shadow.
- Does NOT execute build_acca, PredictionService, or any analysis pipeline.
- Does NOT write database rows.
- Does NOT modify `.cache/athena-research`.
- Does NOT run arbitrary workflow commands.

Analysis is AST/text/Git only. Output is written only to the specified
`--json-output` and `--csv-output` paths.
