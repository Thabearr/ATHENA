from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hosted_shadow_workflow_uses_import_safe_module_entrypoint():
    workflow = (ROOT / ".github/workflows/current-shadow-all-market.yml").read_text(
        encoding="utf-8"
    )
    assert "python -m scripts.execute_current_shadow_all_market" in workflow
    assert "python scripts/execute_current_shadow_all_market.py" not in workflow
