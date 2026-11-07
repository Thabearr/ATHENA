"""VAR-01b: share one authenticated A2 inventory chain inside one pytest process.

Loaded only as a pytest plugin, registered by the repository-root
``conftest.py`` (``pytest_plugins``).  Scripts run from the command line and
production code never import it and behave exactly as before.

Contract (owner decision VAR-01b, Part D):

* D3  Every call re-runs strict generation discovery, re-reads EVERY generation
      file and re-hashes its exact bytes.  The shared value is returned only
      when root, directory and every (generation, path, sha256) match the bytes
      the real loader authenticated cold.  Any difference runs the real loader,
      which fails closed exactly as on main.  HEAD, worktree and Git checks are
      not involved: they are never shared.
* D4  If any A2 module attribute, ``Path.read_bytes`` or ``json.loads`` differs
      from the identity captured when the plugin was installed (for example a
      tamper test monkeypatched a callee), the real loader runs unshared.
* D5  No per-hit copy.  Each shared value is fingerprinted when stored and
      re-fingerprinted when replaced and at session finish.  A mismatch means a
      consumer mutated it in place: the session fails and names every test
      that received the shared value.
* D6  Only a successful real load is shared.  Exceptions propagate unchanged
      and are never stored.
* D7  ``ATHENA_DISABLE_CHAIN_SHARE=1`` disables the plugin entirely.
      ``ATHENA_CHAIN_SHARE_STRICT=1`` (local diagnostics only) also checks the
      fingerprint after every test that received the shared value.
"""
from __future__ import annotations

import functools
import hashlib
import json
import marshal
import os
from pathlib import Path

DISABLE_ENV = "ATHENA_DISABLE_CHAIN_SHARE"
STRICT_ENV = "ATHENA_CHAIN_SHARE_STRICT"
MUTATION_FAILURE = "A2 shared inventory chain was mutated in place"

_state = None


def _fingerprint(chain) -> str:
    # marshal format 2 has no object references, so the bytes depend only on the
    # structure and values (including dict order), never on reference counts.
    return hashlib.sha256(marshal.dumps(chain, 2)).hexdigest()


class _ChainShare:
    def __init__(self, a2):
        self.a2 = a2
        self.original = a2.load_inventory_generations
        self.root = a2.ROOT
        self.directory = a2.INVENTORY_DIRECTORY
        self.read_bytes = Path.read_bytes
        self.json_loads = json.loads
        self.identities = self._identities()
        self.key = None
        self.value = None
        self.digest = None
        self.receivers: list[str] = []
        self.current_test = "<session start>"
        self.test_received = False
        self.failures: list[str] = []
        self.metrics = {"hits": 0, "stores": 0, "unshared": 0}

    def _identities(self):
        return {name: id(value) for name, value in vars(self.a2).items()
                if name != "load_inventory_generations"}

    def _callees_unchanged(self) -> bool:
        return (self.a2.ROOT is self.root
                and Path.read_bytes is self.read_bytes
                and json.loads is self.json_loads
                and self._identities() == self.identities)

    def _current_key(self, directory):
        listing = self.a2.discover_inventory_generations(directory)
        rows = []
        for generation, path in listing:
            raw = (self.root / path).read_bytes()
            rows.append((generation, path, hashlib.sha256(raw).hexdigest()))
        return (str(self.root), str(directory), tuple(rows))

    def verify(self, reason: str) -> None:
        if self.value is None:
            return
        if _fingerprint(self.value) != self.digest:
            self.failures.append(
                f"{MUTATION_FAILURE} ({reason}); tests that received it: "
                + ", ".join(dict.fromkeys(self.receivers)))
            # Never hand a mutated value out again.
            self.key = self.value = self.digest = None

    def load(self, directory=None):
        directory = self.a2.INVENTORY_DIRECTORY if directory is None else directory
        if directory != self.directory or not self._callees_unchanged():
            self.metrics["unshared"] += 1
            return self.original(directory)
        key = self._current_key(directory)
        if self.value is not None and key == self.key:
            self.metrics["hits"] += 1
            self._received()
            return self.value
        value = self.original(directory)
        # Share only what the real loader authenticated from these exact bytes.
        if self._current_key(directory) != key or not self._callees_unchanged():
            self.metrics["unshared"] += 1
            return value
        self.verify("replaced by a new authenticated chain")
        self.key, self.value, self.digest = key, value, _fingerprint(value)
        self.receivers = []
        self.metrics["stores"] += 1
        self._received()
        return value

    def _received(self) -> None:
        self.test_received = True
        self.receivers.append(self.current_test)


def install(a2=None):
    """Wrap the A2 chain loader for this process; returns the share or None."""
    global _state
    if os.environ.get(DISABLE_ENV) == "1":
        return None
    if a2 is None:
        from scripts import audit_core_01d_ci_offline_transport_boundary as a2
    if _state is not None and _state.a2 is a2:
        return _state
    share = _ChainShare(a2)

    @functools.wraps(share.original)
    def load_inventory_generations(directory=None):
        return share.load(directory)

    a2.load_inventory_generations = load_inventory_generations
    _state = share
    return share


def uninstall() -> None:
    global _state
    if _state is not None:
        _state.a2.load_inventory_generations = _state.original
        _state = None


def pytest_configure(config):
    install()


def pytest_runtest_logstart(nodeid, location):
    if _state is not None:
        _state.current_test = nodeid
        _state.test_received = False


def pytest_runtest_logfinish(nodeid, location):
    if _state is not None:
        if _state.test_received and os.environ.get(STRICT_ENV) == "1":
            _state.verify("after " + nodeid)
        _state.current_test = "<between tests>"


def pytest_sessionfinish(session, exitstatus):
    if _state is None:
        return
    _state.verify("at session finish")
    if _state.failures:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    if _state is None:
        return
    terminalreporter.write_line(
        "A2_CHAIN_SHARE: hits={hits} stores={stores} unshared={unshared}".format(**_state.metrics))
    for failure in _state.failures:
        terminalreporter.write_line("A2_CHAIN_SHARE_FAILURE: " + failure, red=True)
