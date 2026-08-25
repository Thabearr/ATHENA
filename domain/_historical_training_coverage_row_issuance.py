"""Closure-owned post-issuance integrity for canonical coverage rows.

The source-replaying builders are the only authority that may mint a canonical
HistoricalTrainingCoverageRow.  This layer freezes the exact canonical bytes at
issuance time so ordinary same-process mutation followed by SHA recomputation
cannot manufacture a new row that still claims the source warehouse ancestry.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence
import weakref

from domain.historical_asof_features import ReadOnlyHistoricalWarehouse


def install(module: Any) -> None:
    """Freeze final row bytes after all source/path hardening has completed."""

    Error = module.HistoricalTrainingCoverageError
    Row = module.HistoricalTrainingCoverageRow
    original_bytes_property = Row.__dict__.get("canonical_bytes")
    if not isinstance(original_bytes_property, property) or original_bytes_property.fget is None:
        raise RuntimeError("historical coverage canonical-bytes property is unavailable")
    raw_bytes = original_bytes_property.fget

    # id(row) -> (weak reference to that exact object, issuance bytes, issuance SHA).
    # Using object identity avoids relying on dataclass hashing: Resolution values
    # can contain dictionaries/lists and therefore are intentionally not hash keys.
    issued: dict[int, tuple[weakref.ReferenceType[Any], bytes, str]] = {}

    def register(row: Any) -> Any:
        if type(row) is not Row:
            raise Error("canonical coverage builder returned an unexpected row type")
        canonical = raw_bytes(row)
        digest = hashlib.sha256(canonical).hexdigest()
        key = id(row)

        def cleanup(reference: weakref.ReferenceType[Any], *, identity: int = key) -> None:
            state = issued.get(identity)
            if state is not None and state[0] is reference:
                issued.pop(identity, None)

        reference = weakref.ref(row, cleanup)
        issued[key] = (reference, canonical, digest)
        return row

    def require(row: Any) -> tuple[weakref.ReferenceType[Any], bytes, str]:
        state = issued.get(id(row))
        if state is None or state[0]() is not row:
            raise Error("canonical coverage row has no live source issuance state")
        current = raw_bytes(row)
        if current != state[1]:
            raise Error("canonical coverage row changed after source issuance")
        return state

    Row.canonical_bytes = property(lambda self: require(self)[1])
    Row.canonical_sha256 = property(lambda self: require(self)[2])

    original_batch = module.build_coverage_rows_from_bound_source

    def build_coverage_rows_from_bound_source(
        source: Any,
        rows: Sequence[Mapping[str, Any]],
        *,
        asof_corpus: Any | None = None,
        tactical_corpus: Any | None = None,
    ) -> tuple[Any, ...]:
        results = original_batch(
            source,
            rows,
            asof_corpus=asof_corpus,
            tactical_corpus=tactical_corpus,
        )
        return tuple(register(row) for row in results)

    def build_coverage_row_from_bound_source(
        source: Any,
        row: Mapping[str, Any],
        *,
        asof_corpus: Any | None = None,
        tactical_corpus: Any | None = None,
    ) -> Any:
        return build_coverage_rows_from_bound_source(
            source,
            (row,),
            asof_corpus=asof_corpus,
            tactical_corpus=tactical_corpus,
        )[0]

    def build_historical_training_coverage_row(
        warehouse_path: Path, match_key: str
    ) -> Any:
        with ReadOnlyHistoricalWarehouse(Path(warehouse_path)) as source:
            row = source.target_match(match_key)
            result = build_coverage_row_from_bound_source(source, row)
            source.assert_unchanged()
            return result

    module.build_coverage_rows_from_bound_source = build_coverage_rows_from_bound_source
    module.build_coverage_row_from_bound_source = build_coverage_row_from_bound_source
    module.build_historical_training_coverage_row = build_historical_training_coverage_row
    module.ROW_POST_ISSUANCE_INTEGRITY_POLICY_ID = (
        "CLOSURE_FROZEN_CANONICAL_ROW_BYTES_AND_SHA_V1"
    )
