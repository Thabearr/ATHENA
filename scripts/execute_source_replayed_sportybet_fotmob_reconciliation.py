"""Execute the reviewed SportyBet -> FotMob reconciliation from preserved sources.

This operator is deliberately offline. It rebuilds every semantic value needed by
PR #164 from exact user-controlled SportyBet/Terms/Sportradar evidence, replays
the PR #165 reviewed FotMob catalog admission from raw captures plus the explicit
review ledger, then asks PR #164 to durably store the exact PR #163 full-UTC
reconciliation bytes.

No network acquisition, bookmaker equivalence, canonical market mapping, fresh
price, model/value, selection, slip, booking-code, execution, or BET authority is
created here.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import hashlib
import json
from pathlib import Path
import sys
from collections.abc import Sequence
from typing import Any

from domain import reviewed_fixture_catalog_admission as fotmob_admission
from domain import sportradar_user_controlled_event_metadata as sportradar_metadata
from domain import sportybet_event_local_time_basis as event_time_basis
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipt
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as event_identity
from domain import sportybet_sportradar_kickoff_identity_promotion as kickoff_promotion
from domain import sportybet_user_controlled_evidence as sportybet_evidence
from domain import sportybet_user_controlled_native_inventory as sportybet_inventory
from domain.fotmob_data_matches_capture import (
    MAX_RESPONSE_BYTES as FOTMOB_MAX_RESPONSE_BYTES,
    RAW_FILENAME as FOTMOB_RAW_FILENAME,
    FotMobDataMatchesCaptureError,
    FotMobDataMatchesCaptureManifest,
    canonical_data_matches_capture_manifest_bytes,
    verify_data_matches_capture_directory,
)
from domain.sportybet_lite_source_capture import (
    MAX_RESPONSE_BYTES as SPORTYBET_MAX_RESPONSE_BYTES,
    SportyBetLiteCaptureError,
    _read_regular,
)
from scripts.capture_fotmob_data_matches import (
    ALLOWED_OUTPUT_RELATIVE as FOTMOB_CAPTURE_ROOT_RELATIVE,
)
from scripts.replay_reviewed_fixture_catalog_admission import (
    ReviewedFixtureCatalogAdmissionReplayCLIError,
    revalidate_stored_admission_from_sources,
)


EXECUTION_STATUS = "SOURCE_REPLAYED_REAL_EVIDENCE_RECONCILIATION_EXECUTED"


class SourceReplayedSportyBetFotMobExecutionError(ValueError):
    """Raised when the offline real-evidence execution cannot fail closed."""


def _repository_root(value: Any) -> Path:
    try:
        repository = Path(value).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(
            "repository_root cannot be resolved"
        ) from exc
    if not repository.is_dir():
        raise SourceReplayedSportyBetFotMobExecutionError(
            "repository_root must be a directory"
        )
    return repository


def _path(value: Any, *, repository: Path, label: str) -> Path:
    try:
        supplied = Path(value)
    except (TypeError, ValueError) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(
            f"{label} path is invalid"
        ) from exc
    if ".." in supplied.parts:
        raise SourceReplayedSportyBetFotMobExecutionError(
            f"{label} path must not contain traversal"
        )
    return supplied if supplied.is_absolute() else repository / supplied


def _same_bytes_hash(raw: bytes, expected_sha256: str, expected_size: int, label: str) -> None:
    if type(raw) is not bytes or not raw:
        raise SourceReplayedSportyBetFotMobExecutionError(
            f"{label} must be non-empty exact bytes"
        )
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise SourceReplayedSportyBetFotMobExecutionError(
            f"{label} bytes do not match the revalidated source manifest"
        )


def _load_sportybet_event_sources(
    event_evidence_directory: Any,
    *,
    repository: Path,
):
    directory = _path(
        event_evidence_directory,
        repository=repository,
        label="SportyBet event evidence directory",
    )
    allowed_root = repository / sportybet_evidence.ALLOWED_OUTPUT_RELATIVE
    try:
        before = sportybet_evidence.verify_evidence_directory(
            directory,
            allowed_root=allowed_root,
        )
        raw = _read_regular(
            directory / sportybet_evidence.RAW_FILENAME,
            maximum=SPORTYBET_MAX_RESPONSE_BYTES,
            label="SportyBet event raw HTML",
        )
        after = sportybet_evidence.verify_evidence_directory(
            directory,
            allowed_root=allowed_root,
        )
        if (
            sportybet_evidence.canonical_manifest_bytes(before)
            != sportybet_evidence.canonical_manifest_bytes(after)
        ):
            raise SourceReplayedSportyBetFotMobExecutionError(
                "SportyBet event manifest changed while source bytes were read"
            )
        _same_bytes_hash(raw, after.raw_sha256, after.raw_size, "SportyBet event raw HTML")
        inventory = sportybet_inventory.build_inventory_from_evidence(
            directory,
            allowed_root=allowed_root,
        )
    except SourceReplayedSportyBetFotMobExecutionError:
        raise
    except (
        sportybet_evidence.SportyBetUserEvidenceError,
        sportybet_inventory.SportyBetUserInventoryError,
        SportyBetLiteCaptureError,
    ) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc
    return after, inventory, raw


def _load_terms_sources(
    terms_evidence_directory: Any,
    *,
    repository: Path,
):
    directory = _path(
        terms_evidence_directory,
        repository=repository,
        label="SportyBet Terms evidence directory",
    )
    allowed_root = repository / terms.ALLOWED_OUTPUT_RELATIVE
    try:
        before = terms.verify_evidence_directory(directory, allowed_root=allowed_root)
        raw = _read_regular(
            directory / terms.RAW_FILENAME,
            maximum=SPORTYBET_MAX_RESPONSE_BYTES,
            label="SportyBet Terms raw HTML",
        )
        after = terms.verify_evidence_directory(directory, allowed_root=allowed_root)
        if terms.canonical_qualification_bytes(before) != terms.canonical_qualification_bytes(after):
            raise SourceReplayedSportyBetFotMobExecutionError(
                "SportyBet Terms qualification changed while source bytes were read"
            )
        _same_bytes_hash(raw, after.raw_sha256, after.raw_size, "SportyBet Terms raw HTML")
    except SourceReplayedSportyBetFotMobExecutionError:
        raise
    except (terms.SportyBetOfficialTimeSemanticsError, SportyBetLiteCaptureError) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc
    return after, raw


def _load_sportradar_sources(
    sportradar_evidence_directory: Any,
    *,
    repository: Path,
    event_bridge: event_identity.SportyBetSportradarEventIdentityBridge,
    event_manifest: sportybet_evidence.SportyBetUserControlledEvidenceManifest,
    event_inventory: sportybet_inventory.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
):
    directory = _path(
        sportradar_evidence_directory,
        repository=repository,
        label="Sportradar evidence directory",
    )
    allowed_root = repository / sportradar_metadata.ALLOWED_OUTPUT_RELATIVE
    try:
        before = sportradar_metadata.verify_evidence_directory(
            directory,
            allowed_root=allowed_root,
        )
        raw = _read_regular(
            directory / sportradar_metadata.RAW_FILENAME,
            maximum=SPORTYBET_MAX_RESPONSE_BYTES,
            label="Sportradar raw response",
        )
        after = sportradar_metadata.verify_evidence_directory(
            directory,
            allowed_root=allowed_root,
        )
        if (
            sportradar_metadata.canonical_manifest_bytes(before)
            != sportradar_metadata.canonical_manifest_bytes(after)
        ):
            raise SourceReplayedSportyBetFotMobExecutionError(
                "Sportradar metadata manifest changed while source bytes were read"
            )
        _same_bytes_hash(raw, after.raw_sha256, after.raw_size, "Sportradar raw response")
        revalidated = sportradar_metadata.revalidate_event_metadata_evidence(
            after,
            raw,
            event_bridge=event_bridge,
            sportybet_manifest=event_manifest,
            sportybet_inventory=event_inventory,
            sportybet_raw_html=event_raw_html,
        )
    except SourceReplayedSportyBetFotMobExecutionError:
        raise
    except (
        sportradar_metadata.SportradarUserControlledEventMetadataError,
        SportyBetLiteCaptureError,
    ) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc
    return revalidated, raw


def _load_fotmob_capture_pairs(
    capture_directories: Sequence[Any],
    *,
    repository: Path,
) -> tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...]:
    if (
        not isinstance(capture_directories, Sequence)
        or isinstance(capture_directories, (str, bytes))
        or not capture_directories
    ):
        raise SourceReplayedSportyBetFotMobExecutionError(
            "at least one FotMob capture directory is required"
        )
    allowed_root = repository / FOTMOB_CAPTURE_ROOT_RELATIVE
    materialized: list[tuple[bytes, FotMobDataMatchesCaptureManifest]] = []
    seen_directories: set[Path] = set()
    for index, value in enumerate(capture_directories):
        directory = _path(
            value,
            repository=repository,
            label=f"FotMob capture directory {index}",
        )
        try:
            resolved = directory.resolve(strict=True)
        except OSError as exc:
            raise SourceReplayedSportyBetFotMobExecutionError(
                f"FotMob capture directory {index} cannot be resolved"
            ) from exc
        if resolved in seen_directories:
            raise SourceReplayedSportyBetFotMobExecutionError(
                "duplicate FotMob capture directory is forbidden"
            )
        seen_directories.add(resolved)
        try:
            before = verify_data_matches_capture_directory(
                directory,
                allowed_root=allowed_root,
                require_network_acquisition_performed=True,
            )
            raw = _read_regular(
                directory / FOTMOB_RAW_FILENAME,
                maximum=FOTMOB_MAX_RESPONSE_BYTES,
                label=f"FotMob capture {index} raw response",
            )
            after = verify_data_matches_capture_directory(
                directory,
                allowed_root=allowed_root,
                require_network_acquisition_performed=True,
            )
            if (
                canonical_data_matches_capture_manifest_bytes(before)
                != canonical_data_matches_capture_manifest_bytes(after)
            ):
                raise SourceReplayedSportyBetFotMobExecutionError(
                    "FotMob capture manifest changed while raw bytes were read"
                )
            _same_bytes_hash(
                raw,
                after.raw_sha256,
                after.raw_size,
                f"FotMob capture {index} raw response",
            )
        except SourceReplayedSportyBetFotMobExecutionError:
            raise
        except (FotMobDataMatchesCaptureError, SportyBetLiteCaptureError) as exc:
            raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc
        materialized.append((raw, after))
    return tuple(materialized)


def build_source_bundle(
    *,
    event_evidence_directory: Any,
    terms_evidence_directory: Any,
    sportradar_evidence_directory: Any,
    fotmob_capture_directories: Sequence[Any],
    fixture_review_decision_ledger: Any,
    check_catalog: Any,
    check_manifest: Any,
    fotmob_admission_directory: Any,
    repository_root: Any,
) -> receipt.FullUtcReconciliationSourceBundle:
    """Rebuild the complete PR #164 source bundle from durable source evidence."""

    repository = _repository_root(repository_root)
    event_manifest, event_inventory, event_raw_html = _load_sportybet_event_sources(
        event_evidence_directory,
        repository=repository,
    )
    terms_qualification, terms_raw_html = _load_terms_sources(
        terms_evidence_directory,
        repository=repository,
    )
    try:
        time_basis = event_time_basis.build_event_local_time_basis(
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
        )
        event_bridge = event_identity.build_sportradar_event_identity_bridge(
            manifest=event_manifest,
            inventory=event_inventory,
            raw_html=event_raw_html,
        )
    except (
        event_time_basis.SportyBetEventLocalTimeBasisError,
        event_identity.SportyBetSportradarEventIdentityError,
    ) as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc

    sportradar_evidence, sportradar_raw_response = _load_sportradar_sources(
        sportradar_evidence_directory,
        repository=repository,
        event_bridge=event_bridge,
        event_manifest=event_manifest,
        event_inventory=event_inventory,
        event_raw_html=event_raw_html,
    )
    try:
        promotion = kickoff_promotion.build_kickoff_identity_promotion(
            event_time_basis=time_basis,
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
            event_bridge=event_bridge,
            sportradar_evidence=sportradar_evidence,
            sportradar_raw_response=sportradar_raw_response,
        )
    except kickoff_promotion.SportyBetSportradarKickoffIdentityPromotionError as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc

    capture_paths = tuple(
        _path(
            value,
            repository=repository,
            label=f"FotMob capture directory {index}",
        )
        for index, value in enumerate(fotmob_capture_directories)
    )
    try:
        admission = revalidate_stored_admission_from_sources(
            _path(
                fotmob_admission_directory,
                repository=repository,
                label="FotMob admission directory",
            ),
            capture_directories=capture_paths,
            fixture_review_decision_ledger=_path(
                fixture_review_decision_ledger,
                repository=repository,
                label="fixture review decision ledger",
            ),
            check_catalog=_path(
                check_catalog,
                repository=repository,
                label="checked Fixture Catalog",
            ),
            check_manifest=_path(
                check_manifest,
                repository=repository,
                label="checked Fixture Catalog manifest",
            ),
            repository_root=repository,
        )
    except ReviewedFixtureCatalogAdmissionReplayCLIError as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc
    if (
        admission.decision.disposition
        is not fotmob_admission.ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ):
        raise SourceReplayedSportyBetFotMobExecutionError(
            "source-replayed FotMob catalog admission must be exact ADMITTED"
        )

    fotmob_captures = _load_fotmob_capture_pairs(
        capture_paths,
        repository=repository,
    )
    try:
        return receipt.FullUtcReconciliationSourceBundle(
            kickoff_promotion=promotion,
            event_time_basis=time_basis,
            event_manifest=event_manifest,
            event_inventory=event_inventory,
            event_raw_html=event_raw_html,
            terms_qualification=terms_qualification,
            terms_raw_html=terms_raw_html,
            event_bridge=event_bridge,
            sportradar_evidence=sportradar_evidence,
            sportradar_raw_response=sportradar_raw_response,
            fotmob_admission_value=admission,
            fotmob_captures=fotmob_captures,
        )
    except receipt.SportyBetFotMobFullUtcReconciliationReceiptError as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc


