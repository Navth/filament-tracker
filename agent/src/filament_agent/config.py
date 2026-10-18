"""Settings, read from the environment (and an optional .env file next to the package)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader: KEY=VALUE lines, existing environment wins."""
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


_load_dotenv()


def config_dir() -> Path:
    base = os.environ.get("FT_AGENT_HOME") or Path.home() / ".filament-agent"
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class AgentConfig:
    # "gemini" (free tier works) or "claude"
    provider: str = os.environ.get("FT_AGENT_PROVIDER", "gemini")
    # Claude settings (Gemini's model and thinking level live in gemini_llm.py)
    model: str = os.environ.get("FT_AGENT_MODEL", "claude-opus-5-5")
    effort: str = os.environ.get("FT_AGENT_EFFORT", "medium")
    max_tokens: int = int(os.environ.get("FT_AGENT_MAX_TOKENS", "16000"))
    # Model calls allowed per turn before the agent gives up (guards against loops).
    max_steps: int = int(os.environ.get("FT_AGENT_MAX_STEPS", "8"))
    # Token budget for conversation history carried into each turn.
    history_budget_tokens: int = int(os.environ.get("FT_AGENT_HISTORY_BUDGET", "3000"))
    # Number of most recent turns always kept verbatim.
    keep_recent_turns: int = int(os.environ.get("FT_AGENT_KEEP_TURNS", "4"))
    # Server-side refusal fallback (Claude API only). Set FT_AGENT_FALLBACKS=0 to disable.
    fallbacks: bool = os.environ.get("FT_AGENT_FALLBACKS", "1") != "0"


def supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    if not url:
        raise RuntimeError("Set SUPABASE_URL (see agent/.env.example)")
    return url


def supabase_key() -> str:
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    if not key:
        raise RuntimeError("Set SUPABASE_PUBLISHABLE_KEY (see agent/.env.example)")
    return key
