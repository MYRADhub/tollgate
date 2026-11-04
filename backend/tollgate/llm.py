"""Thin client for Vultr Serverless Inference (OpenAI-compatible)."""

from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

from openai import OpenAI

from .config import get_settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


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
    return resp


def chat_json(model: str, messages: list[dict], **kw) -> Any:
    last: Exception | None = None
    for _ in range(2):
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
