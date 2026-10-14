"""AI layer: one interface over Gemini, Claude, OpenAI and Azure OpenAI, plus embeddings.

Every AI step in RevenueForge calls `complete_json` / `embed`. Calls are throttled to the configured
requests-per-minute (free Gemini keys are rate-limited), retried on rate-limit errors, and every
caller has a rules-engine fallback so a failed AI call never stops a deal.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import deque

import httpx

from ..config import settings

log = logging.getLogger("revenueforge.llm")


class LLMUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------- provider status
def provider_name() -> str:
    p = settings.llm_provider
    if p == "gemini" and settings.gemini_api_key:
        return "gemini"
    if p == "anthropic" and settings.anthropic_api_key:
        return "anthropic"
    if p == "openai" and settings.openai_api_key:
        return "openai"
    if p == "azure" and settings.azure_api_key and settings.azure_endpoint and settings.azure_deployment:
        return "azure"
    return "none"


def is_enabled() -> bool:
    return provider_name() != "none" and not _state["disabled_reason"]


_state: dict = {"gemini_model": None, "disabled_reason": "", "calls": 0, "failures": 0, "last_error": "", "embed_ok": None}


def status() -> dict:
    p = provider_name()
    model = {"gemini": _state["gemini_model"] or settings.gemini_model or "auto (newest Flash)",
             "anthropic": settings.anthropic_model, "openai": settings.openai_model, "azure": settings.azure_deployment}.get(p, "")
    return {"provider": p, "model": model, "enabled": is_enabled(), "configured_provider": settings.llm_provider,
            "paid": settings.llm_paid, "rpm": settings.llm_rpm, "calls": _state["calls"], "failures": _state["failures"],
            "last_error": _state["last_error"][:300], "disabled_reason": _state["disabled_reason"],
            "embeddings": p in ("gemini", "openai") and _state["embed_ok"] is not False}


# --------------------------------------------------------------------------- throttle
_lock = threading.Lock()
_stamps: deque[float] = deque()


def _throttle():
    rpm = max(1, settings.llm_rpm)
    while True:
        with _lock:
            now = time.time()
            while _stamps and now - _stamps[0] > 60:
                _stamps.popleft()
            if len(_stamps) < rpm:
                _stamps.append(now)
                return
            wait = 60 - (now - _stamps[0]) + 0.2
        time.sleep(max(0.2, wait))


# --------------------------------------------------------------------------- gemini (REST)
def _gemini_headers():
    return {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"}


def _gemini_pick_model(client: httpx.Client) -> str:
    if settings.gemini_model:
        return settings.gemini_model
    if _state["gemini_model"]:
        return _state["gemini_model"]
    try:
        r = client.get(f"{settings.gemini_base_url}/models", headers=_gemini_headers(), params={"pageSize": 200})
        r.raise_for_status()
        names = []
        for m in r.json().get("models", []):
            name = m.get("name", "").split("/")[-1]
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods or "flash" not in name:
                continue
            if re.search(r"lite|image|tts|live|audio|preview|exp|thinking|native|8b|latest|robotics|computer", name):
                continue
            ver = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
            names.append((float(ver.group(1)) if ver else 0, name))
        if names:
            names.sort(reverse=True)
            _state["gemini_model"] = names[0][1]
            log.info("Gemini model selected: %s", names[0][1])
            return names[0][1]
    except Exception as e:  # listing failed: fall back to the rolling alias
        log.warning("Could not list Gemini models: %s", e)
    _state["gemini_model"] = "gemini-flash-latest"
    return _state["gemini_model"]


def _gemini_complete(system: str, prompt: str, max_tokens: int, temperature: float, want_json: bool) -> str:
    with httpx.Client(timeout=180) as client:
        model = _gemini_pick_model(client)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max(max_tokens, 8192)},
        }
        if want_json:
            body["generationConfig"]["responseMimeType"] = "application/json"
        r = client.post(f"{settings.gemini_base_url}/models/{model}:generateContent", headers=_gemini_headers(), json=body)
        if r.status_code == 404 and not settings.gemini_model:
            _state["gemini_model"] = None
        if r.status_code >= 400:
            raise _HttpError(r.status_code, r.text, r.headers.get("retry-after"))
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            raise LLMUnavailable(f"Gemini returned no answer ({data.get('promptFeedback', {}).get('blockReason', 'unknown reason')})")
        parts = cands[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise LLMUnavailable(f"Gemini returned an empty answer (finish reason {cands[0].get('finishReason')})")
        return text


def _gemini_embed(texts: list[str], task: str) -> list[list[float]]:
    out: list[list[float]] = []
    model = settings.gemini_embed_model
    with httpx.Client(timeout=120) as client:
        for start in range(0, len(texts), 100):
            chunk = texts[start:start + 100]
            body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t[:6000] or " "}]}, "taskType": task,
                                  "outputDimensionality": 768} for t in chunk]}
            _throttle()
            r = client.post(f"{settings.gemini_base_url}/models/{model}:batchEmbedContents", headers=_gemini_headers(), json=body)
            if r.status_code >= 400:
                raise _HttpError(r.status_code, r.text, r.headers.get("retry-after"))
            for e in r.json().get("embeddings", []):
                out.append(_normalize(e.get("values", [])))
    return out


# --------------------------------------------------------------------------- other providers
def _other_complete(p: str, system: str, prompt: str, max_tokens: int, temperature: float, want_json: bool) -> str:
    if p == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(model=settings.anthropic_model, max_tokens=max_tokens, temperature=temperature,
                                     system=system, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    if p == "openai":
        from openai import OpenAI

        client, model = OpenAI(api_key=settings.openai_api_key), settings.openai_model
    else:
        from openai import AzureOpenAI

        client = AzureOpenAI(api_key=settings.azure_api_key, azure_endpoint=settings.azure_endpoint, api_version=settings.azure_api_version)
        model = settings.azure_deployment
    kw = {"response_format": {"type": "json_object"}} if want_json else {}
    r = client.chat.completions.create(model=model, max_tokens=max_tokens, temperature=temperature,
                                       messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}], **kw)
    return r.choices[0].message.content or ""


class _HttpError(Exception):
    def __init__(self, status: int, body: str, retry_after: str | None):
        super().__init__(f"HTTP {status}: {body[:400]}")
        self.status, self.body, self.retry_after = status, body, retry_after


# --------------------------------------------------------------------------- public API
def complete(system: str, prompt: str, max_tokens: int = 4000, temperature: float = 0.2, want_json: bool = False) -> str:
    p = provider_name()
    if p == "none":
        raise LLMUnavailable("No AI provider configured")
    if _state["disabled_reason"]:
        raise LLMUnavailable(_state["disabled_reason"])
    last = None
    for attempt in range(4):
        _throttle()
        try:
            _state["calls"] += 1
            if p == "gemini":
                return _gemini_complete(system, prompt, max_tokens, temperature, want_json)
            return _other_complete(p, system, prompt, max_tokens, temperature, want_json)
        except _HttpError as e:
            last = e
            if e.status in (401, 403) or (e.status == 400 and "API key" in e.body):
                _state["disabled_reason"] = "The AI key was rejected. Check GEMINI_API_KEY in backend/.env and restart."
                break
            wait = 15 * (attempt + 1)
            m = re.search(r'"retryDelay":\s*"(\d+)', e.body)
            if m:
                wait = int(m.group(1)) + 1
            elif e.retry_after and e.retry_after.isdigit():
                wait = int(e.retry_after) + 1
            if e.status in (429, 500, 502, 503, 504):
                log.warning("AI call failed (%s); retrying in %ss", e.status, wait)
                time.sleep(min(wait, 65))
                continue
            break
        except Exception as e:
            last = e
            log.warning("AI call failed (attempt %s): %s", attempt + 1, e)
            time.sleep(3 * (attempt + 1))
    _state["failures"] += 1
    _state["last_error"] = str(last)
    raise LLMUnavailable(f"AI call failed: {last}")


def complete_json(system: str, prompt: str, max_tokens: int = 8000):
    raw = complete(system + "\nRespond with valid JSON only. No prose, no code fences.", prompt, max_tokens=max_tokens, want_json=True)
    return parse_json(raw)


def parse_json(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def embeddings_enabled() -> bool:
    return is_enabled() and provider_name() in ("gemini", "openai") and _state["embed_ok"] is not False


def embed(texts: list[str], task: str = "SEMANTIC_SIMILARITY") -> list[list[float]]:
    """Unit-normalised embedding vectors. Raises LLMUnavailable when embeddings aren't available."""
    if not texts:
        return []
    if not embeddings_enabled():
        raise LLMUnavailable("Embeddings not available")
    p = provider_name()
    for attempt in range(3):
        try:
            if p == "gemini":
                vecs = _gemini_embed(texts, task)
            else:
                from openai import OpenAI

                client = OpenAI(api_key=settings.openai_api_key)
                vecs = []
                for start in range(0, len(texts), 500):
                    _throttle()
                    r = client.embeddings.create(model="text-embedding-3-small", input=[t[:6000] or " " for t in texts[start:start + 500]])
                    vecs += [_normalize(d.embedding) for d in r.data]
            _state["embed_ok"] = True
            return vecs
        except _HttpError as e:
            if e.status == 429:
                time.sleep(20 * (attempt + 1))
                continue
            if e.status in (400, 404):
                _state["embed_ok"] = False  # model not available for this key: use text matching instead
            raise LLMUnavailable(str(e))
        except Exception as e:
            raise LLMUnavailable(str(e))
    raise LLMUnavailable("Embedding rate limit")


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
