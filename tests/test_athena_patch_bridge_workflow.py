from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "athena-patch-bridge.yml"
DOC_PATH = ROOT / "docs" / "patch_bridge_bounded_validation.md"


def _text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_patch_bridge_workflow_parses_as_yaml() -> None:
    parsed = yaml.safe_load(_text())
    assert isinstance(parsed, dict)
    assert parsed["name"] == "ATHENA Patch Bridge"
    assert set(parsed["jobs"]) == {
        "validate",
        "synthetic_test_shard",
        "synthetic_syntax",
        "commit",
    }


def test_patch_bridge_keeps_fail_closed_patch_path_and_ref_guards() -> None:
    text = _text()
    required = (
        "Patch Bridge only accepts same-repository pull requests.",
        "Patch Bridge only writes to draft pull requests.",
        "GitHub synthetic merge SHA is unavailable.",
        "GitHub synthetic merge parents differ from exact base plus head.",
        "Stale patch: base-sha=",
        "Patch SHA-256 mismatch",
        "git apply --check --whitespace=error-all athena.patch",
        "Patch Bridge cannot modify GitHub workflows",
        "Changed path is outside the allowlist",
        "Binary patches are forbidden",
        "Pull-request head changed after validation.",
        "Pull-request base changed after validation.",
        "Validated patch artifact SHA-256 mismatch",
    )
    for marker in required:
        assert marker in text


def test_patch_bridge_pins_exact_synthetic_merge_parent_pair() -> None:
    text = _text()
    assert "EXPECTED_MERGE_SHA" in text
    assert "const parents = merge.parents.map((parent) => parent.sha);" in text
    assert "parents[0] !== pr.base.sha" in text
    assert "parents[1] !== pr.head.sha" in text
    assert "refs/pull/${{ github.event.issue.number }}/merge" in text
    assert 'test "$(git rev-parse HEAD)" = "${EXPECTED_MERGE_SHA}"' in text


def test_patch_bridge_runs_full_suite_in_eight_parallel_synthetic_shards() -> None:
    parsed = yaml.safe_load(_text())
    text = _text()

    assert "python -m pytest tests -q" not in text
    matrix = parsed["jobs"]["synthetic_test_shard"]["strategy"]["matrix"]
    assert matrix["shard"] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert "files = sorted(Path(\"tests\").rglob(\"test_*.py\"))" in text
    assert "selected = files[shard_number - 1 :: shard_count]" in text
    assert 'python -m pytest -q --durations=20 "${test_files[@]}"' in text
    assert "Validate synthetic Python syntax" in text


def test_patch_bridge_refuses_push_unless_tested_and_pushed_merge_trees_match() -> None:
    text = _text()
    assert "git write-tree" in text
    assert "git merge-tree --write-tree" in text
    assert "EXPECTED_TREE_SHA" in text
    assert 'test "${actual_tree}" = "${EXPECTED_TREE_SHA}"' in text
    commit_needs = yaml.safe_load(_text())["jobs"]["commit"]["needs"]
    assert set(commit_needs) == {
        "validate",
        "synthetic_test_shard",
        "synthetic_syntax",
    }


def test_patch_bridge_has_bounded_job_timeouts() -> None:
    parsed = yaml.safe_load(_text())
    assert parsed["jobs"]["validate"]["timeout-minutes"] == 5
    assert parsed["jobs"]["synthetic_test_shard"]["timeout-minutes"] == 20
    assert parsed["jobs"]["synthetic_syntax"]["timeout-minutes"] == 5
    assert parsed["jobs"]["commit"]["timeout-minutes"] == 5


def test_patch_bridge_external_actions_are_immutable_commit_pins() -> None:
    text = _text()
    pins = {
        "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/github-script": "f28e40c7f34bde8b3046d885e986cb6290c5673b",
        "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
    }
    for action, sha in pins.items():
        assert f"{action}@{sha}" in text
        assert f"{action}@v" not in text


def test_patch_bridge_still_serializes_writes_per_pull_request() -> None:
    text = _text()
    assert "group: athena-patch-${{ github.event.issue.number }}" in text
    assert "cancel-in-progress: false" in text


def test_patch_bridge_does_not_depend_on_post_push_bot_ci_or_comment_receipt() -> None:
    text = _text()
    assert "Report success" not in text
    assert "issues: write" not in text
    docs = DOC_PATH.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in docs
    assert "action_required" in docs
    assert "before the bridge is allowed to push" in docs
