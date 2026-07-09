"""Symbol-level analysis of Python sources via the stdlib ast module.

Used by the ast_scope strategy (to decide which symbols a write touches) and by
the metrics pipeline (to classify, post hoc, whether a coordination stall was a
false positive — i.e. the concurrent writes touched disjoint symbol sets).

We use stdlib ast rather than tree-sitter: the task suite is pure Python, and a
zero-dependency parser keeps the harness reproducible. Non-parseable or
non-Python files fall back to a single whole-file pseudo-symbol.
"""
from __future__ import annotations

import ast

MODULE_SYMBOL = "<module>"
FILE_SYMBOL = "<file>"


def symbol_sources(source: str) -> dict[str, str] | None:
    """Map each top-level symbol to its exact source segment.

    Top-level functions and classes get their own symbol; everything else
    (imports, module constants, bare statements) is pooled under <module>.
    Returns None when the source does not parse as Python.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    symbols: dict[str, str] = {}
    module_parts: list[str] = []
    for node in tree.body:
        segment = ast.get_source_segment(source, node) or ""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols[node.name] = segment
        else:
            module_parts.append(segment)
    symbols[MODULE_SYMBOL] = "\n".join(module_parts)
    return symbols


def changed_symbols(old_source: str, new_source: str) -> set[str]:
    """Which top-level symbols differ between two versions of a file.

    Falls back to {<file>} when either version is not parseable Python,
    so non-Python files degrade to file-level granularity.
    """
    old = symbol_sources(old_source)
    new = symbol_sources(new_source)
    if old is None or new is None:
        return {FILE_SYMBOL} if old_source != new_source else set()
    changed = set()
    for name in old.keys() | new.keys():
        if old.get(name) != new.get(name):
            changed.add(name)
    return changed


def file_symbols(source: str) -> set[str]:
    """All symbols defined in a file (for read-set recording)."""
    syms = symbol_sources(source)
    if syms is None:
        return {FILE_SYMBOL}
    return set(syms.keys())
