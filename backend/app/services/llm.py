"""Configurable LLM provider adapters (OpenAI-compatible, Anthropic, Ollama) with fallback.

An unavailable provider is reported as unavailable. Outputs are never fabricated, and every
structured response is validated against a schema by the caller before use.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from ..config import get_settings


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    error: str | None = None
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float | None:
        s = get_settings()
        if not (s.llm_price_in_per_mtok or s.llm_price_out_per_mtok):
            return None
        return (self.input_tokens * s.llm_price_in_per_mtok + self.output_tokens * s.llm_price_out_per_mtok) / 1e6


def _call(provider: str, model: str, system: str, user: str) -> LLMResult:
    s = get_settings()
    t0 = time.perf_counter()
    if provider in ("none", "") or not model:
        return LLMResult(False, error="not configured", provider=provider, model=model)
    try:
        with httpx.Client(timeout=s.llm_timeout_s) as client:
            if provider == "openai":
                if not s.openai_api_key:
                    return LLMResult(False, error="OPENAI_API_KEY not set", provider=provider, model=model)
                r = client.post(f"{s.openai_base_url.rstrip('/')}/chat/completions",
                                headers={"Authorization": f"Bearer {s.openai_api_key}"},
                                json={"model": model, "temperature": 0,
                                      "response_format": {"type": "json_object"},
                                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                r.raise_for_status()
                d = r.json()
                u = d.get("usage") or {}
                return LLMResult(True, d["choices"][0]["message"]["content"], provider=provider, model=model,
                                 input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0),
                                 latency_s=time.perf_counter() - t0)
            if provider == "anthropic":
                if not s.anthropic_api_key:
                    return LLMResult(False, error="ANTHROPIC_API_KEY not set", provider=provider, model=model)
                r = client.post("https://api.anthropic.com/v1/messages",
                                headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"},
                                json={"model": model, "max_tokens": 2000, "temperature": 0, "system": system,
                                      "messages": [{"role": "user", "content": user}]})
                r.raise_for_status()
                d = r.json()
                text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
                u = d.get("usage") or {}
                return LLMResult(True, text, provider=provider, model=model, input_tokens=u.get("input_tokens", 0),
                                 output_tokens=u.get("output_tokens", 0), latency_s=time.perf_counter() - t0)
            if provider == "ollama":
                r = client.post(f"{s.ollama_base_url.rstrip('/')}/api/chat",
                                json={"model": model, "stream": False, "format": "json", "options": {"temperature": 0},
                                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                r.raise_for_status()
                d = r.json()
                return LLMResult(True, d.get("message", {}).get("content", ""), provider=provider, model=model,
                                 input_tokens=d.get("prompt_eval_count", 0), output_tokens=d.get("eval_count", 0),
                                 latency_s=time.perf_counter() - t0)
            return LLMResult(False, error=f"unknown provider {provider}", provider=provider, model=model)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        return LLMResult(False, error=f"{type(exc).__name__}: {str(exc)[:300]}", provider=provider, model=model,
                         latency_s=time.perf_counter() - t0)


def complete(system: str, user: str) -> LLMResult:
    s = get_settings()
    attempts = []
    for provider, model in ((s.llm_provider, s.llm_model), (s.llm_fallback_provider, s.llm_fallback_model)):
        if provider in ("none", ""):
            continue
        res = _call(provider, model, system, user)
        attempts.append({"provider": provider, "model": model, "ok": res.ok, "error": res.error})
        if res.ok:
            res.attempts = attempts
            return res
    return LLMResult(False, error="No LLM provider is available" if not attempts else "All configured providers failed",
                     attempts=attempts)


def status() -> dict:
    s = get_settings()
    configured = s.llm_provider not in ("none", "") and bool(s.llm_model)
    return {"provider": s.llm_provider, "model": s.llm_model, "fallback_provider": s.llm_fallback_provider,
            "fallback_model": s.llm_fallback_model, "configured": configured,
            "note": None if configured else "No LLM provider configured. Deterministic agents run; LLM-only features are disabled."}


def parse_json_object(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("response contains no JSON object")
    return json.loads(t[start:end + 1])
