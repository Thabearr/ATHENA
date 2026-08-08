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
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        try:
            if type(self.status) is not int or self.status != 200:
                raise FotMobNetworkError(
                    "captured response status must be exact integer 200"
                )
            try:
                content_type = validate_json_content_type(self.content_type)
            except FotMobCaptureError as exc:
                raise FotMobNetworkError(str(exc)) from exc
            if type(self.body) is not bytes:
                raise FotMobNetworkError("captured response body must be exact bytes")
            if len(self.body) > MAX_RESPONSE_BYTES:
                raise FotMobNetworkError("captured response exceeds the 16 MiB limit")
            if not isinstance(self.observed_at, datetime.datetime):
                raise FotMobNetworkError("captured response observed_at must be a datetime")
            if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
                raise FotMobNetworkError(
                    "captured response observed_at must be timezone-aware"
                )
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobNetworkError(
                    "captured response network provenance must be exact bool"
                )
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(
                self,
                "observed_at",
                self.observed_at.astimezone(datetime.timezone.utc),
            )
        except FotMobNetworkError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobNetworkError(
                f"invalid captured response: {type(exc).__name__}"
            ) from exc


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
            network_acquisition_performed=True,
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


def _load_kernel32() -> Any:
    if os.name != "nt":
        return None
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        kernel32.FlushFileBuffers.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.FlushFileBuffers.restype = ctypes.wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        return kernel32
    except (AttributeError, ImportError, OSError):
        return None


def _last_windows_error(kernel32: Any) -> int:
    try:
        import ctypes

        return int(ctypes.get_last_error())
    except (AttributeError, TypeError, ValueError, OSError):
        try:
            return int(kernel32.GetLastError())
        except (AttributeError, TypeError, ValueError, OSError):
            return 0


def _sync_windows_directory(path: Path) -> None:
    kernel32 = _load_kernel32()
    if kernel32 is None:
        raise FotMobCaptureError(
            f"cannot prove directory durability on Windows: {path}"
        )
    handle = kernel32.CreateFileW(
        str(path),
        0xC0000000,  # GENERIC_READ | GENERIC_WRITE
        0x00000007,  # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
        None,
        3,  # OPEN_EXISTING
        0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
        None,
    )
    invalid_handles = {None, 0, -1}
    try:
        import ctypes
        import ctypes.wintypes

        invalid_handles.add(ctypes.c_void_p(-1).value)
        invalid_handles.add(ctypes.wintypes.HANDLE(-1).value)
    except (AttributeError, ImportError, TypeError, ValueError):
        pass
    if handle in invalid_handles:
        raise FotMobCaptureError(
            "could not open directory for durable synchronization: "
            f"{path} (winerror={_last_windows_error(kernel32)})"
        )
    failures: list[str] = []
    try:
        if not kernel32.FlushFileBuffers(handle):
            failures.append(
                "FlushFileBuffers failed "
                f"(winerror={_last_windows_error(kernel32)})"
            )
    finally:
        if not kernel32.CloseHandle(handle):
            failures.append(
                f"CloseHandle failed (winerror={_last_windows_error(kernel32)})"
            )
    if failures:
        raise FotMobCaptureError(
            f"could not durably synchronize directory {path}: " + "; ".join(failures)
        )


