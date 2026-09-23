"""Verify a complete ATHENA ingest artifact without acquiring provider data."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import sys

from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureError, verify_data_matches_capture_directory,
)
from domain.ingest_contracts import (
    AthenaCanonicalStoreUpdate, AthenaIngestContractError, AthenaIngestReceipt,
    AthenaIngestRequest, REPLAY_RECEIPT_POLICY, READY, canonical_json_bytes,
    sha256_bytes, strict_json_loads,
)
from services.athena_ingest_service import (
    RECEIPT_NAME, REPLAY_NAME, REQUEST_NAME, UPDATE_NAME,
    _record_from_capture, _replay_manifest,
)


class AthenaIngestReplayError(RuntimeError):
    """The artifact cannot prove the original canonical update offline."""


def _regular_bytes(root: Path, relative: str) -> bytes:
    if type(relative) is not str or "\\" in relative:
        raise AthenaIngestReplayError("replay path is not POSIX")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or parsed.as_posix() != relative or ".." in parsed.parts:
        raise AthenaIngestReplayError("replay path contains traversal")
    path = root
    for part in parsed.parts:
        path = path / part
        if path.is_symlink():
            raise AthenaIngestReplayError(f"replay path contains symlink: {relative}")
    if not path.is_file():
        raise AthenaIngestReplayError(f"replay file missing: {relative}")
    return path.read_bytes()


def replay_ingest_artifact(artifact_root: Path) -> dict[str, object]:
    root = Path(artifact_root)
    if any(part.is_symlink() for part in (root, *root.parents)) or not root.is_dir():
        raise AthenaIngestReplayError("artifact root must be a regular directory")
    try:
        request_raw = _regular_bytes(root, REQUEST_NAME)
        request = AthenaIngestRequest.from_mapping(strict_json_loads(request_raw))
        if request_raw != request.canonical_bytes:
            raise AthenaIngestReplayError("resolved request is not canonical")
        update_raw = _regular_bytes(root, UPDATE_NAME)
        update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(update_raw))
        receipt_raw = _regular_bytes(root, RECEIPT_NAME)
        receipt = AthenaIngestReceipt.from_mapping(strict_json_loads(receipt_raw))
        manifest_raw = _regular_bytes(root, REPLAY_NAME)
        manifest = strict_json_loads(manifest_raw)
        if type(manifest) is not dict or manifest_raw != canonical_json_bytes(manifest):
            raise AthenaIngestReplayError("replay manifest is not canonical")
        if receipt.status != "SUCCESS" or update.commit_status != READY:
            raise AthenaIngestReplayError("only a complete committed ingest can satisfy replay gate")
        if update.request_sha256 != request.canonical_sha256 or receipt.request_sha256 != request.canonical_sha256:
            raise AthenaIngestReplayError("request identity differs across artifact")
        if receipt.canonical_store_update_sha256 != update.canonical_sha256:
            raise AthenaIngestReplayError("ingest receipt update identity mismatch")
        if update.source_record_count != len(request.dates) or receipt.source_count != len(request.dates):
            raise AthenaIngestReplayError("ingest artifact date coverage incomplete")
        if [item.request_date for item in update.source_records] != list(request.dates):
            raise AthenaIngestReplayError("source dates differ from resolved request")
        if manifest != _replay_manifest(request, update, receipt):
            raise AthenaIngestReplayError("replay manifest identities differ")
        reproduced = []
        for record in update.source_records:
            capture_path = record.capture_relative_path
            raw = _regular_bytes(root, f"{capture_path}/response.json")
            source_manifest = _regular_bytes(root, f"{capture_path}/manifest.json")
            if sha256_bytes(raw) != record.raw_sha256 or sha256_bytes(source_manifest) != record.manifest_sha256:
                raise AthenaIngestReplayError("raw or manifest SHA mismatch")
            verify_data_matches_capture_directory(
                root / capture_path, allowed_root=root / "sources" / "fotmob",
            )
            reproduced.append(_record_from_capture(
                root / capture_path, artifact_root=root, expected_date=record.request_date,
            ))
        regenerated = AthenaCanonicalStoreUpdate(
            schema_version=update.schema_version, policy_id=update.policy_id,
            request_sha256=request.canonical_sha256, provider=request.provider,
            source_records=tuple(reproduced), source_record_count=len(reproduced),
            all_requested_dates_captured=True, commit_status=READY,
        )
        if regenerated.canonical_sha256 != update.canonical_sha256 or regenerated.canonical_bytes != update_raw:
            raise AthenaIngestReplayError("regenerated canonical update differs")
        if receipt.canonical_bytes != receipt_raw:
            raise AthenaIngestReplayError("ingest receipt is not canonical")
        return {
            "schema_version": 1, "policy_id": REPLAY_RECEIPT_POLICY,
            "status": "ATHENA_INGEST_OFFLINE_REPLAY_VERIFIED",
            "network_acquisition_performed": False, "provider_request_count": 0,
            "source_count": len(reproduced), "request_sha256": request.canonical_sha256,
            "canonical_store_update_sha256": update.canonical_sha256,
            "original_ingest_receipt_sha256": receipt.canonical_sha256,
        }
    except (AthenaIngestContractError, FotMobDataMatchesCaptureError, OSError, ValueError) as exc:
        raise AthenaIngestReplayError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = replay_ingest_artifact(args.artifact_root)
        raw = canonical_json_bytes(receipt)
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise AthenaIngestReplayError("refusing to overwrite replay receipt")
            with args.output.open("xb") as stream:
                stream.write(raw)
        else:
            sys.stdout.buffer.write(raw)
        return 0
    except AthenaIngestReplayError as exc:
        print(f"ATHENA ingest replay failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
