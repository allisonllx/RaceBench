"""Deterministic scripted agents for offline harness validation and demos.

Scripts cannot adapt to runtime file content, so they validate MECHANICS
(does naive lose an update? does git_hash merge or surface a conflict? does
ast_scope stay silent on disjoint edits?) — headline benchmark numbers must
come from real model runs.

Variants:
  edit    — anchored edit_file calls that compose across agents
  clobber — whole-file write_file calls based on the initial (stale) content,
            simulating an agent that rewrites files from its first read
"""
from __future__ import annotations

# ---------------------------------------------------------------- t1 fragments

from pathlib import Path

T1_INITIAL = (Path(__file__).resolve().parent.parent
              / "tasks/t1_stale_read/repo/config.py").read_text(encoding="utf-8")

T1_TIMEOUT_DEFAULT = '    "port": 8080,\n    "timeout": 30.0,\n}'
T1_RETRIES_DEFAULT = '    "host": "localhost",\n    "retries": 3,'
T1_TIMEOUT_RULE = (
    '            raise ValueError("port must be an int in 1..65535")\n'
    '        if key == "timeout" and not (isinstance(value, (int, float)) and value > 0):\n'
    '            raise ValueError("timeout must be a positive number")'
)
T1_RETRIES_RULE = (
    '            raise ValueError("host must be a non-empty string")\n'
    '        if key == "retries" and not (isinstance(value, int) and value >= 0):\n'
    '            raise ValueError("retries must be a non-negative int")'
)


def _t1_full_file(with_timeout: bool, with_retries: bool) -> str:
    content = T1_INITIAL
    if with_timeout:
        content = content.replace('    "port": 8080,\n}', T1_TIMEOUT_DEFAULT, 1)
        content = content.replace(
            '            raise ValueError("port must be an int in 1..65535")',
            T1_TIMEOUT_RULE, 1)
    if with_retries:
        content = content.replace('    "host": "localhost",', T1_RETRIES_DEFAULT, 1)
        content = content.replace(
            '            raise ValueError("host must be a non-empty string")',
            T1_RETRIES_RULE, 1)
    return content


# ---------------------------------------------------------------- t2 fragments

T2_SLUGIFY_OLD = (
    '    slugify("Hello, World!") == "hello-world"\n'
    '    """\n'
    "    raise NotImplementedError"
)
T2_SLUGIFY_NEW = (
    '    slugify("Hello, World!") == "hello-world"\n'
    '    """\n'
    "    text = text.lower()\n"
    '    text = re.sub(r"[^a-z0-9]+", "-", text)\n'
    '    return text.strip("-")'
)
T2_TRUNCATE_OLD = (
    '    truncate("abcdefghij", 7) == "abcd..."\n'
    '    """\n'
    "    raise NotImplementedError"
)
T2_TRUNCATE_NEW = (
    '    truncate("abcdefghij", 7) == "abcd..."\n'
    '    """\n'
    "    if len(text) <= max_len:\n"
    "        return text\n"
    "    if max_len < len(suffix):\n"
    "        return suffix[:max_len]\n"
    "    return text[: max_len - len(suffix)] + suffix"
)

# ---------------------------------------------------------------- script table

SCRIPTS: dict[tuple[str, str, str], list[tuple[str, dict]]] = {
    # t1 — composing anchored edits (correct under every strategy)
    ("t1_stale_read", "agent-timeout", "edit"): [
        ("read_file", {"path": "config.py"}),
        ("edit_file", {"path": "config.py",
                       "old_string": '    "port": 8080,\n}',
                       "new_string": T1_TIMEOUT_DEFAULT}),
        ("edit_file", {"path": "config.py",
                       "old_string": '            raise ValueError("port must be an int in 1..65535")',
                       "new_string": T1_TIMEOUT_RULE}),
        ("run_tests", {}),
        ("done", {"summary": "added timeout key + validation"}),
    ],
    ("t1_stale_read", "agent-retries", "edit"): [
        ("read_file", {"path": "config.py"}),
        ("edit_file", {"path": "config.py",
                       "old_string": '    "host": "localhost",',
                       "new_string": T1_RETRIES_DEFAULT}),
        ("edit_file", {"path": "config.py",
                       "old_string": '            raise ValueError("host must be a non-empty string")',
                       "new_string": T1_RETRIES_RULE}),
        ("run_tests", {}),
        ("done", {"summary": "added retries key + validation"}),
    ],
    # t1 — stale whole-file rewrites (lost update under naive)
    ("t1_stale_read", "agent-timeout", "clobber"): [
        ("read_file", {"path": "config.py"}),
        ("write_file", {"path": "config.py",
                        "content": _t1_full_file(with_timeout=True, with_retries=False)}),
        ("done", {"summary": "rewrote config.py with timeout support"}),
    ],
    ("t1_stale_read", "agent-retries", "clobber"): [
        ("read_file", {"path": "config.py"}),
        ("write_file", {"path": "config.py",
                        "content": _t1_full_file(with_timeout=False, with_retries=True)}),
        ("done", {"summary": "rewrote config.py with retries support"}),
    ],
    # t2 — disjoint-function edits (any stall is a false positive)
    ("t2_benign_overlap", "agent-slugify", "edit"): [
        ("read_file", {"path": "stringutils.py"}),
        ("edit_file", {"path": "stringutils.py",
                       "old_string": T2_SLUGIFY_OLD, "new_string": T2_SLUGIFY_NEW}),
        ("done", {"summary": "implemented slugify"}),
    ],
    ("t2_benign_overlap", "agent-truncate", "edit"): [
        ("read_file", {"path": "stringutils.py"}),
        ("edit_file", {"path": "stringutils.py",
                       "old_string": T2_TRUNCATE_OLD, "new_string": T2_TRUNCATE_NEW}),
        ("done", {"summary": "implemented truncate"}),
    ],
}


def get_script(task: str, agent_id: str, variant: str) -> list[tuple[str, dict]]:
    key = (task, agent_id, variant)
    if key not in SCRIPTS:
        raise KeyError(f"no script for {key}; scripted mode covers "
                       f"{sorted({k[0] for k in SCRIPTS})}")
    return SCRIPTS[key]
