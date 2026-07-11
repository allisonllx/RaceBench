"""Load environment variables from the repo-root .env file (if present).

Called at process startup before any OpenAI client is constructed. Existing
shell exports take precedence (override=False).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


def load_env() -> bool:
    """Load REPO_ROOT/.env into os.environ. Returns True if the file exists."""
    if not ENV_FILE.is_file():
        return False
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=False)
    return True
