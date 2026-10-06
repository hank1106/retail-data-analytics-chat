"""Runtime configuration loaded from environment variables.

All settings have safe defaults so the system runs with no API keys at all
(``LLM_PROVIDER=template``). Copy ``.env.example`` to ``.env`` to override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Load a local ``.env`` file without requiring any dependency."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass
class Settings:
    llm_provider: str = "template"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    database_path: str = "data/retail.db"
    data_csv: str = ""
    kaggle_dataset: str = "fahadrehman07/retail-transaction-dataset"
    backend_url: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            llm_provider=env("LLM_PROVIDER", "template").strip().lower() or "template",
            openai_api_key=env("OPENAI_API_KEY", ""),
            openai_model=env("OPENAI_MODEL", "gpt-4o-mini"),
            anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
            anthropic_model=env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            ollama_base_url=env("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=env("OLLAMA_MODEL", "llama3.1"),
            database_path=env("DATABASE_PATH", "data/retail.db"),
            data_csv=env("DATA_CSV", ""),
            kaggle_dataset=env(
                "KAGGLE_DATASET", "fahadrehman07/retail-transaction-dataset"
            ),
            backend_url=env("BACKEND_URL", ""),
        )

    def resolve_db_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
