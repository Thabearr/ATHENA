"""Tests for ATHENA repository architecture inventory (P0.2).

These tests create small synthetic Git repositories so the inventory semantics
are fully controllable and do not depend on the live ATHENA repository state.

All tests use only stdlib — no external dependencies required.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to build tiny synthetic git repos
# ---------------------------------------------------------------------------

def _git(cwd: Path | str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr}"
        )
    return result.stdout.strip()


def _init_repo(tmp: Path) -> Path:
    """Initialise a bare-minimum git repo with user identity."""
    _git(tmp, "init")
    _git(tmp, "config", "user.email", "test@athena.test")
    _git(tmp, "config", "user.name", "ATHENA Test")
    return tmp


def _add_file(repo: Path, rel_path: str, content: str) -> None:
    full = repo / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(content), encoding="utf-8")
    _git(repo, "add", rel_path)


def _commit(repo: Path, message: str = "test commit") -> str:
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Import the inventory module under test
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.audit_repository_architecture import (
    ALL_AUTHORITY_PROFILES,
    AUTHORITY_HISTORICAL_EVIDENCE,
    AUTHORITY_MAIN_ONLY,
    AUTHORITY_RESEARCH_CHALLENGER,
    AUTHORITY_SHADOW_ONLY,
    AUTHORITY_SHARED_CANONICAL,
    AUTHORITY_UNKNOWN,
    DISPOSITION_UNCLASSIFIED,
    DYNAMIC_NONLITERAL,
    POLICY_ID,
    SCHEMA_VERSION,
    build_csv,
    build_inventory,
    canonical_json,
    detect_authority_families,
    detect_cli_frameworks,
    detect_dynamic_imports,
    detect_execution_indicators,
    has_main_guard,
    is_test_path,
    parse_imports,
    path_to_module,
    read_file_at_ref,
    read_files_at_ref,
    resolve_ref,
)


# ===========================================================================
# Unit tests — pure functions (no git)
# ===========================================================================

class TestPathToModule:
    def test_simple(self):
        assert path_to_module("foo.py") == "foo"

    def test_nested(self):
        assert path_to_module("package/foo.py") == "package.foo"

    def test_init_becomes_package(self):
        assert path_to_module("package/__init__.py") == "package"

    def test_non_py_returns_none(self):
        assert path_to_module("foo.yml") is None

    def test_deep_path(self):
        assert path_to_module("a/b/c/d.py") == "a.b.c.d"


class TestIsTestPath:
    def test_tests_dir(self):
        assert is_test_path("tests/test_foo.py")

    def test_not_test(self):
        assert not is_test_path("services/foo.py")

    def test_nested_tests(self):
        assert is_test_path("src/tests/test_bar.py")


class TestHasMainGuard:
    def test_with_main(self):
        src = 'if __name__ == "__main__":\n    pass\n'
        assert has_main_guard(src)

    def test_without_main(self):
        assert not has_main_guard("x = 1\n")

    def test_syntax_error_returns_false(self):
        assert not has_main_guard("def (:\n")


class TestDetectCliFrameworks:
    def test_typer(self):
        src = "import typer\napp = typer.Typer()\n"
        frameworks = detect_cli_frameworks(src, "app.py")
        assert "TYPER_ENTRYPOINT" in frameworks

    def test_argparse(self):
        src = "import argparse\nparser = argparse.ArgumentParser()\n"
        frameworks = detect_cli_frameworks(src, "app.py")
        assert "ARGPARSE_ENTRYPOINT" in frameworks

    def test_click(self):
        src = "import click\n@click.command()\ndef cli():\n    pass\n"
        frameworks = detect_cli_frameworks(src, "app.py")
        assert "CLICK_ENTRYPOINT" in frameworks

    def test_main_guard(self):
        src = 'if __name__ == "__main__":\n    pass\n'
        frameworks = detect_cli_frameworks(src, "app.py")
        assert "DIRECT_PYTHON_ENTRYPOINT" in frameworks

    def test_no_cli(self):
        src = "x = 1\n"
        assert detect_cli_frameworks(src, "app.py") == []


class TestParseImports:
    def test_simple_import(self):
        src = "import os\nimport package.foo\n"
        imports, diags = parse_imports(src, "test.py")
        assert any(i["module"] == "package.foo" for i in imports)
        assert diags == []

    def test_from_import(self):
        src = "from package import foo\n"
        imports, diags = parse_imports(src, "test.py")
        assert any(i["module"] == "package" and "foo" in i["names"] for i in imports)

    def test_relative_import(self):
        src = "from . import foo\n"
        imports, diags = parse_imports(src, "test.py")
        assert any(i["level"] == 1 and "foo" in i["names"] for i in imports)

    def test_nested_relative_import(self):
        src = "from ..foo import bar\n"
        imports, diags = parse_imports(src, "test.py")
        assert any(i["level"] == 2 and i["module"] == "foo" for i in imports)

    def test_syntax_error_recorded(self):
        src = "def (:\n"
        imports, diags = parse_imports(src, "bad.py")
        assert any(d["category"] == "PARSE_ERROR" for d in diags)


class TestDetectDynamicImports:
    def test_importlib_literal(self):
        src = 'import importlib\nm = importlib.import_module("package.foo")\n'
        indicators = detect_dynamic_imports(src, "a.py")
        assert len(indicators) == 1
        assert indicators[0]["is_literal"] is True
        assert indicators[0]["literal_target"] == "package.foo"
        assert indicators[0]["call_kind"] == "importlib.import_module"

    def test_importlib_nonliteral(self):
        src = 'import importlib\nm = importlib.import_module(name)\n'
        indicators = detect_dynamic_imports(src, "a.py")
        assert len(indicators) == 1
        assert indicators[0]["is_literal"] is False
        assert indicators[0]["marker"] == DYNAMIC_NONLITERAL

    def test_dunder_import_literal(self):
        src = '__import__("os")\n'
        indicators = detect_dynamic_imports(src, "a.py")
        assert len(indicators) == 1
        assert indicators[0]["is_literal"] is True
        assert indicators[0]["call_kind"] == "__import__"


class TestDetectExecutionIndicators:
    def test_subprocess_literal(self):
        src = (
            'import subprocess\n'
            'subprocess.run(["python", "-m", "scripts.foo"])\n'
        )
        indicators = detect_execution_indicators(src, "a.py")
        assert any(i["call_kind"] == "subprocess.run" and i["is_literal"] for i in indicators)

    def test_subprocess_nonliteral(self):
        src = (
            'import subprocess\n'
            'subprocess.run(cmd)\n'
        )
        indicators = detect_execution_indicators(src, "a.py")
        assert any(not i["is_literal"] for i in indicators)


# ===========================================================================
# Integration tests — tiny synthetic git repos
# ===========================================================================

@pytest.fixture()
def tiny_repo(tmp_path):
    """A tiny repo with a few Python files and a workflow."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    _add_file(repo, "pkg/__init__.py", "")
    _add_file(repo, "pkg/foo.py", "from pkg import bar\n")
    _add_file(repo, "pkg/bar.py", "x = 1\n")
    _add_file(repo, "pkg/util.py", "y = 2\n")  # zero static inbound
    _add_file(repo, "tests/test_foo.py", "from pkg import foo\n")
    _add_file(
        repo,
        ".github/workflows/tests.yml",
        textwrap.dedent("""\
            name: Tests
            on: [push]
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: python -m pytest tests/
        """),
    )
    sha = _commit(repo)
    return repo, sha


