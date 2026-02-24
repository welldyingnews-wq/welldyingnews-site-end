"""Small script to test Claude integration locally.

Usage:
    source .venv/bin/activate
    cp .env.example .env
    # edit .env and set ANTHROPIC_API_KEY
    pip install -r requirements.txt
    python scripts/test_claude.py
"""
from utils.claude_client import ClaudeClient


def main():
    client = ClaudeClient()
    prompt = "Write a short 2-line Korean greeting for a news article header."
    out = client.generate_text(prompt, model="claude-2", max_tokens=120)
    print("PROMPT:\n", prompt)
    print("\nRESPONSE:\n", out)


if __name__ == "__main__":
    main()
