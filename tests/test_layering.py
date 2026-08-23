"""Architecture guardrails.

These fail the build if the layering the README claims ever stops being true.
"""
from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
ROUTERS = sorted((APP / "routers").glob("*.py"))
SERVICES = sorted((APP / "services").glob("*.py"))

#: Anything that means "this module is talking to the database itself".
DB_CALL_NAMES = {"execute", "scalar", "scalars", "scalar_one", "scalar_one_or_none",
                 "add", "delete", "flush", "commit", "rollback", "query", "get"}


def _calls_on_db_object(path: pathlib.Path) -> list[str]:
    """Find `db.<something>(...)` / `session.<something>(...)` calls."""
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in {"db", "session", "Session"} and func.attr in DB_CALL_NAMES:
                found.append(f"{path.name}:{node.lineno} {func.value.id}.{func.attr}()")
    return found


def test_routers_exist():
    assert ROUTERS, "expected router modules"
    assert SERVICES, "expected service modules"


def test_routers_never_touch_the_database():
    offenders = [hit for p in ROUTERS for hit in _calls_on_db_object(p)]
    assert not offenders, f"router files must not call the DB directly: {offenders}"


def test_routers_do_not_import_sqlalchemy_or_the_session():
    offenders = []
    for path in ROUTERS:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mod = None
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            elif isinstance(node, ast.Import):
                mod = ",".join(a.name for a in node.names)
            if mod and ("sqlalchemy" in mod or "db.session" in mod):
                offenders.append(f"{path.name}:{node.lineno} imports {mod}")
    assert not offenders, f"routers must not import the DB layer: {offenders}"


def test_routers_do_not_import_repositories():
    """Routers go through services; they must not reach past them."""
    offenders = []
    for path in ROUTERS:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and "repositories" in (node.module or ""):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"routers must not import repositories directly: {offenders}"


def test_services_do_not_issue_sql():
    """Services orchestrate repositories; SQL belongs in the data-access layer."""
    offenders = []
    for path in SERVICES:
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"select", "insert", "update", "delete", "text"}:
                    offenders.append(f"{path.name}:{node.lineno} {node.func.id}()")
        offenders += _calls_on_db_object(path)
    assert not offenders, f"services must not issue SQL: {offenders}"
