"""Prompt-injection screening for inbound documents and emails.

Layers, any of which raises a signal:
1. Text a human cannot see on the rendered page (pdfdoc.find_hidden_text).
2. Instruction-shaped phrases anywhere in the text.
3. Vultr's content-safety model, when configured.
4. The extraction model's own report of instructions it noticed.
Signals never change extracted values; they hold the invoice for a person.
"""

from __future__ import annotations

import logging
import re

from .config import get_settings

log = logging.getLogger(__name__)

PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above) ",
    r"\b(you are|act as) (an? )?(ai|assistant|language model|llm)\b",
    r"\b(ai|llm) (assistant|agent|model)\s*[:,]",
    r"system prompt",
    r"\bpre-?approved\b",
    r"(do not|don't|never) (flag|report|mention|escalate|hold)",
    r"(mark|set) (this )?(invoice )?(as )?(paid|approved|verified)",
    r"(update|change|replace) (the )?(vendor'?s? )?(bank|remit|payment) (account|details|info)",
    r"approve (this|the) (payment|invoice) (immediately|automatically|without)",
    r"\b(ai|automated|llm)( processing)? (systems?|readers?|assistants?|agents?|models?)\b.{0,80}\b(approve|pay|skip|bypass|without review)",
    r"\bwithout (human |manual )?review\b",
]
_RX = [re.compile(p, re.I) for p in PATTERNS]


def scan_text(text: str, source: str) -> list[dict]:
    hits = []
    for rx in _RX:
        m = rx.search(text or "")
        if m:
            a, b = max(0, m.start() - 120), min(len(text), m.end() + 160)
            hits.append({"kind": "instruction phrase", "source": source, "excerpt": text[a:b].strip(), "pattern": rx.pattern})
            break
    return hits


def screen(text: str, hidden_spans: list[str], model_reported: list[str] | None = None) -> list[dict]:
    signals: list[dict] = []
    for span in hidden_spans:
        if len(span.split()) >= 4:
            signals.append({"kind": "hidden text", "source": "pdf", "excerpt": span})
    if not signals:
        signals += scan_text(text, "document text")
    for rep in model_reported or []:
        if rep and len(rep.strip()) > 8 and not any(rep[:40] in s["excerpt"] for s in signals):
            signals.append({"kind": "reported by extraction model", "source": "model", "excerpt": rep})
    safety = safety_check(text) if signals or len(text) < 20000 else None
    if safety:
        if signals:
            signals[0]["safety_model"] = safety
        elif safety.get("unsafe"):
            signals.append({"kind": "content-safety model", "source": "model", "excerpt": safety.get("raw", "")[:300]})
    return signals


def safety_check(text: str) -> dict | None:
    s = get_settings()
    if not s.inference_api_key or not s.model_safety:
        return None
    try:
        from .llm import chat

        resp = chat(
            s.model_safety,
            [{"role": "user", "content": text[:8000]}],
            max_tokens=200,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        unsafe = bool(re.search(r"\bunsafe\b", raw, re.I)) and not re.search(r"user safety:\s*safe\b", raw, re.I)
        return {"unsafe": unsafe, "raw": raw}
    except Exception as e:  # safety model is defence in depth, never a hard dependency
        log.warning("safety model unavailable: %s", e)
        return None
