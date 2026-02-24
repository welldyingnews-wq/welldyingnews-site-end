"""Simple Anthropic/Claude client wrapper used by the app.

This wrapper prefers the official `anthropic` package when available and
falls back to a direct HTTP call via `requests` if not. It reads the
`ANTHROPIC_API_KEY` from environment (optionally from a `.env` file).

Usage:
    from utils.claude_client import ClaudeClient
    client = ClaudeClient()
    out = client.generate_text("Summarize: ...")
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY not set in environment. See .env.example")


class ClaudeClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or API_KEY
        # detect if official SDK is available
        try:
            from anthropic import Anthropic  # type: ignore

            self._sdk = Anthropic(api_key=self.api_key)
        except Exception:
            self._sdk = None

    def generate_text(self, prompt: str, model: str = "claude-2", max_tokens: int = 300, temperature: float = 0.0) -> str:
        """Generate text from Claude.

        This tries to use the `anthropic` SDK; if unavailable, it falls
        back to a simple HTTP POST to the Anthropic endpoint.
        """
        if self._sdk:
            try:
                # SDK interface may vary; attempt common pattern
                resp = self._sdk.completions.create(
                    model=model,
                    prompt=prompt,
                    max_tokens_to_sample=max_tokens,
                    temperature=temperature,
                )
                # SDKs may return different shapes; try common keys
                return getattr(resp, "completion", None) or resp.get("completion") or str(resp)
            except Exception:
                pass

        # Fallback via HTTP
        import requests

        url = "https://api.anthropic.com/v1/complete"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens_to_sample": max_tokens,
            "temperature": temperature,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("completion") or data.get("text") or str(data)


if __name__ == "__main__":
    # quick local smoke test
    c = ClaudeClient()
    print(c.generate_text("Say hello in Korean."))