def execute_source_replayed_reconciliation(
    **kwargs: Any,
) -> dict[str, Any]:
    """Build the source bundle, store the exact receipt, and verify it again."""

    repository = _repository_root(kwargs["repository_root"])
    source_bundle = build_source_bundle(**kwargs)
    try:
        directory, result = receipt.store_reconciliation_receipt(
            source_bundle=source_bundle,
            repository_root=repository,
        )
        verified = receipt.verify_reconciliation_receipt_directory(
            directory,
            source_bundle=source_bundle,
            repository_root=repository,
        )
        if reconciliation.canonical_reconciliation_bytes(result) != reconciliation.canonical_reconciliation_bytes(
            verified
        ):
            raise SourceReplayedSportyBetFotMobExecutionError(
                "post-store reconciliation verification mismatch"
            )
        payload = reconciliation.canonical_reconciliation_bytes(verified)
    except SourceReplayedSportyBetFotMobExecutionError:
        raise
    except receipt.SportyBetFotMobFullUtcReconciliationReceiptError as exc:
        raise SourceReplayedSportyBetFotMobExecutionError(str(exc)) from exc

    matched = None if verified.matched_fixture is None else verified.matched_fixture.to_dict()
    return {
        "status": EXECUTION_STATUS,
        "receipt_directory": directory.relative_to(repository).as_posix(),
        "receipt_sha256": receipt.receipt_sha256_from_bytes(payload),
        "disposition": verified.disposition.value,
        "exact_match_count": verified.exact_match_count,
        "fixture_reconciliation_authorized": verified.fixture_reconciliation_authorized,
        "matched_fixture": matched,
        "bookmaker_equivalence_authorized": False,
        "canonical_market_mapping_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "model_integration_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "booking_code_authorized": False,
        "sportybet_execution_authorized": False,
        "bet_authorized": False,
        "athena_network_acquisition_performed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the reviewed SportyBet/FotMob full-UTC reconciliation entirely "
            "from preserved user-controlled and FotMob source evidence."
        )
    )
    parser.add_argument("--event-evidence-directory", required=True)
    parser.add_argument("--terms-evidence-directory", required=True)
    parser.add_argument("--sportradar-evidence-directory", required=True)
    parser.add_argument("--fotmob-capture-directory", action="append", required=True)
    parser.add_argument("--fixture-review-decision-ledger", required=True)
    parser.add_argument("--check-catalog", required=True)
    parser.add_argument("--check-manifest", required=True)
    parser.add_argument("--fotmob-admission-directory", required=True)
    parser.add_argument("--repository-root", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = execute_source_replayed_reconciliation(
            event_evidence_directory=args.event_evidence_directory,
            terms_evidence_directory=args.terms_evidence_directory,
            sportradar_evidence_directory=args.sportradar_evidence_directory,
            fotmob_capture_directories=tuple(args.fotmob_capture_directory),
            fixture_review_decision_ledger=args.fixture_review_decision_ledger,
            check_catalog=args.check_catalog,
            check_manifest=args.check_manifest,
            fotmob_admission_directory=args.fotmob_admission_directory,
            repository_root=args.repository_root,
        )
    except SourceReplayedSportyBetFotMobExecutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
