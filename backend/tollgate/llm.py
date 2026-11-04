"""Thin client for Vultr Serverless Inference (OpenAI-compatible)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from functools import lru_cache
from typing import Any

from openai import OpenAI

from .config import get_settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


# USD per token, from https://api.vultrinference.com/v1/models (completion price).
# Prompt tokens are charged at the same rate here so the estimate errs high.
PRICE_PER_TOKEN = {
    "glm-5.3": 0.000003,
    "glm-5.3-flash": 0.00000035,
    "mimo-v2.6-pro": 0.000003,
    "qwen3.8-27b": 0.000001,
    "qwen3.8-flash-next": 0.0000002,
    "deepseek-v4.1-flash-1017": 0.0000006,
    "minimax-m3.1-flash": 0.0000009,
    "nemotron-3.5-content-safety": 0.00000015,
}
DEFAULT_PRICE = 0.000003


_pending: dict[str, list[float]] = {}
_lock = threading.Lock()


def _record(model: str, usage) -> None:
    """Accumulate usage in memory; flush_spend() persists it outside any open
    transaction (a nested write would deadlock SQLite)."""
    if usage is None:
        return
    p, c = int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)
    with _lock:
        row = _pending.setdefault(model, [0, 0, 0, 0.0])
        row[0] += 1
        row[1] += p
        row[2] += c
        row[3] += (p + c) * PRICE_PER_TOKEN.get(model, DEFAULT_PRICE)


def flush_spend() -> None:
    from decimal import Decimal

    from sqlalchemy import select

    from .db import session_scope
    from .models import InferenceSpend

    with _lock:
        items = list(_pending.items())
        _pending.clear()
    if not items:
        return
    try:
        with session_scope() as s:
            for model, (calls, p, c, usd) in items:
                row = s.execute(select(InferenceSpend).where(InferenceSpend.model == model)).scalar_one_or_none()
                if row is None:
                    row = InferenceSpend(model=model, calls=0, prompt_tokens=0, completion_tokens=0, usd=Decimal(0))
                    s.add(row)
                row.calls += int(calls)
                row.prompt_tokens += int(p)
                row.completion_tokens += int(c)
                row.usd = (row.usd or Decimal(0)) + Decimal(str(usd))
    except Exception:
        with _lock:
            for model, vals in items:
                row = _pending.setdefault(model, [0, 0, 0, 0.0])
                for i in range(4):
                    row[i] += vals[i]
        raise


def spent_usd() -> float:
    from sqlalchemy import func, select

    from .db import SessionLocal
    from .models import InferenceSpend

    with SessionLocal() as s:
        stored = float(s.execute(select(func.coalesce(func.sum(InferenceSpend.usd), 0))).scalar_one())
    with _lock:
        return stored + sum(v[3] for v in _pending.values())


@lru_cache
def client() -> OpenAI:
    s = get_settings()
    if not s.inference_api_key:
        raise LLMError("TOLLGATE_INFERENCE_API_KEY is not set")
    return OpenAI(base_url=s.inference_base_url, api_key=s.inference_api_key, timeout=s.llm_timeout_s, max_retries=2)


_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_json(text: str) -> Any:
    text = _THINK.sub("", text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError(f"model did not return JSON: {text[:200]!r}")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise LLMError(f"unterminated JSON from model: {text[:200]!r}")


def chat(model: str, messages: list[dict], *, json_mode: bool = False, temperature: float = 0.1, max_tokens: int = 4000, **kw):
    kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kw)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    budget = get_settings().inference_budget_usd
    if spent_usd() >= budget:
        raise BudgetExceeded(f"inference budget of ${budget:.2f} reached")
    t0 = time.monotonic()
    try:
        resp = client().chat.completions.create(**kwargs)
    except Exception as e:
        if json_mode and "response_format" in str(e):
            kwargs.pop("response_format", None)
            resp = client().chat.completions.create(**kwargs)
        else:
            raise
    log.info("llm %s %.1fs usage=%s", model, time.monotonic() - t0, getattr(resp, "usage", None))
    _record(model, getattr(resp, "usage", None))
    return resp


NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False, "thinking": False}}


def chat_json(model: str, messages: list[dict], **kw) -> Any:
    last: Exception | None = None
    for _ in range(2):
        resp = chat(model, messages, json_mode=True, **kw)
        choice = resp.choices[0]
        if not (choice.message.content or "").strip() and choice.finish_reason == "length":
            # Reasoning used the whole budget before any answer; ask again without it.
            log.warning("%s spent its token budget reasoning; retrying without thinking", model)
            kw = {**kw, "extra_body": {**kw.get("extra_body", {}), **NO_THINKING}}
            resp = chat(model, messages, json_mode=True, **kw)
        try:
            return parse_json(resp.choices[0].message.content or "")
        except (LLMError, json.JSONDecodeError) as e:
            last = e
            messages = messages + [
                {"role": "assistant", "content": resp.choices[0].message.content or ""},
                {"role": "user", "content": "That was not valid JSON. Reply with only the JSON object."},
            ]
    raise LLMError(str(last))
