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
    # t7 — schema rename + handler that reads live constant
    ("t7_rw_canary", "agent-schema", "edit"): [
        ("read_file", {"path": "schema/constants.py"}),
        ("edit_file", {"path": "schema/constants.py",
                       "old_string": 'STATUS_ACTIVE = "active"',
                       "new_string": 'STATUS_ACTIVE = "enabled"'}),
        ("done", {"summary": "renamed STATUS_ACTIVE to enabled"}),
    ],
    ("t7_rw_canary", "agent-handlers", "edit"): [
        ("read_file", {"path": "schema/constants.py"}),
        ("read_file", {"path": "handlers/report.py"}),
        ("write_file", {"path": "handlers/report.py", "content": (
            "from schema.constants import STATUS_ACTIVE\n\n\n"
            "def filter_active(records):\n"
            '    return [r for r in records if r.get("status") == STATUS_ACTIVE]\n\n\n'
            "def summarize_active(records):\n"
            '    return {"active_count": len(filter_active(records))}\n'
        )}),
        ("done", {"summary": "handlers use live STATUS_ACTIVE"}),
    ],
    # t8 — opposite-order edits (file_lock stress)
    ("t8_livelock", "agent-ab", "edit"): [
        ("edit_file", {"path": "alpha.py",
                       "old_string": 'GREETING = "hi"',
                       "new_string": 'GREETING = "hello"'}),
        ("edit_file", {"path": "beta.py",
                       "old_string": 'FAREWELL = "bye"',
                       "new_string": 'FAREWELL = "goodbye"'}),
        ("done", {"summary": "alpha then beta"}),
    ],
    ("t8_livelock", "agent-ba", "edit"): [
        ("edit_file", {"path": "beta.py",
                       "old_string": "COUNT = 1",
                       "new_string": "COUNT = 2"}),
        ("edit_file", {"path": "alpha.py",
                       "old_string": 'VERSION = "0.1"',
                       "new_string": 'VERSION = "0.2"'}),
        ("done", {"summary": "beta then alpha"}),
    ],
    # t9 — provably disjoint packages (any stall is overhead)
    ("t9_overhead", "agent-a", "edit"): [
        ("write_file", {"path": "mod_a/mathops.py",
                        "content": "def double(x):\n    return 2 * x\n"}),
        ("write_file", {"path": "mod_a/textops.py",
                        "content": 'def greet(name):\n    return f"hello {name}"\n'}),
        ("done", {"summary": "mod_a features"}),
    ],
    ("t9_overhead", "agent-b", "edit"): [
        ("write_file", {"path": "mod_b/mathops.py",
                        "content": "def square(x):\n    return x * x\n"}),
        ("write_file", {"path": "mod_b/textops.py",
                        "content": 'def shout(name):\n    return f"{name}!".upper()\n'}),
        ("done", {"summary": "mod_b features"}),
    ],
}


def get_script(task: str, agent_id: str, variant: str) -> list[tuple[str, dict]]:
    key = (task, agent_id, variant)
    if key not in SCRIPTS:
        raise KeyError(f"no script for {key}; scripted mode covers "
                       f"{sorted({k[0] for k in SCRIPTS})}")
    return SCRIPTS[key]
