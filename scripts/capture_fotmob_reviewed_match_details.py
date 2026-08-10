"""One-request durable raw capture for reviewed FotMob match details.

This operator boundary performs exactly one transparent request for one fixture
already admitted through the reviewed Fixture Intelligence bootstrap chain. It
preserves exact full response bytes plus the exact canonical PR #50 manifest.
No response-body JSON parsing or football-semantic interpretation occurs here.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import dataclasses
import datetime
import http.client
import os
from pathlib import Path
from typing import Any, Callable

from domain.fotmob_data_matches_capture import validate_json_content_type
from domain.fotmob_reviewed_match_details_capture import (
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    CapturedFotMobReviewedMatchDetailsResponse,
    FotMobReviewedMatchDetailsCaptureError,
    build_reviewed_match_details_raw_capture,
    reviewed_match_details_capture_identifier,
)
from domain.fotmob_reviewed_match_details_capture_artifact import (
    FotMobReviewedMatchDetailsCaptureArtifact,
    FotMobReviewedMatchDetailsCaptureArtifactError,
    build_reviewed_match_details_capture_artifact,
    revalidate_reviewed_match_details_capture_artifact,
)
from domain.fotmob_reviewed_match_details_probe import (
    ALLOWED_HOST,
    HTTPS_PORT,
    FotMobReviewedMatchDetailsProbeError,
    build_match_details_probe_plan,
    canonical_match_details_probe_plan_bytes,
)

ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/fotmob-reviewed-match-details-captures"
)
REQUEST_TIMEOUT_SECONDS = 30
READ_CHUNK_BYTES = 64 * 1024


class FotMobReviewedMatchDetailsDurableCaptureError(RuntimeError):
    """Raised when the controlled transport or durable publication fails closed."""


@dataclasses.dataclass(frozen=True)
class DurableMatchDetailsCaptureExecution:
    """Convenience result for one already-committed PR #50 artifact.

    This wrapper is deliberately not a downstream verifier. All state-dependent
    artifact revalidation occurs before durable publication; later consumers
    must independently revalidate the PR #50 artifact they intend to trust.
    """

    capture_directory: Path
    artifact: FotMobReviewedMatchDetailsCaptureArtifact

    def __post_init__(self) -> None:
        if not isinstance(self.capture_directory, Path):
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "capture_directory must be a pathlib.Path"
            )
        if type(self.artifact) is not FotMobReviewedMatchDetailsCaptureArtifact:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "artifact must be exact FotMobReviewedMatchDetailsCaptureArtifact"
            )


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_failure(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"


def _observed(
    clock: Callable[[], datetime.datetime],
    label: str,
) -> datetime.datetime:
    try:
        value = clock()
        if not isinstance(value, datetime.datetime):
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                f"{label} clock value must be a datetime"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                f"{label} clock value must be timezone-aware"
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobReviewedMatchDetailsDurableCaptureError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"{label} clock value is invalid"
        ) from exc


def _parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not str or not value or not value.isascii() or not value.isdigit():
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "Content-Length must be a non-negative ASCII integer"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "Content-Length is invalid"
        ) from exc
    if parsed > MAX_RESPONSE_BYTES:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "FotMob match-details response exceeds the 8 MiB capture limit"
        )
    return parsed


def _read_bounded_body(response: Any) -> bytes:
    body = bytearray()
    while True:
        amount = min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES - len(body) + 1)
        try:
            chunk = response.read(amount)
        except (OSError, http.client.HTTPException) as exc:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                f"FotMob response body read failed: {type(exc).__name__}"
            ) from exc
        if type(chunk) is not bytes:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "FotMob response body chunk was not exact bytes"
            )
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "FotMob match-details response exceeds the 8 MiB capture limit"
            )
    if not body:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "FotMob match-details response body was empty"
        )
    return bytes(body)


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
            raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "output root is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "output root must not contain traversal"
        )
    supplied_absolute = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(supplied_absolute, "output root")
    if supplied_absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "output root must be "
            ".cache/athena-research/fotmob-reviewed-match-details-captures"
        )
    if expected.exists() and (expected.is_symlink() or not expected.is_dir()):
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"could not durably synchronize directory {path}: "
            + "; ".join(failures)
        )


def _sync_directory(path: Path, *, platform_name: str | None = None) -> None:
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        _sync_windows_directory(path)
        return
    if platform != "posix":
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"could not durably synchronize directory {path}"
        ) from exc


def _ensure_directory_tree_durable(target: Path, *, boundary: Path) -> list[Path]:
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
                raise FotMobReviewedMatchDetailsDurableCaptureError(
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
                    raise FotMobReviewedMatchDetailsDurableCaptureError(
                        "refusing to remove a symlink"
                    )
                directory.rmdir()
                _sync_directory(directory.parent)
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{directory}: {_bounded_failure(cleanup_error)}"
                )
        if cleanup_failures:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "directory creation failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


@dataclasses.dataclass
class _CaptureTransactionState:
    capture_directory: Path
    capture_directory_owned: bool = False
    owned_final_files: set[Path] = dataclasses.field(default_factory=set)
    owned_temp_files: set[Path] = dataclasses.field(default_factory=set)


def _publish_no_overwrite(
    temporary: Path,
    final: Path,
    transaction: _CaptureTransactionState,
) -> None:
    if temporary not in transaction.owned_temp_files:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "temporary path is not transaction-owned"
        )
    if final.parent != transaction.capture_directory:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "final path is outside capture directory"
        )
    if final in transaction.owned_final_files:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "final path is already transaction-owned"
        )
    try:
        os.link(temporary, final)
    except FileExistsError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"capture output already exists and was not overwritten: {final}"
        ) from exc
    except OSError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
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
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "capture content must be exact bytes"
        )
    if not transaction.capture_directory_owned:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "capture directory is not transaction-owned"
        )
    if path.parent != transaction.capture_directory:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "capture output is outside owned directory"
        )
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        try:
            handle = temporary.open("xb")
        except FileExistsError as exc:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                f"capture temporary file already exists: {temporary}"
            ) from exc
        transaction.owned_temp_files.add(temporary)
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_no_overwrite(temporary, path, transaction)
    except Exception as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"could not durably write {path.name}: {_bounded_failure(exc)}"
        ) from exc


def _cleanup_owned_capture(transaction: _CaptureTransactionState) -> tuple[str, ...]:
    failures: list[str] = []
    directory = transaction.capture_directory
    for path in sorted(
        transaction.owned_temp_files | transaction.owned_final_files,
        key=lambda item: item.as_posix(),
    ):
        try:
            if path.parent != directory:
                raise FotMobReviewedMatchDetailsDurableCaptureError(
                    "owned path escaped capture directory"
                )
            if path.is_symlink():
                raise FotMobReviewedMatchDetailsDurableCaptureError(
                    "refusing to remove a symlink"
                )
            if path.exists():
                if not path.is_file():
                    raise FotMobReviewedMatchDetailsDurableCaptureError(
                        "owned path is not a regular file"
                    )
                path.unlink()
        except Exception as exc:
            failures.append(f"{path}: {_bounded_failure(exc)}")
    try:
        if directory.exists() and not directory.is_symlink():
            _sync_directory(directory)
    except Exception as exc:
        failures.append(f"{directory}: {_bounded_failure(exc)}")
    if transaction.capture_directory_owned:
        try:
            if directory.is_symlink():
                raise FotMobReviewedMatchDetailsDurableCaptureError(
                    "refusing to remove symlink capture directory"
                )
            if directory.exists():
                directory.rmdir()
                _sync_directory(directory.parent)
        except Exception as exc:
            failures.append(f"{directory}: {_bounded_failure(exc)}")
    return tuple(failures)


def _read_exact_regular_file(path: Path, *, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"published path is not a regular non-symlink file: {path.name}"
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"could not read published {path.name}"
        ) from exc
    if len(content) > maximum:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"published {path.name} exceeds its allowed size"
        )
    return content


def write_reviewed_match_details_capture_artifact(
    artifact: Any,
    *,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
    repository_root: Path | None = None,
) -> Path:
    """Durably publish one exact PR #50 artifact without overwriting evidence."""

    try:
        rebuilt = revalidate_reviewed_match_details_capture_artifact(artifact)
    except FotMobReviewedMatchDetailsCaptureArtifactError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "capture artifact failed current exact revalidation"
        ) from exc
    repository = (repository_root or _repository_root()).resolve(strict=True)
    root = validate_output_root(output_root, repository_root=repository)
    _ensure_directory_tree_durable(root, boundary=repository)
    _reject_symlink_components(root, "output root")

    identifier = reviewed_match_details_capture_identifier(rebuilt.capture)
    capture_directory = root / identifier
    transaction = _CaptureTransactionState(capture_directory=capture_directory)
    try:
        try:
            capture_directory.mkdir()
        except FileExistsError as exc:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "capture directory already exists; evidence was not overwritten"
            ) from exc
        transaction.capture_directory_owned = True
        _sync_directory(root)
        _sync_directory(capture_directory)

        _atomic_write(
            capture_directory / RAW_FILENAME,
            rebuilt.capture.raw_bytes,
            transaction,
        )
        _atomic_write(
            capture_directory / MANIFEST_FILENAME,
            rebuilt.manifest_bytes,
            transaction,
        )

        raw_disk = _read_exact_regular_file(
            capture_directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
        )
        manifest_disk = _read_exact_regular_file(
            capture_directory / MANIFEST_FILENAME,
            maximum=1024 * 1024,
        )
        if raw_disk != rebuilt.capture.raw_bytes:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "published response.json bytes differ from exact PR #50 raw bytes"
            )
        if manifest_disk != rebuilt.manifest_bytes:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "published manifest.json bytes differ from exact PR #50 canonical bytes"
            )
        _sync_directory(capture_directory)
        _sync_directory(root)
        return capture_directory
    except Exception as operation_error:
        cleanup_failures = _cleanup_owned_capture(transaction)
        if cleanup_failures:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "capture publication failed: "
                f"{_bounded_failure(operation_error)}; cleanup incomplete: "
                + "; ".join(cleanup_failures)
            ) from operation_error
        raise


