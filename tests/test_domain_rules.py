"""Enforces plan section 11, rules 2 and 3."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from arcelikSalesHelper import domain

DOMAIN_DIR = Path(domain.__file__).parent
FILES = sorted(DOMAIN_DIR.glob("*.py"))
FORBIDDEN = {"PySide6", "sqlite3", "infrastructure", "application", "ui"}


def _trees() -> Iterator[tuple[Path, ast.AST]]:
    for f in FILES:
        yield f, ast.parse(f.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_domain_has_no_forbidden_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            parts = {p for a in node.names for p in a.name.split(".")}
        elif isinstance(node, ast.ImportFrom):
            parts = set((node.module or "").split("."))
        else:
            continue
        assert FORBIDDEN.isdisjoint(parts), (
            f"{path.name} imports {parts & FORBIDDEN}"
        )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_domain_never_uses_binary_floats(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "float", f"{path.name}:{node.lineno} uses float"
        if isinstance(node, ast.Constant):
            assert not isinstance(node.value, float), (
                f"{path.name}:{node.lineno} float literal"
            )
