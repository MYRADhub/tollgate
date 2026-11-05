"""Vendor document fingerprint: a model trained per vendor on that vendor's own
past invoices, which flags a PDF that was not produced the way that vendor's
invoices are produced, even when every field on it is right.

A vendor's billing system (Sage, SAP, QuickBooks...) lays out every invoice the
same way: the same producer and creator, the same fonts, the title and labels in
the same places, the same line pitch. A fraudster who rebuilds the invoice in a
word processor, or edits a real one to change the bank details, changes some of
that. The fields can be perfect and the document still gives itself away.

The model is one-class (it only ever sees genuine documents):
  - categorical features (producer, creator, fonts, page size): frequency tables;
  - numeric features (anchor positions and sizes, row pitch, text drawn after the
    footer): median and a robust spread (MAD) per feature, with a floor;
  - a document's score sums how far each feature is from what this vendor does;
  - the threshold is set from leave-one-out scores on the vendor's own invoices.
Every flag comes with the features that caused it, in plain words.
"""

from __future__ import annotations

import io
import random
import statistics
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache

from pypdf import PdfReader

VERSION = 1
ANCHORS = {  # label -> which of its coordinates are fixed by the layout (y moves with the line count for some)
    "INVOICE": ("x", "y", "size"),
    "BILL TO": ("x", "y", "size"),
    "Invoice No.": ("x", "y", "size"),
    "Item": ("x", "y", "size"),
    "Subtotal": ("x", "size"),
    "REMIT PAYMENT TO": ("x", "size"),
}
FLOOR = {"x": 0.0015, "y": 0.0015, "size": 0.4, "row_pitch": 0.8, "after_footer": 0.3, "vendor_name_size": 0.4}
CATEGORICAL = ("producer", "creator", "fonts", "page")
LABEL = {
    "producer": "PDF producer", "creator": "software that created it", "fonts": "fonts", "page": "page size",
    "row_pitch": "spacing between line items", "after_footer": "text drawn after the footer", "vendor_name_size": "size of the company name",
}


def _mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def features(data: bytes) -> dict:
    """What the PDF says about how it was made. Never raises: a PDF we cannot
    parse becomes a feature of its own."""
    try:
        r = PdfReader(io.BytesIO(data))
        page = r.pages[0]
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        meta = r.metadata or {}
        runs: list[tuple[str, float, float, float, str]] = []

        def visit(text, cm, tm, font, size):
            t = (text or "").strip()
            if not t:
                return
            m = _mul(tm, cm)
            name = str((font or {}).get("/BaseFont", "?")).lstrip("/")
            runs.append((t, m[4], m[5], float(size or 0) * (abs(m[3]) or 1), name))

        page.extract_text(visitor_text=visit)
    except Exception:
        return {"producer": "unreadable", "creator": "unreadable", "fonts": "unreadable", "page": "unreadable"}
    f: dict = {
        "producer": str(meta.get("/Producer") or "none")[:80],
        "creator": str(meta.get("/Creator") or "none")[:80],
        "fonts": "+".join(sorted({x[4] for x in runs if x[3] >= 3})) or "none",
        "page": f"{round(w)}x{round(h)}",
    }
    first = next((x for x in runs if x[3] >= 3), None)
    f["vendor_name_size"] = round(first[3], 2) if first else None
    for label, dims in ANCHORS.items():
        hit = next((x for x in runs if x[0] == label or x[0].startswith(label + " ") or x[0].startswith(label + "\n")), None)
        for d in dims:
            key = f"{label}.{d}"
            if hit is None:
                f[key] = None
            else:
                f[key] = round({"x": hit[1] / w, "y": hit[2] / h, "size": hit[3]}[d], 4)
    item = next((x for x in runs if x[0] == "Item"), None)
    sub = next((x for x in runs if x[0].startswith("Subtotal")), None)
    if item and sub:
        ys = sorted({round(x[2], 1) for x in runs if sub[2] + 20 < x[2] < item[2] - 1 and x[1] < 0.15 * w}, reverse=True)
        pitches = [a - b for a, b in zip([item[2]] + ys, ys)]
        f["row_pitch"] = round(statistics.median(pitches), 2) if pitches else None
    else:
        f["row_pitch"] = None
    footer_i = max((i for i, x in enumerate(runs) if x[2] < 0.09 * h and x[3] >= 3), default=None)
    f["after_footer"] = (len(runs) - 1 - footer_i) if footer_i is not None else None
    return f


@dataclass
class Verdict:
    score: float
    threshold: float
    anomalous: bool
    reasons: list[str]

    def as_dict(self) -> dict:
        return {"score": round(self.score, 2), "threshold": round(self.threshold, 2), "anomalous": self.anomalous, "reasons": self.reasons}


def _kind(key: str) -> str:
    return key.split(".")[-1] if "." in key else key


