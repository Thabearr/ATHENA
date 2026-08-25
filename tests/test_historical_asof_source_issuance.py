from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

import domain.historical_asof_features as haf
from domain.historical_asof_features import (
    HistoricalAsOfError,
    ReadOnlyHistoricalWarehouse,
    TeamMatchProjection,
    validate_historical_feature_registry,
    validate_historical_generation_contract,
)
from scripts.build_historical_warehouse import Warehouse


def _match(
    match_date: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    *,
    source_id: str,
    home_xg: float | None = None,
) -> dict:
    return {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": match_date,
        "kickoff_time": "20:00",
        "home_team": home,
        "away_team": away,
        "home_score_ft": home_score,
        "away_score_ft": away_score,
        "home_xg": home_xg,
        "_source_id": source_id,
    }


def _warehouse(tmp_path: Path) -> tuple[Path, list[str]]:
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    keys: list[str] = []
    for row in (
        _match(
            "2025-01-01", "Home", "Prior", 2, 0,
            source_id="prior", home_xg=1.4,
        ),
        _match(
            "2025-01-10", "Home", "Away", 0, 0,
            source_id="target",
        ),
    ):
        payload = dict(row)
        source_id = payload.pop("_source_id")
        keys.append(
            warehouse.upsert_match(
                payload,
                source_key="football_data_uk",
                source_match_id=source_id,
            )
        )
    warehouse.close()
    return path, keys


def _assembly_ids() -> tuple[str, str]:
    return (
        validate_historical_feature_registry(),
        validate_historical_generation_contract(),
    )


def test_readable_tokens_cannot_mint_fresh_sha_projection(tmp_path: Path) -> None:
    db, keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        target = haf._target(source.target_match(keys[-1]))
        row = source.historical_matches(
            "club", "eng_premier", "Home", "2025-01-10"
        )[0]
        legitimate = haf._projection(row, "Home")

        values = {
            field.name: getattr(legitimate, field.name)
            for field in dataclasses.fields(TeamMatchProjection)
            if field.name != "projection_sha256"
        }
        values["goals_for"] = 99
        values["xg_for"] = 99.0
        forged = TeamMatchProjection(
            _token=haf._PROJECTION_TOKEN,
            **values,
        )

        assert forged.projection_sha256 != legitimate.projection_sha256
        registry_sha, generation_sha = _assembly_ids()
        with pytest.raises(HistoricalAsOfError, match="not issued unchanged"):
            haf._assemble_snapshot(
                target,
                (forged,),
                (),
                source,
                registry_sha,
                generation_sha,
            )


def test_readable_tokens_cannot_mint_fresh_sha_target(tmp_path: Path) -> None:
    db, keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        legitimate = haf._target(source.target_match(keys[-1]))
        values = {
            field.name: getattr(legitimate, field.name)
            for field in dataclasses.fields(haf.HistoricalAsOfTarget)
            if field.name != "target_sha256"
        }
        values["match_key"] = "not-present-in-warehouse"
        forged = haf.HistoricalAsOfTarget(
            _token=haf._TARGET_TOKEN,
            **values,
        )

        assert forged.target_sha256 != legitimate.target_sha256
        registry_sha, generation_sha = _assembly_ids()
        with pytest.raises(HistoricalAsOfError, match="not issued unchanged"):
            haf._assemble_snapshot(
                forged,
                (),
                (),
                source,
                registry_sha,
                generation_sha,
            )


def test_forged_bound_row_with_real_source_token_cannot_be_issued(
    tmp_path: Path,
) -> None:
    db, keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        real = source.target_match(keys[-1])
        forged = haf._SourceBoundWarehouseMatch(
            _token=haf._BOUND_MATCH_TOKEN,
            source_warehouse_sha256=source.sha256,
            row_items=real.row_items,
            _source_instance_token=source._source_instance_token,
        )
        assert forged.row_sha256 == real.row_sha256
        with pytest.raises(HistoricalAsOfError, match="not issued unchanged"):
            source.issue_target(forged)


def test_issue_time_sha_rejects_post_issuance_mutation_even_when_rehashed(
    tmp_path: Path,
) -> None:
    db, keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        target = haf._target(source.target_match(keys[-1]))
        row = source.historical_matches(
            "club", "eng_premier", "Home", "2025-01-10"
        )[0]
        projection = haf._projection(row, "Home")

        object.__setattr__(projection, "goals_for", 99)
        identity = {
            field.name: getattr(projection, field.name)
            for field in dataclasses.fields(TeamMatchProjection)
            if field.name not in {"projection_sha256", "_source_instance_token"}
        }
        identity["field_source_keys"] = [list(item) for item in projection.field_source_keys]
        identity["conflict_fields"] = list(projection.conflict_fields)
        identity["blocked_primitives"] = list(projection.blocked_primitives)
        fresh_sha = hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        object.__setattr__(projection, "projection_sha256", fresh_sha)
        projection.verify_integrity()

        registry_sha, generation_sha = _assembly_ids()
        with pytest.raises(HistoricalAsOfError, match="not issued unchanged"):
            haf._assemble_snapshot(
                target,
                (projection,),
                (),
                source,
                registry_sha,
                generation_sha,
            )


def test_caller_created_private_ledger_attributes_have_no_authority(
    tmp_path: Path,
) -> None:
    db, keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        target = haf._target(source.target_match(keys[-1]))
        row = source.historical_matches(
            "club", "eng_premier", "Home", "2025-01-10"
        )[0]
        legitimate = haf._projection(row, "Home")
        values = {
            field.name: getattr(legitimate, field.name)
            for field in dataclasses.fields(TeamMatchProjection)
            if field.name != "projection_sha256"
        }
        values["goals_for"] = 99
        forged = TeamMatchProjection(_token=haf._PROJECTION_TOKEN, **values)

        # These attributes intentionally mimic the prior implementation's
        # readable mutable issuance ledgers. The hardened boundary ignores them.
        source._issued_bound_rows = {id(row): (None, row.row_sha256)}
        source._issued_targets = {id(target): (None, target.target_sha256)}
        source._issued_projections = {
            id(forged): (None, forged.projection_sha256)
        }

        registry_sha, generation_sha = _assembly_ids()
        with pytest.raises(HistoricalAsOfError, match="not issued unchanged"):
            haf._assemble_snapshot(
                target,
                (forged,),
                (),
                source,
                registry_sha,
                generation_sha,
            )


def test_issuance_state_and_unsafe_assembly_are_not_exposed_as_module_state(
    tmp_path: Path,
) -> None:
    assert not hasattr(haf, "_SOURCE_BY_TOKEN_ID")
    assert not hasattr(haf, "_UNSAFE_ASSEMBLE_SNAPSHOT")
    assert not hasattr(haf, "_build_hardened_boundary")

    db, _keys = _warehouse(tmp_path)
    with ReadOnlyHistoricalWarehouse(db) as source:
        assert "_issued_bound_rows" not in vars(source)
        assert "_issued_targets" not in vars(source)
        assert "_issued_projections" not in vars(source)
