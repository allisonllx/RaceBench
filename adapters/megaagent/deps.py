"""Python packages required to import upstream MegaAgent in the bridge subprocess."""
from __future__ import annotations

import importlib

MEGAAGENT_PYTHON_DEPS = ("chromadb", "requests")

INSTALL_HINT = (
    "pip install -e '.[megaagent]'   # from the RaceBench repo root"
)


def missing_megaagent_deps() -> list[str]:
    """Return import names that are not available in the current interpreter."""
    missing: list[str] = []
    for name in MEGAAGENT_PYTHON_DEPS:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return missing


def require_megaagent_deps() -> None:
    """Exit with a clear message if MegaAgent's imports would fail."""
    missing = missing_megaagent_deps()
    if missing:
        raise SystemExit(
            "MegaAgent bridge missing Python packages: "
            + ", ".join(missing)
            + f". Install with: {INSTALL_HINT}"
        )