def _fit_core(docs: list[dict]) -> dict:
    model: dict = {"version": VERSION, "n": len(docs), "cat": {}, "num": {}, "threshold": 6.0}
    for k in CATEGORICAL:
        counts: dict[str, int] = {}
        for d in docs:
            counts[str(d.get(k))] = counts.get(str(d.get(k)), 0) + 1
        model["cat"][k] = counts
    for k in sorted({k for d in docs for k in d if k not in CATEGORICAL}):
        vals = [d[k] for d in docs if d.get(k) is not None]
        if not vals:
            model["num"][k] = {"present": 0}
            continue
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals])
        model["num"][k] = {"median": med, "spread": max(1.4826 * mad, FLOOR.get(_kind(k), 0.01)), "present": len(vals) / len(docs)}
    return model


def fit(docs: list[dict]) -> dict:
    """Train on one vendor's genuine invoices. The threshold comes from scoring
    each invoice against a model trained on all the others (leave-one-out)."""
    model = _fit_core(docs)
    loo = [score(_fit_core(docs[:i] + docs[i + 1 :]), docs[i]).score for i in range(len(docs))] if len(docs) >= 5 else []
    model["threshold"] = max(6.0, 1.5 * max(loo, default=0.0))
    return model


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _describe(key: str) -> str:
    if key in LABEL:
        return LABEL[key]
    label, dim = key.rsplit(".", 1)
    return {"x": f"horizontal position of '{label}'", "y": f"vertical position of '{label}'", "size": f"font size of '{label}'"}[dim]


def score(model: dict, doc: dict, vendor: str = "this vendor") -> Verdict:
    total = 0.0
    reasons: list[tuple[float, str]] = []
    n = max(model.get("n", 1), 1)
    for k, counts in model["cat"].items():
        v = str(doc.get(k))
        seen = counts.get(v, 0)
        if seen / n >= 0.1:
            continue
        pts = 8.0 if seen == 0 else 3.0
        usual = max(counts, key=counts.get)
        total += pts
        reasons.append((pts, f"{_cap(LABEL[k])}: '{v}', but {vendor}'s invoices use '{usual}' ({counts[usual]} of {n})"))
    for k, st in model["num"].items():
        v = doc.get(k)
        if st.get("present", 0) == 0:
            if v not in (None, 0):
                total += 2.0
                reasons.append((2.0, f"Has {_describe(k)}, which {vendor}'s invoices never do"))
            continue
        if v is None:
            if st["present"] >= 0.9:
                total += 4.0
                reasons.append((4.0, f"Missing the {_describe(k)} every {vendor} invoice has"))
            continue
        z = abs(v - st["median"]) / st["spread"]
        if z <= 3:
            continue
        pts = min(z, 8.0)
        total += pts
        unit = "% of the page" if _kind(k) in ("x", "y") else ("pt" if _kind(k) in ("size", "row_pitch", "vendor_name_size") else "")
        shown = (lambda x: f"{x * 100:.1f}{unit}") if unit == "% of the page" else (lambda x: f"{x:g}{unit}")
        if _kind(k) == "y":
            shown = lambda x: f"{(1 - x) * 100:.1f}% down the page"  # noqa: E731
        elif _kind(k) == "x":
            shown = lambda x: f"{x * 100:.1f}% across the page"  # noqa: E731
        reasons.append((pts, f"{_cap(_describe(k))}: {shown(v)}, but on {vendor}'s invoices it is {shown(st['median'])}"))
    reasons.sort(key=lambda r: -r[0])  # stable: metadata and fonts (listed first) lead a tie
    thr = float(model.get("threshold", 6.0))
    return Verdict(total, thr, total >= thr, [r for _, r in reasons[:5]])


# ---------------------------------------------------------------------------- training data


def history_specs(slug: str, n: int, seed: int = 7) -> list:
    """The vendor's invoice archive. In the demo it is generated: n past invoices
    from the vendor's own billing system with varied lines, dates and amounts."""
    from .seed import POS, TODAY, spec_for

    rnd = random.Random(f"{slug}-{seed}")
    catalogue = [ln for po in POS if po[1] == slug for ln in po[6]] or [("SVC-GEN", "Services", 1, "100.00")]
    pos = [po[0] for po in POS if po[1] == slug] or [None]
    prefix = {"brightline": "BIS-1", "ostara": "OC-6", "kestrel": "KFL-87", "granite": "GE-4", "vantage": "VCS-09", "lumen": "LOS-2", "polaris": "PNS-54"}.get(slug, "INV-")
    out = []
    for i in range(n):
        k = rnd.randint(1, min(5, len(catalogue)))
        lines = [(sku, desc, rnd.randint(1, int(q) if float(q) > 1 else 3), price) for sku, desc, q, price in rnd.sample(catalogue, k)]
        d = TODAY - timedelta(days=rnd.randint(20, 400))
        out.append(spec_for(slug, f"{prefix}{100 + i * 7 + rnd.randint(0, 6)}", d, rnd.choice(pos), lines,
                            tax_rate=Decimal(rnd.choice(["0", "0.08", "0.0725"]))))
    return out


