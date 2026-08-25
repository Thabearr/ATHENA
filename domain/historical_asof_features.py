"""Leakage-safe historical as-of features with source-owned canonical issuance.

The reviewed Phase 2 implementation lives in ``_historical_asof_features_impl``.
This facade hardens its canonical construction boundary: targets, warehouse rows,
and team projections are accepted only when the exact live
``ReadOnlyHistoricalWarehouse`` instance issued them from rows it actually read.
Readable module constructor tokens are therefore insufficient to manufacture
canonical warehouse ancestry.
"""
from __future__ import annotations

import weakref
from typing import Any, Iterable, Sequence

from . import _historical_asof_features_impl as _impl
from ._historical_asof_features_impl import *  # noqa: F401,F403

# Preserve the implementation's private research helpers for existing reviewed
# tests/callers. Safe overrides below deliberately replace the canonical-boundary
# helpers after this compatibility export.
for _name in dir(_impl):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

_UNSAFE_TARGET = _impl._target
_UNSAFE_PROJECTION = _impl._projection
_UNSAFE_ASSEMBLE_SNAPSHOT = _impl._assemble_snapshot
_BASE_READ_ONLY_HISTORICAL_WAREHOUSE = _impl.ReadOnlyHistoricalWarehouse

# Resolve a source only by the exact token object owned by that live source.
# The row itself must additionally be present in that source's issuance ledger.
_SOURCE_BY_TOKEN_ID: dict[int, tuple[object, weakref.ReferenceType[Any]]] = {}


def _remember_issued(
    source: "ReadOnlyHistoricalWarehouse",
    registry_name: str,
    value: object,
    canonical_sha256: str,
) -> None:
    registry: dict[int, tuple[weakref.ReferenceType[Any], str]] = getattr(
        source, registry_name
    )
    key = id(value)
    source_ref = weakref.ref(source)

    def cleanup(reference: weakref.ReferenceType[Any]) -> None:
        owner = source_ref()
        if owner is None:
            return
        live_registry = getattr(owner, registry_name, None)
        if live_registry is None:
            return
        current = live_registry.get(key)
        if current is not None and current[0] is reference:
            live_registry.pop(key, None)

    reference = weakref.ref(value, cleanup)
    registry[key] = (reference, canonical_sha256)


def _require_issued(
    source: "ReadOnlyHistoricalWarehouse",
    registry_name: str,
    value: object,
    canonical_sha256: str,
    label: str,
) -> None:
    registry: dict[int, tuple[weakref.ReferenceType[Any], str]] = getattr(
        source, registry_name
    )
    entry = registry.get(id(value))
    if (
        entry is None
        or entry[0]() is not value
        or entry[1] != canonical_sha256
    ):
        raise HistoricalAsOfError(
            f"{label} was not issued unchanged by the bound historical warehouse"
        )


