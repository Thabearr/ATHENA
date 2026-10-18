"""Controlled transport and durable raw FotMob data-matches capture."""

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

from domain.fotmob_data_matches_capture import (
    ALLOWED_HOST,
    HTTPS_PORT,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    REQUEST_HEADERS,
    CapturedFotMobDataMatchesResponse,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    build_data_matches_capture_manifest,
    canonical_data_matches_capture_manifest_bytes,
    capture_identifier,
    serialize_utc,
    sha256_data_matches_capture_manifest,
    validate_json_content_type,
    verify_data_matches_capture_directory,
)
from domain.fotmob_data_matches_probe import (
    FotMobDataMatchesProbeError,
    request_target,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)


ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/fotmob-data-matches-captures"
)
REQUEST_TIMEOUT_SECONDS = 30
READ_CHUNK_BYTES = 64 * 1024


class FotMobDataMatchesNetworkError(RuntimeError):
    """Raised when the one authorized data-matches request fails."""


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_failure(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"


def parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("-") and value[1:].isdigit():
        raise FotMobDataMatchesNetworkError(
            "FotMob returned a negative Content-Length"
        )
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
    ):
        raise FotMobDataMatchesNetworkError(
            "FotMob returned an invalid Content-Length"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesNetworkError(
            "FotMob returned an invalid Content-Length"
        ) from exc
    if parsed > MAX_RESPONSE_BYTES:
        raise FotMobDataMatchesNetworkError(
            "FotMob data-matches response exceeds the 8 MiB limit"
        )
    return parsed


def _read_bounded_body(response: Any) -> bytes:
    body = bytearray()
    while True:
        amount = min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES - len(body) + 1)
        try:
            chunk = response.read(amount)
        except (OSError, http.client.HTTPException) as exc:
            raise FotMobDataMatchesNetworkError(
                f"FotMob response body read failed: {type(exc).__name__}"
            ) from exc
        if type(chunk) is not bytes:
            raise FotMobDataMatchesNetworkError(
                "FotMob response body chunk was not bytes"
            )
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise FotMobDataMatchesNetworkError(
                "FotMob data-matches response exceeds the 8 MiB limit"
            )
    if not body:
        raise FotMobDataMatchesNetworkError(
            "FotMob data-matches response body was empty"
        )
    return bytes(body)


