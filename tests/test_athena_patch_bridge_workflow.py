from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "athena-patch-bridge.yml"


def _text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_patch_bridge_workflow_parses_as_yaml() -> None:
    parsed = yaml.safe_load(_text())
    assert isinstance(parsed, dict)
    assert parsed["name"] == "ATHENA Patch Bridge"
    assert set(parsed["jobs"]) == {"validate", "commit"}


def test_patch_bridge_keeps_fail_closed_patch_and_path_guards() -> None:
    text = _text()
    required = (
        "Patch Bridge only accepts same-repository pull requests.",
        "Patch Bridge only writes to draft pull requests.",
        "Stale patch: base-sha=",
        "Patch SHA-256 mismatch",
        "git apply --check --whitespace=error-all athena.patch",
        "Patch Bridge cannot modify GitHub workflows",
        "Changed path is outside the allowlist",
        "Binary patches are forbidden",
        "Pull-request head changed after validation.",
        "Validated patch artifact SHA-256 mismatch",
    )
    for marker in required:
        assert marker in text


def test_patch_bridge_uses_bounded_pre_push_validation_not_monolithic_suite() -> None:
    text = _text()

    assert "python -m pytest tests -q" not in text
    assert "Run bounded pre-push validation" in text
    assert "python -m compileall -q" in text
    assert "git diff --check HEAD^ HEAD" in text
    assert "mapfile -t changed_tests" in text
    assert "git diff --name-only HEAD^ HEAD -- tests" in text
    assert "python -m pytest -q --durations=20 \"${changed_tests[@]}\"" in text
    assert (
        "Normal sharded pull-request CI remains the authoritative full-suite gate."
        in text
    )


def test_patch_bridge_has_bounded_job_timeouts() -> None:
    parsed = yaml.safe_load(_text())
    assert parsed["jobs"]["validate"]["timeout-minutes"] == 10
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
