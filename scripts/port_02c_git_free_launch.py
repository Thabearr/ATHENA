"""Build/qualification launcher only; the frozen runtime never invokes Python."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess


def sanitized_git_free_path(value: str) -> str:
    """Exclude entries that actually resolve Git, not entries named 'git'."""
    kept = []
    for entry in value.split(os.pathsep):
        if not entry:
            continue  # Empty entries confer current-directory executable lookup.
        directory = Path(entry)
        names = {"git", "git.exe", "git.cmd", "git.bat"}
        names.update("git" + ext.lower() for ext in os.environ.get("PATHEXT", "").split(os.pathsep) if ext)
        if shutil.which("git", path=entry) is not None or any((directory / name).is_file() for name in names):
            continue
        kept.append(entry)
    result = os.pathsep.join(kept)
    if shutil.which("git", path=result) is not None:
        raise ValueError("Git still resolves from sanitized PATH")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch frozen qualifier with Git absent from PATH")
    parser.add_argument("executable")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    env = dict(os.environ)
    env["NoDefaultCurrentDirectoryInExePath"] = "1"
    env["PATH"] = sanitized_git_free_path(env.get("PATH", ""))
    return subprocess.run([args.executable, *args.arguments], env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
