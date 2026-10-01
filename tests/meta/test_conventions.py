"""Mechanical checks of CONSTITUTION.md and docs/testing.md."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
import re

import pytest

import pyairseekers

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "pyairseekers"
TESTS = ROOT / "tests"

# Modules with no mirrored test module, and why
EXEMPT_FROM_MIRRORING = {
    "const.py": "constants only",
    "exceptions.py": "exercised by every tier",
    "mqtt.py": "experimental (D9)",
    "ble.py": "experimental (D9)",
    "cloud/transport.py": "tested over loopback in tests/integration/test_transport.py",
}
# Which package areas may import which (CONSTITUTION.md §3)
ALLOWED_IMPORTS = {
    "cloud": {"cloud", "const", "exceptions", "models"},
    "local": {"local", "exceptions"},
    "live": {"const", "exceptions", "models"},
    "models": set(),
    "const": set(),
    "exceptions": set(),
}


def _modules() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if p.name != "__init__.py")


def _area(path: Path) -> str:
    rel = path.relative_to(PACKAGE)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _test_files() -> list[Path]:
    return sorted(TESTS.rglob("*.py"))


class TestLayout:
    @pytest.mark.parametrize("module", _modules(), ids=lambda p: str(p.relative_to(PACKAGE)))
    def test_every_module_has_a_test_module(self, module: Path) -> None:
        rel = module.relative_to(PACKAGE).as_posix()
        if rel in EXEMPT_FROM_MIRRORING:
            return
        name = f"test_{module.stem}.py"
        candidates = [
            TESTS / "unit" / module.relative_to(PACKAGE).parent / name,
            TESTS / "integration" / name,
        ]
        assert any(c.exists() for c in candidates), f"{rel} has no test module at {candidates}"

    @pytest.mark.parametrize("module", _modules(), ids=lambda p: str(p.relative_to(PACKAGE)))
    def test_layers_import_only_what_they_may(self, module: Path) -> None:
        area = _area(module)
        if area not in ALLOWED_IMPORTS:
            return
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pyairseekers."):
                target = node.module.split(".")[1]
                assert target in ALLOWED_IMPORTS[area], f"{module.name} ({area}) imports pyairseekers.{target}"


class TestPublicSurface:
    def test_all_is_sorted_and_importable(self) -> None:
        assert list(pyairseekers.__all__) == sorted(pyairseekers.__all__)
        for name in pyairseekers.__all__:
            assert getattr(pyairseekers, name)

    def test_package_never_mentions_home_assistant(self) -> None:
        for module in _modules():
            assert "homeassistant" not in module.read_text(), module


class TestTestConventions:
    @pytest.mark.parametrize("path", _test_files(), ids=lambda p: str(p.relative_to(TESTS)))
    def test_no_mock_library(self, path: Path) -> None:
        if path == Path(__file__):
            return
        assert not re.search(
            r"^\s*(from|import) unittest\.mock|^\s*from unittest import mock", path.read_text(), re.MULTILINE
        )

    @pytest.mark.parametrize("path", _test_files(), ids=lambda p: str(p.relative_to(TESTS)))
    def test_no_sleeping_for_synchronisation(self, path: Path) -> None:
        assert not re.search(r"asyncio\.sleep\((?!0\))", path.read_text()), "wait on an Event, not a clock"

    @pytest.mark.parametrize("path", sorted((TESTS / "unit").rglob("*.py")), ids=lambda p: str(p.relative_to(TESTS)))
    def test_unit_tier_does_not_use_the_fake_server(self, path: Path) -> None:
        assert "fakeserver" not in path.read_text()

    @pytest.mark.parametrize("path", _test_files(), ids=lambda p: str(p.relative_to(TESTS)))
    def test_regression_tests_say_what_was_wrong(self, path: Path) -> None:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                "regression" in ast.unparse(d) for d in node.decorator_list
            ):
                assert ast.get_docstring(node), f"{node.name} is marked regression but has no docstring"


def test_experimental_modules_stay_importable() -> None:
    for name in ("pyairseekers.ble",):
        importlib.import_module(name)
