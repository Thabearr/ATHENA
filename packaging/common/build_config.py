"""Shared PORT-02C native-packaging constants.

Build tooling only. This module is never frozen into an installed executable
and never consulted at installed runtime.
"""
from __future__ import annotations

BUILD_PYTHON = "3.12"
ARCHITECTURE_TAG = "x86_64"
PLATFORM_TAGS = ("windows", "linux")

# Release-manifest closed-world roots staged by the PORT-02C slice builder.
# Minimal slice: only resources the installed qualification proof reads.
# "domain" carries exactly the five staged CANONICAL_COMPONENT_SOURCE files
# required by installed resolve_canonical_core (discovered from the reviewed
# registry at build time, never broad-collected). Qualification-only replay
# bytes live under "qualification/" with their own strict qualification
# manifest, outside these trusted runtime roots.
SLICE_CLOSED_WORLD_ROOTS = ("config", "database/migrations", "domain", "ui")

# Exact allowlisted resource files (repo-relative POSIX paths) staged from
# exact tracked HEAD identities. role is the PORT-02A resource-role vocabulary.
# logical_path == payload_path: the slice preserves repository layout.
SLICE_RESOURCES: tuple[tuple[str, str], ...] = (
    ("config/architecture/component-authority-registry-v1.json", "AUTHORITY_REGISTRY"),
    ("config/architecture/main-shadow-authority-parity-v1.json", "CONFIG"),
    ("config/architecture/architecture-boundary-policy-v1.json", "CONFIG"),
    ("config/release_manifest.schema.json", "SCHEMA"),
    ("config/model_weights.json", "CONFIG"),
    ("database/migrations/002_add_elo_columns.sql", "MIGRATION"),
    ("ui/index.html", "UI"),
    ("ui/app.js", "UI"),
    ("ui/styles.css", "UI"),
)

# Retained P4.4R offline-replay fixtures staged as qualification resources.
# The builder discovers exact files via `git ls-tree` under these prefixes;
# hashes are pinned in the qualification manifest at build time.
QUALIFICATION_FIXTURE_PREFIXES = (
    "tests/fixtures/p4_4r_run_36285099805_quote_evidence",
    "tests/fixtures/p4_4r_pre_fix_quote_context_verifier.py",
)

# Modules that must never be collected into a production executable.
BANNED_FROZEN_MODULES = ("pytest", "_pytest", "tests")

# Expected frozen executable basenames per platform.
SHELL_EXE = {"windows": "athena-shell.exe", "linux": "athena-shell"}
WORKER_EXE = {"windows": "athena-worker.exe", "linux": "athena-worker"}
QUALIFY_EXE = {"windows": "athena-port02c-qualify.exe", "linux": "athena-port02c-qualify"}