def capture_fotmob_reviewed_match_details(
    *,
    verified_bootstrap_artifact: Any,
    verification_receipt_bytes: Any,
    fixture_identifier: Any,
    execute_live_network: Any,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
    repository_root: Path | None = None,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], datetime.datetime] = _utc_clock,
) -> DurableMatchDetailsCaptureExecution:
    """Perform exactly one reviewed full-body request and durably preserve it."""

    if type(execute_live_network) is not bool or execute_live_network is not True:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "one live capture requires exact execute_live_network=True"
        )

    request_started_at = _observed(clock, "request_started_at")
    try:
        plan = build_match_details_probe_plan(
            verified_bootstrap_artifact,
            verification_receipt_bytes,
            fixture_identifier=fixture_identifier,
            request_started_at=request_started_at,
        )
        plan_bytes = canonical_match_details_probe_plan_bytes(plan)
    except FotMobReviewedMatchDetailsProbeError as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "could not build exact PR #49 request plan"
        ) from exc

    connection = None
    try:
        connection = connection_factory(
            ALLOWED_HOST,
            HTTPS_PORT,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        connection.putrequest(
            "GET",
            plan.request_target,
            skip_accept_encoding=True,
        )
        for name, value in plan.request_headers:
            connection.putheader(name, value)

        request_send_at = _observed(clock, "request_send_at")
        try:
            plan = dataclasses.replace(plan)
            current_plan_bytes = canonical_match_details_probe_plan_bytes(plan)
        except (
            FotMobReviewedMatchDetailsProbeError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "PR #49 request plan failed final pre-send revalidation"
            ) from exc
        if current_plan_bytes != plan_bytes:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "PR #49 request plan bytes changed before network send"
            )
        if request_send_at < plan.request_started_at:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "request_send_at must not predate request_started_at"
            )
        if request_send_at >= plan.kickoff:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "request_send_at must be strictly before fixture kickoff"
            )

        connection.endheaders()
        response = connection.getresponse()
        status = getattr(response, "status", None)
        if type(status) is not int or status != 200:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "raw match-details capture requires exact HTTP 200"
            )
        content_type = response.getheader("Content-Type")
        try:
            validated_content_type = validate_json_content_type(content_type)
        except ValueError as exc:
            raise FotMobReviewedMatchDetailsDurableCaptureError(str(exc)) from exc
        content_length = _parse_content_length(
            response.getheader("Content-Length")
        )
        body = _read_bounded_body(response)
        if content_length is not None and content_length != len(body):
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "Content-Length does not match complete received body"
            )
        observed_at = _observed(clock, "observed_at")
        if observed_at < plan.request_started_at:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "observed_at must not predate request_started_at"
            )
        if observed_at >= plan.kickoff:
            raise FotMobReviewedMatchDetailsDurableCaptureError(
                "observed_at must be strictly before fixture kickoff"
            )

        captured_response = CapturedFotMobReviewedMatchDetailsResponse(
            status=status,
            content_type=validated_content_type,
            content_length=content_length,
            body=body,
            observed_at=observed_at,
            network_acquisition_performed=True,
        )
        raw_capture = build_reviewed_match_details_raw_capture(
            plan=plan,
            plan_bytes=plan_bytes,
            response=captured_response,
        )
        artifact = build_reviewed_match_details_capture_artifact(raw_capture)

        # The PR #50 artifact is revalidated inside the writer before the first
        # filesystem mutation. The durable publication and exact read-back are
        # the commit point; no live capability/state check is allowed after it.
        capture_directory = write_reviewed_match_details_capture_artifact(
            artifact,
            output_root=output_root,
            repository_root=repository_root,
        )
        return DurableMatchDetailsCaptureExecution(
            capture_directory=capture_directory,
            artifact=artifact,
        )
    except FotMobReviewedMatchDetailsDurableCaptureError:
        raise
    except (
        FotMobReviewedMatchDetailsCaptureError,
        FotMobReviewedMatchDetailsCaptureArtifactError,
    ) as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "PR #50 capture artifact construction failed closed"
        ) from exc
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            f"FotMob match-details network request failed: {type(exc).__name__}"
        ) from exc
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsDurableCaptureError(
            "FotMob match-details response handling failed: "
            f"{type(exc).__name__}"
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


__all__ = [
    "ALLOWED_OUTPUT_RELATIVE",
    "DurableMatchDetailsCaptureExecution",
    "FotMobReviewedMatchDetailsDurableCaptureError",
    "READ_CHUNK_BYTES",
    "REQUEST_TIMEOUT_SECONDS",
    "capture_fotmob_reviewed_match_details",
    "validate_output_root",
    "write_reviewed_match_details_capture_artifact",
]