def _sync_directory(path: Path, *, platform_name: str | None = None) -> None:
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        _sync_windows_directory(path)
        return
    if platform != "posix":
        raise FotMobCaptureError(
            f"directory durability is unsupported on platform {platform!r}"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(str(path), flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise FotMobCaptureError(
            f"could not durably synchronize directory {path}"
        ) from exc


def _bounded_failure(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"


def _ensure_directory_tree_durable(target: Path, *, boundary: Path) -> list[Path]:
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise FotMobCaptureError("durable directory target is outside repository") from exc
    created: list[Path] = []
    current = boundary
    _sync_directory(current)
    try:
        for component in relative.parts:
            child = current / component
            if not child.exists():
                child.mkdir()
                created.append(child)
                _sync_directory(current)
                _sync_directory(child)
            elif child.is_symlink() or not child.is_dir():
                raise FotMobCaptureError(
                    f"capture directory component is not a regular directory: {child}"
                )
            else:
                _sync_directory(child)
            current = child
        return created
    except Exception as operation_error:
        cleanup_failures: list[str] = []
        for directory in reversed(created):
            try:
                if directory.is_symlink():
                    raise FotMobCaptureError("refusing to remove a symlink")
                directory.rmdir()
                _sync_directory(directory.parent)
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{directory}: {_bounded_failure(cleanup_error)}"
                )
        if cleanup_failures:
            raise FotMobCaptureError(
                "directory creation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


def _validate_transport_receipt(response: Any) -> CapturedHttpResponse:
    if not isinstance(response, CapturedHttpResponse):
        raise FotMobCaptureError("response must be CapturedHttpResponse")
    try:
        return CapturedHttpResponse(
            status=response.status,
            content_type=response.content_type,
            body=response.body,
            observed_at=response.observed_at,
            network_acquisition_performed=response.network_acquisition_performed,
        )
    except FotMobNetworkError as exc:
        raise FotMobCaptureError(f"invalid transport receipt: {exc}") from exc


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
        _sync_directory(path.parent)
    except Exception as exc:
        raise FotMobCaptureError(
            f"could not durably write {path.name}: {_bounded_failure(exc)}"
        ) from exc


def _cleanup_owned_capture(
    capture_directory: Path,
    date_directory_created: bool,
) -> tuple[str, ...]:
    owned_names = (
        RESPONSE_FILENAME,
        CANDIDATE_FILENAME,
        MANIFEST_FILENAME,
        f".{RESPONSE_FILENAME}.tmp",
        f".{CANDIDATE_FILENAME}.tmp",
        f".{MANIFEST_FILENAME}.tmp",
    )
    failures: list[str] = []
    for name in owned_names:
        path = capture_directory / name
        try:
            if path.is_symlink():
                raise FotMobCaptureError("refusing to remove a symlink")
            if path.exists():
                if not path.is_file():
                    raise FotMobCaptureError("owned capture path is not a regular file")
                path.unlink()
        except Exception as exc:
            failures.append(f"{path}: {_bounded_failure(exc)}")
    if capture_directory.exists() and not capture_directory.is_symlink():
        try:
            _sync_directory(capture_directory)
        except Exception as exc:
            failures.append(
                f"{capture_directory}: {_bounded_failure(exc)}"
            )
    try:
        if capture_directory.is_symlink():
            raise FotMobCaptureError("refusing to remove a symlink capture directory")
        if capture_directory.exists():
            capture_directory.rmdir()
            _sync_directory(capture_directory.parent)
    except Exception as exc:
        failures.append(f"{capture_directory}: {_bounded_failure(exc)}")
    if date_directory_created:
        try:
            date_directory = capture_directory.parent
            if date_directory.is_symlink():
                raise FotMobCaptureError("refusing to remove a symlink date directory")
            if date_directory.exists():
                date_directory.rmdir()
                _sync_directory(date_directory.parent)
        except Exception as exc:
            failures.append(
                f"{capture_directory.parent}: {_bounded_failure(exc)}"
            )
    return tuple(failures)


def write_capture_directory(
    response: CapturedHttpResponse,
    *,
    request_date: str,
    output_root: Path,
    repository_root: Path | None = None,
) -> tuple[Path, FotMobMatchesCaptureManifest]:
    response = _validate_transport_receipt(response)
    date = validate_request_date(request_date)
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(output_root, repository_root=repository)
    _ensure_directory_tree_durable(root, boundary=repository)
    _reject_symlink_components(root, "output root")
    date_directory = root / date
    date_directory_created = not date_directory.exists()
    if date_directory.exists() and (date_directory.is_symlink() or not date_directory.is_dir()):
        raise FotMobCaptureError("capture date directory is invalid")
    observed = response.observed_at
    capture_name = (
        observed.strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + sha256_bytes(response.body)[:12]
    )
    capture_directory = date_directory / capture_name
    if capture_directory.exists() or capture_directory.is_symlink():
        raise FotMobCaptureError("capture directory already exists")
    try:
        if date_directory_created:
            date_directory.mkdir()
            _sync_directory(root)
            _sync_directory(date_directory)
        else:
            _sync_directory(date_directory)
        capture_directory.mkdir()
        _sync_directory(date_directory)
        _sync_directory(capture_directory)
        _atomic_write(capture_directory / RESPONSE_FILENAME, response.body)
        manifest = build_capture_manifest(
            response.body,
            request_date=date,
            observed_at=observed,
            http_status=response.status,
            content_type=response.content_type,
            evidence_file_path=RESPONSE_FILENAME,
            network_acquisition_performed=response.network_acquisition_performed,
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
    except Exception as operation_error:
        cleanup_failures = _cleanup_owned_capture(
            capture_directory,
            date_directory_created,
        )
        if cleanup_failures:
            raise FotMobCaptureError(
                "capture operation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
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
        if response.network_acquisition_performed is not True:
            raise FotMobNetworkError(
                "live capture requires validated network acquisition provenance"
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
