"""Observe the native test volume, execute four offline cases, then seal evidence."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

POLICY = "ATHENA_DATA_01C_NATIVE_RESTORE_PORTABILITY_QUALIFICATION_V1"
TEST_FILE = "tests/native/test_data_01c_bundle_migrations.py"
NODEIDS = [TEST_FILE + "::test_cross_process_app_root_lock_excludes_a_second_writer",
           TEST_FILE + "::test_native_same_volume_switch_recovers_each_crash_marker"]
PHASES = ["JOURNAL_PREPARED", "OLD_ROOT_PRESERVED", "NEW_ROOT_ACTIVE"]
CASES = [NODEIDS[0], *(NODEIDS[1] + "[" + phase + "]" for phase in PHASES)]


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def observe_volume(path):
    path = Path(path).resolve(strict=True)
    host = platform.system()
    if host == "Windows":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        volume = ctypes.create_unicode_buffer(32768)
        get_path = kernel.GetVolumePathNameW
        get_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        get_path.restype = ctypes.c_int
        if not get_path(str(path), volume, len(volume)):
            raise ctypes.WinError(ctypes.get_last_error())
        fs = ctypes.create_unicode_buffer(256)
        info = kernel.GetVolumeInformationW
        info.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32,
                         ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                         ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p, ctypes.c_uint32]
        info.restype = ctypes.c_int
        if not info(volume.value, None, 0, None, None, None, fs, len(fs)):
            raise ctypes.WinError(ctypes.get_last_error())
        filesystem = fs.value
        observation = "WIN32_GET_VOLUME_PATH_NAME_AND_GET_VOLUME_INFORMATION"
        host_version = platform.version()
    elif host == "Linux":
        release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines()
                       if "=" in line)
        if release.get("ID", "").strip('"') != "ubuntu" or release.get("VERSION_ID", "").strip('"') != "24.04":
            raise ValueError("qualification requires native Ubuntu 24.04")
        filesystem = subprocess.check_output(
            ["findmnt", "--noheadings", "--output", "FSTYPE", "--target", str(path)],
            text=True).strip()
        observation = "FINDMNT_TARGET_TEST_BASETEMP"
        host_version = release["PRETTY_NAME"].strip('"')
    else:
        raise ValueError("unsupported native qualification OS")
    expected = {"Windows": "NTFS", "Linux": "ext4"}[host]
    if filesystem != expected:
        raise ValueError("observed test filesystem is not " + expected + ": " + filesystem)
    return {"host_os": host, "host_os_version": host_version,
            "filesystem_type": filesystem, "filesystem_observation": observation}


def validate_receipt(value, expected_head, *, require_natural=True):
    keys = {"schema_version", "policy_id", "host_os", "host_os_version", "filesystem_type",
            "filesystem_observation", "python_version", "final_pr_head", "checkout_sha",
            "event_name", "run_id", "run_attempt", "pytest_nodeids", "passed_nodeids",
            "crash_phases", "pytest_exit_code", "cross_process_lock_tested",
            "same_volume_switch_tested", "network_calls", "provider_calls", "delivery_calls",
            "wager_actions", "canonical_sha256"}
    if type(value) is not dict or set(value) != keys:
        raise ValueError("qualification receipt has unexpected or missing fields")
    body = {k: v for k, v in value.items() if k != "canonical_sha256"}
    if value.get("canonical_sha256") != hashlib.sha256(canonical(body)).hexdigest():
        raise ValueError("qualification receipt seal mismatch")
    expected_fs = {"Windows": "NTFS", "Linux": "ext4"}
    expected_observation = {"Windows": "WIN32_GET_VOLUME_PATH_NAME_AND_GET_VOLUME_INFORMATION",
                            "Linux": "FINDMNT_TARGET_TEST_BASETEMP"}
    host = value.get("host_os")
    if (value.get("policy_id") != POLICY or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("final_pr_head") != expected_head
            or host not in expected_fs or value.get("filesystem_type") != expected_fs[host]
            or value.get("filesystem_observation") != expected_observation[host]
            or value.get("pytest_nodeids") != NODEIDS or value.get("passed_nodeids") != CASES
            or value.get("crash_phases") != PHASES or value.get("pytest_exit_code") != 0
            or value.get("cross_process_lock_tested") is not True
            or value.get("same_volume_switch_tested") is not True
            or value.get("event_name") not in ("pull_request", "workflow_dispatch")
            or (require_natural and value.get("event_name") != "pull_request")
            or type(value.get("run_id")) is not int or value["run_id"] < 1
            or type(value.get("run_attempt")) is not int or value["run_attempt"] < 1
            or (require_natural and value["run_attempt"] != 1)
            or not value.get("host_os_version") or not value.get("python_version")
            or type(value.get("pytest_exit_code")) is not int
            or any(type(value.get(k)) is not int or value[k] != 0 for k in
                   ("network_calls", "provider_calls", "delivery_calls", "wager_actions"))):
        raise ValueError("native qualification evidence is incomplete or mismatched")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", required=True)
    args = parser.parse_args()
    runner_temp = Path(args.runner_temp).resolve(strict=True)
    test_root = runner_temp / "data01c-native-restore-tests"
    output = runner_temp / "data01c-restore-portability.json"
    if output.exists() or test_root.exists():
        raise ValueError("qualification refuses an existing receipt or test generation")
    head = os.environ["D5_PR_HEAD"]
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("missing exact PR source head")
    observed = observe_volume(runner_temp)
    junit = runner_temp / "data01c-restore-portability.junit.xml"
    command = [sys.executable, "-m", "pytest", "-q", "-rA", *NODEIDS,
               "--basetemp=" + str(test_root), "--junitxml=" + str(junit)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    # JUnit independently identifies every executed parametrization. A green
    # exit alone cannot manufacture evidence for absent or skipped cases.
    cases = list(ET.parse(junit).iter("testcase"))
    expected_names = [node.rsplit("::", 1)[-1] for node in CASES]
    if len(cases) != 4 or sorted(case.get("name") for case in cases) != sorted(expected_names) or any(list(case) for case in cases):
        raise ValueError("pytest did not pass the exact four required native cases")
    if observe_volume(test_root) != observed:
        raise ValueError("test data root filesystem differs from the observed runner temp")
    value = {"schema_version": 1, "policy_id": POLICY, **observed,
             "python_version": platform.python_version(), "final_pr_head": head,
             "checkout_sha": os.environ["GITHUB_SHA"],
             "event_name": os.environ["GITHUB_EVENT_NAME"],
             "run_id": int(os.environ["GITHUB_RUN_ID"]),
             "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
             "pytest_nodeids": NODEIDS, "passed_nodeids": CASES, "crash_phases": PHASES,
             "pytest_exit_code": result.returncode, "cross_process_lock_tested": True,
             "same_volume_switch_tested": True,
             "network_calls": 0, "provider_calls": 0, "delivery_calls": 0, "wager_actions": 0}
    value["canonical_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    validate_receipt(value, head, require_natural=False)
    with output.open("xb") as stream:
        stream.write(canonical(value))
    print(canonical(value).decode(), end="")


if __name__ == "__main__":
    main()
