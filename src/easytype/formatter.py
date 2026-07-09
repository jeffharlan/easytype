from __future__ import annotations

import json
import os
import urllib.request

from easytype.config import Config

PROMPT = (
    "You clean up dictated text. Apply ONLY these changes:\n"
    "- Remove filler words (um, uh, er, like).\n"
    "- When the speaker corrects themselves mid-thought, keep only the final "
    "wording and drop the abandoned false start.\n"
    "- Fix punctuation: add commas at natural pauses, split run-on sentences with "
    "periods, end questions with a question mark.\n\n"
    "Hard rules: do NOT drop, summarize, merge, or omit any point the speaker "
    "actually made. Do NOT add, substitute, or reword content. Do NOT change proper "
    "nouns or capitalization. If unsure, leave the words as they are. Output ONLY "
    "the cleaned text — no preamble, no explanation, no surrounding quotes.\n\nText:\n"
)


def format_text(text: str, config: Config) -> str:
    if not config.formatter_enabled or not text.strip():
        return text
    try:
        call = _call_openai if config.formatter_backend == "openai" else _call_ollama
        return _unwrap(call(text, config)) or text
    except Exception:
        return text  # never lose the transcript over a cleanup failure


def _unwrap(out: str) -> str:
    """Small models often wrap the answer in a 'Here is ...:' preamble line and/or
    surrounding quotes despite being told not to. Strip those so only the cleaned
    text reaches the document."""
    out = (out or "").strip()
    head, sep, rest = out.partition("\n")
    if sep and head.rstrip().endswith(":") and len(head) <= 60:
        out = rest.strip()
    if len(out) >= 2 and out[0] in "\"'“‘" and out[-1] in "\"'”’":
        out = out[1:-1].strip()
    return out


def _call_ollama(text: str, config: Config) -> str:
    payload = json.dumps({
        "model": config.ollama_model,
        "prompt": PROMPT + text,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        f"{config.ollama_url}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
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
