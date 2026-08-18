"""Explicit read-only capture of the reviewed public SportyBet Lite HTML surface."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import datetime as dt
import http.client
import json
import os
from pathlib import Path
from typing import Any, Callable

from domain.sportybet_lite_source_capture import (
    ALLOWED_HOST,
    ALLOWED_OUTPUT_RELATIVE,
    DEFAULT_MARKET_GROUP,
    FOOTBALL_SPORT_ID,
    HTTPS_PORT,
    MAX_RESPONSE_BYTES,
    REQUEST_HEADERS,
    CapturedSportyBetLiteResponse,
    SportyBetLiteCaptureError,
    SportyBetLiteRequestKind,
    canonical_manifest_bytes,
    request_target,
    sha256_bytes,
    store_capture,
    validate_html_content_type,
)
from domain.sportybet_provider_native_inventory import (
    SportyBetProviderInventoryError,
    build_inventory,
    canonical_inventory_bytes,
)


REQUEST_TIMEOUT_SECONDS = 30
READ_CHUNK_BYTES = 64 * 1024
INVENTORY_RELATIVE = Path(
    ".cache/athena-research/sportybet-provider-native-inventory"
)


class SportyBetLiteNetworkError(RuntimeError):
    """Raised when the explicit read-only SportyBet request fails."""


def _utc_clock() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_content_length(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise SportyBetLiteNetworkError("SportyBet returned an invalid Content-Length")
    parsed = int(value)
    if parsed > MAX_RESPONSE_BYTES:
        raise SportyBetLiteNetworkError("SportyBet response exceeds the 8 MiB limit")
    return parsed


def _read_bounded_body(response: Any) -> bytes:
    body = bytearray()
    while True:
        amount = min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES - len(body) + 1)
        try:
            chunk = response.read(amount)
        except (OSError, http.client.HTTPException) as exc:
            raise SportyBetLiteNetworkError(
                f"SportyBet response read failed: {type(exc).__name__}"
            ) from exc
        if type(chunk) is not bytes:
            raise SportyBetLiteNetworkError("SportyBet response chunk was not bytes")
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise SportyBetLiteNetworkError("SportyBet response exceeds the 8 MiB limit")
    if not body:
        raise SportyBetLiteNetworkError("SportyBet response body was empty")
    return bytes(body)


def fetch_sportybet_lite(
    *,
    request_kind: SportyBetLiteRequestKind,
    event_id: str | None = None,
    sport_id: str | None = None,
    market_groups_name: str | None = None,
    connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
    clock: Callable[[], dt.datetime] = _utc_clock,
) -> CapturedSportyBetLiteResponse:
    """Perform exactly one public, unauthenticated, cookie-free HTTPS GET."""

    target = request_target(
        request_kind,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_groups_name,
    )
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
            raise SportyBetLiteNetworkError(
                f"SportyBet Lite capture requires HTTP 200; received {status!r}"
            )
        try:
            content_type = validate_html_content_type(response.getheader("Content-Type"))
        except SportyBetLiteCaptureError as exc:
            raise SportyBetLiteNetworkError(str(exc)) from exc
        content_length = parse_content_length(response.getheader("Content-Length"))
        body = _read_bounded_body(response)
        if content_length is not None and content_length != len(body):
            raise SportyBetLiteNetworkError(
                "SportyBet Content-Length does not match received body"
            )
        observed_at = clock()
        if not isinstance(observed_at, dt.datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise SportyBetLiteNetworkError("acquisition clock must be timezone-aware")
        return CapturedSportyBetLiteResponse(
            status=status,
            content_type=content_type,
            content_length=content_length,
            body=body,
            observed_at=observed_at.astimezone(dt.timezone.utc),
            network_acquisition_performed=True,
        )
    except (SportyBetLiteCaptureError, SportyBetLiteNetworkError):
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise SportyBetLiteNetworkError(
            f"SportyBet Lite request failed: {type(exc).__name__}"
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _validate_inventory_root(repository_root: Path) -> Path:
    repository = repository_root.resolve(strict=True)
    root = repository / INVENTORY_RELATIVE
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise SportyBetLiteCaptureError(
                "inventory output root contains a forbidden symlink"
            )
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise SportyBetLiteCaptureError(
            "inventory output root must be a non-symlink directory"
        )
    return root


def _publish_inventory(
    *,
    repository_root: Path,
    capture_directory: Path,
    manifest: Any,
    raw_html: bytes,
) -> tuple[Path, str]:
    manifest_sha = sha256_bytes(canonical_manifest_bytes(manifest))
    inventory = build_inventory(
        manifest,
        raw_html,
        source_manifest_sha256=manifest_sha,
    )
    inventory_bytes = canonical_inventory_bytes(inventory)
    inventory_sha = sha256_bytes(inventory_bytes)
    root = _validate_inventory_root(repository_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{capture_directory.name}.json"
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise SportyBetLiteCaptureError("inventory path is not a regular file")
        existing = path.read_bytes()
        if existing != inventory_bytes:
            raise SportyBetLiteCaptureError(
                "refusing to overwrite differing provider-native inventory"
            )
        return path, inventory_sha
    try:
        with path.open("xb") as handle:
            handle.write(inventory_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise SportyBetLiteCaptureError("could not durably publish inventory") from exc
    return path, inventory_sha


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the public read-only SportyBet Lite HTML source. "
            "This command never logs in, sends cookies, builds a slip, or places a bet."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--index", action="store_true", help="capture /ng/lite")
    mode.add_argument("--event-id", help="capture one provider-native sr:match event")
    parser.add_argument(
        "--output-root",
        default=str(ALLOWED_OUTPUT_RELATIVE),
        help="must remain the reviewed ignored research capture root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = _repository_root()
    if args.index:
        request_kind = SportyBetLiteRequestKind.INDEX
        event_id = None
        sport_id = None
        market_group = None
    else:
        request_kind = SportyBetLiteRequestKind.EVENT_DETAIL
        event_id = args.event_id
        sport_id = FOOTBALL_SPORT_ID
        market_group = DEFAULT_MARKET_GROUP
    try:
        response = fetch_sportybet_lite(
            request_kind=request_kind,
            event_id=event_id,
            sport_id=sport_id,
            market_groups_name=market_group,
        )
        capture_directory, manifest = store_capture(
            response,
            request_kind=request_kind,
            repository_root=repository_root,
            output_root=Path(args.output_root),
            event_id=event_id,
            sport_id=sport_id,
            market_groups_name=market_group,
        )
        inventory_path, inventory_sha = _publish_inventory(
            repository_root=repository_root,
            capture_directory=capture_directory,
            manifest=manifest,
            raw_html=response.body,
        )
    except (SportyBetLiteCaptureError, SportyBetProviderInventoryError, SportyBetLiteNetworkError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "CAPTURED_SOURCE_EVIDENCE_ONLY",
                "capture_directory": str(capture_directory.relative_to(repository_root)),
                "manifest_sha256": sha256_bytes(canonical_manifest_bytes(manifest)),
                "raw_sha256": manifest.raw_sha256,
                "inventory_path": str(inventory_path.relative_to(repository_root)),
                "inventory_sha256": inventory_sha,
                "provider_quote_timestamp": None,
                "provider_snapshot_id": None,
                "bookmaker_equivalence_authorized": False,
                "pricing_authorized": False,
                "selection_authorized": False,
                "sportybet_execution_authorized": False,
                "bet_authorized": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
