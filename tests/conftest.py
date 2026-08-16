from __future__ import annotations

import pytest


_PR125_RUNNER_TEST_MODULE = "test_pr69_primary_time_basis_evidence_acquisition_runner"
_PR125_REAL_UPSTREAM_TESTS = {
    "test_upstream_protocol_mutation_fails_closed",
}


@pytest.fixture(scope="session")
def _pr125_verified_upstream_protocol():
    """Perform the expensive PR125→PR124 ancestry validation once per test session."""
    import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract

    return contract._verify_upstream()


@pytest.fixture(autouse=True)
def _reuse_pr125_verified_upstream_protocol(request, monkeypatch):
    """Reuse verified immutable ancestry for PR125 state-machine tests only.

    Production code is unchanged. The dedicated upstream-mutation test deliberately
    retains the original verifier so fail-closed tamper detection remains exercised.
    """
    if request.module.__name__.split(".")[-1] != _PR125_RUNNER_TEST_MODULE:
        return
    if request.node.name in _PR125_REAL_UPSTREAM_TESTS:
        return

    import domain.pr69_primary_time_basis_evidence_acquisition_runner as contract

    verified = request.getfixturevalue("_pr125_verified_upstream_protocol")
    monkeypatch.setattr(contract, "_verify_upstream", lambda: verified)
