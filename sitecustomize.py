"""Activate the test boundary before pytest plugin discovery; other CLI is inert."""
from pathlib import Path
import sys

# Patch Bridge forbids this root path. Its allowed tests/scripts patches must
# not replace the trusted boundary or auditor before pytest starts. These are
# LF source identities, not normalization of any raw runtime artifact.
ROOT_TEST_SOURCE_PINS = {
    "scripts/audit_core_01d_ci_offline_transport_boundary.py": "dd06b0958847d169f7ce9baade10bbcaa4488fb5ae225db3d2f54841ca60a07c",
    "tests/_offline_bootstrap/sitecustomize.py": "1b1968215b72f913e17a840b7b3ac22aa4e8508e5fa529990487c59b2e0c878d",
    "tests/conftest.py": "500e47d9937ddf89f725d41117a84abf207de2e768a861adc5c4a49c7a87e052",
    "tests/offline_linux.py": "565e1698bebfc30d5463a3c3b6ded43e6ff9378af955129a011bf28e1a5b999f",
    "tests/offline_transport.py": "a35dcca52929598a5f6d97a69274e475f10c2229889599a82d5371886c437ad1",
}

_args = getattr(sys, "orig_argv", ())
_pytest_module = any(
    _args[i:i + 2] == ["-m", "pytest"]
    and all(flag in {"-u", "-B", "-s", "-q", "-v", "-vv", "-b", "-bb", "-O", "-OO"} for flag in _args[1:i])
    for i in range(1, len(_args) - 1)
)
_pytest_script = any(Path(arg).name.lower() in {"pytest", "pytest.exe", "py.test"} for arg in _args[1:2])
if _pytest_module or _pytest_script:
    try:
        import hashlib

        _root = Path(__file__).resolve().parent
        for _path, _expected in ROOT_TEST_SOURCE_PINS.items():
            _raw = (_root / _path).read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(_raw).hexdigest() != _expected:
                raise RuntimeError("test boundary source identity drift: " + _path)
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
        from offline_transport import install

        install()
    except Exception as error:
        # Python otherwise prints and ignores an exception in sitecustomize.
        raise SystemExit("pytest offline boundary failed to activate") from error