def _validated_inputs(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> tuple[str, str, str]:
    try:
        return (
            validate_request_date(request_date),
            validate_timezone(timezone),
            validate_ccode3(ccode3),
        )
    except FotMobDataMatchesProbeError as exc:
        raise FotMobDataMatchesCaptureError(str(exc)) from exc


def fetch_fotmob_data_matches(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> CapturedFotMobDataMatchesResponse:
    """Perform exactly one transparent GET for the fixed data-matches route."""

    date, zone, country = _validated_inputs(request_date, timezone, ccode3)
    try:
        target = request_target(date, zone, country)
    except FotMobDataMatchesProbeError as exc:
        raise FotMobDataMatchesCaptureError(str(exc)) from exc
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
            raise FotMobDataMatchesNetworkError(
                "FotMob data-matches capture requires HTTP 200; "
                f"received {status!r}"
            )
        content_type = response.getheader("Content-Type")
        try:
            validated_content_type = validate_json_content_type(content_type)
        except FotMobDataMatchesCaptureError as exc:
            raise FotMobDataMatchesNetworkError(str(exc)) from exc
        content_length = parse_content_length(
            response.getheader("Content-Length")
        )
        body = _read_bounded_body(response)
        if content_length is not None and content_length != len(body):
            raise FotMobDataMatchesNetworkError(
                "Content-Length does not match received body"
            )
        try:
            observed_at = clock()
            if not isinstance(observed_at, datetime.datetime):
                raise FotMobDataMatchesNetworkError(
                    "acquisition clock must return a datetime"
                )
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise FotMobDataMatchesNetworkError(
                    "acquisition clock must be timezone-aware"
                )
            observed_at = observed_at.astimezone(datetime.timezone.utc)
        except FotMobDataMatchesNetworkError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobDataMatchesNetworkError(
                "acquisition clock returned invalid time"
            ) from exc
        return CapturedFotMobDataMatchesResponse(
            status=status,
            content_type=validated_content_type,
            content_length=content_length,
            body=body,
            observed_at=observed_at,
            network_acquisition_performed=True,
        )
    except (FotMobDataMatchesCaptureError, FotMobDataMatchesNetworkError):
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FotMobDataMatchesNetworkError(
            f"FotMob data-matches request failed: {type(exc).__name__}"
        ) from exc
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesNetworkError(
            "FotMob data-matches response handling failed: "
            f"{type(exc).__name__}"
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
            raise FotMobDataMatchesCaptureError(
                f"{label} contains a forbidden symlink"
            )


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
        raise FotMobDataMatchesCaptureError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise FotMobDataMatchesCaptureError(
            "output root must not contain traversal"
        )
    supplied_absolute = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(supplied_absolute, "output root")
    if supplied_absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise FotMobDataMatchesCaptureError(
            "output root must be "
            ".cache/athena-research/fotmob-data-matches-captures"
        )
    if expected.exists() and (expected.is_symlink() or not expected.is_dir()):
        raise FotMobDataMatchesCaptureError(
            "output root must be a non-symlink directory"
        )
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
        raise FotMobDataMatchesCaptureError(
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
        raise FotMobDataMatchesCaptureError(
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
        raise FotMobDataMatchesCaptureError(
            f"could not durably synchronize directory {path}: "
            + "; ".join(failures)
        )


def _sync_directory(path: Path, *, platform_name: str | None = None) -> None:
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        _sync_windows_directory(path)
        return
    if platform != "posix":
        raise FotMobDataMatchesCaptureError(
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
        raise FotMobDataMatchesCaptureError(
            f"could not durably synchronize directory {path}"
        ) from exc


def _ensure_directory_tree_durable(target: Path, *, boundary: Path) -> list[Path]:
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise FotMobDataMatchesCaptureError(
            "output root is outside repository"
        ) from exc
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
                raise FotMobDataMatchesCaptureError(
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
                    raise FotMobDataMatchesCaptureError(
                        "refusing to remove a symlink"
                    )
                directory.rmdir()
                _sync_directory(directory.parent)
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{directory}: {_bounded_failure(cleanup_error)}"
                )
        if cleanup_failures:
            raise FotMobDataMatchesCaptureError(
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
        raise FotMobDataMatchesCaptureError(
            "temporary path is not transaction-owned"
        )
    if final.parent != transaction.capture_directory:
        raise FotMobDataMatchesCaptureError(
            "final path is outside capture directory"
        )
    if final in transaction.owned_final_files:
        raise FotMobDataMatchesCaptureError(
            "final path is already transaction-owned"
        )
    try:
        os.link(temporary, final)
    except FileExistsError as exc:
        raise FotMobDataMatchesCaptureError(
            f"capture output already exists and was not overwritten: {final}"
        ) from exc
    except OSError as exc:
        raise FotMobDataMatchesCaptureError(
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
        raise FotMobDataMatchesCaptureError(
            "capture content must be exact bytes"
        )
    if not isinstance(transaction, _CaptureTransactionState):
        raise FotMobDataMatchesCaptureError("capture transaction is invalid")
    if not transaction.capture_directory_owned:
        raise FotMobDataMatchesCaptureError(
            "capture directory is not transaction-owned"
        )
    if path.parent != transaction.capture_directory:
        raise FotMobDataMatchesCaptureError(
            "capture output is outside owned directory"
        )
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        try:
            handle = temporary.open("xb")
        except FileExistsError as exc:
            raise FotMobDataMatchesCaptureError(
                f"capture temporary file already exists: {temporary}"
            ) from exc
        transaction.owned_temp_files.add(temporary)
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_no_overwrite(temporary, path, transaction)
    except Exception as exc:
        raise FotMobDataMatchesCaptureError(
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
                    raise FotMobDataMatchesCaptureError(
                        "owned path escaped capture directory"
                    )
                if path.is_symlink():
                    raise FotMobDataMatchesCaptureError(
                        "refusing to remove a symlink"
                    )
                if path.exists():
                    if not path.is_file():
                        raise FotMobDataMatchesCaptureError(
                            "owned path is not a regular file"
                        )
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
                raise FotMobDataMatchesCaptureError(
                    "refusing to remove symlink directory"
                )
            if capture_directory.exists():
                capture_directory.rmdir()
                _sync_directory(capture_directory.parent)
        except Exception as exc:
            failures.append(f"{capture_directory}: {_bounded_failure(exc)}")
    if transaction.date_directory_owned:
        try:
            if transaction.date_directory.is_symlink():
                raise FotMobDataMatchesCaptureError(
                    "refusing to remove symlink date directory"
                )
            if transaction.date_directory.exists():
                transaction.date_directory.rmdir()
                _sync_directory(transaction.date_directory.parent)
        except Exception as exc:
            failures.append(
                f"{transaction.date_directory}: {_bounded_failure(exc)}"
            )
    return tuple(failures)


def write_data_matches_capture_directory(
    response: CapturedFotMobDataMatchesResponse,
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
    repository_root: Path | None = None,
) -> tuple[Path, FotMobDataMatchesCaptureManifest]:
    if not isinstance(response, CapturedFotMobDataMatchesResponse):
        raise FotMobDataMatchesCaptureError(
            "response must be CapturedFotMobDataMatchesResponse"
        )
    response = CapturedFotMobDataMatchesResponse(
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        body=response.body,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
    )
    date, zone, country = _validated_inputs(request_date, timezone, ccode3)
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=date,
        timezone=zone,
        ccode3=country,
    )
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(output_root, repository_root=repository)
    _ensure_directory_tree_durable(root, boundary=repository)
    _reject_symlink_components(root, "output root")
    date_directory = root / date
    capture_directory = date_directory / capture_identifier(
        request_date=date,
        timezone=zone,
        ccode3=country,
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
                raise FotMobDataMatchesCaptureError(
                    "capture date directory is invalid"
                )
            _sync_directory(date_directory)
        else:
            try:
                date_directory.mkdir()
            except FileExistsError as exc:
                raise FotMobDataMatchesCaptureError(
                    "capture date directory appeared concurrently"
                ) from exc
            transaction.date_directory_owned = True
            _sync_directory(root)
            _sync_directory(date_directory)
        try:
            capture_directory.mkdir()
        except FileExistsError as exc:
            raise FotMobDataMatchesCaptureError(
                "capture directory already exists"
            ) from exc
        transaction.capture_directory_owned = True
        _sync_directory(date_directory)
        _sync_directory(capture_directory)
        _atomic_write(
            capture_directory / RAW_FILENAME,
            response.body,
            transaction,
        )
        _atomic_write(
            capture_directory / MANIFEST_FILENAME,
            canonical_data_matches_capture_manifest_bytes(manifest),
            transaction,
        )
        return capture_directory, manifest
    except Exception as operation_error:
        cleanup_failures = _cleanup_owned_capture(transaction)
        if cleanup_failures:
            raise FotMobDataMatchesCaptureError(
                "capture operation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


def _summary(
    manifest: FotMobDataMatchesCaptureManifest,
    capture_directory: Path,
) -> dict[str, Any]:
    return {
        "capture_directory": capture_directory.as_posix(),
        "request_date": manifest.request_date,
        "timezone": manifest.timezone,
        "ccode3": manifest.ccode3,
        "status": manifest.status,
        "content_type": manifest.content_type,
        "content_length": manifest.content_length,
        "observed_at": serialize_utc(manifest.observed_at),
        "raw_size": manifest.raw_size,
        "raw_sha256": manifest.raw_sha256,
        "manifest_sha256": sha256_data_matches_capture_manifest(manifest),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one exact raw FotMob /api/data/matches response using "
            "the unsigned transparent ATHENA profile."
        )
    )
    parser.add_argument("--date", required=True, help="Exact Gregorian YYYYMMDD date")
    parser.add_argument("--timezone", required=True, help="Explicit UTC or IANA-style timezone")
    parser.add_argument("--ccode3", required=True, help="Three uppercase ASCII letters")
    parser.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize exactly one unsigned transparent HTTPS request",
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
    if not args.execute_live_network:
        parser.error(
            "live network acquisition is disabled; supply --execute-live-network"
        )
    try:
        date, zone, country = _validated_inputs(
            args.date, args.timezone, args.ccode3
        )
        response = fetch_fotmob_data_matches(
            request_date=date,
            timezone=zone,
            ccode3=country,
            connection_factory=connection_factory,
            clock=clock,
        )
        if response.network_acquisition_performed is not True:
            raise FotMobDataMatchesNetworkError(
                "live capture requires validated network acquisition provenance"
            )
        capture, manifest = write_data_matches_capture_directory(
            response,
            request_date=date,
            timezone=zone,
            ccode3=country,
            repository_root=repository_root,
        )
        print(json.dumps(_summary(manifest, capture), sort_keys=True))
        return 0
    except (
        FotMobDataMatchesCaptureError,
        FotMobDataMatchesNetworkError,
    ) as exc:
        parser.exit(1, f"capture failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
