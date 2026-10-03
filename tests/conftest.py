from __future__ import annotations

import pytest

from offline_transport import install

install()


def pytest_sessionstart(session):
    # Dynamic discovery cannot silently grow beyond the source-reviewed corpus.
    from scripts import audit_core_01d_ci_offline_transport_boundary as audit
    audit.authenticate_predecessors()
    audit.authenticate_inventory()


_A2_NATIVE_PASSED = set()
_A2_NATIVE_NAMES = {
    "test_native_kernel_socket_denial_is_independent_of_python_monkeypatches",
    "test_child_cannot_remove_kernel_filter",
}


def pytest_runtest_logreport(report):
    name = report.nodeid.rsplit("::", 1)[-1]
    if report.when == "call" and report.passed and name in _A2_NATIVE_NAMES:
        _A2_NATIVE_PASSED.add(name)


def pytest_terminal_summary(terminalreporter):
    if _A2_NATIVE_PASSED == _A2_NATIVE_NAMES:
        terminalreporter.write_line("CORE_01D_A2_LINUX_NATIVE_PROOF: parent-native and inherited-child PASSED (2/2)")


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
