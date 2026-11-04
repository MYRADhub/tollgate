"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useContext, useEffect, useState } from "react";
import { Activity, BookCheck, Building2, ScrollText, FlaskConical, Gauge, Inbox, Landmark, Network, ShieldCheck } from "lucide-react";
import { ActorContext, LiveContext, PEOPLE, ROLE_LABEL, api, useData, useLiveFeed, useStoredActor } from "@/lib/api";
import { Logo } from "./Logo";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Invoices", icon: Inbox },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck, badge: true },
  { href: "/payments", label: "Payment runs", icon: Landmark },
  { href: "/contracts", label: "Contracts", icon: ScrollText },
  { href: "/vendors", label: "Vendors & POs", icon: Building2 },
  { href: "/lab", label: "Attack lab", icon: FlaskConical },
  { href: "/audit", label: "Audit trail", icon: BookCheck },
  { href: "/how-it-works", label: "How it works", icon: Network },
];

function Nav() {
  const path = usePathname();
  const { data } = useData<{ pending_approvals: number }>("/api/stats");
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" || path.startsWith("/invoices") : path.startsWith(n.href);
        const Icon = n.icon;
        return (
          <Link
            key={n.href}
            href={n.href}
            className={cx(
              "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition",
              active ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
            )}
          >
            <Icon className="h-4 w-4" />
            <span className="flex-1">{n.label}</span>
            {n.badge && data && data.pending_approvals > 0 && (
              <span className="rounded-full bg-indigo-500 px-1.5 text-[11px] font-semibold text-white">{data.pending_approvals}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function MobileNav() {
  const path = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 py-1.5 md:hidden">
      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" || path.startsWith("/invoices") : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} className={cx("whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium", active ? "bg-slate-900 text-white" : "text-slate-600")}>
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Dot({ on }: { on: boolean }) {
  return <span className={cx("h-1.5 w-1.5 rounded-full", on ? "bg-emerald-400" : "bg-slate-500")} />;
}

function Health() {
  const [h, setH] = useState<{ inference: boolean; mail: boolean; storage: string } | null>(null);
  useEffect(() => {
    api<{ inference: boolean; mail: boolean; storage: string }>("/api/health").then(setH).catch(() => setH(null));
  }, []);
  return (
    <div className="space-y-1.5 rounded-lg border border-white/10 p-2.5 text-[11px] text-slate-400">
      <div className="flex items-center gap-1.5 font-medium text-slate-300">
        <Gauge className="h-3.5 w-3.5" /> Running on Vultr
      </div>
      <div className="flex items-center gap-2"><Dot on={!!h?.inference} /> Serverless Inference</div>
      <div className="flex items-center gap-2"><Dot on={h?.storage === "s3"} /> Object Storage</div>
      <div className="flex items-center gap-2"><Dot on={!!h?.mail} /> AP mailbox</div>
    </div>
  );
}

function Who() {
  const { actor, setActor } = useContext(ActorContext);
  return (
    <div className="rounded-lg border border-white/10 p-2.5">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">Acting as</div>
      <div className="flex flex-col gap-1">
        {PEOPLE.map((p) => (
          <button
            key={p.user}
            onClick={() => setActor(p)}
            className={cx(
              "flex items-center justify-between rounded-md px-2 py-1 text-left text-xs transition",
              actor.user === p.user ? "bg-indigo-500/20 text-white ring-1 ring-indigo-400/40" : "text-slate-400 hover:bg-white/5",
            )}
          >
            <span>{p.user}</span>
            <span className="text-[10px] text-slate-500">{ROLE_LABEL[p.role]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function LiveTicker() {
  const { last } = useContext(LiveContext);
  const ev = last[0];
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-slate-500">
      <Activity className={cx("h-3.5 w-3.5 shrink-0", ev ? "text-emerald-500" : "text-slate-400")} />
      <span className="truncate">{ev ? `${ev.actor}: ${ev.summary}` : "Agent idle, watching the AP inbox"}</span>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const live = useLiveFeed();
  const [actor, setActor] = useStoredActor();
  return (
    <LiveContext.Provider value={live}>
      <ActorContext.Provider value={{ actor, setActor }}>
        <div className="flex min-h-screen bg-slate-50">
          <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-5 bg-slate-950 px-3 py-4 md:flex">
            <Link href="/" className="flex items-center gap-2 px-1.5 text-white">
              <Logo className="h-7 w-7 text-slate-200" />
              <div>
                <div className="text-[15px] font-semibold leading-none">Tollgate</div>
                <div className="mt-0.5 text-[10px] text-slate-500">Halden Robotics · Accounts Payable</div>
              </div>
            </Link>
            <Nav />
            <div className="mt-auto space-y-3">
              <Who />
              <Health />
            </div>
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="sticky top-0 z-10 flex h-10 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur md:px-6">
              <Link href="/" className="flex items-center gap-1.5 font-semibold md:hidden">
                <Logo className="h-5 w-5 text-slate-800" /> Tollgate
              </Link>
              <LiveTicker />
            </div>
            <MobileNav />
            <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5 md:px-6">{children}</main>
          </div>
        </div>
      </ActorContext.Provider>
    </LiveContext.Provider>
  );
}
