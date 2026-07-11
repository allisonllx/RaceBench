"""Workspace-wide Python import / name-use dependency graph.

Used by the ast_dep strategy to see cross-file races that same-file ast_scope
misses. Stdlib ast only; unresolved references are ignored (no false stalls).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from harness.symbols import MODULE_SYMBOL

SKIP_PARTS = {".git", ".racebench_git", ".worktrees", "__pycache__", "oracle_tests"}

SymKey = tuple[str, str]  # (relpath, symbol)


@dataclass
class DepGraph:
    """Forward: use-site → defs it references. Reverse: def → use-sites."""

    root: Path
    forward: dict[SymKey, set[SymKey]] = field(default_factory=dict)
    reverse: dict[SymKey, set[SymKey]] = field(default_factory=dict)
    # package dotted name -> exported name -> defining (path, symbol)
    package_exports: dict[str, dict[str, SymKey]] = field(default_factory=dict)
    # module dotted name -> relpath (e.g. models.user -> models/user.py)
    modules: dict[str, str] = field(default_factory=dict)
    # relpath -> top-level symbol names defined in that file
    definitions: dict[str, set[str]] = field(default_factory=dict)

    def rebuild(self) -> None:
        self.forward.clear()
        self.reverse.clear()
        self.package_exports.clear()
        self.modules.clear()
        self.definitions.clear()
        sources: dict[str, str] = {}
        for path in sorted(self.root.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            rel = str(path.relative_to(self.root)).replace("\\", "/")
            try:
                sources[rel] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            self.modules[self._module_name(rel)] = rel
            self.definitions[rel] = self._defined_symbols(sources[rel])

        # First pass: package re-exports from __init__.py
        for rel, src in sources.items():
            if Path(rel).name != "__init__.py":
                continue
            pkg = self._module_name(rel)
            self.package_exports[pkg] = self._parse_reexports(rel, src)

        # Second pass: per-symbol use edges
        for rel, src in sources.items():
            for use_sym, defs in self._symbol_refs(rel, src).items():
                key = (rel, use_sym)
                self.forward.setdefault(key, set()).update(defs)
                for d in defs:
                    self.reverse.setdefault(d, set()).add(key)

    def refs_of(self, relpath: str, symbol: str) -> set[SymKey]:
        return set(self.forward.get((relpath, symbol), set()))

    def dependents_of(self, relpath: str, symbol: str) -> set[SymKey]:
        return set(self.reverse.get((relpath, symbol), set()))

    def refs_from_source(self, relpath: str, source: str,
                         symbols: set[str] | None = None) -> set[SymKey]:
        """References made by symbols in *source* (e.g. proposed write content)."""
        per = self._symbol_refs(relpath, source)
        out: set[SymKey] = set()
        for sym, defs in per.items():
            if symbols is None or sym in symbols:
                out.update(defs)
        return out

    def expanded_read_keys(self, relpath: str, source: str) -> set[SymKey]:
        """Local symbols plus foreign defs referenced anywhere in the file."""
        from harness.symbols import file_symbols
        keys: set[SymKey] = {(relpath, s) for s in file_symbols(source)}
        for defs in self._symbol_refs(relpath, source).values():
            keys.update(defs)
        return keys

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _module_name(relpath: str) -> str:
        p = Path(relpath)
        parts = list(p.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    @staticmethod
    def _defined_symbols(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
        return names

    def _find_def_in_package(self, package: str, name: str) -> SymKey | None:
        """Locate name as a top-level def under package (including submodules)."""
        if package in self.package_exports and name in self.package_exports[package]:
            return self.package_exports[package][name]
        prefix = package + "."
        for mod_name, rel in self.modules.items():
            if mod_name == package or mod_name.startswith(prefix):
                if name in self.definitions.get(rel, ()):
                    return (rel, name)
        return None

    def _parse_reexports(self, relpath: str, source: str) -> dict[str, SymKey]:
        """Map exported name → defining (path, symbol) for a package __init__."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        aliases = self._import_aliases(relpath, tree)
        exports: dict[str, SymKey] = {}
        all_names: set[str] | None = None
        for node in tree.body:
            if (isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple))):
                all_names = set()
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        all_names.add(elt.value)
        for local, target in aliases.items():
            if all_names is not None and local not in all_names:
                continue
            if target is not None:
                exports[local] = target
        return exports

    def _import_aliases(self, relpath: str,
                        tree: ast.AST) -> dict[str, SymKey | None]:
        """local name → resolved (path, symbol) or None if only a module/package bind."""
        aliases: dict[str, SymKey | None] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    # module bind only — attribute access resolves later
                    aliases[local] = None
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                mod = node.module
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    resolved = self._resolve_from_import(mod, alias.name)
                    aliases[local] = resolved
        return aliases

    def _resolve_from_import(self, module: str, name: str) -> SymKey | None:
        # from models.user import make_user
        if module in self.modules:
            rel = self.modules[module]
            if name in self.definitions.get(rel, {name}):
                return (rel, name)
            return (rel, name)
        # from models import make_user  (package re-export or submodule scan)
        hit = self._find_def_in_package(module, name)
        if hit is not None:
            return hit
        init = module.replace(".", "/") + "/__init__.py"
        if init in self.modules.values() or (self.root / init).is_file():
            return (init, name)
        return None

    def _resolve_attr(self, aliases: dict[str, SymKey | None],
                      root_name: str, attr: str) -> SymKey | None:
        """Resolve models.make_user where models is an imported package."""
        if root_name not in aliases:
            return None
        bound = aliases[root_name]
        if bound is not None:
            return None
        hit = self._find_def_in_package(root_name, attr)
        if hit is not None:
            return hit
        if root_name in self.modules:
            return (self.modules[root_name], attr)
        return None

    def _symbol_refs(self, relpath: str, source: str) -> dict[str, set[SymKey]]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        aliases = self._import_aliases(relpath, tree)
        # also bind package names from `import pkg`
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    aliases.setdefault(local, None)

        per: dict[str, set[SymKey]] = {}

        def collect(sym: str, node: ast.AST) -> None:
            refs = per.setdefault(sym, set())
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and not isinstance(child.ctx, ast.Store):
                    if child.id in aliases and aliases[child.id] is not None:
                        refs.add(aliases[child.id])  # type: ignore[arg-type]
                elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    hit = self._resolve_attr(aliases, child.value.id, child.attr)
                    if hit is not None:
                        refs.add(hit)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                collect(node.name, node)
            else:
                collect(MODULE_SYMBOL, node)
        return per


def build_depgraph(root: Path) -> DepGraph:
    g = DepGraph(root=Path(root))
    g.rebuild()
    return g