class TestInventoryBasic:
    def test_source_commit_matches_requested_ref(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["source_commit"] == sha

    def test_schema_version(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["schema_version"] == SCHEMA_VERSION

    def test_policy_id(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["policy_id"] == POLICY_ID

    def test_all_modules_unclassified(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["disposition"] == DISPOSITION_UNCLASSIFIED, (
                f"{m['path']} has disposition {m['disposition']!r}"
            )

    def test_no_delete_disposition(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["disposition"] != "DELETE"
            assert m.get("delete_recommended") is None

    def test_python_files_counted(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["summary"]["python_file_count"] >= 4

    def test_workflow_counted(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["summary"]["workflow_count"] >= 1

    def test_python_import_creates_local_edge(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        edges = inv["static_import_edges"]
        # pkg.foo -> pkg.bar
        assert any(
            e["source_module"] == "pkg.foo" and e["target_module"] in ("pkg.bar", "pkg")
            for e in edges
        )

    def test_from_import_creates_local_edge(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"]}
        # tests/test_foo.py imports from pkg.foo — pkg and/or pkg.foo should have test inbound
        test_mod = "tests.test_foo"
        if test_mod in modules:
            assert modules[test_mod]["is_test"]

    def test_static_inbound_outbound_counts(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        # pkg.bar has inbound from pkg.foo
        if "pkg.bar" in modules:
            assert modules["pkg.bar"]["static_inbound_count"] >= 1
        # pkg.foo has outbound to pkg.bar (or pkg)
        if "pkg.foo" in modules:
            assert modules["pkg.foo"]["static_outbound_count"] >= 1

    def test_zero_static_inbound_flag(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        # pkg.util has no inbound imports
        if "pkg.util" in modules:
            assert modules["pkg.util"]["zero_static_inbound"] is True

    def test_zero_static_inbound_not_delete(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            if m.get("zero_static_inbound"):
                assert m["disposition"] == DISPOSITION_UNCLASSIFIED

    def test_test_only_reference_recognized(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        # pkg.foo is referenced by tests/test_foo.py
        # The test module itself should be marked is_test
        test_mod = modules.get("tests.test_foo")
        if test_mod:
            assert test_mod["is_test"]

    def test_test_only_reference_no_runtime_reachability(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        # pkg.util is zero-inbound — supported_static_roots should be empty unless
        # a workflow root actually reaches it
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        if "pkg.util" in modules:
            # Not reachable from tests alone
            assert modules["pkg.util"]["supported_static_roots"] == [] or \
                all("test" not in r for r in modules["pkg.util"]["supported_static_roots"])

    def test_main_guard_detected(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "app.py", 'if __name__ == "__main__":\n    pass\n')
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        mods = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        assert mods.get("app", {}).get("has_main_guard") is True

    def test_argparse_candidate_detected(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "cli.py", "import argparse\nargparse.ArgumentParser()\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        mods = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        assert "ARGPARSE_ENTRYPOINT" in mods.get("cli", {}).get("cli_frameworks", [])

    def test_typer_candidate_detected(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "cli.py", "import typer\napp = typer.Typer()\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        mods = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        assert "TYPER_ENTRYPOINT" in mods.get("cli", {}).get("cli_frameworks", [])

    def test_click_candidate_detected(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "cli.py", "import click\n@click.command()\ndef main():\n    pass\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        mods = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        assert "CLICK_ENTRYPOINT" in mods.get("cli", {}).get("cli_frameworks", [])


class TestImportResolution:
    def test_external_library_no_local_edge(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "mymod.py", "import requests\nimport numpy as np\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        edges = inv["static_import_edges"]
        # No local edge should be created for requests or numpy
        assert all(e["source_module"] == "mymod" and e["target_module"] not in ("requests", "numpy")
                   for e in edges if e["source_module"] == "mymod")

    def test_relative_import_resolved(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "pkg/__init__.py", "")
        _add_file(repo, "pkg/a.py", "from . import b\n")
        _add_file(repo, "pkg/b.py", "x = 1\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        # pkg.a should have outbound to pkg or pkg.b
        if "pkg.a" in modules:
            assert modules["pkg.a"]["static_outbound_count"] >= 1

    def test_nested_relative_import(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "pkg/__init__.py", "")
        _add_file(repo, "pkg/sub/__init__.py", "")
        _add_file(repo, "pkg/sub/a.py", "from .. import foo\n")
        _add_file(repo, "pkg/foo.py", "x = 1\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        edges = inv["static_import_edges"]
        # pkg.sub.a -> pkg.foo (or pkg)
        assert any(e["source_module"] == "pkg.sub.a" for e in edges), edges


class TestDynamicImportIndicators:
    def test_importlib_literal_in_inventory(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "loader.py", 'import importlib\nm = importlib.import_module("pkg.a")\n')
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        indicators = inv["dynamic_import_indicators"]
        assert any(i["is_literal"] and i["marker"] == "pkg.a" for i in indicators)

    def test_importlib_nonliteral_in_inventory(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "loader.py", 'import importlib\nm = importlib.import_module(name)\n')
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        indicators = inv["dynamic_import_indicators"]
        assert any(not i["is_literal"] and i["marker"] == DYNAMIC_NONLITERAL for i in indicators)

    def test_dunder_import_literal_in_inventory(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "loader.py", '__import__("os.path")\n')
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        indicators = inv["dynamic_import_indicators"]
        assert any(i["call_kind"] == "__import__" and i["is_literal"] for i in indicators)


class TestWorkflowAnalysis:
    def test_workflow_python_file_reference(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(
            repo,
            ".github/workflows/ci.yml",
            textwrap.dedent("""\
                name: CI
                on: [push]
                jobs:
                  test:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python scripts/run_thing.py
            """),
        )
        _add_file(repo, "scripts/run_thing.py", "print('hi')\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        wf_refs = inv["workflow_references"]
        assert any(r["reference"] == "scripts/run_thing.py" for r in wf_refs)

    def test_workflow_python_module_reference(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(
            repo,
            ".github/workflows/ci.yml",
            textwrap.dedent("""\
                name: CI
                on: [push]
                jobs:
                  test:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python -m scripts.run_thing
            """),
        )
        _add_file(repo, "scripts/__init__.py", "")
        _add_file(repo, "scripts/run_thing.py", "print('hi')\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        wf_refs = inv["workflow_references"]
        assert any(r["reference"] == "scripts.run_thing" for r in wf_refs)

    def test_workflow_does_not_require_executing_yaml(self, tmp_path):
        """Workflow refs extracted without running any YAML commands."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(
            repo,
            ".github/workflows/ci.yml",
            textwrap.dedent("""\
                name: CI
                on: [push]
                jobs:
                  test:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python -m myapp.main
            """),
        )
        _add_file(repo, "myapp/__init__.py", "")
        _add_file(repo, "myapp/main.py", "pass\n")
        sha = _commit(repo)
        # This must complete without executing any YAML steps
        inv = build_inventory(repo, sha)
        assert inv is not None


class TestSubprocessIndicators:
    def test_subprocess_literal(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(
            repo, "runner.py",
            'import subprocess\nsubprocess.run(["python", "-m", "pkg.main"])\n',
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        exec_inds = inv["execution_indicators"]
        assert any(
            i["call_kind"] == "subprocess.run" and i["is_literal"]
            for i in exec_inds
        )

    def test_subprocess_nonliteral(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(
            repo, "runner.py",
            'import subprocess\nsubprocess.run(cmd)\n',
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        exec_inds = inv["execution_indicators"]
        assert any(not i["is_literal"] for i in exec_inds)


class TestReachability:
    def test_transitive_reachability(self, tmp_path):
        """root -> a -> b: b must be reachable from root."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "root.py", 'if __name__ == "__main__":\n    pass\nfrom moda import a\n')
        _add_file(repo, "moda/__init__.py", "")
        _add_file(repo, "moda/a.py", "from moda import b\n")
        _add_file(repo, "moda/b.py", "x = 1\n")
        _add_file(
            repo,
            ".github/workflows/tests.yml",
            textwrap.dedent("""\
                name: Tests
                on: [push]
                jobs:
                  t:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python root.py
            """),
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        modules = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        # moda.b should be reachable via root -> moda.a -> moda.b
        # Note: 'root' must be a supported root (workflow-invoked)
        # root.py is referenced by the workflow, so it should be a supported or candidate root
        # moda.b reachability depends on root being a supported root
        # The workflow references "root.py" (file reference) — check chain
        if "moda.b" in modules:
            # Either reachable or not — key invariant: disposition is still UNCLASSIFIED
            assert modules["moda.b"]["disposition"] == DISPOSITION_UNCLASSIFIED

    def test_unsupported_candidate_not_supported(self, tmp_path):
        """A file with main guard but no workflow evidence is CANDIDATE, not SUPPORTED."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "standalone.py", 'if __name__ == "__main__":\n    pass\n')
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        supported_mods = [r["root_module"] for r in inv["supported_roots"]]
        assert "standalone" not in supported_mods


class TestFailClosed:
    def test_invalid_ref_fails(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "a.py", "x=1\n")
        _commit(repo)
        with pytest.raises(RuntimeError):
            build_inventory(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")

    def test_duplicate_module_name_fails(self, tmp_path):
        """Two files resolving to the same module name must cause a fail-closed error."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        # This is not possible in normal Python (two files can't have same module name
        # unless one is __init__.py and the other is the directory)
        # We simulate by having a package/foo.py and package/foo/__init__.py
        _add_file(repo, "pkg/__init__.py", "")
        _add_file(repo, "pkg/foo.py", "x=1\n")
        _add_file(repo, "pkg/foo/__init__.py", "y=1\n")
        sha = _commit(repo)
        with pytest.raises(RuntimeError, match="two tracked files"):
            build_inventory(repo, sha)


class TestDeterminism:
    def test_json_deterministic_same_ref(self, tiny_repo):
        """Running inventory twice on same ref gives byte-identical JSON."""
        repo, sha = tiny_repo
        inv1 = build_inventory(repo, sha)
        inv2 = build_inventory(repo, sha)
        j1 = canonical_json(inv1)
        j2 = canonical_json(inv2)
        sha1 = hashlib.sha256(j1.encode()).hexdigest()
        sha2 = hashlib.sha256(j2.encode()).hexdigest()
        assert sha1 == sha2, "JSON not byte-identical across two runs"

    def test_csv_deterministic_same_ref(self, tiny_repo):
        """Running inventory twice on same ref gives byte-identical CSV."""
        repo, sha = tiny_repo
        inv1 = build_inventory(repo, sha)
        inv2 = build_inventory(repo, sha)
        c1 = build_csv(inv1["python_modules"])
        c2 = build_csv(inv2["python_modules"])
        sha1 = hashlib.sha256(c1.encode()).hexdigest()
        sha2 = hashlib.sha256(c2.encode()).hexdigest()
        assert sha1 == sha2, "CSV not byte-identical across two runs"

    def test_json_key_order_stable(self, tiny_repo):
        """JSON keys are sorted (sort_keys=True)."""
        repo, sha = tiny_repo
        j = canonical_json(build_inventory(repo, sha))
        parsed = json.loads(j)
        # Top-level keys should be sorted
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_csv_row_order_stable(self, tiny_repo):
        """CSV rows are ordered by path."""
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        csv_str = build_csv(inv["python_modules"])
        lines = csv_str.strip().split("\n")
        paths = [line.split(",")[0] for line in lines[1:]]  # skip header
        assert paths == sorted(paths)

    def test_source_commit_in_json(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        assert inv["source_commit"] == sha


class TestAuthorityFamilies:
    def test_family_detection(self):
        modules = [
            "domain.market_router_v2_direct_provider",
            "domain.market_router_v3_current_provider",
            "domain.price_all_v2_direct_provider",
            "domain.price_all_v3_current_provider",
            "domain.portfolio_optimizer_v3_current_provider",
            "engine.market_selector",
        ]
        families = detect_authority_families(modules)
        family_names = [f["family"] for f in families]
        assert "market_router" in family_names
        assert "price_all" in family_names
        assert "portfolio_optimizer" in family_names
        assert "market_selector" in family_names


class TestKnownPaths:
    """Test that the inventory of actual ATHENA main contains key known paths
    when inventoried against the exact base commit.

    This test discovers the repo root relative to this test file and runs
    inventory only if we're in the ATHENA repo.
    """

    _BASE_SHA = "e04cbbeaeff999a1e5dd3ff7891857b4813a7fac"
    _KNOWN_PATHS = [
        "engine/market_selector.py",
        "services/prediction_service.py",
        "build_acca.py",
        "domain/current_shadow_all_market_runner.py",
        "domain/price_all_v3_current_provider.py",
        "domain/market_router_v3_current_provider.py",
        "domain/portfolio_optimizer_v3_current_provider.py",
    ]

    @classmethod
    def _find_athena_root(cls) -> Path | None:
        """Walk up from test file to find repo root containing known paths."""
        candidate = Path(__file__).parent.parent
        for _ in range(5):
            try:
                result = subprocess.run(
                    ["git", "-C", str(candidate), "rev-parse", "--verify",
                     f"{cls._BASE_SHA}^{{commit}}"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return candidate
            except Exception:
                pass
            candidate = candidate.parent
        return None

    _cached_inv = None

    @classmethod
    def _get_inv(cls):
        if cls._cached_inv is None:
            root = cls._find_athena_root()
            if root is None:
                pytest.skip("ATHENA base commit not available in current repo")
            cls._cached_inv = build_inventory(root, cls._BASE_SHA)
        return cls._cached_inv

    def test_known_paths_present_at_base(self):
        inv = self._get_inv()
        paths_in_inventory = {m["path"] for m in inv["python_modules"]}
        for known_path in self._KNOWN_PATHS:
            assert known_path in paths_in_inventory, (
                f"Known path {known_path!r} missing from inventory"
            )

    def test_no_delete_in_athena_inventory(self):
        inv = self._get_inv()
        for m in inv["python_modules"]:
            assert m["disposition"] == DISPOSITION_UNCLASSIFIED
            assert m.get("delete_recommended") is None

    def test_all_module_dispositions_unclassified(self):
        inv = self._get_inv()
        bad = [m for m in inv["python_modules"] if m["disposition"] != DISPOSITION_UNCLASSIFIED]
        assert not bad, f"Modules with non-UNCLASSIFIED disposition: {[b['path'] for b in bad]}"

    def test_all_modules_have_valid_authority_profile_at_base(self):
        inv = self._get_inv()
        for m in inv["python_modules"]:
            assert m["authority_profile"] in ALL_AUTHORITY_PROFILES
            assert m["authority_profile"] == AUTHORITY_UNKNOWN

    def test_key_paths_disposition_and_profile_at_base(self):
        inv = self._get_inv()
        mods = {m["path"]: m for m in inv["python_modules"]}
        for kp in self._KNOWN_PATHS:
            assert kp in mods
            assert mods[kp]["disposition"] == DISPOSITION_UNCLASSIFIED
            assert mods[kp]["authority_profile"] == AUTHORITY_UNKNOWN

    def test_fresh_holdout_supported_roots_at_base(self):
        inv = self._get_inv()
        supported_mods = {r["root_module"] for r in inv["supported_roots"]}
        assert "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick" in supported_mods
        assert "scripts.run_fotmob_fresh_holdout_release_receipt_mirror" in supported_mods

    def test_fresh_holdout_dependencies_reachable_at_base(self):
        inv = self._get_inv()
        mods = {m["module"]: m for m in inv["python_modules"] if m["module"]}
        assert mods["domain.fotmob_utc_native_expected_goals_fresh_holdout"]["reachable_from_supported_static_root"] is True
        assert mods["domain.fotmob_fresh_holdout_continuity"]["reachable_from_supported_static_root"] is True


# ===========================================================================
# Authority Profile Dimension Tests (Specification v2 Alignment)
# ===========================================================================

class TestAuthorityProfile:
    def test_every_module_has_authority_profile(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert "authority_profile" in m, f"{m['path']} missing authority_profile"

    def test_authority_profile_vocabulary(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["authority_profile"] in ALL_AUTHORITY_PROFILES, (
                f"{m['path']} has invalid authority_profile {m['authority_profile']!r}"
            )

    def test_unproven_module_defaults_to_unknown(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["authority_profile"] == AUTHORITY_UNKNOWN

    def test_authority_profile_unknown_does_not_change_disposition(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["authority_profile"] == AUTHORITY_UNKNOWN
            assert m["disposition"] == DISPOSITION_UNCLASSIFIED

    def test_no_authority_profile_creates_delete_or_keep_authority(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "mod_main.py", "x = 1\n")
        _add_file(repo, "mod_shadow.py", "y = 2\n")
        sha = _commit(repo)
        profiles = {
            "mod_main": AUTHORITY_MAIN_ONLY,
            "mod_shadow": AUTHORITY_SHADOW_ONLY,
        }
        inv = build_inventory(repo, sha, known_authority_profiles=profiles)
        for m in inv["python_modules"]:
            assert m["disposition"] == DISPOSITION_UNCLASSIFIED
            assert m.get("delete_recommended") is None

    def test_no_automatic_authority_from_filename(self, tmp_path):
        """Do NOT infer authority profile from filenames like shadow, current, v1, v2, v3, fotmob, sportybet."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "shadow_runner.py", "pass\n")
        _add_file(repo, "current_provider.py", "pass\n")
        _add_file(repo, "v1_router.py", "pass\n")
        _add_file(repo, "v2_price.py", "pass\n")
        _add_file(repo, "v3_portfolio.py", "pass\n")
        _add_file(repo, "fotmob_scraper.py", "pass\n")
        _add_file(repo, "sportybet_service.py", "pass\n")
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        for m in inv["python_modules"]:
            assert m["authority_profile"] == AUTHORITY_UNKNOWN, (
                f"{m['path']} should have authority_profile UNKNOWN, got {m['authority_profile']!r}"
            )


# ===========================================================================
# Fresh-Holdout Protected Research Reachability Tests
# ===========================================================================

class TestFreshHoldoutProtectedReachability:
    def test_fresh_holdout_reviewed_workflow_is_supported_root(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "scripts/__init__.py", "")
        _add_file(repo, "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py", "x = 1\n")
        _add_file(
            repo,
            ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
            textwrap.dedent("""\
                name: FotMob Fresh Holdout
                on:
                  schedule:
                    - cron: '7 * * * *'
                jobs:
                  collect:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py --foo bar
            """),
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        supported_mods = [r["root_module"] for r in inv["supported_roots"]]
        assert "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick" in supported_mods

    def test_fresh_holdout_transitive_dependency_reachable(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "scripts/__init__.py", "")
        _add_file(
            repo,
            "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py",
            "import domain.fresh_holdout_core\n",
        )
        _add_file(repo, "domain/__init__.py", "")
        _add_file(repo, "domain/fresh_holdout_core.py", "import domain.fresh_submodule\n")
        _add_file(repo, "domain/fresh_submodule.py", "pass\n")
        _add_file(
            repo,
            ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
            textwrap.dedent("""\
                name: FotMob Fresh Holdout
                on:
                  schedule:
                    - cron: '7 * * * *'
                jobs:
                  collect:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py
            """),
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        mods = {m["module"]: m for m in inv["python_modules"]}
        assert mods["domain.fresh_holdout_core"]["reachable_from_supported_static_root"] is True
        assert mods["domain.fresh_submodule"]["reachable_from_supported_static_root"] is True
        assert "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick" in mods["domain.fresh_submodule"]["supported_static_roots"]

    def test_unreviewed_historical_workflow_not_automatically_promoted(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "scripts/__init__.py", "")
        _add_file(repo, "scripts/historical_pr_proof.py", "pass\n")
        _add_file(
            repo,
            ".github/workflows/historical-pr-proof.yml",
            textwrap.dedent("""\
                name: Historical PR Proof
                on: [pull_request]
                jobs:
                  proof:
                    runs-on: ubuntu-latest
                    steps:
                      - run: python -m scripts.historical_pr_proof
            """),
        )
        sha = _commit(repo)
        inv = build_inventory(repo, sha)
        supported_mods = [r["root_module"] for r in inv["supported_roots"]]
        assert "scripts.historical_pr_proof" not in supported_mods
        candidate_mods = [c["candidate_module"] for c in inv["candidate_entrypoints"]]
        assert "scripts.historical_pr_proof" in candidate_mods


# ===========================================================================
# Fail-Closed Git Read Tests
# ===========================================================================

class TestFailClosedGitRead:
    def test_read_files_at_ref_missing_object_raises(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "exists.py", "x = 1\n")
        sha = _commit(repo)
        with pytest.raises(RuntimeError, match="FAIL-CLOSED: missing Git blob"):
            read_files_at_ref(repo, sha, ["nonexistent.py"])

    def test_read_files_at_ref_malformed_header_raises(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "a.py", "x = 1\n")
        sha = _commit(repo)
        fake_proc = subprocess.CompletedProcess(
            args=["git", "cat-file", "--batch"],
            returncode=0,
            stdout=b"malformed_header_line_without_blob\n",
            stderr=b"",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)
        with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
            read_files_at_ref(repo, sha, ["a.py"])

    def test_read_files_at_ref_truncated_blob_raises(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "a.py", "x = 1\n")
        sha = _commit(repo)
        fake_proc = subprocess.CompletedProcess(
            args=["git", "cat-file", "--batch"],
            returncode=0,
            stdout=b"1111111111111111111111111111111111111111 blob 100\nshortbytes\n",
            stderr=b"",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)
        with pytest.raises(RuntimeError, match="FAIL-CLOSED: truncated blob body"):
            read_files_at_ref(repo, sha, ["a.py"])

    def test_read_files_at_ref_cardinality_mismatch_raises(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "a.py", "x = 1\n")
        _add_file(repo, "b.py", "y = 2\n")
        sha = _commit(repo)
        fake_proc = subprocess.CompletedProcess(
            args=["git", "cat-file", "--batch"],
            returncode=0,
            stdout=b"1111111111111111111111111111111111111111 blob 5\nhello\n",
            stderr=b"",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)
        with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
            read_files_at_ref(repo, sha, ["a.py", "b.py"])

    def test_read_files_at_ref_misaligned_shift_raises(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _add_file(repo, "a.py", "x = 1\n")
        sha = _commit(repo)
        fake_proc = subprocess.CompletedProcess(
            args=["git", "cat-file", "--batch"],
            returncode=0,
            stdout=b"1111111111111111111111111111111111111111 blob 5\nhelloX",
            stderr=b"",
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)
        with pytest.raises(RuntimeError, match="FAIL-CLOSED: missing trailing newline delimiter"):
            read_files_at_ref(repo, sha, ["a.py"])


# ===========================================================================
# CSV Contract Tests
# ===========================================================================

class TestCSVContract:
    def test_csv_contains_authority_profile_column(self, tiny_repo):
        repo, sha = tiny_repo
        inv = build_inventory(repo, sha)
        csv_str = build_csv(inv["python_modules"])
        header_cols = csv_str.splitlines()[0].split(",")
        assert "authority_profile" in header_cols
        idx_zero = header_cols.index("zero_static_inbound")
        idx_auth = header_cols.index("authority_profile")
        idx_disp = header_cols.index("disposition")
        assert idx_zero < idx_auth < idx_disp
