"""Controlled one-request transport and durable raw FotMob date-page capture."""

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

from domain.fotmob_page_capture import (
    ALLOWED_HOST,
    HTTPS_PORT,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    REQUEST_HEADERS,
    CapturedFotMobPageResponse,
    FotMobPageCaptureError,
    FotMobPageCaptureManifest,
    build_page_capture_manifest,
    canonical_page_capture_manifest_bytes,
    capture_identifier,
    request_target,
    serialize_utc,
    sha256_page_capture_manifest,
    validate_html_content_type,
    validate_request_date,
    verify_page_capture_directory,
)


ALLOWED_OUTPUT_RELATIVE = Path("artifacts/source-captures/fotmob-date-page")
REQUEST_TIMEOUT_SECONDS = 30
READ_CHUNK_BYTES = 64 * 1024


class FotMobPageNetworkError(RuntimeError):
    """Raised when the one authorized page request fails."""


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_failure(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"


def parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("-") and value[1:].isdigit():
        raise FotMobPageNetworkError("FotMob returned a negative Content-Length")
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise FotMobPageNetworkError("FotMob returned an invalid Content-Length")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageNetworkError("FotMob returned an invalid Content-Length") from exc
    if parsed > MAX_RESPONSE_BYTES:
        raise FotMobPageNetworkError("FotMob page exceeds the 8 MiB limit")
    return parsed


def _read_bounded_body(response: Any) -> bytes:
    body = bytearray()
    while True:
        amount = min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES - len(body) + 1)
        try:
            chunk = response.read(amount)
        except (OSError, http.client.HTTPException) as exc:
            raise FotMobPageNetworkError(
                f"FotMob page body read failed: {type(exc).__name__}"
            ) from exc
        if type(chunk) is not bytes:
            raise FotMobPageNetworkError("FotMob page body chunk was not bytes")
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise FotMobPageNetworkError("FotMob page exceeds the 8 MiB limit")
    if not body:
        raise FotMobPageNetworkError("FotMob page body was empty")
    return bytes(body)


