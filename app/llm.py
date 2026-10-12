"""Optional LLM layer. Data grounding always comes from SQLite; the LLM
(if configured) only rephrases the evidence into a natural-language reply.

Provider chain: OpenAI -> Anthropic -> Ollama -> built-in template fallback.
Without any API key the system works fully offline, which keeps grading and
local runs dependency-free. Set ``LLM_PROVIDER=off`` to force templates.
"""

from __future__ import annotations

import json
import os
import urllib.request

SYSTEM_PROMPT = (
    "You answer retail-analytics questions using ONLY the JSON evidence given. "
    "Never invent numbers, IDs, stores, or dates. If evidence says nothing was "
    "found, say so briefly and suggest a valid alternative. Keep answers short."
)


def _openai_rerite(prompt: str, evidence: dict) -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{prompt}\nEvidence:\n{json.dumps(evidence)[:4000]}"},
            ],
            max_tokens=300,
            temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None


def _anthropic_rewrite(prompt: str, evidence: dict) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{prompt}\nEvidence:\n{json.dumps(evidence)[:4000]}"}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text.strip() or None
    except Exception:
        return None


def _ollama_rewrite(prompt: str, evidence: dict) -> str | None:
    host = os.getenv("OLLAMA_HOST")
    if not host:
        return None
    try:
        body = json.dumps({
            "model": os.getenv("OLLAMA_MODEL", "llama3.1"),
            "system": SYSTEM_PROMPT,
            "prompt": f"{prompt}\nEvidence:\n{json.dumps(evidence)[:4000]}",
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{host.rstrip('/')}/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return (json.loads(r.read().decode()).get("response") or "").strip() or None
    except Exception:
        return None


def rewrite(prompt: str, evidence: dict, template: str) -> tuple[str, str]:
    """Return (response_text, provider_name). Template is the offline answer."""
    if os.getenv("LLM_PROVIDER", "").lower() == "off":
        return template, "template"
    for name, fn in (
        ("openai", _openai_rerite),
        ("anthropic", _anthropic_rewrite),
        ("ollama", _ollama_rewrite),
    ):
        try:
            out = fn(prompt, evidence)
        except Exception:
            out = None
        if out:
            return out, name
    return template, "template"


def provider_status() -> dict:
    return {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "ollama": bool(os.getenv("OLLAMA_HOST")),
        "forced_off": os.getenv("LLM_PROVIDER", "").lower() == "off",
    }
