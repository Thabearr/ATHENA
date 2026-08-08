"""Controlled CLI transport for one FotMob matches-by-date capture."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import dataclasses
import datetime
import http.client
import json
import os
from pathlib import Path
from typing import Any, Callable

from domain.fotmob_capture import (
    ALLOWED_HOST,
    CANDIDATE_FILENAME,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RESPONSE_FILENAME,
    FotMobCaptureError,
    FotMobMatchesCaptureManifest,
    build_capture_manifest,
    canonical_candidate_jsonl_bytes,
    canonical_manifest_bytes,
    request_target,
    serialize_utc,
    sha256_bytes,
    validate_json_content_type,
    validate_request_date,
    verify_capture_directory,
)


ALLOWED_OUTPUT_RELATIVE = Path(".cache/athena-research/fotmob-captures")
USER_AGENT = "ATHENA/1.0"
REQUEST_TIMEOUT_SECONDS = 30


class FotMobNetworkError(RuntimeError):
    """Raised when the single authorized HTTPS request fails."""


@dataclasses.dataclass(frozen=True)
class CapturedHttpResponse:
    status: int
    content_type: str
    body: bytes
    observed_at: datetime.datetime


def parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("-") and value[1:].isdigit():
        raise FotMobNetworkError("FotMob returned a negative Content-Length")
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise FotMobNetworkError("FotMob returned an invalid Content-Length header")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobNetworkError("FotMob returned an invalid Content-Length header") from exc
    if parsed < 0:
        raise FotMobNetworkError("FotMob returned a negative Content-Length")
    if parsed > MAX_RESPONSE_BYTES:
        raise FotMobNetworkError("FotMob response exceeds the 16 MiB limit")
    return parsed


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def fetch_matches_by_date(
    request_date: str,
    *,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> CapturedHttpResponse:
    """Perform exactly one HTTPS GET to the fixed matches-by-date resource."""

    date = validate_request_date(request_date)
    target = request_target(date)
    connection = None
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            443,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.request(
            "GET",
            target,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        status = getattr(response, "status", None)
        if type(status) is not int or status != 200:
            raise FotMobNetworkError(
                f"FotMob matches capture requires HTTP 200; received {status!r}"
            )
        content_type = response.getheader("Content-Type")
        try:
            validated_content_type = validate_json_content_type(content_type)
        except FotMobCaptureError as exc:
            raise FotMobNetworkError(str(exc)) from exc
        parse_content_length(response.getheader("Content-Length"))
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if not isinstance(body, bytes):
            raise FotMobNetworkError("FotMob response body was not bytes")
        if len(body) > MAX_RESPONSE_BYTES:
            raise FotMobNetworkError("FotMob response exceeds the 16 MiB limit")
        observed_at = clock()
        if not isinstance(observed_at, datetime.datetime):
            raise FotMobNetworkError("acquisition clock did not return a datetime")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise FotMobNetworkError("acquisition clock must be timezone-aware")
        return CapturedHttpResponse(
            status=status,
            content_type=validated_content_type,
            body=body,
            observed_at=observed_at.astimezone(datetime.timezone.utc),
        )
    except FotMobNetworkError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FotMobNetworkError(
            f"FotMob matches request failed: {type(exc).__name__}"
        ) from exc
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobNetworkError(
            f"FotMob response handling failed: {type(exc).__name__}"
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _absolute_without_resolving_symlinks(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = _absolute_without_resolving_symlinks(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FotMobCaptureError(f"{label} contains a forbidden symlink component")


def validate_output_root(
    output_root: Path,
    *,
    repository_root: Path | None = None,
) -> Path:
    repository = (repository_root or _repository_root()).resolve(strict=True)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise FotMobCaptureError("output root is invalid") from exc
    supplied_absolute = supplied if supplied.is_absolute() else repository / supplied
    if ".." in supplied.parts:
        raise FotMobCaptureError("output root must not contain traversal")
    _reject_symlink_components(supplied_absolute, "output root")
    if supplied_absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise FotMobCaptureError(
            "output root must be .cache/athena-research/fotmob-captures"
        )
    if expected.exists() and (expected.is_symlink() or not expected.is_dir()):
        raise FotMobCaptureError("output root must be a non-symlink directory")
    return expected


def _atomic_write(path: Path, content: bytes) -> None:
    if not isinstance(content, bytes):
        raise FotMobCaptureError("capture file content must be bytes")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink() or path.exists() or path.is_symlink():
        raise FotMobCaptureError("capture output or transaction file already exists")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass
        raise FotMobCaptureError(f"could not durably write {path.name}") from exc


def _cleanup_owned_capture(capture_directory: Path, date_directory_created: bool) -> None:
    owned_names = {
        RESPONSE_FILENAME,
        CANDIDATE_FILENAME,
        MANIFEST_FILENAME,
        f".{RESPONSE_FILENAME}.tmp",
        f".{CANDIDATE_FILENAME}.tmp",
        f".{MANIFEST_FILENAME}.tmp",
    }
    for name in owned_names:
        path = capture_directory / name
        try:
            if path.exists() and not path.is_symlink() and path.is_file():
                path.unlink()
        except OSError:
            pass
    try:
        capture_directory.rmdir()
    except OSError:
        pass
    if date_directory_created:
        try:
            capture_directory.parent.rmdir()
        except OSError:
            pass


def write_capture_directory(
    response: CapturedHttpResponse,
    *,
    request_date: str,
    output_root: Path,
    repository_root: Path | None = None,
) -> tuple[Path, FotMobMatchesCaptureManifest]:
    if not isinstance(response, CapturedHttpResponse):
        raise FotMobCaptureError("response must be CapturedHttpResponse")
    date = validate_request_date(request_date)
    root = validate_output_root(output_root, repository_root=repository_root)
    root.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root, "output root")
    date_directory = root / date
    date_directory_created = not date_directory.exists()
    if date_directory.exists() and (date_directory.is_symlink() or not date_directory.is_dir()):
        raise FotMobCaptureError("capture date directory is invalid")
    date_directory.mkdir(exist_ok=True)
    observed = response.observed_at.astimezone(datetime.timezone.utc)
    capture_name = (
        observed.strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + sha256_bytes(response.body)[:12]
    )
    capture_directory = date_directory / capture_name
    if capture_directory.exists() or capture_directory.is_symlink():
        raise FotMobCaptureError("capture directory already exists")
    capture_directory.mkdir()
    try:
        _atomic_write(capture_directory / RESPONSE_FILENAME, response.body)
        manifest = build_capture_manifest(
            response.body,
            request_date=date,
            observed_at=observed,
            http_status=response.status,
            content_type=response.content_type,
            evidence_file_path=RESPONSE_FILENAME,
            network_acquisition_performed=True,
        )
        _atomic_write(
            capture_directory / CANDIDATE_FILENAME,
            canonical_candidate_jsonl_bytes(manifest.candidates),
        )
        _atomic_write(
            capture_directory / MANIFEST_FILENAME,
            canonical_manifest_bytes(manifest),
        )
        return capture_directory, manifest
    except Exception:
        _cleanup_owned_capture(capture_directory, date_directory_created)
        raise


def _capture_under_allowed_root(
    capture_directory: Path,
    *,
    repository_root: Path | None = None,
) -> Path:
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repository)
    try:
        capture = Path(capture_directory)
    except (TypeError, ValueError) as exc:
        raise FotMobCaptureError("capture directory is invalid") from exc
    capture_absolute = capture if capture.is_absolute() else repository / capture
    if ".." in capture.parts:
        raise FotMobCaptureError("capture directory must not contain traversal")
    _reject_symlink_components(capture_absolute, "capture directory")
    resolved = capture_absolute.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise FotMobCaptureError("capture directory must be beneath the allowed root") from exc
    return resolved


def _summary(manifest: FotMobMatchesCaptureManifest, capture_directory: Path) -> dict[str, Any]:
    return {
        "capture_directory": capture_directory.as_posix(),
        "observed_at": serialize_utc(manifest.observed_at),
        "http_status": manifest.http_status,
        "content_type": manifest.content_type,
        "payload_byte_size": manifest.payload_byte_size,
        "payload_sha256": manifest.payload_sha256,
        "candidate_fixture_count": manifest.candidate_fixture_count,
        "rejected_fixture_count": manifest.rejected_fixture_count,
        "review_status": "UNREVIEWED",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preserve or verify one controlled FotMob matches-by-date capture. "
            "Live network access requires --execute-live-network."
        )
    )
    parser.add_argument("--date", help="Exact Gregorian date in YYYYMMDD format")
    parser.add_argument(
        "--output-root",
        default=str(ALLOWED_OUTPUT_RELATIVE),
        help="Must remain .cache/athena-research/fotmob-captures",
    )
    parser.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize exactly one GET /api/matches?date=YYYYMMDD request",
    )
    parser.add_argument(
        "--check-capture",
        type=Path,
        help="Verify one existing capture directory without network access",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
    repository_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check_capture is not None and args.execute_live_network:
        parser.error("--check-capture and --execute-live-network are mutually exclusive")
    try:
        if args.check_capture is not None:
            capture = _capture_under_allowed_root(
                args.check_capture,
                repository_root=repository_root,
            )
            manifest = verify_capture_directory(
                capture,
                require_network_acquisition_performed=True,
            )
            print(json.dumps(_summary(manifest, capture), sort_keys=True))
            return 0
        if not args.execute_live_network:
            parser.error(
                "live network acquisition is disabled; supply --execute-live-network "
                "for the exact matches-by-date request"
            )
        if args.date is None:
            parser.error("--date YYYYMMDD is required for live capture")
        date = validate_request_date(args.date)
        response = fetch_matches_by_date(
            date,
            connection_factory=connection_factory,
            clock=clock,
        )
        capture, manifest = write_capture_directory(
            response,
            request_date=date,
            output_root=Path(args.output_root),
            repository_root=repository_root,
        )
        print(json.dumps(_summary(manifest, capture), sort_keys=True))
        return 0
    except (FotMobCaptureError, FotMobNetworkError) as exc:
        parser.exit(1, f"capture failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
