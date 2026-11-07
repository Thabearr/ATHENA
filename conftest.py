"""Repository-root pytest configuration (VAR-01b).

Registers the per-process A2 chain share plugin for every pytest run rooted
here. It loads before tests/conftest.py, so the session-start A2
authentication already uses it. Set ATHENA_DISABLE_CHAIN_SHARE=1 to restore
main's loader behaviour exactly.
"""
pytest_plugins = ["scripts.pytest_a2_chain_share"]
