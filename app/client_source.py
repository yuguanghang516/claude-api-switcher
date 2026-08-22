"""Classify gateway callers without storing identifying header values."""

from typing import Mapping


def classify_client_source(headers: Mapping[str, str]) -> str:
    """Return a coarse local client type used only for usage-scope filtering."""
    explicit = str(headers.get("X-Client-Source", "")).strip().lower()
    user_agent = str(headers.get("User-Agent", "")).strip().lower()
    combined = f"{explicit} {user_agent}"
    if "codex" in combined or "openai-cli" in combined:
        return "codex"
    if "claude" in combined or "anthropic" in combined:
        return "claude"
    return "other"
