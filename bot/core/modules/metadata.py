"""
bot/core/modules/metadata.py

Modification():

- Read Extension metadata without importing feature modules。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ModuleMetadata:
    """Static information declared by a module's extension file."""

    version: str
    display_name: str
    dependencies: tuple[str, ...]


def _assignment_value(node: ast.stmt, key: str) -> ast.expr | None:
    """Return a literal assignment value for regular and annotated syntax."""

    if isinstance(node, ast.Assign):
        if any(isinstance(target, ast.Name) and target.id == key for target in node.targets):
            return node.value
        return None
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == key:
            return node.value
    return None


def _literal(tree: ast.Module, key: str) -> object | None:
    for node in tree.body:
        value = _assignment_value(node, key)
        if value is None:
            continue
        try:
            return ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            return None
    return None


def read_module_metadata(extension_file: Path, *, module_name: str) -> ModuleMetadata:
    """Parse validated metadata from an extension file with safe fallbacks."""

    tree = ast.parse(extension_file.read_text(encoding="utf-8"), filename=str(extension_file))
    raw_version = _literal(tree, "MODULE_VERSION")
    raw_name = _literal(tree, "MODULE_DISPLAY_NAME")
    raw_dependencies = _literal(tree, "MODULE_DEPENDENCIES")
    version = raw_version.strip() if isinstance(raw_version, str) and raw_version.strip() else "0.1.0"
    display_name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else module_name.replace("_", " ").title()
    dependencies = (
        tuple(item.strip() for item in raw_dependencies)
        if isinstance(raw_dependencies, (list, tuple)) and all(isinstance(item, str) and item.strip() for item in raw_dependencies)
        else ()
    )
    return ModuleMetadata(version=version, display_name=display_name, dependencies=dependencies)