class ReadOnlyHistoricalWarehouse(_BASE_READ_ONLY_HISTORICAL_WAREHOUSE):
    """Read-only warehouse with bounded, source-owned canonical issuance ledgers."""

    def __init__(self, path: Any) -> None:
        self._issued_bound_rows: dict[
            int, tuple[weakref.ReferenceType[Any], str]
        ] = {}
        self._issued_targets: dict[
            int, tuple[weakref.ReferenceType[Any], str]
        ] = {}
        self._issued_projections: dict[
            int, tuple[weakref.ReferenceType[Any], str]
        ] = {}
        super().__init__(path)
        token = self._source_instance_token
        _SOURCE_BY_TOKEN_ID[id(token)] = (token, weakref.ref(self))

    def _register_bound_row(self, row: Any) -> Any:
        if not isinstance(row, _impl._SourceBoundWarehouseMatch):
            raise HistoricalAsOfError("historical source emitted an invalid bound row")
        row.verify_integrity()
        if row.source_warehouse_sha256 != self.sha256:
            raise HistoricalAsOfError("bound row belongs to a different warehouse")
        if row._source_instance_token is not self._source_instance_token:
            raise HistoricalAsOfError("bound row belongs to a different source instance")
        _remember_issued(self, "_issued_bound_rows", row, row.row_sha256)
        return row

    def _require_bound_row(self, row: Any) -> None:
        if not isinstance(row, _impl._SourceBoundWarehouseMatch):
            raise HistoricalAsOfError("canonical issuance requires a source-bound row")
        row.verify_integrity()
        if row.source_warehouse_sha256 != self.sha256:
            raise HistoricalAsOfError("bound row belongs to a different warehouse")
        if row._source_instance_token is not self._source_instance_token:
            raise HistoricalAsOfError("bound row belongs to a different source instance")
        _require_issued(
            self, "_issued_bound_rows", row, row.row_sha256, "warehouse row"
        )

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
        target = _UNSAFE_TARGET(row)
        _remember_issued(self, "_issued_targets", target, target.target_sha256)
        return target

    def issue_projection(self, row: Any, team: str) -> TeamMatchProjection:
        self._require_bound_row(row)
        projection = _UNSAFE_PROJECTION(row, team)
        _remember_issued(
            self,
            "_issued_projections",
            projection,
            projection.projection_sha256,
        )
        return projection

    def verify_issued_target(self, target: Any) -> None:
        if not isinstance(target, HistoricalAsOfTarget):
            raise HistoricalAsOfError("canonical assembly requires a source-bound target")
        target.verify_integrity()
        if target.source_warehouse_sha256 != self.sha256:
            raise HistoricalAsOfError("historical target belongs to a different warehouse")
        if target._source_instance_token is not self._source_instance_token:
            raise HistoricalAsOfError("historical target belongs to a different source instance")
        _require_issued(
            self, "_issued_targets", target, target.target_sha256, "historical target"
        )

    def verify_issued_projection(self, projection: Any) -> None:
        if not isinstance(projection, TeamMatchProjection):
            raise HistoricalAsOfError("canonical history requires source-bound projections")
        projection.verify_integrity()
        if projection.source_warehouse_sha256 != self.sha256:
            raise HistoricalAsOfError("historical projection belongs to a different warehouse")
        if projection._source_instance_token is not self._source_instance_token:
            raise HistoricalAsOfError(
                "historical projection belongs to a different source instance"
            )
        _require_issued(
            self,
            "_issued_projections",
            projection,
            projection.projection_sha256,
            "historical projection",
        )

    def close(self) -> None:
        token = getattr(self, "_source_instance_token", None)
        if token is not None:
            entry = _SOURCE_BY_TOKEN_ID.get(id(token))
            if entry is not None and entry[0] is token and entry[1]() is self:
                _SOURCE_BY_TOKEN_ID.pop(id(token), None)
        super().close()


def _source_for_bound_row(row: Any) -> ReadOnlyHistoricalWarehouse:
    if not isinstance(row, _impl._SourceBoundWarehouseMatch):
        raise HistoricalAsOfError("canonical issuance requires a source-bound row")
    token = row._source_instance_token
    entry = _SOURCE_BY_TOKEN_ID.get(id(token))
    if entry is None or entry[0] is not token:
        raise HistoricalAsOfError("bound row has no live issuing warehouse")
    source = entry[1]()
    if source is None:
        raise HistoricalAsOfError("bound row issuing warehouse is no longer live")
    source._require_bound_row(row)
    return source


def _target(row: Any) -> HistoricalAsOfTarget:
    """Issue a target only from a row actually emitted by its live warehouse."""
    return _source_for_bound_row(row).issue_target(row)


def _projection(row: Any, team: str) -> TeamMatchProjection:
    """Issue a team projection only from a row actually emitted by its warehouse."""
    return _source_for_bound_row(row).issue_projection(row, team)


def _assemble_snapshot(
    target: HistoricalAsOfTarget,
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
    source.verify_issued_target(target)
    for projection in (*home_history, *away_history):
        source.verify_issued_projection(projection)
    return _UNSAFE_ASSEMBLE_SNAPSHOT(
        target,
        home_history,
        away_history,
        source,
        registry_sha,
        generation_contract_sha,
    )


# Patch the implementation module's runtime globals. Its public builders resolve
# these names at call time, so direct and bulk construction share this exact
# source-owned issuance boundary without duplicating the reviewed feature logic.
_impl.ReadOnlyHistoricalWarehouse = ReadOnlyHistoricalWarehouse
_impl._target = _target
_impl._projection = _projection
_impl._assemble_snapshot = _assemble_snapshot

# Re-export hardened private boundary helpers explicitly.
globals()["_target"] = _target
globals()["_projection"] = _projection
globals()["_assemble_snapshot"] = _assemble_snapshot
