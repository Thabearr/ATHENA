from __future__ import annotations

import ast
from pathlib import Path

from domain.ingest_contracts import FORBIDDEN_AUTHORITIES


INGEST_FILES = (
    "domain/ingest_contracts.py",
    "services/athena_ingest_service.py",
    "scripts/resolve_athena_ingest_workflow_request.py",
    "scripts/execute_athena_ingest_workflow.py",
    "scripts/replay_athena_ingest_artifact.py",
)


def test_ingest_code_has_no_betting_or_model_imports() -> None:
    forbidden = (
        "sportybet", "pricing", "router", "portfolio", "share_code",
        "prediction", "model_execution", "wallet", "wager", "stake",
    )
    for path in INGEST_FILES:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        imports = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names
        ]
        assert not any(token in module.lower() for module in imports for token in forbidden), path


def test_ingest_authority_contract_denies_downstream_actions() -> None:
    assert set(FORBIDDEN_AUTHORITIES) >= {
        "fixture_selection_authority", "model_feature_authority", "probability_authority",
        "pricing_authority", "market_routing_authority", "portfolio_authority",
        "share_code_authority", "login", "cookies", "wallet", "staking", "wager",
    }
