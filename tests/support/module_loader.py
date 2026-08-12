"""Load test helper modules once under their canonical package identity."""

from __future__ import annotations

import importlib
import re
from functools import lru_cache
from types import ModuleType


_TEST_MODULE_NAME = re.compile(r"test_[a-z0-9_]+", flags=re.ASCII)


@lru_cache(maxsize=None)
def load_test_module(module_name: str) -> ModuleType:
    """Return one cached local ``tests.<module_name>`` helper module.

    The closed module-name grammar prevents path traversal and arbitrary
    imports while the canonical package name lets Python's normal import cache
    eliminate repeated execution of recursively shared test helpers.
    """

    if type(module_name) is not str or _TEST_MODULE_NAME.fullmatch(module_name) is None:
        raise ValueError("test helper module name must match test_[a-z0-9_]+")
    return importlib.import_module(f"tests.{module_name}")
