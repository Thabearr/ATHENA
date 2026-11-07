"""Activate the test boundary before pytest plugin discovery; other CLI is inert."""
from pathlib import Path
import sys

# Patch Bridge forbids this root path. Its allowed tests/scripts patches must
# not replace the trusted boundary or auditor before pytest starts. These are
# LF source identities, not normalization of any raw runtime artifact.
ROOT_TEST_SOURCE_PINS = {
    "scripts/audit_core_01d_ci_offline_transport_boundary.py": "3a42c6e50fddecd482cb8e6dd3758e8c58f453885e133ecf68798f0a51832404",
    "tests/_offline_bootstrap/sitecustomize.py": "1b1968215b72f913e17a840b7b3ac22aa4e8508e5fa529990487c59b2e0c878d",
    "tests/conftest.py": "500e47d9937ddf89f725d41117a84abf207de2e768a861adc5c4a49c7a87e052",
    "tests/offline_linux.py": "565e1698bebfc30d5463a3c3b6ded43e6ff9378af955129a011bf28e1a5b999f",
    "tests/offline_transport.py": "6fff0df3acc0f886cdaa452e3c5232762cd4069f4b956085dfa174bb95021e49",
}

# Owner-authorized, path-exact retention successors. Preserve the original pins
# and the previously admitted auditor; no other guard gains an alternate identity.
ROOT_TEST_SOURCE_SUCCESSORS = {
    "scripts/audit_core_01d_ci_offline_transport_boundary.py": (
        "282e1b9c5258eb4fcbe51581816e7894e5c9b581f085be1162aa6f9bca864299",
        "61056b7e5d233bcfe259716985dd8626d2be38bd00f0015329725b0da6a080c5",
    ),
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
            _digest = hashlib.sha256(_raw).hexdigest()
            if _digest != _expected and _digest not in ROOT_TEST_SOURCE_SUCCESSORS.get(_path, ()):
                raise RuntimeError("test boundary source identity drift: " + _path)
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
        from offline_transport import install

        install()
    except Exception as error:
        # Python otherwise prints and ignores an exception in sitecustomize.
        raise SystemExit("pytest offline boundary failed to activate") from error
