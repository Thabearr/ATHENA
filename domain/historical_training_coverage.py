"""Hardened public facade for ATHENA historical training coverage.

The implementation is intentionally split from this facade so canonical coverage
rows can only be minted by source-replaying builders.  Normal imports of both
``domain.historical_training_coverage`` and the underscore implementation name
are routed to this module by ``domain.__init__``.
"""
from __future__ import annotations

import hashlib
import importlib
import itertools
import json
import sqlite3
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


def _install_hardened_boundary() -> dict[str, Any]:
    impl = importlib.import_module("domain._historical_training_coverage_impl")

    from domain.historical_asof_features import (
        HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
        HISTORICAL_ASOF_DATASET,
        HISTORICAL_ASOF_SCHEMA_VERSION,
        HISTORICAL_COMPLETION_POLICY_ID,
        HISTORICAL_FEATURE_REGISTRY_VERSION,
        HISTORICAL_GENERATION_CONTRACT_VERSION,
        HISTORICAL_TEAM_IDENTITY_POLICY_ID,
        TEMPORAL_POLICY_ID,
        file_sha256,
        validate_historical_feature_registry,
        validate_historical_generation_contract,
    )
    from domain.tactical_identity import (
        COMPETITION_BASELINE_POLICY_ID,
        DESCRIPTOR_POLICY_ID,
        MANAGER_REGIME_POLICY_ID,
        MATCHUP_INTERACTION_POLICY_ID,
        OPPONENT_ADJUSTMENT_POLICY_ID,
        RECENCY_POLICY_ID,
        RECENCY_RELIABILITY_POLICY_ID,
        REGIME_PROFILE_POLICY_ID,
        SCHEDULE_CONTEXT_POLICY_ID,
        SCORE_STATE_POLICY_ID,
        SHRINKAGE_POLICY_ID,
        TACTICAL_GENERATION_CONTRACT_VERSION,
        TACTICAL_HISTORY_POLICY_ID,
        TACTICAL_IDENTITY_DATASET,
        TACTICAL_IDENTITY_REGISTRY_VERSION,
        TACTICAL_IDENTITY_SCHEMA_VERSION,
        validate_tactical_generation_contract,
        validate_tactical_identity_registry,
    )

    Error = impl.HistoricalTrainingCoverageError
    Resolution = impl.Resolution
    ResolutionStatus = impl.ResolutionStatus

    OWN_GOAL_ATTRIBUTION_POLICY_ID = (
        "SOURCE_SPECIFIC_STATSBOMB_OWN_GOAL_TYPE_AND_FJELSTUL_FLAG_V1"
    )
    MALFORMED_SCORE_POLICY_ID = "PRESENT_INVALID_REGULATION_SCORE_BLOCKS_V1"
    OPTIONAL_CORPUS_VALIDATION_POLICY_ID = (
        "FULL_FROZEN_META_ROW_AND_CROSS_CORPUS_BINDING_V1"
    )
    SOURCE_ISSUANCE_POLICY_ID = "SOURCE_REPLAYED_EVIDENCE_NO_CALLER_PAYLOADS_V1"
    OPTIONAL_JOIN_BATCH_POLICY_ID = "BOUNDED_SET_BASED_OPTIONAL_JOIN_V1"

    def _canonical_bytes(value: Any) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    def generation_contract_payload(
        *, registry_sha256: str, market_sha256: str
    ) -> dict[str, Any]:
        tactical_registry_sha = validate_tactical_identity_registry()
        tactical_generation_sha = validate_tactical_generation_contract(
            tactical_registry_sha256=tactical_registry_sha
        )
        payload = dict(
            impl.generation_contract_payload(
                registry_sha256=registry_sha256,
                market_sha256=market_sha256,
            )
        )
        payload.update(
            {
                "own_goal_attribution_policy_id": OWN_GOAL_ATTRIBUTION_POLICY_ID,
                "malformed_score_policy_id": MALFORMED_SCORE_POLICY_ID,
                "optional_corpus_validation_policy_id": (
                    OPTIONAL_CORPUS_VALIDATION_POLICY_ID
                ),
                "source_issuance_policy_id": SOURCE_ISSUANCE_POLICY_ID,
                "optional_join_batch_policy_id": OPTIONAL_JOIN_BATCH_POLICY_ID,
                "historical_asof_dataset": HISTORICAL_ASOF_DATASET,
                "historical_asof_schema_version": HISTORICAL_ASOF_SCHEMA_VERSION,
                "historical_feature_registry_version": (
                    HISTORICAL_FEATURE_REGISTRY_VERSION
                ),
                "historical_feature_registry_sha256": (
                    validate_historical_feature_registry()
                ),
                "historical_generation_contract_version": (
                    HISTORICAL_GENERATION_CONTRACT_VERSION
                ),
                "historical_generation_contract_sha256": (
                    validate_historical_generation_contract()
                ),
                "historical_temporal_policy_id": TEMPORAL_POLICY_ID,
                "historical_team_identity_policy_id": (
                    HISTORICAL_TEAM_IDENTITY_POLICY_ID
                ),
                "historical_completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
                "historical_advanced_period_safety_policy_id": (
                    HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID
                ),
                "tactical_dataset": TACTICAL_IDENTITY_DATASET,
                "tactical_schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
                "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
                "tactical_registry_sha256": tactical_registry_sha,
                "tactical_generation_contract_version": (
                    TACTICAL_GENERATION_CONTRACT_VERSION
                ),
                "tactical_generation_contract_sha256": tactical_generation_sha,
            }
        )
        return payload

    def calculate_label_generation_contract_sha256(
        *,
        registry_sha256: str,
        market_sha256: str,
        version: int = impl.LABEL_GENERATION_CONTRACT_VERSION,
    ) -> str:
        return hashlib.sha256(
            _canonical_bytes(
                {
                    "version": version,
                    "semantics": generation_contract_payload(
                        registry_sha256=registry_sha256,
                        market_sha256=market_sha256,
                    ),
                }
            )
        ).hexdigest()

    EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION = {
        1: "cf6434c6ad1a16e4ff8b6ca05a3a2c4d3b4d3d2c2fce60dd293640b40219b7ab",
    }

    def validate_contracts(
        *,
        registry_definitions: Sequence[Any] = impl.MARKET_LABEL_REGISTRY,
        registry_version: int = impl.MARKET_LABEL_REGISTRY_VERSION,
        expected_registry_by_version: Mapping[int, str] = (
            impl.EXPECTED_MARKET_LABEL_REGISTRY_SHA256_BY_VERSION
        ),
        market_registry: Mapping[Any, Any] = impl.MARKET_REGISTRY,
        expected_market_sha256: str = impl.EXPECTED_CANONICAL_MARKET_SEMANTICS_SHA256,
        generation_version: int = impl.LABEL_GENERATION_CONTRACT_VERSION,
        expected_generation_by_version: Mapping[int, str] = (
            EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION
        ),
    ) -> tuple[str, str, str]:
        registry = impl.calculate_market_label_registry_sha256(
            registry_definitions, registry_version
        )
        expected_registry = expected_registry_by_version.get(registry_version)
        if expected_registry is None or registry != expected_registry:
            raise Error("unreviewed market-label registry semantics")
        market = impl.calculate_canonical_market_semantics_sha256(market_registry)
        if market != expected_market_sha256:
            raise Error("canonical market semantics drift")
        generation = calculate_label_generation_contract_sha256(
            registry_sha256=registry,
            market_sha256=market,
            version=generation_version,
        )
        expected_generation = expected_generation_by_version.get(generation_version)
        if expected_generation is None or generation != expected_generation:
            raise Error("unreviewed label generation semantics")
        return registry, market, generation

    def _present_invalid_score(value: Any) -> bool:
        return value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        )

    def _score_resolution_state(
        row: Mapping[str, Any],
    ) -> tuple[Any, str | None, tuple[int, int] | None]:
        conflicts = impl._conflicts(row)
        if conflicts & set(impl._FT):
            return (
                ResolutionStatus.BLOCKED,
                "UNRESOLVED_REQUIRED_FT_CONFLICT",
                None,
            )
        home = impl._row_get(row, "home_score_ft")
        away = impl._row_get(row, "away_score_ft")
        if _present_invalid_score(home) or _present_invalid_score(away):
            return ResolutionStatus.BLOCKED, "INVALID_REGULATION_FT_SCORE", None
        if home is None or away is None:
            return ResolutionStatus.MISSING, None, None
        return ResolutionStatus.AVAILABLE, None, (home, away)

    def _half_resolution_state(
        row: Mapping[str, Any], ft: tuple[int, int] | None
    ) -> tuple[Any, str | None, tuple[int, int] | None]:
        if impl._conflicts(row) & set(impl._HT):
            return (
                ResolutionStatus.BLOCKED,
                "UNRESOLVED_REQUIRED_HALF_CONFLICT",
                None,
            )
        for field in ("home_score_ft", "away_score_ft"):
            if _present_invalid_score(impl._row_get(row, field)):
                return ResolutionStatus.BLOCKED, "INVALID_REGULATION_FT_SCORE", None
        home = impl._row_get(row, "home_score_ht")
        away = impl._row_get(row, "away_score_ht")
        if _present_invalid_score(home) or _present_invalid_score(away):
            return ResolutionStatus.BLOCKED, "INVALID_REGULATION_HT_SCORE", None
        if ft is None or home is None or away is None:
            return ResolutionStatus.MISSING, None, None
        if home > ft[0] or away > ft[1]:
            return ResolutionStatus.BLOCKED, "NEGATIVE_SECOND_HALF_SCORE", None
        return ResolutionStatus.AVAILABLE, None, (home, away)

    def _base_event_side(event: Mapping[str, Any], row: Mapping[str, Any]) -> str | None:
        team = event.get("team")
        if team == impl._row_get(row, "home_team"):
            return "HOME"
        if team == impl._row_get(row, "away_team"):
            return "AWAY"
        return None

    def _statsbomb_event_type(event: Mapping[str, Any]) -> str | None:
        details = event.get("details_json")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (TypeError, json.JSONDecodeError):
                return None
        if not isinstance(details, Mapping):
            return None
        value = details.get("type")
        return value if isinstance(value, str) and value else None

    def _event_side(event: Mapping[str, Any], row: Mapping[str, Any]) -> str | None:
        side = _base_event_side(event, row)
        if side is None:
            return None
        source = str(event.get("source_key") or "")
        own_goal = bool(event.get("is_own_goal"))
        if source == "statsbomb_open":
            if not own_goal:
                return side
            provider_type = _statsbomb_event_type(event)
            if provider_type == "Own Goal Against":
                return "AWAY" if side == "HOME" else "HOME"
            if provider_type == "Own Goal For":
                return side
            return None
        if source == "fjelstul_worldcup":
            return ("AWAY" if side == "HOME" else "HOME") if own_goal else side
        return None

    def _event_timestamp(
        event: Mapping[str, Any], period: int
    ) -> tuple[int, int, int, int] | None:
        minute = event.get("minute")
        if (
            isinstance(minute, bool)
            or not isinstance(minute, int)
            or minute < 0
        ):
            return None
        source = str(event.get("source_key") or "")
        if source == "statsbomb_open":
            second = event.get("second")
            if (
                isinstance(second, bool)
                or not isinstance(second, int)
                or second < 0
            ):
                return None
            return period, minute, 0, second
        if source == "fjelstul_worldcup":
            stoppage = event.get("stoppage_minute")
            if stoppage is None:
                stoppage = 0
            if (
                isinstance(stoppage, bool)
                or not isinstance(stoppage, int)
                or stoppage < 0
            ):
                return None
            return period, minute, stoppage, 0
        return None

    def evaluate_goal_path(
        row: Mapping[str, Any],
        preferred_events: Sequence[Mapping[str, Any]],
        has_approved_event_source: bool,
    ) -> tuple[Any, dict[str, bool] | None]:
        warehouse_sha = str(
            getattr(
                row,
                "source_warehouse_sha256",
                impl._row_get(row, "source_warehouse_sha256"),
            )
        )
        identity = impl._row_identity(row, warehouse_sha)
        ft_state, ft_blocker, ft = _score_resolution_state(row)
        if ft_state is ResolutionStatus.BLOCKED:
            return (
                Resolution(
                    ft_state,
                    blocker=ft_blocker,
                    evidence_identities=(identity,),
                ),
                None,
            )
        if ft is None:
            return Resolution(ResolutionStatus.MISSING), None
        path_conflicts = sorted(
            field
            for field in impl._conflicts(row)
            if "event" in field.lower() or "goal" in field.lower()
        )
        if path_conflicts:
            return (
                Resolution(
                    ResolutionStatus.BLOCKED,
                    blocker="UNRESOLVED_REQUIRED_GOAL_PATH_CONFLICT",
                    evidence_identities=(identity,),
                ),
                None,
            )
        goal_events = [
            event
            for event in preferred_events
            if str(event.get("event_type", "")).lower() == "goal"
        ]
        if not goal_events and not has_approved_event_source:
            return Resolution(ResolutionStatus.MISSING), None

        chronology: list[tuple[tuple[int, int, int, int], str]] = []
        for event in goal_events:
            source = str(event.get("source_key") or "")
            period = impl._regulation_period(source, event.get("period"))
            if period is None:
                if source == "statsbomb_open" and str(event.get("period")) in {
                    "3",
                    "4",
                    "5",
                }:
                    continue
                return (
                    Resolution(
                        ResolutionStatus.BLOCKED,
                        blocker="UNSUPPORTED_GOAL_PERIOD_SEMANTICS",
                        evidence_identities=(identity,),
                    ),
                    None,
                )
            side = _event_side(event, row)
            timestamp = _event_timestamp(event, period)
            if side is None or timestamp is None:
                return (
                    Resolution(
                        ResolutionStatus.BLOCKED,
                        blocker="INCOMPLETE_GOAL_ATTRIBUTION_OR_CHRONOLOGY",
                        evidence_identities=(identity,),
                    ),
                    None,
                )
            chronology.append((timestamp, side))

        if (
            sum(side == "HOME" for _, side in chronology) != ft[0]
            or sum(side == "AWAY" for _, side in chronology) != ft[1]
        ):
            return (
                Resolution(
                    ResolutionStatus.BLOCKED,
                    blocker="GOAL_PATH_DOES_NOT_RECONCILE_TO_REGULATION_FT",
                    evidence_identities=(identity,),
                ),
                None,
            )

        chronology.sort(key=lambda item: item[0])
        states = {(0, False, False, False, False)}
        for _, group_iter in itertools.groupby(chronology, key=lambda item: item[0]):
            sides = tuple(item[1] for item in group_iter)
            if len(sides) > 8:
                return (
                    Resolution(
                        ResolutionStatus.BLOCKED,
                        blocker="UNBOUNDED_SAME_TIMESTAMP_GOAL_AMBIGUITY",
                        evidence_identities=(identity,),
                    ),
                    None,
                )
            orders = (
                {sides}
                if len(set(sides)) == 1
                else set(itertools.permutations(sides))
            )
            next_states = set()
            for state in states:
                for order in orders:
                    margin, home1, away1, home2, away2 = state
                    for side in order:
                        margin += 1 if side == "HOME" else -1
                        home1 |= margin >= 1
                        away1 |= margin <= -1
                        home2 |= margin >= 2
                        away2 |= margin <= -2
                    next_states.add((margin, home1, away1, home2, away2))
            states = next_states
        trigger_states = {
            (state[1], state[2], state[3], state[4]) for state in states
        }
        if len(trigger_states) != 1:
            return (
                Resolution(
                    ResolutionStatus.BLOCKED,
                    blocker="ORDER_SENSITIVE_SAME_TIMESTAMP_GOALS",
                    evidence_identities=(identity,),
                ),
                None,
            )
        home1, away1, home2, away2 = next(iter(trigger_states))
        flags = {
            "1UP_HOME": home1,
            "1UP_AWAY": away1,
            "2UP_HOME": home2 or ft[0] > ft[1],
            "2UP_AWAY": away2 or ft[1] > ft[0],
        }
        event_ids = tuple(
            sorted(
                "PREFERRED_EVENT:" + str(event.get("event_key"))
                for event in goal_events
            )
        )
        return (
            Resolution(
                ResolutionStatus.AVAILABLE,
                value="COMPLETE",
                evidence_identities=(identity,) + event_ids,
            ),
            flags,
        )

    impl.validate_contracts = validate_contracts
    impl._score_resolution_state = _score_resolution_state
    impl._half_resolution_state = _half_resolution_state
    impl._event_side = _event_side
    impl._event_timestamp = _event_timestamp
    impl.evaluate_goal_path = evaluate_goal_path

    class ReadOnlyOptionalJoinCorpus:
        """Strict, SHA-bound validator for current Phase 2/Phase 3 corpora."""

        _KINDS = {
            "ASOF": (HISTORICAL_ASOF_DATASET, "historical_asof_snapshots"),
            "TACTICAL": (TACTICAL_IDENTITY_DATASET, "tactical_identity_snapshots"),
        }

        def __init__(
            self,
            path: Path,
            kind: str,
            expected_warehouse_sha256: str,
            *,
            expected_asof_sha256: str | None = None,
        ) -> None:
            self.kind = kind.upper()
            if self.kind not in self._KINDS:
                raise Error("unsupported optional corpus kind")
            self.path = Path(path).resolve()
            if not self.path.is_file():
                raise Error("optional corpus does not exist")
            self._assert_no_active_companions()
            self._before = self.path.stat()
            self.sha256 = file_sha256(self.path)
            self._assert_no_active_companions()
            self.connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro", uri=True
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only=ON")
            self.expected_warehouse_sha256 = expected_warehouse_sha256
            self.expected_asof_sha256 = expected_asof_sha256
            try:
                self._validate_schema_and_meta()
                self._assert_no_active_companions()
            except Exception:
                self.close()
                raise

        def _assert_no_active_companions(self) -> None:
            for suffix in ("-wal", "-journal"):
                companion = Path(str(self.path) + suffix)
                if companion.exists() and companion.stat().st_size:
                    raise Error("unsafe active optional-corpus companion")

        def _validate_schema_and_meta(self) -> None:
            expected_dataset, table = self._KINDS[self.kind]
            self.table = table
            objects = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"corpus_meta", table}.issubset(objects):
                raise Error("optional corpus schema mismatch")
            columns = {
                row[1]
                for row in self.connection.execute(f"PRAGMA table_info({table})")
            }
            if not {"match_key", "canonical_sha256", "payload_json"}.issubset(
                columns
            ):
                raise Error("optional corpus target table schema mismatch")
            raw = dict(self.connection.execute("SELECT key,value FROM corpus_meta"))
            try:
                meta = {key: json.loads(value) for key, value in raw.items()}
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise Error("invalid optional corpus metadata") from exc
            self.meta = MappingProxyType(meta)
            if meta.get("dataset") != expected_dataset:
                raise Error("optional corpus dataset mismatch")
            if meta.get("source_warehouse_sha256") != self.expected_warehouse_sha256:
                raise Error("optional corpus warehouse ancestry mismatch")

            if self.kind == "ASOF":
                expected = {
                    "generation_schema_version": HISTORICAL_ASOF_SCHEMA_VERSION,
                    "feature_registry_version": HISTORICAL_FEATURE_REGISTRY_VERSION,
                    "feature_registry_sha256": validate_historical_feature_registry(),
                    "generation_contract_version": HISTORICAL_GENERATION_CONTRACT_VERSION,
                    "generation_contract_sha256": validate_historical_generation_contract(),
                    "historical_completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
                    "historical_advanced_period_safety_policy_id": (
                        HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID
                    ),
                    "historical_team_identity_policy_id": (
                        HISTORICAL_TEAM_IDENTITY_POLICY_ID
                    ),
                    "temporal_policy_id": TEMPORAL_POLICY_ID,
                }
            else:
                tactical_registry_sha = validate_tactical_identity_registry()
                expected = {
                    "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
                    "historical_feature_registry_version": (
                        HISTORICAL_FEATURE_REGISTRY_VERSION
                    ),
                    "historical_feature_registry_sha256": (
                        validate_historical_feature_registry()
                    ),
                    "historical_generation_contract_version": (
                        HISTORICAL_GENERATION_CONTRACT_VERSION
                    ),
                    "historical_generation_contract_sha256": (
                        validate_historical_generation_contract()
                    ),
                    "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
                    "tactical_registry_sha256": tactical_registry_sha,
                    "tactical_generation_contract_version": (
                        TACTICAL_GENERATION_CONTRACT_VERSION
                    ),
                    "tactical_generation_contract_sha256": (
                        validate_tactical_generation_contract(
                            tactical_registry_sha256=tactical_registry_sha
                        )
                    ),
                    "recency_policy_id": RECENCY_POLICY_ID,
                    "recency_reliability_policy_id": RECENCY_RELIABILITY_POLICY_ID,
                    "competition_baseline_policy_id": COMPETITION_BASELINE_POLICY_ID,
                    "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
                    "manager_regime_policy_id": MANAGER_REGIME_POLICY_ID,
                    "regime_profile_policy_id": REGIME_PROFILE_POLICY_ID,
                    "opponent_adjustment_policy_id": OPPONENT_ADJUSTMENT_POLICY_ID,
                    "descriptor_policy_id": DESCRIPTOR_POLICY_ID,
                    "tactical_history_policy_id": TACTICAL_HISTORY_POLICY_ID,
                    "schedule_context_policy_id": SCHEDULE_CONTEXT_POLICY_ID,
                    "score_state_policy_id": SCORE_STATE_POLICY_ID,
                    "matchup_interaction_policy_id": MATCHUP_INTERACTION_POLICY_ID,
                }
                if (
                    self.expected_asof_sha256 is not None
                    and meta.get("source_asof_corpus_sha256")
                    != self.expected_asof_sha256
                ):
                    raise Error("tactical corpus as-of ancestry mismatch")
            if any(meta.get(key) != value for key, value in expected.items()):
                raise Error("optional corpus frozen contract mismatch")

        def _validate_join_row(self, row: sqlite3.Row) -> tuple[str, str]:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise Error("invalid optional corpus payload") from exc
            canonical = _canonical_bytes(payload)
            if canonical != row["payload_json"].encode("utf-8"):
                raise Error("optional corpus payload is not canonical")
            actual = hashlib.sha256(canonical).hexdigest()
            if actual != row["canonical_sha256"]:
                raise Error("optional corpus row identity mismatch")
            if payload.get("source_warehouse_sha256") != self.expected_warehouse_sha256:
                raise Error("optional corpus row ancestry mismatch")
            target = payload.get("target")
            if not isinstance(target, dict) or target.get("match_key") != row["match_key"]:
                raise Error("optional corpus row target mismatch")
            if self.kind == "ASOF":
                expected_payload = {
                    "dataset": HISTORICAL_ASOF_DATASET,
                    "feature_registry_version": HISTORICAL_FEATURE_REGISTRY_VERSION,
                    "feature_registry_sha256": validate_historical_feature_registry(),
                    "generation_contract_version": HISTORICAL_GENERATION_CONTRACT_VERSION,
                    "generation_contract_sha256": validate_historical_generation_contract(),
                    "generation_schema_version": HISTORICAL_ASOF_SCHEMA_VERSION,
                    "temporal_policy_id": TEMPORAL_POLICY_ID,
                    "team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
                    "completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
                    "advanced_period_safety_policy_id": (
                        HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID
                    ),
                }
            else:
                tactical_registry_sha = validate_tactical_identity_registry()
                expected_payload = {
                    "dataset": TACTICAL_IDENTITY_DATASET,
                    "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
                    "source_asof_corpus_sha256": self.meta.get(
                        "source_asof_corpus_sha256"
                    ),
                    "historical_feature_registry_version": (
                        HISTORICAL_FEATURE_REGISTRY_VERSION
                    ),
                    "historical_feature_registry_sha256": (
                        validate_historical_feature_registry()
                    ),
                    "historical_generation_contract_version": (
                        HISTORICAL_GENERATION_CONTRACT_VERSION
                    ),
                    "historical_generation_contract_sha256": (
                        validate_historical_generation_contract()
                    ),
                    "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
                    "tactical_registry_sha256": tactical_registry_sha,
                    "tactical_generation_contract_version": (
                        TACTICAL_GENERATION_CONTRACT_VERSION
                    ),
                    "tactical_generation_contract_sha256": (
                        validate_tactical_generation_contract(
                            tactical_registry_sha256=tactical_registry_sha
                        )
                    ),
                    "temporal_policy_id": TEMPORAL_POLICY_ID,
                    "team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
                    "recency_policy_id": RECENCY_POLICY_ID,
                    "recency_reliability_policy_id": RECENCY_RELIABILITY_POLICY_ID,
                    "competition_baseline_policy_id": COMPETITION_BASELINE_POLICY_ID,
                    "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
                    "manager_regime_policy_id": MANAGER_REGIME_POLICY_ID,
                    "regime_profile_policy_id": REGIME_PROFILE_POLICY_ID,
                    "opponent_adjustment_policy_id": OPPONENT_ADJUSTMENT_POLICY_ID,
                    "descriptor_policy_id": DESCRIPTOR_POLICY_ID,
                    "tactical_history_policy_id": TACTICAL_HISTORY_POLICY_ID,
                    "schedule_context_policy_id": SCHEDULE_CONTEXT_POLICY_ID,
                    "score_state_policy_id": SCORE_STATE_POLICY_ID,
                    "matchup_interaction_policy_id": MATCHUP_INTERACTION_POLICY_ID,
                }
            if any(payload.get(key) != value for key, value in expected_payload.items()):
                raise Error("optional corpus row frozen contract mismatch")
            return str(row["match_key"]), actual

        def join_identity(self, match_key: str) -> str | None:
            values = self.join_identities((match_key,))
            return values.get(match_key)

        def join_identities(self, match_keys: Sequence[str]) -> Mapping[str, str]:
            unique = tuple(dict.fromkeys(str(key) for key in match_keys))
            output: dict[str, str] = {}
            for offset in range(0, len(unique), 400):
                batch = unique[offset : offset + 400]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                for row in self.connection.execute(
                    f"SELECT match_key,canonical_sha256,payload_json FROM {self.table} "
                    f"WHERE match_key IN ({placeholders}) ORDER BY match_key",
                    batch,
                ):
                    key, sha = self._validate_join_row(row)
                    output[key] = sha
            return MappingProxyType(output)

        def assert_unchanged(self) -> None:
            self._assert_no_active_companions()
            after = self.path.stat()
            if (after.st_size, after.st_mtime_ns) != (
                self._before.st_size,
                self._before.st_mtime_ns,
            ):
                raise Error("optional corpus changed during audit")
            if file_sha256(self.path) != self.sha256:
                raise Error("optional corpus bytes changed during audit")
            self._assert_no_active_companions()

        def close(self) -> None:
            connection = getattr(self, "connection", None)
            if connection is not None:
                connection.close()
                self.connection = None

        def __enter__(self) -> "ReadOnlyOptionalJoinCorpus":
            return self

        def __exit__(self, *_args: Any) -> None:
            self.close()

    def _preferred_events_for_keys(
        source: Any, keys: Sequence[str]
    ) -> dict[str, tuple[Mapping[str, Any], ...]]:
        result: dict[str, list[Mapping[str, Any]]] = {key: [] for key in keys}
        if not keys:
            return {}
        for offset in range(0, len(keys), 400):
            batch = keys[offset : offset + 400]
            placeholders = ",".join("?" for _ in batch)
            for event in source.connection.execute(
                f"SELECT * FROM warehouse_events_preferred "
                f"WHERE match_key IN ({placeholders}) "
                "ORDER BY match_key,event_type,source_key,minute,"
                "stoppage_minute,second,event_key",
                batch,
            ):
                result[str(event["match_key"])].append(
                    MappingProxyType(dict(event))
                )
        return {key: tuple(values) for key, values in result.items()}

    def _counts_for_keys(
        source: Any, keys: Sequence[str]
    ) -> dict[str, Mapping[str, int]]:
        result: dict[str, dict[str, int]] = {key: {} for key in keys}
        if not keys:
            return result
        queries = {
            "home_lineups": "SELECT l.match_key,count(*) n FROM warehouse_lineups l JOIN warehouse_matches m ON m.match_key=l.match_key WHERE l.match_key IN ({}) AND l.team=m.home_team GROUP BY l.match_key",
            "away_lineups": "SELECT l.match_key,count(*) n FROM warehouse_lineups l JOIN warehouse_matches m ON m.match_key=l.match_key WHERE l.match_key IN ({}) AND l.team=m.away_team GROUP BY l.match_key",
            "home_coaches": "SELECT c.match_key,count(*) n FROM warehouse_coaches c JOIN warehouse_matches m ON m.match_key=c.match_key WHERE c.match_key IN ({}) AND c.team=m.home_team GROUP BY c.match_key",
            "away_coaches": "SELECT c.match_key,count(*) n FROM warehouse_coaches c JOIN warehouse_matches m ON m.match_key=c.match_key WHERE c.match_key IN ({}) AND c.team=m.away_team GROUP BY c.match_key",
            "referees": "SELECT match_key,count(*) n FROM warehouse_officials WHERE match_key IN ({}) AND role='referee' GROUP BY match_key",
            "advanced_sources": "SELECT match_key,count(*) n FROM warehouse_match_sources WHERE match_key IN ({}) AND has_advanced_stats=1 GROUP BY match_key",
            "provenance": "SELECT match_key,count(*) n FROM warehouse_field_provenance WHERE match_key IN ({}) GROUP BY match_key",
            "approved_event_sources": "SELECT match_key,count(*) n FROM warehouse_match_sources WHERE match_key IN ({}) AND has_events=1 AND source_key IN ('statsbomb_open','fjelstul_worldcup') GROUP BY match_key",
        }
        for offset in range(0, len(keys), 400):
            batch = keys[offset : offset + 400]
            placeholders = ",".join("?" for _ in batch)
            for name, template in queries.items():
                for row in source.connection.execute(
                    template.format(placeholders), batch
                ):
                    result[str(row["match_key"])][name] = int(row["n"])
        return {
            key: MappingProxyType(values) for key, values in result.items()
        }

    def _conflicts_for_keys(source: Any, keys: Sequence[str]) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {key: [] for key in keys}
        for offset in range(0, len(keys), 400):
            batch = keys[offset : offset + 400]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            for row in source.connection.execute(
                f"SELECT DISTINCT match_key,field_name FROM warehouse_conflicts "
                f"WHERE resolved=0 AND match_key IN ({placeholders}) "
                "ORDER BY match_key,field_name",
                batch,
            ):
                result[str(row["match_key"])].append(str(row["field_name"]))
        return {key: tuple(values) for key, values in result.items()}

    def build_coverage_rows_from_bound_source(
        source: Any,
        rows: Sequence[Mapping[str, Any]],
        *,
        asof_corpus: ReadOnlyOptionalJoinCorpus | None = None,
        tactical_corpus: ReadOnlyOptionalJoinCorpus | None = None,
    ) -> tuple[Any, ...]:
        for row in rows:
            source._require_bound_row(row)
        keys = [str(row["match_key"]) for row in rows]
        if not keys:
            return ()
        events = _preferred_events_for_keys(source, keys)
        counts = _counts_for_keys(source, keys)
        conflicts = _conflicts_for_keys(source, keys)
        asof_joins = (
            {} if asof_corpus is None else dict(asof_corpus.join_identities(keys))
        )
        tactical_joins = (
            {}
            if tactical_corpus is None
            else dict(tactical_corpus.join_identities(keys))
        )
        return tuple(
            impl._assemble_coverage_row(
                source,
                row,
                preferred_events=events[str(row["match_key"])],
                counts=counts[str(row["match_key"])],
                unresolved_conflict_fields=conflicts[str(row["match_key"])],
                asof_join_sha256=asof_joins.get(str(row["match_key"])),
                tactical_join_sha256=tactical_joins.get(str(row["match_key"])),
            )
            for row in rows
        )

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
        with impl.ReadOnlyHistoricalWarehouse(Path(warehouse_path)) as source:
            row = source.target_match(match_key)
            result = build_coverage_row_from_bound_source(source, row)
            source.assert_unchanged()
            return result

    exported: dict[str, Any] = {
        name: getattr(impl, name)
        for name in impl.__all__
        if name
        not in {
            "ReadOnlyOptionalJoinCorpus",
            "build_historical_training_coverage_row",
            "build_coverage_row_from_bound_source",
            "build_coverage_rows_from_bound_source",
            "calculate_label_generation_contract_sha256",
            "validate_contracts",
        }
    }
    exported.update(
        {
            "ReadOnlyOptionalJoinCorpus": ReadOnlyOptionalJoinCorpus,
            "build_historical_training_coverage_row": (
                build_historical_training_coverage_row
            ),
            "build_coverage_row_from_bound_source": (
                build_coverage_row_from_bound_source
            ),
            "build_coverage_rows_from_bound_source": (
                build_coverage_rows_from_bound_source
            ),
            "calculate_label_generation_contract_sha256": (
                calculate_label_generation_contract_sha256
            ),
            "generation_contract_payload": generation_contract_payload,
            "validate_contracts": validate_contracts,
            "EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION": (
                MappingProxyType(
                    dict(EXPECTED_LABEL_GENERATION_CONTRACT_SHA256_BY_VERSION)
                )
            ),
            "OWN_GOAL_ATTRIBUTION_POLICY_ID": OWN_GOAL_ATTRIBUTION_POLICY_ID,
            "MALFORMED_SCORE_POLICY_ID": MALFORMED_SCORE_POLICY_ID,
            "OPTIONAL_CORPUS_VALIDATION_POLICY_ID": (
                OPTIONAL_CORPUS_VALIDATION_POLICY_ID
            ),
            "SOURCE_ISSUANCE_POLICY_ID": SOURCE_ISSUANCE_POLICY_ID,
            "OPTIONAL_JOIN_BATCH_POLICY_ID": OPTIONAL_JOIN_BATCH_POLICY_ID,
            "MarketId": impl.MarketId,
            "MarketFamily": impl.MarketFamily,
            "MARKET_REGISTRY": impl.MARKET_REGISTRY,
            "EXPECTED_MARKET_LABEL_REGISTRY_SHA256_BY_VERSION": (
                impl.EXPECTED_MARKET_LABEL_REGISTRY_SHA256_BY_VERSION
            ),
            "EXPECTED_CANONICAL_MARKET_SEMANTICS_SHA256": (
                impl.EXPECTED_CANONICAL_MARKET_SEMANTICS_SHA256
            ),
            "EARLY_PAYOUT_SETTLEMENT_RECEIPT_SHA256": (
                impl.EARLY_PAYOUT_SETTLEMENT_RECEIPT_SHA256
            ),
        }
    )
    exported["__all__"] = tuple(sorted(exported))
    return exported


_exports = _install_hardened_boundary()
globals().update(_exports)
del _exports
del _install_hardened_boundary