@lru_cache(maxsize=16)
def history_features(slug: str, n: int = 40) -> tuple:
    from .invoicegen import render

    return tuple(features(render(sp)) for sp in history_specs(slug, n))


def forgeries(slug: str, n: int = 4) -> list[tuple[str, bytes]]:
    """Documents that carry this vendor's name and correct fields but were not
    produced by its billing system: rebuilt in a word processor, made from another
    company's template, or a genuine invoice edited to change the bank account."""
    from dataclasses import replace

    from .invoicegen import STYLES, HouseStyle, render

    specs = history_specs(slug, n, seed=99)
    others = [k for k in STYLES if k not in (slug, "forger") and not k.startswith("careful-")]
    own = STYLES[slug]
    # A careful forger copies the fonts, page size and even the metadata; only the layout is theirs.
    STYLES[f"careful-{slug}"] = HouseStyle(font=own.font, bold=own.bold, pagesize=own.pagesize, creator=own.creator, producer=own.producer,
                                          footer=own.footer)
    out = []
    for i, sp in enumerate(specs):
        out.append(("rebuilt in a word processor", render(replace(sp, style="forger"))))
        out.append(("careful rebuild, fonts and metadata copied", render(replace(sp, style=f"careful-{slug}"))))
        out.append(("another company's template", render(replace(sp, style=others[i % len(others)]))))
        out.append(("genuine invoice edited", edit_bank(render(sp), "4417 2200 9183")))
    return out


def edit_runs(pdf: bytes, changes: dict[str, str], editor: str = "Adobe Acrobat Pro (64-bit) 24.2") -> bytes:
    """What editing a real invoice in a PDF editor does: a white patch over each
    changed piece of text, the new text on top in the editor's font, and the
    editor's name in the metadata. Text is matched exactly, or by prefix for
    labelled values ("Account No.: ...")."""
    from pypdf import PdfWriter
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    r = PdfReader(io.BytesIO(pdf))
    page = r.pages[0]
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    hits: list[tuple[str, str, float, float, float]] = []

    def visit(text, cm, tm, font, size):
        t = (text or "").strip()
        for old, new in changes.items():
            if t == old or (old.endswith(":") and t.startswith(old)):
                m = _mul(tm, cm)
                hits.append((t, new, m[4], m[5], float(size or 9) * (abs(m[3]) or 1)))

    page.extract_text(visitor_text=visit)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    for old, new, x, y, size in hits:
        size = size if size >= 3 else 9
        ow, nw = stringWidth(old, "Helvetica", size), stringWidth(new, "Helvetica", size)
        right_aligned = not old.endswith(":") and any(ch.isdigit() for ch in old)
        nx = x + ow - nw if right_aligned else x
        c.setFillColor(colors.white)
        c.rect(min(x, nx) - 1, y - 2, max(ow, nw) + 3, size + 2, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", size)
        c.drawString(nx, y, new)
    c.save()
    wr = PdfWriter(clone_from=r)
    wr.pages[0].merge_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
    meta = {k: v for k, v in (r.metadata or {}).items()}
    meta["/Producer"] = editor
    wr.add_metadata(meta)
    out = io.BytesIO()
    wr.write(out)
    return out.getvalue()


def edit_bank(pdf: bytes, account: str) -> bytes:
    return edit_runs(pdf, {"Account No.:": f"Account No.: {account}"})


def train_vendor(slug: str, n: int = 40, holdout: int = 10) -> tuple[dict, dict]:
    """Fit on the archive and measure on held-out genuine invoices and forgeries."""
    import copy

    return copy.deepcopy(_train_vendor(slug, n, holdout))


@lru_cache(maxsize=16)
def _train_vendor(slug: str, n: int, holdout: int) -> tuple[dict, dict]:
    docs = list(history_features(slug, n))
    train, test = docs[: n - holdout], docs[n - holdout :]
    m = fit(train)
    fp = sum(score(m, d).anomalous for d in test)
    forged = forgeries(slug)
    caught: dict[str, list[int]] = {}
    for kind, pdf in forged:
        c = caught.setdefault(kind, [0, 0])
        c[0] += int(score(m, features(pdf)).anomalous)
        c[1] += 1
    full = fit(docs)
    metrics = {"trained_on": len(docs), "holdout_genuine": len(test), "false_alarms": fp, "forgeries": {k: {"caught": v[0], "of": v[1]} for k, v in caught.items()},
               "caught": sum(v[0] for v in caught.values()), "forged_total": sum(v[1] for v in caught.values())}
    return full, metrics


def check(s, vendor_id: str | None, doc: dict | None, vendor_name: str = "this vendor") -> Verdict | None:
    from .models import VendorFingerprint

    if not vendor_id or not doc:
        return None
    fp = s.get(VendorFingerprint, vendor_id)
    if fp is None:
        return None
    return score(fp.model, doc, vendor_name)
