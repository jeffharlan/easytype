from __future__ import annotations

import json
import os
import urllib.request

from easytype.config import Config

PROMPT = (
    "Clean up this dictated text: remove filler words (um, uh, like), resolve spoken "
    "self-corrections, and fix punctuation. Preserve meaning and wording otherwise. "
    "Return ONLY the cleaned text.\n\nText:\n"
)


def format_text(text: str, config: Config) -> str:
    if not config.formatter_enabled or not text.strip():
        return text
    try:
        if config.formatter_backend == "openai":
            return _call_openai(text, config) or text
        return _call_ollama(text, config) or text
    except Exception:
        return text  # never lose the transcript over a cleanup failure


def _call_ollama(text: str, config: Config) -> str:
    payload = json.dumps({
        "model": config.ollama_model,
        "prompt": PROMPT + text,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{config.ollama_url}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["response"].strip()


def _call_openai(text: str, config: Config) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return ""
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": PROMPT + text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
