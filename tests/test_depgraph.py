"""Unit tests for the cross-file dependency graph."""
from pathlib import Path

import pytest

from harness.depgraph import build_depgraph
from harness.task import load_task


def test_t5_package_reexport_and_attr_use(tmp_path):
    task = load_task("t05_cross_file")
    # overlay a services file that calls models.make_user
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    (dst / "services" / "registration.py").write_text(
        '"""Registration."""\n'
        "import models\n"
        "from db import append_user\n\n\n"
        "def register(name, email):\n"
        "    user = models.make_user(name)\n"
        "    return append_user(user)\n",
        encoding="utf-8",
    )
    g = build_depgraph(dst)
    assert g.package_exports["models"]["make_user"] == ("models/user.py", "make_user")
    refs = g.refs_of("services/registration.py", "register")
    assert ("models/user.py", "make_user") in refs
    deps = g.dependents_of("models/user.py", "make_user")
    assert ("services/registration.py", "register") in deps


def test_t5_create_user_resolves_via_submodule_scan(tmp_path):
    task = load_task("t05_cross_file")
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    (dst / "models" / "user.py").write_text(
        "from models.validators import looks_like_email\n\n\n"
        "def create_user(name, email):\n"
        "    if not looks_like_email(email):\n"
        "        raise ValueError('invalid email')\n"
        "    return {'name': name, 'email': email, 'active': True}\n",
        encoding="utf-8",
    )
    # __init__ still exports make_user (stale) — attr should still find create_user
    g = build_depgraph(dst)
    hit = g._find_def_in_package("models", "create_user")
    assert hit == ("models/user.py", "create_user")
    src = (
        "import models\n\n\n"
        "def register(name, email):\n"
        "    return models.create_user(name, email)\n"
    )
    refs = g.refs_from_source("services/registration.py", src, {"register"})
    assert ("models/user.py", "create_user") in refs


def test_t9_disjoint_packages_no_cross_edges():
    task = load_task("t09_overhead")
    g = build_depgraph(task.repo)
    # no edges from mod_a into mod_b or vice versa
    for (path, _sym), defs in g.forward.items():
        if path.startswith("mod_a/"):
            assert all(not d[0].startswith("mod_b/") for d in defs)
        if path.startswith("mod_b/"):
            assert all(not d[0].startswith("mod_a/") for d in defs)


def test_rebuild_updates_edges(tmp_path):
    task = load_task("t05_cross_file")
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(task.repo, dst)
    (dst / "services" / "registration.py").write_text(
        "import models\n\n\ndef register(name, email):\n"
        "    return models.make_user(name)\n",
        encoding="utf-8",
    )
    g = build_depgraph(dst)
    assert ("services/registration.py", "register") in g.dependents_of(
        "models/user.py", "make_user")
    (dst / "services" / "registration.py").write_text(
        "import models\n\n\ndef register(name, email):\n"
        "    return models.create_user(name, email)\n",
        encoding="utf-8",
    )
    (dst / "models" / "user.py").write_text(
        "def create_user(name, email):\n    return {}\n", encoding="utf-8")
    g.rebuild()
    assert ("services/registration.py", "register") in g.dependents_of(
        "models/user.py", "create_user")
    assert ("services/registration.py", "register") not in g.dependents_of(
        "models/user.py", "make_user")
