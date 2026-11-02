"""Environment configuration. Secrets are only ever read from the environment."""
import os
from pathlib import Path

MAX_NODES = 30
MAX_DEPTH = 10
MAX_RUN_SECONDS = 600
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))  # local models can be slow on first load
LLM_RETRIES = 1


def load_env_file(path: Path) -> None:
    """Minimal .env loader; real environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).resolve().parent.parent / ".env")


def llm_settings() -> dict:
    return {"base_url": os.getenv("LLM_BASE_URL", "").rstrip("/"), "model": os.getenv("LLM_MODEL", ""),
            "api_key": os.getenv("LLM_API_KEY", ""), "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "350")),
            "max_words": int(os.getenv("LLM_MAX_WORDS", "120"))}


def llm_configured() -> bool:
    s = llm_settings()
    return bool(s["base_url"] and s["model"])


def db_path() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./promptgraph.db").replace("sqlite:///", "", 1)


def cors_origins() -> list:
    return [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
