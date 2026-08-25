"""Leakage-safe historical as-of features with source-owned canonical issuance.

The reviewed Phase 2 implementation lives in ``_historical_asof_features_impl``.
This facade hardens its canonical construction boundary: targets, warehouse rows,
and team projections are accepted only when the exact live
``ReadOnlyHistoricalWarehouse`` instance issued them from rows it actually read.
Readable constructor tokens, source-instance attributes, and caller-created
private-looking attributes are therefore insufficient to manufacture canonical
warehouse ancestry.
"""
from __future__ import annotations

import weakref
from typing import Any, Iterable, Sequence

from . import _historical_asof_features_impl as _impl
from ._historical_asof_features_impl import *  # noqa: F401,F403

# Preserve the implementation's private research helpers for existing reviewed
# tests/callers. Hardened overrides below deliberately replace the canonical
# boundary helpers after this compatibility export.
for _name in dir(_impl):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


def _build_hardened_boundary() -> tuple[type[Any], Any, Any, Any]:
    """Create a closure-owned issuance boundary over the reviewed implementation.

    The issuance ledgers deliberately do not live on the source object or in
    module-level mutable dictionaries. Their only authority is object identity
    observed at actual warehouse-read time plus the exact content SHA frozen at
    issuance. This makes readable underscore tokens/attributes insufficient and
    prevents a caller from minting canonical ancestry by constructing a fresh
    object and recomputing its SHA.
    """

    base_warehouse = _impl.ReadOnlyHistoricalWarehouse
    unsafe_target = _impl._target
    unsafe_projection = _impl._projection
    unsafe_assemble_snapshot = _impl._assemble_snapshot

    # Closure-owned state only. Each source state is weakly held and contains
    # weak object-identity ledgers for rows, targets, and projections.
    source_by_token_id: dict[int, tuple[object, weakref.ReferenceType[Any]]] = {}
    source_states: dict[
        int,
        tuple[
            weakref.ReferenceType[Any],
            dict[str, dict[int, tuple[weakref.ReferenceType[Any], str]]],
        ],
    ] = {}

    def _register_source(source: Any) -> None:
        source_id = id(source)
        token = source._source_instance_token
        token_id = id(token)
        state: dict[str, dict[int, tuple[weakref.ReferenceType[Any], str]]] = {
            "rows": {},
            "targets": {},
            "projections": {},
        }

        def cleanup_source(reference: weakref.ReferenceType[Any]) -> None:
            current = source_states.get(source_id)
            if current is not None and current[0] is reference:
                source_states.pop(source_id, None)
            token_entry = source_by_token_id.get(token_id)
            if (
                token_entry is not None
                and token_entry[0] is token
                and token_entry[1] is reference
            ):
                source_by_token_id.pop(token_id, None)

        source_ref = weakref.ref(source, cleanup_source)
        source_states[source_id] = (source_ref, state)
        source_by_token_id[token_id] = (token, source_ref)

    def _unregister_source(source: Any) -> None:
        source_entry = source_states.get(id(source))
        if source_entry is not None and source_entry[0]() is source:
            source_states.pop(id(source), None)
        token = getattr(source, "_source_instance_token", None)
        if token is not None:
            token_entry = source_by_token_id.get(id(token))
            if (
                token_entry is not None
                and token_entry[0] is token
                and token_entry[1]() is source
            ):
                source_by_token_id.pop(id(token), None)

    def _state_for(
        source: Any,
    ) -> dict[str, dict[int, tuple[weakref.ReferenceType[Any], str]]]:
        entry = source_states.get(id(source))
        if entry is None or entry[0]() is not source:
            raise HistoricalAsOfError(
                "historical warehouse has no live canonical issuance state"
            )
        return entry[1]

    def _remember_issued(
        source: Any,
        registry_name: str,
        value: object,
        canonical_sha256: str,
    ) -> None:
        registry = _state_for(source)[registry_name]
        key = id(value)

        def cleanup_value(reference: weakref.ReferenceType[Any]) -> None:
            current = registry.get(key)
            if current is not None and current[0] is reference:
                registry.pop(key, None)

        reference = weakref.ref(value, cleanup_value)
        registry[key] = (reference, canonical_sha256)

    def _require_issued(
        source: Any,
        registry_name: str,
        value: object,
        canonical_sha256: str,
        label: str,
    ) -> None:
        registry = _state_for(source)[registry_name]
        entry = registry.get(id(value))
        if (
            entry is None
            or entry[0]() is not value
            or entry[1] != canonical_sha256
        ):
            raise HistoricalAsOfError(
                f"{label} was not issued unchanged by the bound historical warehouse"
            )

    class ReadOnlyHistoricalWarehouse(base_warehouse):
        """Read-only warehouse with closure-owned canonical issuance ledgers."""

        def __init__(self, path: Any) -> None:
            super().__init__(path)
            _register_source(self)

        def _register_bound_row(self, row: Any) -> Any:
            if not isinstance(row, _impl._SourceBoundWarehouseMatch):
                raise HistoricalAsOfError(
                    "historical source emitted an invalid bound row"
                )
            row.verify_integrity()
            if row.source_warehouse_sha256 != self.sha256:
                raise HistoricalAsOfError(
                    "bound row belongs to a different warehouse"
                )
            if row._source_instance_token is not self._source_instance_token:
                raise HistoricalAsOfError(
                    "bound row belongs to a different source instance"
                )
            _remember_issued(self, "rows", row, row.row_sha256)
            return row

        def _require_bound_row(self, row: Any) -> None:
            if not isinstance(row, _impl._SourceBoundWarehouseMatch):
                raise HistoricalAsOfError(
                    "canonical issuance requires a source-bound row"
                )
            row.verify_integrity()
            if row.source_warehouse_sha256 != self.sha256:
                raise HistoricalAsOfError(
                    "bound row belongs to a different warehouse"
                )
            if row._source_instance_token is not self._source_instance_token:
                raise HistoricalAsOfError(
                    "bound row belongs to a different source instance"
                )
            _require_issued(self, "rows", row, row.row_sha256, "warehouse row")

        def _bound_matches(
            self,
            where_sql: str = "",
            parameters: Sequence[Any] = (),
            order_sql: str = "",
        ) -> tuple[Any, ...]:
            rows = super()._bound_matches(where_sql, parameters, order_sql)
            return tuple(self._register_bound_row(row) for row in rows)

        def stream_matches(self) -> Iterable[Any]:
            for row in super().stream_matches():
                yield self._register_bound_row(row)

        def issue_target(self, row: Any) -> HistoricalAsOfTarget:
            self._require_bound_row(row)
            target = unsafe_target(row)
            _remember_issued(self, "targets", target, target.target_sha256)
            return target

        def issue_projection(self, row: Any, team: str) -> TeamMatchProjection:
            self._require_bound_row(row)
            projection = unsafe_projection(row, team)
            _remember_issued(
                self,
                "projections",
                projection,
                projection.projection_sha256,
            )
            return projection

        def verify_issued_target(self, target: Any) -> None:
            if not isinstance(target, HistoricalAsOfTarget):
                raise HistoricalAsOfError(
                    "canonical assembly requires a source-bound target"
                )
            target.verify_integrity()
            if target.source_warehouse_sha256 != self.sha256:
                raise HistoricalAsOfError(
                    "historical target belongs to a different warehouse"
                )
            if target._source_instance_token is not self._source_instance_token:
                raise HistoricalAsOfError(
                    "historical target belongs to a different source instance"
                )
            _require_issued(
                self,
                "targets",
                target,
                target.target_sha256,
                "historical target",
            )

        def verify_issued_projection(self, projection: Any) -> None:
            if not isinstance(projection, TeamMatchProjection):
                raise HistoricalAsOfError(
                    "canonical history requires source-bound projections"
                )
            projection.verify_integrity()
            if projection.source_warehouse_sha256 != self.sha256:
                raise HistoricalAsOfError(
                    "historical projection belongs to a different warehouse"
                )
            if projection._source_instance_token is not self._source_instance_token:
                raise HistoricalAsOfError(
                    "historical projection belongs to a different source instance"
                )
            _require_issued(
                self,
                "projections",
                projection,
                projection.projection_sha256,
                "historical projection",
            )

        def close(self) -> None:
            _unregister_source(self)
            super().close()

    def source_for_bound_row(row: Any) -> ReadOnlyHistoricalWarehouse:
        if not isinstance(row, _impl._SourceBoundWarehouseMatch):
            raise HistoricalAsOfError(
                "canonical issuance requires a source-bound row"
            )
        token = row._source_instance_token
        entry = source_by_token_id.get(id(token))
        if entry is None or entry[0] is not token:
            raise HistoricalAsOfError(
                "bound row has no live issuing warehouse"
            )
        source = entry[1]()
        if source is None:
            raise HistoricalAsOfError(
                "bound row issuing warehouse is no longer live"
            )
        source._require_bound_row(row)
        return source

    def target(row: Any) -> HistoricalAsOfTarget:
        """Issue a target only from a row actually emitted by its live warehouse."""
        return source_for_bound_row(row).issue_target(row)

    def projection(row: Any, team: str) -> TeamMatchProjection:
        """Issue a team projection only from an actually emitted warehouse row."""
        return source_for_bound_row(row).issue_projection(row, team)

    def assemble_snapshot(
        target_value: HistoricalAsOfTarget,
        home_history: Sequence[TeamMatchProjection],
        away_history: Sequence[TeamMatchProjection],
        source: ReadOnlyHistoricalWarehouse,
        registry_sha: str,
        generation_contract_sha: str,
    ) -> HistoricalAsOfFixtureSnapshot:
        """Assemble only source-issued, unchanged target/history objects."""
        if not isinstance(source, ReadOnlyHistoricalWarehouse):
            raise HistoricalAsOfError(
                "canonical assembly requires the source-owning historical warehouse"
            )
        source.verify_issued_target(target_value)
        for projection_value in (*home_history, *away_history):
            source.verify_issued_projection(projection_value)
        return unsafe_assemble_snapshot(
            target_value,
            home_history,
            away_history,
            source,
            registry_sha,
            generation_contract_sha,
        )

    return ReadOnlyHistoricalWarehouse, target, projection, assemble_snapshot


(
    ReadOnlyHistoricalWarehouse,
    _target,
    _projection,
    _assemble_snapshot,
) = _build_hardened_boundary()

# Patch the implementation module's runtime globals. Its public builders resolve
# these names at call time, so direct and bulk construction share this exact
# source-owned issuance boundary without duplicating the reviewed feature logic.
_impl.ReadOnlyHistoricalWarehouse = ReadOnlyHistoricalWarehouse
_impl._target = _target
_impl._projection = _projection
_impl._assemble_snapshot = _assemble_snapshot

# Remove the installer itself so the closure-owned ledgers are not exposed as a
# reusable module-level construction surface.
del _build_hardened_boundary
