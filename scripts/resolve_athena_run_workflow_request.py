"""Resolve and persist one GitHub event into exact canonical request bytes."""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Mapping

from domain.run_contracts import RunRequest, canonical_json_bytes
from services.athena_run_request_parser import CLI_TIMEZONE_ID
from services.athena_run_workflow_request import (
    AthenaRunWorkflowRequestError,
    WORKFLOW_INPUT_NAMES,
    resolve_workflow_request,
)


DEFAULT_OUTPUT_ROOT = Path("artifacts/athena-run-workflow")
REQUEST_FILENAME = "resolved-run-request.json"
METADATA_FILENAME = "workflow-request-resolution.json"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)


def _write_consistent(path: Path, payload: bytes) -> None:
    """Create a file atomically, accepting only an identical existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise AthenaRunWorkflowRequestError(f"refusing to replace contradictory {path.name}")
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not path.is_file() or path.read_bytes() != payload:
                raise AthenaRunWorkflowRequestError(
                    f"refusing to replace concurrently written {path.name}"
                )
    except AthenaRunWorkflowRequestError:
        raise
    except OSError as exc:
        raise AthenaRunWorkflowRequestError(f"could not persist {path.name}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _validate_github_identity(github_sha: str, github_ref: str) -> None:
    if type(github_sha) is not str or _GIT_SHA_RE.fullmatch(github_sha) is None:
        raise AthenaRunWorkflowRequestError("GITHUB_SHA must be exact lowercase 40-character SHA")
    if type(github_ref) is not str or not github_ref or github_ref != github_ref.strip():
        raise AthenaRunWorkflowRequestError("GITHUB_REF must be exact non-empty text")


def resolve_and_persist(
    *,
    event_name: str,
    dispatch_inputs: Mapping[str, str] | None,
    github_sha: str,
    github_ref: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    github_output_path: Path | None = None,
    now: datetime | None = None,
) -> tuple[RunRequest, dict[str, object]]:
    """Resolve once, then immediately persist request and non-secret metadata."""

    _validate_github_identity(github_sha, github_ref)
    if not isinstance(output_root, Path):
        raise AthenaRunWorkflowRequestError("output_root must be pathlib.Path")
    request = resolve_workflow_request(
        event_name=event_name,
        dispatch_inputs=dispatch_inputs,
        now=now,
    )
    request_bytes = canonical_json_bytes(request)
    request_path = output_root / REQUEST_FILENAME
    metadata_path = output_root / METADATA_FILENAME
    metadata: dict[str, object] = {
        "github_event_name": event_name,
        "exact_github_sha": github_sha,
        "exact_github_ref": github_ref,
        "request_canonical_sha256": request.canonical_sha256,
        "dates": [day.isoformat() for day in request.dates],
        "authority_profile": request.authority_profile,
        "mode": request.mode,
        "bookie": request.bookie,
        "create_share_code": request.create_share_code,
        "place_wager": False,
        "timezone": CLI_TIMEZONE_ID,
    }
    _write_consistent(request_path, request_bytes)
    _write_consistent(metadata_path, canonical_json_bytes(metadata))

    if github_output_path is not None:
        github_output_path.parent.mkdir(parents=True, exist_ok=True)
        outputs = (
            ("request_sha256", request.canonical_sha256),
            ("authority_profile", request.authority_profile),
            ("mode", request.mode),
            ("bookie", request.bookie),
            ("create_share_code", str(request.create_share_code).lower()),
        )
        with github_output_path.open("a", encoding="utf-8", newline="\n") as stream:
            for key, value in outputs:
                stream.write(f"{key}={value}\n")
    return request, metadata


def _environment_dispatch_inputs(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        "days": environment.get("INPUT_DAYS", ""),
        "target_legs": environment.get("INPUT_TARGET_LEGS", ""),
        "target_total_odds": environment.get("INPUT_TARGET_TOTAL_ODDS", ""),
        "bookie": environment.get("INPUT_BOOKIE", ""),
        "profile": environment.get("INPUT_PROFILE", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    environment = os.environ
    event_name = environment.get("GITHUB_EVENT_NAME", "")
    dispatch = _environment_dispatch_inputs(environment) if event_name == "workflow_dispatch" else None
    output_value = environment.get("GITHUB_OUTPUT")
    try:
        request, metadata = resolve_and_persist(
            event_name=event_name,
            dispatch_inputs=dispatch,
            github_sha=environment.get("GITHUB_SHA", ""),
            github_ref=environment.get("GITHUB_REF", ""),
            output_root=args.output_root,
            github_output_path=Path(output_value) if output_value else None,
        )
    except (AthenaRunWorkflowRequestError, OSError) as exc:
        print(f"ATHENA workflow request resolution failed: {exc}", file=sys.stderr)
        return 2
    print(
        "Resolved and persisted canonical RunRequest "
        f"{request.canonical_sha256} for {metadata['authority_profile']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
