"""Final source-bound hardening for historical training coverage.

This module is installed by :mod:`domain` after the public coverage facade has
finished importing.  It adds exact source/corpus object issuance checks and
post-assembly canonical evidence normalization without exposing the hidden
coverage assembler.
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

        def validate_target_identities(
            self, rows: Sequence[Mapping[str, Any]]
        ) -> None:
            expected_by_key = {str(row["match_key"]): row for row in rows}
            keys = tuple(expected_by_key)
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
                    self._validate_join_row(record)
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
                    if any(target.get(key) != value for key, value in expected.items()):
                        raise Error("optional corpus target does not match bound warehouse")

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
        corpus.assert_unchanged()

    def _regulation_goal_evidence(
        source: ReadOnlyHistoricalWarehouse, match_key: str
    ) -> tuple[str, ...]:
        identities: list[str] = []
        for event in source.connection.execute(
            "SELECT event_key,source_key,period FROM warehouse_events_preferred "
            "WHERE match_key=? AND event_type='goal' ORDER BY event_key",
            (match_key,),
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
                identities.append("PREFERRED_EVENT:" + str(event["event_key"]))
        return tuple(sorted(identities))

    def _normalize_path_evidence(
        source: ReadOnlyHistoricalWarehouse,
        result: Any,
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
        evidence = (match_identity,) + _regulation_goal_evidence(
            source, str(result.match_key)
        )
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
        results = original_batch(
            source,
            rows,
            asof_corpus=asof_corpus,
            tactical_corpus=tactical_corpus,
        )
        if len(results) != len(rows):
            raise Error("source-replayed coverage cardinality mismatch")
        normalized = tuple(_normalize_path_evidence(source, result) for result in results)
        source.assert_unchanged()
        if asof_corpus is not None:
            asof_corpus.assert_unchanged()
        if tactical_corpus is not None:
            tactical_corpus.assert_unchanged()
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
