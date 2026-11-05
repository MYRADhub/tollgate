"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useContext, useEffect, useState } from "react";
import { Activity, BookCheck, Building2, Clock, FastForward, ScrollText, FlaskConical, Gauge, Inbox, Landmark, MailQuestion, Network, Scale, ShieldCheck, Users } from "lucide-react";
import { ActorContext, LiveContext, PEOPLE, ROLE_LABEL, ago, api, clockLabel, setClockOffset, useData, useLiveFeed, useStoredActor } from "@/lib/api";
import { FeedbackProvider, useFeedback } from "./Feedback";
import { StoryProvider } from "./StoryMode";
import { Logo } from "./Logo";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Invoices", icon: Inbox },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck, badge: true },
  { href: "/payments", label: "Payment runs", icon: Landmark },
  { href: "/statements", label: "Statements", icon: Scale },
  { href: "/inquiries", label: "Vendor questions", icon: MailQuestion },
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
  const ev = last.find((e) => !e.lab);
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-slate-500">
      <Activity className={cx("h-3.5 w-3.5 shrink-0", ev ? "text-emerald-500" : "text-slate-400")} />
      <span className="truncate">{ev ? `${ev.actor}: ${ev.summary}` : "Agent idle, watching the AP inbox"}</span>
    </div>
  );
}

type ClockCfg = { demo_mode: boolean; clock?: { now: string; offset_hours: number; max_days: number } };

function DemoClock() {
  const fb = useFeedback();
  const { data, reload } = useData<ClockCfg>("/api/config");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (data?.clock) setClockOffset(data.clock.offset_hours);
  }, [data]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);
  if (!data?.clock || !data.demo_mode) return null;
  const days = data.clock.offset_hours / 24;
  const forward = async () => {
    setBusy(true);
    try {
      const r = await api<{ now: string; offset_hours: number; due: number }>("/api/demo/clock", { method: "POST", json: { hours: 24 } });
      setClockOffset(r.offset_hours);
      fb.toast(
        "info",
        `It is now ${clockLabel(r.now)}`,
        r.due ? `${r.due} step(s) the agent had scheduled are running now: follow-ups, colleagues' answers, deliveries, reminders.` : "Nothing was scheduled in that time.",
      );
      reload();
    } catch (e) {
      fb.toast("error", "Could not fast-forward", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-slate-600" data-testid="demo-clock">
      <span className="hidden items-center gap-1 sm:inline-flex" title="The demo company's clock. Fast-forward moves it on so you can watch a day of the agent's work in seconds.">
        <Clock className="h-3.5 w-3.5 text-slate-400" />
        {clockLabel(new Date(now + data.clock.offset_hours * 3600 * 1000).toISOString())}
        {days > 0 && <span className="text-slate-400">(+{days % 1 ? days.toFixed(1) : days}d)</span>}
      </span>
      <button
        onClick={forward}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2 py-1 font-medium text-white hover:bg-slate-700 disabled:opacity-50"
      >
        <FastForward className="h-3 w-3" /> {busy ? "Moving..." : "Fast-forward a day"}
      </button>
    </div>
  );
}

function SharedNotice() {
  const { data } = useData<{ last_reset_at: string | null; demo_mode: boolean }>("/api/config");
  if (!data?.demo_mode) return null;
  return (
    <span
      className="hidden shrink-0 items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-200 sm:inline-flex"
      title="Everyone who opens this demo works in the same company. If something changed under you, another visitor did it."
    >
      <Users className="h-3 w-3" /> Shared demo{data.last_reset_at ? `, reset ${ago(data.last_reset_at)}` : ""}
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const live = useLiveFeed();
  const [actor, setActor] = useStoredActor();
  return (
    <LiveContext.Provider value={live}>
      <ActorContext.Provider value={{ actor, setActor }}>
        <FeedbackProvider>
        <StoryProvider>
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
              <DemoClock />
              <SharedNotice />
            </div>
            <MobileNav />
            <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5 md:px-6">{children}</main>
          </div>
        </div>
        </StoryProvider>
        </FeedbackProvider>
      </ActorContext.Provider>
    </LiveContext.Provider>
  );
}
