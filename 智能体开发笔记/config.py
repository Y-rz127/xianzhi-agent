"""Shared config helpers for AI learning scripts.

Copy `.env.example` to `.env` and fill local values before running examples.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Keep scripts importable before installing optional deps.
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"

if load_dotenv is not None:
    load_dotenv(ENV_FILE)


def get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


OPENAI_MODEL = get_env("OPENAI_MODEL", "openai:gpt-4.1-mini")
REDIS_URL = get_env("REDIS_URL", "redis://127.0.0.1:6379")
MILVUS_URI = get_env("MILVUS_URI", "http://127.0.0.1:19530")
OLLAMA_BASE_URL = get_env("OLLAMA_BASE_URL", "http://localhost:11434")

