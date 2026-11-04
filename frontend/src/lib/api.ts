"use client";

import { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore } from "react";

export type Role = "clerk" | "controller" | "cfo";
export type Actor = { user: string; role: Role };

export const PEOPLE: Actor[] = [
  { user: "Sam Patel", role: "clerk" },
  { user: "Rosa Kim", role: "controller" },
  { user: "Theo Grant", role: "cfo" },
];

export const ROLE_LABEL: Record<Role, string> = { clerk: "AP clerk", controller: "Controller", cfo: "CFO" };

const RANK: Record<Role, number> = { clerk: 0, controller: 1, cfo: 2 };

export function canApprove(actor: Role, required: Role) {
  return RANK[actor] >= RANK[required];
}

/** The first demo person who can approve at this level. */
export function personFor(required: Role): Actor {
  return PEOPLE.find((p) => RANK[p.role] >= RANK[required]) || PEOPLE[PEOPLE.length - 1];
}

export class ApiError extends Error {}

export async function api<T = unknown>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init || {};
  const res = await fetch(path, {
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(rest.headers || {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const b = await res.json();
      msg = b.detail || msg;
    } catch {}
    throw new ApiError(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json() as Promise<T>;
}

export function money(x: number | null | undefined, currency = "USD") {
  if (x === null || x === undefined) return "-";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(x);
}

export function compactMoney(x: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: x >= 100000 ? "compact" : "standard", maximumFractionDigits: x >= 100000 ? 1 : 0 }).format(x);
}

export function ago(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return `${Math.max(1, Math.floor(d))}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

// ---- live updates: one EventSource for the app, a tick that bumps on every audit event
type LiveCtx = { tick: number; last: AuditEvent[] };
export type AuditEvent = {
  id: number;
  actor: string;
  kind: string;
  summary: string;
  invoice_id: string | null;
  created_at: string;
  number?: string | null;
  vendor?: string | null;
  lab?: boolean;
};

export const LiveContext = createContext<LiveCtx>({ tick: 0, last: [] });

export function useLiveFeed(): LiveCtx {
  const [state, setState] = useState<LiveCtx>({ tick: 0, last: [] });
  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    const connect = () => {
      es = new EventSource("/api/events");
      es.addEventListener("audit", (e) => {
        const ev = JSON.parse((e as MessageEvent).data) as AuditEvent;
        setState((s) => ({ tick: s.tick + 1, last: [ev, ...s.last].slice(0, 60) }));
      });
      es.onerror = () => {
        es?.close();
        if (!closed) retry = setTimeout(connect, 3000);
      };
    };
    connect();
    // Fallback refresh: proxies that buffer server-sent events (and sleeping laptops)
    // must not leave the page stale. Cheap: a handful of small JSON reads.
    const beat = setInterval(() => {
      if (typeof document === "undefined" || document.visibilityState === "visible") setState((s) => ({ ...s, tick: s.tick + 1 }));
    }, 5000);
    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(beat);
      es?.close();
    };
  }, []);
  return state;
}

export function useLive() {
  return useContext(LiveContext);
}

/** Fetch JSON and refetch whenever the live feed ticks (debounced). */
export function useData<T>(path: string | null) {
  const { tick } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [debouncedTick, setDebouncedTick] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedTick(tick), 250);
    return () => clearTimeout(t);
  }, [tick]);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    api<T>(path)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [path, debouncedTick, nonce]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, reload };
}

// ---- acting as a person (demo identity switcher)
export const ActorContext = createContext<{ actor: Actor; setActor: (a: Actor) => void }>({
  actor: PEOPLE[0],
  setActor: () => {},
});

export function useActor() {
  return useContext(ActorContext);
}

const ACTOR_KEY = "tollgate.actor";
const actorListeners = new Set<() => void>();

function readActor(): string {
  try {
    return localStorage.getItem(ACTOR_KEY) || PEOPLE[0].user;
  } catch {
    return PEOPLE[0].user;
  }
}

export function useStoredActor(): [Actor, (a: Actor) => void] {
  const name = useSyncExternalStore(
    (cb) => {
      actorListeners.add(cb);
      return () => actorListeners.delete(cb);
    },
    readActor,
    () => PEOPLE[0].user,
  );
  const actor = PEOPLE.find((p) => p.user === name) || PEOPLE[0];
  const set = (a: Actor) => {
    try {
      localStorage.setItem(ACTOR_KEY, a.user);
    } catch {}
    actorListeners.forEach((l) => l());
  };
  return [actor, set];
}

// ---- types mirrored from the API
export type InvoiceRow = {
  id: string;
  status: string;
  source: string;
  file_name: string;
  number: string | null;
  po_number: string | null;
  vendor_name: string | null;
  vendor_name_raw: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string | null;
  total: number | null;
  summary: string | null;
  created_at: string;
  blocking: number;
  flags: string[];
  at_risk: number;
  waiting_for: string | null;
  supersedes_id: string | null;
  recover: string[];
  recover_amount: number;
};

export type Finding = {
  id: number;
  code: string;
  severity: "info" | "warn" | "block" | "recover";
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
  amount_at_risk: number | null;
  resolved: boolean;
  resolution: string | null;
  resolved_by: string | null;
};

export type Approval = {
  id: number;
  kind: "payment" | "bank_change";
  required_role: Role;
  reason: string;
  decision: string | null;
  decided_by: string | null;
  decided_role: Role | null;
  comment: string | null;
  created_at: string;
  decided_at: string | null;
  bank_change_id: number | null;
  invoice_id?: string;
  invoice?: InvoiceRow;
  bank_change?: { old_account: string; new_account: string; new_bank_name: string; status: string; callback_note: string | null; vendor: string };
  other_approvers?: string[];
};

export type InvoiceDetail = InvoiceRow & {
  remit_bank_name: string | null;
  remit_account: string | null;
  remit_routing: string | null;
  subtotal: number | null;
  tax: number | null;
  extraction: {
    method?: string;
    ungrounded?: string[];
    injection_signals?: { kind: string; excerpt: string; source?: string }[];
    hidden_spans?: string[];
    notes?: string | null;
    vendor_email_on_document?: string | null;
    vendor_tax_id?: string | null;
  };
  agent_state: { waiting_for?: string; hold_reason?: string; decisions?: number };
  line_matches: { line: number; po_sku: string | null; po_qty?: string; po_price?: string; received?: string; billed_before?: string }[];
  lines: { position: number; sku: string | null; description: string; quantity: number; unit_price: number; amount: number }[];
  findings: Finding[];
  vendor: {
    id: string;
    name: string;
    email: string;
    tax_id: string;
    bank_name: string;
    bank_account: string;
    bank_routing: string;
    bank_verified_at: string | null;
    payment_terms_days: number;
    status: string;
  } | null;
  po: {
    number: string;
    department: string;
    budget_owner_name: string;
    budget_owner_email: string;
    currency: string;
    status: string;
    issued_on: string;
    lines: { sku: string; description: string; quantity: number; unit_price: number; received: number }[];
  } | null;
  approvals: Approval[];
  emails: { id: number; direction: "in" | "out"; sender: string; recipient: string; subject: string; body: string; attachments: string[]; status: string; created_at: string }[];
  payment: {
    gross: number | null;
    deductions: number;
    discount: number;
    amount: number;
    currency: string;
    pay_to_account: string;
    scheduled_for: string;
    due_date: string | null;
    discount_deadline: string | null;
    discount_pct: number | null;
    status: string;
    run_id: number | null;
  } | null;
  critic: CriticReview[];
  controls_count: number;
  cost: InvoiceCost | null;
  min_role: Role | null;
  bank_change: { id: number; old_account: string; new_account: string; new_bank_name: string; status: string; callback_note: string | null } | null;
  timeline: { id: number; actor: string; kind: string; summary: string; detail: Record<string, unknown>; created_at: string; hash: string; invoice_id: string }[];
  superseded_by: string | null;
  pages: number;
  approval_needed: Role | null;
};

export type CriticReview = {
  id: number;
  verdict: "agree" | "concerns" | "disagree" | "unavailable";
  summary: string;
  points: string[];
  independent_amount: number | null;
  model: string;
  proposal: { invoice_total: string; pay: string; approval: string; deductions: { title: string; amount: string; clause: string | null }[] };
  created_at: string;
};

export type Stats = {
  invoices: number;
  by_status: Record<string, number>;
  decided: number;
  touchless: number;
  touchless_rate: number;
  prevented: number;
  recovered: number;
  discounts: number;
  caught: { id: string; number: string; codes: string[]; amount: number }[];
  pending_approvals: number;
  scheduled_total: number;
  queue: number;
  cost: { invoices: number; usd: number; calls: number; per_invoice_usd: number | null; benchmark_usd: number; benchmark_source: string };
};

export type InvoiceCost = { calls: number; prompt_tokens: number; completion_tokens: number; usd: number };

/** Sub-cent amounts, e.g. $0.0042. */
export function microMoney(n: number): string {
  if (n >= 1) return money(n);
  return `$${n.toFixed(n < 0.01 ? 4 : 3)}`;
}

// ---- guided demo progress (per viewer, best effort)
const SEEN_KEY = "tollgate.seen";
const seenListeners = new Set<() => void>();

function readSeen(): string {
  try {
    return localStorage.getItem(SEEN_KEY) || "";
  } catch {
    return "";
  }
}

export function markSeen(key: string) {
  try {
    const cur = new Set(readSeen().split(",").filter(Boolean));
    if (cur.has(key)) return;
    cur.add(key);
    localStorage.setItem(SEEN_KEY, [...cur].join(","));
    seenListeners.forEach((l) => l());
  } catch {}
}

export function useSeen(): Set<string> {
  const raw = useSyncExternalStore(
    (cb) => {
      seenListeners.add(cb);
      return () => seenListeners.delete(cb);
    },
    readSeen,
    () => "",
  );
  return new Set(raw.split(",").filter(Boolean));
}
