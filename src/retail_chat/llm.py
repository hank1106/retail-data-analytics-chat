"""LLM integration: pluggable response generation with a safe fallback.

Providers
---------
* ``template`` (default): deterministic, dependency-free answers rendered
  from the retrieved data. Works with no API keys and no network.
* ``openai``: Chat Completions API (needs ``OPENAI_API_KEY``).
* ``anthropic``: Messages API (needs ``ANTHROPIC_API_KEY``).
* ``ollama``: local Ollama server (needs Ollama running, no key).

All LLM providers receive the *already retrieved* database facts and are
instructed to answer only from them; any error (missing key, network
failure, bad response) raises :class:`LLMError` so the caller can fall back
to the template provider instead of failing the query.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .config import Settings
from .intent import (
    BUSINESS_OVERVIEW,
    CUSTOMER_HISTORY,
    CUSTOMER_PRODUCT,
    CUSTOMER_TOTAL,
    PRODUCT_DISCOUNT,
    PRODUCT_STORES,
    PRODUCT_SUMMARY,
    STORE_METRICS,
    TOP_CUSTOMERS,
    TOP_PRODUCTS,
)

SYSTEM_PROMPT = (
    "You are a retail analytics assistant. Answer the user's question using "
    "ONLY the facts in the provided DATA JSON. Quote the exact numbers. "
    "If the data shows no matching records, say so plainly. Keep the answer "
    "to a few sentences."
)


class LLMError(RuntimeError):
    pass


def money(value: float | None) -> str:
    return f"${(value or 0.0):,.2f}"


def pct(value: float | None) -> str:
    return f"{(value or 0.0) * 100:.1f}%"


class BaseProvider:
    name = "base"

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        raise NotImplementedError


class TemplateProvider(BaseProvider):
    """Deterministic answers rendered directly from retrieved facts."""

    name = "template"

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        window = f" in {data['window']}" if data.get("window") else ""
        if intent == CUSTOMER_HISTORY:
            lines = [
                f"Customer {data['customer_id']} made {data['transaction_count']} "
                f"purchase(s){window}, spending {money(data['total_spent'])} in total."
            ]
            for p in data["purchases"][:5]:
                lines.append(
                    f"- {p['transaction_date']}: {p['quantity']} x {p['product_id']} "
                    f"at {p['store_id']} for {money(p['total_amount'])}"
                )
            if data["transaction_count"] > 5:
                lines.append(
                    f"... and {data['transaction_count'] - 5} more transaction(s)."
                )
            return "\n".join(lines)
        if intent == CUSTOMER_TOTAL:
            return (
                f"Customer {data['customer_id']} has spent "
                f"{money(data['total_spent'])} in total across "
                f"{data['transaction_count']} transaction(s){window}."
            )
        if intent == CUSTOMER_PRODUCT:
            return (
                f"Customer {data['customer_id']} bought product "
                f"{data['product_id']} {data['times_bought']} time(s){window} "
                f"({data['total_quantity']} unit(s), {money(data['total_spent'])})."
            )
        if intent == PRODUCT_DISCOUNT:
            return (
                f"Product {data['product_id']} was sold {data['times_sold']} "
                f"time(s){window} with an average discount of "
                f"{pct(data['avg_discount'])}."
            )
        if intent == PRODUCT_STORES:
            stores = ", ".join(data["stores"]) if data["stores"] else "no stores"
            return (
                f"Product {data['product_id']} is sold at {len(data['stores'])} "
                f"store(s){window}: {stores} "
                f"({data['times_sold']} sale(s) in total)."
            )
        if intent == PRODUCT_SUMMARY:
            stores = ", ".join(data["stores"]) if data["stores"] else "no stores"
            return (
                f"Product {data['product_id']}{window}: sold {data['times_sold']} "
                f"time(s) ({data['total_quantity']} unit(s)) for "
                f"{money(data['total_revenue'])} in revenue, average discount "
                f"{pct(data['avg_discount'])}. Available at: {stores}."
            )
        if intent == BUSINESS_OVERVIEW:
            return (
                f"Business overview{window}: {money(data['total_revenue'])} revenue "
                f"across {data['transaction_count']} transaction(s) from "
                f"{data['customer_count']} customer(s), {data['product_count']} "
                f"product(s) and {data['store_count']} store(s). "
                f"Average basket: {money(data['avg_basket'])}."
            )
        if intent == TOP_PRODUCTS:
            rows = [
                f"{i + 1}. {r['product_id']} — {money(r['revenue'])} "
                f"({r['times_sold']} sales)"
                for i, r in enumerate(data["items"])
            ]
            return f"Top {len(rows)} product(s) by revenue{window}:\n" + "\n".join(rows)
        if intent == TOP_CUSTOMERS:
            rows = [
                f"{i + 1}. {r['customer_id']} — {money(r['total_spent'])} "
                f"({r['transactions']} purchases)"
                for i, r in enumerate(data["items"])
            ]
            return f"Top {len(rows)} customer(s) by spending{window}:\n" + "\n".join(rows)
        if intent == STORE_METRICS:
            rows = [
                f"- {r['store_id']}: {money(r['revenue'])} "
                f"({r['transactions']} transactions)"
                for r in data["stores"]
            ]
            by_cat = ""
            if data.get("categories"):
                cats = ", ".join(
                    f"{c['product_category']} ({money(c['revenue'])})"
                    for c in data["categories"][:3]
                )
                by_cat = f" Top categories: {cats}."
            return f"Revenue by store{window}:\n" + "\n".join(rows) + by_cat
        return str(data)


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network/auth errors -> caller falls back
        raise LLMError(f"LLM request failed: {exc}") from exc


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set.")
        self.api_key = api_key
        self.model = model

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        body = _post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"QUESTION: {question}\nDATA: {json.dumps(data)}",
                    },
                ],
                "temperature": 0.2,
            },
            {"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            return body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise LLMError(f"Unexpected OpenAI response: {body!r}") from exc


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set.")
        self.api_key = api_key
        self.model = model

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        body = _post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "model": self.model,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"QUESTION: {question}\nDATA: {json.dumps(data)}",
                    }
                ],
            },
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            return body["content"][0]["text"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise LLMError(f"Unexpected Anthropic response: {body!r}") from exc


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        body = _post_json(
            f"{self.base_url}/api/generate",
            {
                "model": self.model,
                "system": SYSTEM_PROMPT,
                "prompt": f"QUESTION: {question}\nDATA: {json.dumps(data)}",
                "stream": False,
            },
            {},
            timeout=90,
        )
        try:
            return body["response"].strip()
        except KeyError as exc:
            raise LLMError(f"Unexpected Ollama response: {body!r}") from exc


@dataclass
class Responder:
    """Primary provider with automatic template fallback on any failure."""

    primary: BaseProvider
    fallback: BaseProvider = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.fallback is None:
            self.fallback = TemplateProvider()

    def generate(self, *, question: str, intent: str, data: dict) -> str:
        try:
            return self.primary.generate(
                question=question, intent=intent, data=data
            )
        except LLMError:
            return self.fallback.generate(
                question=question, intent=intent, data=data
            )


def build_provider(settings: Settings) -> BaseProvider:
    """Build the configured provider (no network calls at build time)."""
    provider = settings.llm_provider
    if provider == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    if provider != "template":
        raise LLMError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            "Use template | openai | anthropic | ollama."
        )
    return TemplateProvider()


def build_responder(settings: Settings) -> Responder:
    try:
        return Responder(primary=build_provider(settings))
    except LLMError:
        # Misconfiguration (e.g. unknown provider name) -> fail closed to template.
        return Responder(primary=TemplateProvider())
