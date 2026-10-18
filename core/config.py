import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(key, default)
    except Exception:
        return default


@dataclass
class Settings:
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: _env("GOOGLE_GEMINI_API_KEY"))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = field(default_factory=lambda: _env(
        "OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free"
    ))
    max_repair_retries: int = 2
    max_files_analyzed: int = 80
    max_file_size: int = 80_000
    request_timeout: int = 90
    ignore_dirs: list = field(
        default_factory=lambda: [
            ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
            "node_modules", "dist", "build", ".tox", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "site-packages", ".idea", ".vscode",
        ]
    )
    ignore_exts: list = field(
        default_factory=lambda: [
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
            ".pdf", ".zip", ".tar", ".gz", ".whl", ".exe", ".dll",
            ".so", ".bin", ".woff", ".woff2", ".ttf", ".db", ".sqlite",
        ]
    )


settings = Settings()
