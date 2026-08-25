"""Final source-bound hardening for historical training coverage.

Installed by :mod:`domain` after the public coverage facade has initialized.
The boundary freezes exact optional-corpus objects in closure-owned state,
requires the canonical read-only warehouse class, validates optional target
identity against source-issued warehouse rows, and normalizes path evidence to
regulation-contributing events only.  Batch checks remain bounded and avoid
rehashing multi-gigabyte sources per target batch; the offline builder performs
full byte-stability checks once after construction.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import weakref

from domain.historical_asof_features import ReadOnlyHistoricalWarehouse


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def install(module: Any) -> None:
    """Install exact-object checks over one fully initialized coverage facade."""

    Error = module.HistoricalTrainingCoverageError
    ResolutionStatus = module.ResolutionStatus
    Resolution = module.Resolution
    EvidenceCapabilityId = module.EvidenceCapabilityId
    BaseOptionalCorpus = module.ReadOnlyOptionalJoinCorpus
    original_batch = module.build_coverage_rows_from_bound_source

    issued: weakref.WeakKeyDictionary[Any, tuple[Any, ...]] = weakref.WeakKeyDictionary()
    join_cache: weakref.WeakKeyDictionary[
        Any, dict[str, str | None]
    ] = weakref.WeakKeyDictionary()

    def _is_sha256(value: Any) -> bool:
        return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None

    class ReadOnlyOptionalJoinCorpus(BaseOptionalCorpus):
        """Optional corpus whose exact constructor state is frozen in a closure."""

        def __init__(
            self,
            path: Path,
            kind: str,
            expected_warehouse_sha256: str,
            *,
            expected_asof_sha256: str | None = None,
        ) -> None:
            super().__init__(
                path,
                kind,
                expected_warehouse_sha256,
                expected_asof_sha256=expected_asof_sha256,
            )
            if not _is_sha256(self.sha256):
                self.close()
                raise Error("optional corpus SHA-256 is invalid")
            if not _is_sha256(expected_warehouse_sha256):
                self.close()
                raise Error("optional corpus warehouse SHA-256 is invalid")
            source_asof = self.meta.get("source_asof_corpus_sha256")
            if self.kind == "TACTICAL" and not _is_sha256(source_asof):
                self.close()
                raise Error("tactical corpus source as-of SHA-256 is invalid")
            if expected_asof_sha256 is not None and not _is_sha256(expected_asof_sha256):
                self.close()
                raise Error("expected as-of corpus SHA-256 is invalid")
            issued[self] = (
                self.kind,
                self.path,
                self.sha256,
                expected_warehouse_sha256,
                expected_asof_sha256,
                id(self.connection),
                source_asof,
            )
            join_cache[self] = {}

        def validate_target_identities(
            self, rows: Sequence[Mapping[str, Any]]
        ) -> None:
            expected_by_key = {str(row["match_key"]): row for row in rows}
            keys = tuple(expected_by_key)
            cache: dict[str, str | None] = {key: None for key in keys}
            for offset in range(0, len(keys), 400):
                batch = keys[offset : offset + 400]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                for record in self.connection.execute(
                    f"SELECT match_key,canonical_sha256,payload_json FROM {self.table} "
                    f"WHERE match_key IN ({placeholders}) ORDER BY match_key",
                    batch,
                ):
                    key, sha = self._validate_join_row(record)
                    try:
                        payload = json.loads(record["payload_json"])
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise Error("invalid optional corpus payload") from exc
                    target = payload.get("target")
                    if not isinstance(target, dict):
                        raise Error("optional corpus target payload missing")
                    warehouse_row = expected_by_key[str(record["match_key"])]
                    expected = {
                        "match_key": str(warehouse_row["match_key"]),
                        "match_date": str(warehouse_row["match_date"]),
                        "competition_key": warehouse_row["competition_key"],
                        "scope": str(warehouse_row["scope"]),
                        "home_team": str(warehouse_row["home_team"]),
                        "away_team": str(warehouse_row["away_team"]),
                    }
                    if any(target.get(name) != value for name, value in expected.items()):
                        raise Error("optional corpus target does not match bound warehouse")
                    cache[str(key)] = sha
            join_cache[self] = cache

        def join_identities(self, match_keys: Sequence[str]) -> Mapping[str, str]:
            keys = tuple(dict.fromkeys(str(key) for key in match_keys))
            cache = join_cache.get(self, {})
            if all(key in cache for key in keys):
                return MappingProxyType(
                    {key: cache[key] for key in keys if cache[key] is not None}
                )
            return super().join_identities(keys)

    def _fast_source_stability(source: ReadOnlyHistoricalWarehouse) -> None:
        source._assert_no_active_companions()
        after = source.path.stat()
        before = source._before_stat
        if (after.st_size, after.st_mtime_ns) != (
            before.st_size,
            before.st_mtime_ns,
        ):
            raise Error("historical warehouse changed during coverage replay")
        source._assert_no_active_companions()

    def _fast_optional_stability(corpus: ReadOnlyOptionalJoinCorpus) -> None:
        corpus._assert_no_active_companions()
        after = corpus.path.stat()
        before = corpus._before
        if (after.st_size, after.st_mtime_ns) != (
            before.st_size,
            before.st_mtime_ns,
        ):
            raise Error("optional corpus changed during coverage replay")
        corpus._assert_no_active_companions()

    def _require_optional(
        corpus: Any,
        *,
        kind: str,
        source: ReadOnlyHistoricalWarehouse,
        expected_asof_sha256: str | None = None,
    ) -> None:
        if type(corpus) is not ReadOnlyOptionalJoinCorpus:
            raise Error("optional corpus must be issued by the canonical read-only validator")
        state = issued.get(corpus)
        if state is None:
            raise Error("optional corpus has no live canonical issuance state")
        frozen = (
            corpus.kind,
            corpus.path,
            corpus.sha256,
            corpus.expected_warehouse_sha256,
            corpus.expected_asof_sha256,
            id(corpus.connection),
            corpus.meta.get("source_asof_corpus_sha256"),
        )
        if frozen != state:
            raise Error("optional corpus changed after canonical issuance")
        if corpus.kind != kind or corpus.expected_warehouse_sha256 != source.sha256:
            raise Error("optional corpus source binding mismatch")
        if expected_asof_sha256 is not None:
            if corpus.expected_asof_sha256 != expected_asof_sha256:
                raise Error("tactical corpus expected as-of binding mismatch")
            if corpus.meta.get("source_asof_corpus_sha256") != expected_asof_sha256:
                raise Error("tactical corpus source as-of ancestry mismatch")
        _fast_optional_stability(corpus)

    def _regulation_goal_evidence_by_key(
        source: ReadOnlyHistoricalWarehouse,
        rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, tuple[str, ...]]:
        keys = tuple(str(row["match_key"]) for row in rows)
        result: dict[str, list[str]] = {key: [] for key in keys}
        for offset in range(0, len(keys), 400):
            batch = keys[offset : offset + 400]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            for event in source.connection.execute(
                f"SELECT match_key,event_key,source_key,period "
                f"FROM warehouse_events_preferred WHERE event_type='goal' "
                f"AND match_key IN ({placeholders}) ORDER BY match_key,event_key",
                batch,
            ):
                source_key = str(event["source_key"])
                period = event["period"]
                regulation = False
                if source_key == "statsbomb_open":
                    regulation = str(period) in {"1", "2"}
                elif source_key == "fjelstul_worldcup" and isinstance(period, str):
                    normalized = period.strip().lower().replace("_", " ")
                    regulation = (
                        ("first" in normalized and "half" in normalized)
                        or ("second" in normalized and "half" in normalized)
                    )
                if regulation:
                    result[str(event["match_key"])].append(
                        "PREFERRED_EVENT:" + str(event["event_key"])
                    )
        return {key: tuple(sorted(values)) for key, values in result.items()}

    def _normalize_path_evidence(
        source: ReadOnlyHistoricalWarehouse,
        result: Any,
        regulation_event_ids: tuple[str, ...],
    ) -> Any:
        capabilities = dict(result.capabilities)
        capability_id = EvidenceCapabilityId.COMPLETE_REGULATION_GOAL_PATH.value
        path = capabilities[capability_id]
        if path.status is not ResolutionStatus.AVAILABLE:
            return result
        match_identity = (
            "WAREHOUSE_MATCH:"
            + source.sha256
            + ":"
            + str(result.match_key)
        )
        evidence = (match_identity,) + regulation_event_ids
        capabilities[capability_id] = Resolution(
            path.status,
            value=path.value,
            blocker=path.blocker,
            evidence_identities=evidence,
        )
        labels = dict(result.labels)
        for threshold in (1, 2):
            for side in ("HOME", "AWAY"):
                key = f"MATCH_RESULT_{threshold}UP_{side}"
                label = labels[key]
                if label.status is ResolutionStatus.AVAILABLE:
                    labels[key] = Resolution(
                        label.status,
                        value=label.value,
                        blocker=label.blocker,
                        evidence_identities=evidence,
                    )
        object.__setattr__(result, "capabilities", tuple(sorted(capabilities.items())))
        object.__setattr__(result, "labels", tuple(sorted(labels.items())))
        return result

    def build_coverage_rows_from_bound_source(
        source: Any,
        rows: Sequence[Mapping[str, Any]],
        *,
        asof_corpus: ReadOnlyOptionalJoinCorpus | None = None,
        tactical_corpus: ReadOnlyOptionalJoinCorpus | None = None,
    ) -> tuple[Any, ...]:
        if type(source) is not ReadOnlyHistoricalWarehouse:
            raise Error("coverage source must be the canonical read-only warehouse")
        _fast_source_stability(source)
        for row in rows:
            source._require_bound_row(row)
        if asof_corpus is not None:
            _require_optional(asof_corpus, kind="ASOF", source=source)
            asof_corpus.validate_target_identities(rows)
        if tactical_corpus is not None:
            expected_asof = None if asof_corpus is None else asof_corpus.sha256
            _require_optional(
                tactical_corpus,
                kind="TACTICAL",
                source=source,
                expected_asof_sha256=expected_asof,
            )
            tactical_corpus.validate_target_identities(rows)
        regulation_evidence = _regulation_goal_evidence_by_key(source, rows)
        results = original_batch(
            source,
            rows,
            asof_corpus=asof_corpus,
            tactical_corpus=tactical_corpus,
        )
        if len(results) != len(rows):
            raise Error("source-replayed coverage cardinality mismatch")
        normalized = tuple(
            _normalize_path_evidence(
                source,
                result,
                regulation_evidence[str(result.match_key)],
            )
            for result in results
        )
        _fast_source_stability(source)
        if asof_corpus is not None:
            _fast_optional_stability(asof_corpus)
        if tactical_corpus is not None:
            _fast_optional_stability(tactical_corpus)
        return normalized

    def build_coverage_row_from_bound_source(
        source: Any,
        row: Mapping[str, Any],
        *,
        asof_corpus: ReadOnlyOptionalJoinCorpus | None = None,
        tactical_corpus: ReadOnlyOptionalJoinCorpus | None = None,
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

    module.ReadOnlyOptionalJoinCorpus = ReadOnlyOptionalJoinCorpus
    module.build_coverage_rows_from_bound_source = build_coverage_rows_from_bound_source
    module.build_coverage_row_from_bound_source = build_coverage_row_from_bound_source
    module.build_historical_training_coverage_row = build_historical_training_coverage_row
    module.OPTIONAL_CORPUS_OBJECT_ISSUANCE_POLICY_ID = (
        "CLOSURE_FROZEN_EXACT_OPTIONAL_CORPUS_OBJECT_V1"
    )
    module.OPTIONAL_TARGET_IDENTITY_POLICY_ID = (
        "EXACT_BOUND_WAREHOUSE_TARGET_IDENTITY_V1"
    )
    module.REGULATION_PATH_EVIDENCE_POLICY_ID = (
        "CANONICAL_SHA_INCLUDES_REGULATION_CONTRIBUTING_EVENTS_ONLY_V1"
    )
    module.BATCH_STABILITY_POLICY_ID = (
        "FAST_STAT_COMPANION_PER_BATCH_FULL_SHA_AT_BUILDER_END_V1"
    )
