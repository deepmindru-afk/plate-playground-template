"""Application configuration loaded from the environment."""

import os


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.environ.get("PLATE_DATA_DIR", os.path.join(BACKEND_DIR, "data"))
DOCS_DIR = os.path.join(DATA_DIR, "docs")

# --- LLM (LiveKit OpenAI plugin) ----------------------------------------
# Server-side credential. A key sent by the client in the request body is
# used as a fallback when this is unset.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None

AI_COMMAND_MODEL = os.environ.get("AI_COMMAND_MODEL", "gpt-4o-mini")
AI_CHOOSE_MODEL = os.environ.get("AI_CHOOSE_MODEL", "gpt-4o-mini")
AI_EDIT_MODEL = os.environ.get("AI_EDIT_MODEL", "gpt-4o-mini")
AI_EDIT_SELECTION_MODEL = os.environ.get("AI_EDIT_SELECTION_MODEL", "gpt-4o-mini")
AI_COPILOT_MODEL = os.environ.get("AI_COPILOT_MODEL", "gpt-4o-mini")

# Whether the client-supplied apiKey is honored when the env key is missing.
ALLOW_CLIENT_API_KEY = _get_bool("ALLOW_CLIENT_API_KEY", True)

# --- HTTP ----------------------------------------------------------------
CORS_ORIGINS = _get_csv(
    "BACKEND_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)


def ensure_dirs() -> None:
    os.makedirs(DOCS_DIR, exist_ok=True)