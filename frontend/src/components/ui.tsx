"use client";

import { ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

const STATUS: Record<string, { label: string; cls: string }> = {
  received: { label: "Received", cls: "bg-slate-100 text-slate-700 ring-slate-200" },
  extracting: { label: "Reading", cls: "bg-sky-50 text-sky-700 ring-sky-200 animate-pulse" },
  checking: { label: "Checking", cls: "bg-sky-50 text-sky-700 ring-sky-200 animate-pulse" },
  deciding: { label: "Deciding", cls: "bg-violet-50 text-violet-700 ring-violet-200 animate-pulse" },
  awaiting_vendor: { label: "Waiting on vendor", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  awaiting_approval: { label: "Needs approval", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200" },
  on_hold: { label: "Held", cls: "bg-rose-50 text-rose-700 ring-rose-200" },
  scheduled: { label: "Payment scheduled", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  paid: { label: "Paid", cls: "bg-emerald-100 text-emerald-800 ring-emerald-300" },
  rejected: { label: "Rejected", cls: "bg-zinc-100 text-zinc-600 ring-zinc-300" },
  superseded: { label: "Replaced", cls: "bg-zinc-50 text-zinc-500 ring-zinc-200" },
  failed: { label: "Error", cls: "bg-rose-100 text-rose-800 ring-rose-300" },
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const s = STATUS[status] || { label: status, cls: "bg-slate-100 text-slate-700 ring-slate-200" };
  return <span className={cx("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s.cls, className)}>{s.label}</span>;
}

export const FLAG_LABEL: Record<string, string> = {
  PROMPT_INJECTION: "Hidden AI instructions",
  LOW_CONFIDENCE: "Unconfirmed fields",
  UNKNOWN_VENDOR: "Unknown vendor",
  VENDOR_INACTIVE: "Vendor inactive",
  BANK_MISMATCH: "Bank details changed",
  DUPLICATE_FILE: "Duplicate file",
  DUPLICATE_NUMBER: "Duplicate number",
  DUPLICATE_SUSPECT: "Likely duplicate",
  LINE_MATH: "Line math",
  SUBTOTAL_MATH: "Subtotal math",
  TOTAL_MATH: "Total math",
  NO_PO: "No PO",
  PO_NOT_FOUND: "PO not found",
  PO_VENDOR_MISMATCH: "Wrong vendor PO",
  PO_CLOSED: "PO closed",
  CURRENCY_MISMATCH: "Currency",
  UNORDERED_ITEM: "Not ordered",
  PRICE_VARIANCE: "Over PO price",
  QTY_OVER_ORDERED: "Over ordered qty",
  QTY_NOT_RECEIVED: "Not received",
  TERMS_SHORTENED: "Short terms",
  LOOKALIKE_VENDOR: "Lookalike vendor",
  TAX_ID_CONFLICT: "Tax ID conflict",
  SPLIT_BILLING: "Split billing",
  SLA_CREDIT: "SLA credit owed",
  VOLUME_PRICE: "Volume price owed",
  PRICE_CAP: "Price cap owed",
};

export function Flag({ code, severity = "block" }: { code: string; severity?: string }) {
  const cls =
    severity === "recover"
      ? "bg-sky-50 text-sky-800 ring-sky-200"
      : severity === "block"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : severity === "warn"
        ? "bg-amber-50 text-amber-800 ring-amber-200"
        : "bg-slate-50 text-slate-600 ring-slate-200";
  return <span className={cx("inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset", cls)}>{FLAG_LABEL[code] || code}</span>;
}

export function Card({ title, action, children, className, pad = true }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-2.5">
          <h2 className="text-[13px] font-semibold text-slate-800">{title}</h2>
          {action}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone = "default" }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "default" | "good" | "bad" | "brand" }) {
  const color = { default: "text-slate-900", good: "text-emerald-700", bad: "text-rose-700", brand: "text-indigo-700" }[tone];
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", color)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  size = "md",
  type = "button",
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost" | "good";
  disabled?: boolean;
  size?: "sm" | "md";
  type?: "button" | "submit";
  className?: string;
}) {
  const v = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm",
    good: "bg-emerald-600 text-white hover:bg-emerald-500 shadow-sm",
    danger: "bg-white text-rose-700 ring-1 ring-inset ring-rose-200 hover:bg-rose-50",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    ghost: "text-slate-600 hover:bg-slate-100",
  }[variant];
  const s = size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm";
  return (
    <button type={type} disabled={disabled} onClick={onClick} className={cx("inline-flex items-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50", v, s, className)}>
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-slate-500">{children}</div>;
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[12px]", className)}>{children}</span>;
}

export function maskAcct(a?: string | null) {
  if (!a) return "-";
  const d = a.replace(/\s/g, "");
  return `•••• ${d.slice(-4)}`;
}
