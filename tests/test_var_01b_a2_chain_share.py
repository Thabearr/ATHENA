"""VAR-01b Part D: tamper parity of the per-process shared A2 chain.

Each case runs the real A2 loader and the shared loader over the same exact
bytes and requires the same result or the same exception type and message,
both cold and after a warm hit on the good bytes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import pytest_a2_chain_share as share_plugin

GENERATIONS = 3


def _real_loader():
    loader = boundary.load_inventory_generations
    return getattr(loader, "__wrapped__", loader)


def _seed(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for generation in range(1, GENERATIONS + 1):
        source = boundary.ROOT / boundary.inventory_generation_path(generation)
        shutil.copyfile(source, directory / source.name)


def _share(directory: Path):
    module = types.ModuleType("a2_view")
    module.__dict__.update(vars(boundary))
    module.load_inventory_generations = _real_loader()
    module.INVENTORY_DIRECTORY = str(directory)
    return share_plugin._ChainShare(module)


def _outcome(call):
    try:
        return ("ok", json.dumps(call(), sort_keys=True))
    except Exception as error:  # compared, never swallowed: both sides must match
        return ("raise", type(error).__name__, str(error))


def _path(directory: Path, generation: int) -> Path:
    return directory / Path(boundary.inventory_generation_path(generation)).name


def _mutate_byte(directory):
    target = _path(directory, 2)
    raw = target.read_bytes()
    mutated = raw.replace(b"LINUX_X86_64", b"LINUX_X86_65", 1)
    assert mutated != raw
    target.write_bytes(mutated)


def _swap(directory):
    first, second = _path(directory, 2), _path(directory, 3)
    a, b = first.read_bytes(), second.read_bytes()
    first.write_bytes(b)
    second.write_bytes(a)


def _missing(directory):
    _path(directory, 2).unlink()


def _duplicate(directory):
    shutil.copyfile(_path(directory, 2), directory / _path(directory, 2).name.replace("-v2.", "-v02."))


def _extra(directory):
    shutil.copyfile(_path(directory, 3), _path(directory, 5))


def _downgraded_predecessor(directory):
    target = _path(directory, 3)
    value = json.loads(target.read_bytes())
    value["predecessor_inventory"]["canonical_sha256"] = "0" * 64
    target.write_bytes(boundary.canonical(boundary.seal(value)))


TAMPERS = {
    "mutated_byte": _mutate_byte,
    "swapped": _swap,
    "missing": _missing,
    "duplicate": _duplicate,
    "extra_gap": _extra,
    "downgraded_predecessor": _downgraded_predecessor,
}


@pytest.mark.parametrize("warm", [False, True], ids=["cold", "warm"])
@pytest.mark.parametrize("tamper", sorted(TAMPERS))
def test_shared_chain_fails_closed_exactly_like_main(tmp_path, tamper, warm):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    if warm:
        good = share.load()
        assert share.load() is good and share.metrics["hits"] == 1
    TAMPERS[tamper](directory)
    expected = _outcome(lambda: _real_loader()(str(directory)))
    assert expected[0] == "raise"
    assert _outcome(share.load) == expected
    # Still fails on repeat: exceptions are never stored.
    assert _outcome(share.load) == expected


@pytest.mark.parametrize("order", ["forward", "reversed"])
def test_tamper_matrix_is_order_independent(tmp_path, order):
    names = sorted(TAMPERS)
    if order == "reversed":
        names.reverse()
    for index, name in enumerate(names):
        directory = tmp_path / f"chain-{index}"
        _seed(directory)
        share = _share(directory)
        share.load()
        TAMPERS[name](directory)
        assert _outcome(share.load) == _outcome(lambda: _real_loader()(str(directory))), name


def test_shared_value_is_the_real_authenticated_chain_and_hits_reuse_it(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    first = share.load()
    assert first == _real_loader()(str(directory))
    assert share.load() is first
    assert share.metrics == {"hits": 1, "stores": 1, "unshared": 0}


def test_restoring_good_bytes_after_tamper_reauthenticates(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    good = share.load()
    target = _path(directory, 2)
    raw = target.read_bytes()
    _mutate_byte(directory)
    with pytest.raises(AssertionError):
        share.load()
    target.write_bytes(raw)
    assert share.load() == good


def test_monkeypatched_callee_bypasses_the_share(tmp_path, monkeypatch):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    share.load()

    def tampered_read_generation(path):
        raise AssertionError("tampered callee ran: " + path)

    monkeypatch.setattr(share.a2, "read_generation", tampered_read_generation)
    # The real loader's global is the module the view was copied from.
    monkeypatch.setattr(boundary, "read_generation", tampered_read_generation)
    expected = _outcome(lambda: _real_loader()(str(directory)))
    assert expected[0] == "raise" and "tampered callee ran" in expected[2]
    assert _outcome(share.load) == expected
    assert share.metrics["unshared"] == 1


def test_monkeypatched_path_reader_bypasses_the_share(tmp_path, monkeypatch):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    share.load()
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: original(self))
    share.load()
    assert share.metrics["unshared"] == 1 and share.metrics["hits"] == 0


def test_other_directories_are_never_shared(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    share.load(str(directory) + "/")
    assert share.metrics == {"hits": 0, "stores": 0, "unshared": 1}


def test_in_place_mutation_of_shared_value_fails_the_session(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    share.current_test = "tests/example.py::mutator"
    chain = share.load()
    chain[-1][1]["source_identities"].pop()
    share.verify("at session finish")
    assert len(share.failures) == 1
    assert share_plugin.MUTATION_FAILURE in share.failures[0]
    assert "tests/example.py::mutator" in share.failures[0]
    # A mutated value is never handed out again: the next load is a fresh real load.
    fresh = share.load()
    assert fresh is not chain and fresh == _real_loader()(str(directory))


def test_reordering_shared_value_is_detected(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    chain = share.load()
    latest = chain[-1][1]
    items = list(latest.items())
    latest.clear()
    latest.update(reversed(items))
    share.verify("at session finish")
    assert share.failures


def test_unmutated_share_passes_session_verification(tmp_path):
    directory = tmp_path / "chain"
    _seed(directory)
    share = _share(directory)
    share.load()
    share.load()
    share.verify("at session finish")
    assert share.failures == []


def test_kill_switch_leaves_the_loader_untouched(monkeypatch):
    module = types.ModuleType("a2_view")
    module.__dict__.update(vars(boundary))
    original = module.load_inventory_generations
    monkeypatch.setenv(share_plugin.DISABLE_ENV, "1")
    assert share_plugin.install(module) is None
    assert module.load_inventory_generations is original


def test_plugin_is_active_in_this_pytest_process():
    if os.environ.get(share_plugin.DISABLE_ENV) == "1":
        pytest.skip("chain share disabled by the kill switch for this run")
    assert boundary.load_inventory_generations.__wrapped__ is share_plugin._state.original


def test_command_line_scripts_do_not_load_the_share():
    code = ("import sys; from scripts import audit_core_01d_ci_offline_transport_boundary as a2; "
            "print('pytest_a2_chain_share' in str(sorted(sys.modules)), "
            "hasattr(a2.load_inventory_generations, '__wrapped__'))")
    output = subprocess.run([sys.executable, "-c", code], cwd=boundary.ROOT, check=True,
                            capture_output=True, text=True).stdout.split()
    assert output == ["False", "False"]


def test_tamper_matrix_in_a_fresh_process(tmp_path):
    script = (
        "import sys, json\n"
        "sys.path.insert(0, 'tests')\n"
        "import test_var_01b_a2_chain_share as t\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1])\n"
        "bad = []\n"
        "for i, name in enumerate(sorted(t.TAMPERS)):\n"
        "    d = root / f'c{i}'\n"
        "    t._seed(d)\n"
        "    s = t._share(d)\n"
        "    s.load()\n"
        "    t.TAMPERS[name](d)\n"
        "    if t._outcome(s.load) != t._outcome(lambda: t._real_loader()(str(d))):\n"
        "        bad.append(name)\n"
        "print(json.dumps(bad))\n"
    )
    output = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=boundary.ROOT,
                            check=True, capture_output=True, text=True).stdout
    assert json.loads(output.strip().splitlines()[-1]) == []