def fetch_fotmob_date_page(
    request_date: str,
    *,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> CapturedFotMobPageResponse:
    """Perform exactly one transparent GET for the fixed public date page."""

    date = validate_request_date(request_date)
    target = request_target(date)
    connection = None
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            HTTPS_PORT,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.putrequest("GET", target, skip_accept_encoding=True)
        for name, value in REQUEST_HEADERS:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        status = getattr(response, "status", None)
        if type(status) is not int or status != 200:
            raise FotMobPageNetworkError(
                f"FotMob date-page capture requires HTTP 200; received {status!r}"
            )
        content_type = response.getheader("Content-Type")
        try:
            validated_content_type = validate_html_content_type(content_type)
        except FotMobPageCaptureError as exc:
            raise FotMobPageNetworkError(str(exc)) from exc
        content_length = parse_content_length(response.getheader("Content-Length"))
        body = _read_bounded_body(response)
        if content_length is not None and content_length != len(body):
            raise FotMobPageNetworkError("Content-Length does not match received body")
        try:
            observed_at = clock()
            if not isinstance(observed_at, datetime.datetime):
                raise FotMobPageNetworkError("acquisition clock must return a datetime")
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise FotMobPageNetworkError("acquisition clock must be timezone-aware")
            observed_at = observed_at.astimezone(datetime.timezone.utc)
        except FotMobPageNetworkError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobPageNetworkError("acquisition clock returned invalid time") from exc
        return CapturedFotMobPageResponse(
            status=status,
            content_type=validated_content_type,
            content_length=content_length,
            body=body,
            observed_at=observed_at,
            network_acquisition_performed=True,
        )
    except (FotMobPageCaptureError, FotMobPageNetworkError):
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FotMobPageNetworkError(
            f"FotMob date-page request failed: {type(exc).__name__}"
        ) from exc
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageNetworkError(
            f"FotMob date-page response handling failed: {type(exc).__name__}"
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
            raise FotMobPageCaptureError(f"{label} contains a forbidden symlink")


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
        raise FotMobPageCaptureError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise FotMobPageCaptureError("output root must not contain traversal")
    supplied_absolute = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(supplied_absolute, "output root")
    if supplied_absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise FotMobPageCaptureError(
            "output root must be artifacts/source-captures/fotmob-date-page"
        )
    if expected.exists() and (expected.is_symlink() or not expected.is_dir()):
        raise FotMobPageCaptureError("output root must be a non-symlink directory")
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
        raise FotMobPageCaptureError(
            f"cannot prove directory durability on Windows: {path}"
        )
    handle = kernel32.CreateFileW(
        str(path),
        0xC0000000,
        0x00000007,
        None,
        3,
        0x02000000,
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
        raise FotMobPageCaptureError(
            "could not open directory for durable synchronization: "
            f"{path} (winerror={_last_windows_error(kernel32)})"
        )
    failures: list[str] = []
    try:
        if not kernel32.FlushFileBuffers(handle):
            failures.append(
                f"FlushFileBuffers failed (winerror={_last_windows_error(kernel32)})"
            )
    finally:
        if not kernel32.CloseHandle(handle):
            failures.append(
                f"CloseHandle failed (winerror={_last_windows_error(kernel32)})"
            )
    if failures:
        raise FotMobPageCaptureError(
            f"could not durably synchronize directory {path}: " + "; ".join(failures)
        )


def _sync_directory(path: Path, *, platform_name: str | None = None) -> None:
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        _sync_windows_directory(path)
        return
    if platform != "posix":
        raise FotMobPageCaptureError(
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
        raise FotMobPageCaptureError(
            f"could not durably synchronize directory {path}"
        ) from exc


def _ensure_directory_tree_durable(target: Path, *, boundary: Path) -> list[Path]:
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise FotMobPageCaptureError("output root is outside repository") from exc
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
                raise FotMobPageCaptureError(
                    f"output component is not a regular directory: {child}"
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
                    raise FotMobPageCaptureError("refusing to remove a symlink")
                directory.rmdir()
                _sync_directory(directory.parent)
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{directory}: {_bounded_failure(cleanup_error)}"
                )
        if cleanup_failures:
            raise FotMobPageCaptureError(
                "directory creation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


@dataclasses.dataclass
class _CaptureTransactionState:
    date_directory: Path
    capture_directory: Path
    date_directory_owned: bool = False
    capture_directory_owned: bool = False
    owned_final_files: set[Path] = dataclasses.field(default_factory=set)
    owned_temp_files: set[Path] = dataclasses.field(default_factory=set)


def _publish_no_overwrite(
    temporary: Path,
    final: Path,
    transaction: _CaptureTransactionState,
) -> None:
    if temporary not in transaction.owned_temp_files:
        raise FotMobPageCaptureError("temporary path is not transaction-owned")
    if final.parent != transaction.capture_directory:
        raise FotMobPageCaptureError("final path is outside capture directory")
    if final in transaction.owned_final_files:
        raise FotMobPageCaptureError("final path is already transaction-owned")
    try:
        os.link(temporary, final)
    except FileExistsError as exc:
        raise FotMobPageCaptureError(
            f"capture output already exists and was not overwritten: {final}"
        ) from exc
    except OSError as exc:
        raise FotMobPageCaptureError(
            "atomic no-overwrite publication is unavailable for "
            f"{final.name}: {_bounded_failure(exc)}"
        ) from exc
    transaction.owned_final_files.add(final)
    _sync_directory(final.parent)
    temporary.unlink()
    transaction.owned_temp_files.remove(temporary)
    _sync_directory(final.parent)


def _atomic_write(
    path: Path,
    content: bytes,
    transaction: _CaptureTransactionState,
) -> None:
    if type(content) is not bytes:
        raise FotMobPageCaptureError("capture content must be exact bytes")
    if not isinstance(transaction, _CaptureTransactionState):
        raise FotMobPageCaptureError("capture transaction is invalid")
    if not transaction.capture_directory_owned:
        raise FotMobPageCaptureError("capture directory is not transaction-owned")
    if path.parent != transaction.capture_directory:
        raise FotMobPageCaptureError("capture output is outside owned directory")
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        try:
            handle = temporary.open("xb")
        except FileExistsError as exc:
            raise FotMobPageCaptureError(
                f"capture temporary file already exists: {temporary}"
            ) from exc
        transaction.owned_temp_files.add(temporary)
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_no_overwrite(temporary, path, transaction)
    except Exception as exc:
        raise FotMobPageCaptureError(
            f"could not durably write {path.name}: {_bounded_failure(exc)}"
        ) from exc


def _cleanup_owned_capture(transaction: _CaptureTransactionState) -> tuple[str, ...]:
    failures: list[str] = []
    capture_directory = transaction.capture_directory
    if transaction.capture_directory_owned:
        owned = sorted(
            transaction.owned_temp_files | transaction.owned_final_files,
            key=lambda item: item.as_posix(),
        )
        for path in owned:
            try:
                if path.parent != capture_directory:
                    raise FotMobPageCaptureError("owned path escaped capture directory")
                if path.is_symlink():
                    raise FotMobPageCaptureError("refusing to remove a symlink")
                if path.exists():
                    if not path.is_file():
                        raise FotMobPageCaptureError("owned path is not a regular file")
                    path.unlink()
            except Exception as exc:
                failures.append(f"{path}: {_bounded_failure(exc)}")
        try:
            if capture_directory.exists() and not capture_directory.is_symlink():
                _sync_directory(capture_directory)
        except Exception as exc:
            failures.append(f"{capture_directory}: {_bounded_failure(exc)}")
        try:
            if capture_directory.is_symlink():
                raise FotMobPageCaptureError("refusing to remove symlink directory")
            if capture_directory.exists():
                capture_directory.rmdir()
                _sync_directory(capture_directory.parent)
        except Exception as exc:
            failures.append(f"{capture_directory}: {_bounded_failure(exc)}")
    if transaction.date_directory_owned:
        try:
            if transaction.date_directory.is_symlink():
                raise FotMobPageCaptureError("refusing to remove symlink date directory")
            if transaction.date_directory.exists():
                transaction.date_directory.rmdir()
                _sync_directory(transaction.date_directory.parent)
        except Exception as exc:
            failures.append(
                f"{transaction.date_directory}: {_bounded_failure(exc)}"
            )
    return tuple(failures)


def write_page_capture_directory(
    response: CapturedFotMobPageResponse,
    *,
    request_date: str,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
    repository_root: Path | None = None,
) -> tuple[Path, FotMobPageCaptureManifest]:
    if not isinstance(response, CapturedFotMobPageResponse):
        raise FotMobPageCaptureError("response must be CapturedFotMobPageResponse")
    response = CapturedFotMobPageResponse(
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        body=response.body,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
    )
    date = validate_request_date(request_date)
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(output_root, repository_root=repository)
    _ensure_directory_tree_durable(root, boundary=repository)
    _reject_symlink_components(root, "output root")
    manifest = build_page_capture_manifest(response, request_date=date)
    date_directory = root / date
    capture_directory = date_directory / capture_identifier(
        request_date=date,
        observed_at=response.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    transaction = _CaptureTransactionState(
        date_directory=date_directory,
        capture_directory=capture_directory,
    )
    try:
        if date_directory.exists() or date_directory.is_symlink():
            if date_directory.is_symlink() or not date_directory.is_dir():
                raise FotMobPageCaptureError("capture date directory is invalid")
            _sync_directory(date_directory)
        else:
            try:
                date_directory.mkdir()
            except FileExistsError as exc:
                raise FotMobPageCaptureError(
                    "capture date directory appeared concurrently"
                ) from exc
            transaction.date_directory_owned = True
            _sync_directory(root)
            _sync_directory(date_directory)
        try:
            capture_directory.mkdir()
        except FileExistsError as exc:
            raise FotMobPageCaptureError("capture directory already exists") from exc
        transaction.capture_directory_owned = True
        _sync_directory(date_directory)
        _sync_directory(capture_directory)
        _atomic_write(capture_directory / RAW_FILENAME, response.body, transaction)
        _atomic_write(
            capture_directory / MANIFEST_FILENAME,
            canonical_page_capture_manifest_bytes(manifest),
            transaction,
        )
        return capture_directory, manifest
    except Exception as operation_error:
        cleanup_failures = _cleanup_owned_capture(transaction)
        if cleanup_failures:
            raise FotMobPageCaptureError(
                "capture operation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


def _capture_under_allowed_root(
    capture_directory: Path,
    *,
    repository_root: Path | None = None,
) -> tuple[Path, Path]:
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(ALLOWED_OUTPUT_RELATIVE, repository_root=repository)
    try:
        capture = Path(capture_directory)
    except (TypeError, ValueError) as exc:
        raise FotMobPageCaptureError("capture directory is invalid") from exc
    if ".." in capture.parts:
        raise FotMobPageCaptureError("capture directory must not contain traversal")
    absolute = capture if capture.is_absolute() else repository / capture
    _reject_symlink_components(absolute, "capture directory")
    resolved = absolute.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise FotMobPageCaptureError("capture directory is outside allowed root") from exc
    return resolved, root.resolve(strict=True)


def _summary(
    manifest: FotMobPageCaptureManifest,
    capture_directory: Path,
) -> dict[str, Any]:
    return {
        "capture_directory": capture_directory.as_posix(),
        "request_date": manifest.request_date,
        "status": manifest.status,
        "content_type": manifest.content_type,
        "content_length": manifest.content_length,
        "observed_at": serialize_utc(manifest.observed_at),
        "raw_size": manifest.raw_size,
        "raw_sha256": manifest.raw_sha256,
        "manifest_sha256": sha256_page_capture_manifest(manifest),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture or verify one exact raw FotMob public date page."
    )
    parser.add_argument("--date", help="Exact Gregorian date in YYYYMMDD format")
    parser.add_argument(
        "--output-root",
        default=str(ALLOWED_OUTPUT_RELATIVE),
        help="Must remain artifacts/source-captures/fotmob-date-page",
    )
    parser.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize exactly one transparent public date-page request",
    )
    parser.add_argument(
        "--check-capture",
        type=Path,
        help="Verify one existing capture without network",
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
            capture, root = _capture_under_allowed_root(
                args.check_capture,
                repository_root=repository_root,
            )
            manifest = verify_page_capture_directory(
                capture,
                allowed_root=root,
                require_network_acquisition_performed=True,
            )
            print(json.dumps(_summary(manifest, capture), sort_keys=True))
            return 0
        if not args.execute_live_network:
            parser.error(
                "live network acquisition is disabled; supply --execute-live-network"
            )
        if args.date is None:
            parser.error("--date YYYYMMDD is required for live capture")
        date = validate_request_date(args.date)
        response = fetch_fotmob_date_page(
            date,
            connection_factory=connection_factory,
            clock=clock,
        )
        if response.network_acquisition_performed is not True:
            raise FotMobPageNetworkError(
                "live capture requires validated network acquisition provenance"
            )
        capture, manifest = write_page_capture_directory(
            response,
            request_date=date,
            output_root=Path(args.output_root),
            repository_root=repository_root,
        )
        print(json.dumps(_summary(manifest, capture), sort_keys=True))
        return 0
    except (FotMobPageCaptureError, FotMobPageNetworkError) as exc:
        parser.exit(1, f"capture failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
