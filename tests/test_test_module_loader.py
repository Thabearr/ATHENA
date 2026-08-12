from __future__ import annotations

import sys

import pytest

from tests.support.module_loader import load_test_module


def test_loader_reuses_the_canonical_test_module() -> None:
    loaded = load_test_module("test_test_module_loader")

    assert loaded is sys.modules[__name__]
    assert load_test_module("test_test_module_loader") is loaded


@pytest.mark.parametrize(
    "module_name",
    (
        "",
        "test_UPPER",
        "test-with-dash",
        "tests.test_test_module_loader",
        "../test_test_module_loader",
        "test_test_module_loader.py",
        1,
        True,
        None,
    ),
)
def test_loader_rejects_noncanonical_or_non_string_module_names(module_name) -> None:
    with pytest.raises(ValueError, match=r"test_\[a-z0-9_\]\+"):
        load_test_module(module_name)
