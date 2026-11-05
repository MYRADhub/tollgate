"use client";

import { useRouter } from "next/navigation";
import { ReactNode, createContext, useCallback, useContext, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { InvoiceRow, api } from "@/lib/api";
import { cx } from "./ui";

type Caption = { step: number; total: number; title: string; body: string; done?: boolean };
type Ctx = { running: boolean; start: () => void; stop: () => void };
const StoryContext = createContext<Ctx>({ running: false, start: () => {}, stop: () => {} });
export const useStory = () => useContext(StoryContext);

const TOTAL = 5;
const BUSY = ["received", "extracting", "checking", "deciding"];

class Stopped extends Error {}

export function StoryProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [caption, setCaption] = useState<Caption | null>(null);
  const run = useRef(0);

  const stop = useCallback(() => {
    run.current += 1;
    setCaption(null);
  }, []);

  const start = useCallback(() => {
    const me = ++run.current;
    const alive = () => {
      if (run.current !== me) throw new Stopped();
    };
    const sleep = async (ms: number) => {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        alive();
        await new Promise((r) => setTimeout(r, Math.min(250, end - Date.now())));
      }
    };
    const say = (step: number, title: string, body: string) => {
      alive();
      setCaption({ step, total: TOTAL, title, body });
    };
    const rows = () => api<InvoiceRow[]>("/api/invoices");
    const find = async (n: string) => (await rows()).find((r) => r.number === n);
    const until = async (test: () => Promise<boolean>, ms: number) => {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        if (await test()) return true;
        await sleep(2000);
      }
      return false;
    };
    const focus = async (id: string) => {
      for (let i = 0; i < 30; i++) {
        alive();
        const el = document.getElementById(id);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.add("story-focus");
          setTimeout(() => el.classList.remove("story-focus"), 9000);
          return;
        }
        await sleep(200);
      }
    };
    const open = async (n: string, id: string) => {
      const r = await find(n);
      if (!r) return false;
      router.push(`/invoices/${r.id}`);
      await sleep(1200);
      await focus(id);
      return true;
    };

    (async () => {
      try {
        router.push("/");
        let all = await rows();
        if (all.length === 0) {
          say(1, "Twelve invoices arrive in the AP inbox", "A Vultr vision model reads each one, and the controls in code check it against POs, receipts, the vendor master and the contract.");
          await api("/api/demo/inbox", { method: "POST", json: null });
        }
        await until(async () => {
          all = await rows();
          const done = all.filter((r) => !BUSY.includes(r.status)).length;
          say(1, "Twelve invoices arrive in the AP inbox", `Read and checked ${done} of ${all.length}. Clean ones are paid on terms with nobody touching them; the rest are exceptions the agent starts working.`);
          return all.length > 0 && done === all.length;
        }, 240000);

        say(2, "An invoice with no PO number", "Normally a clerk would chase this. The agent searches Granite's open POs, finds the one that covers the lines, and asks Marcus, who owns it.");
        await until(async () => (await find("GE-5570"))?.status === "scheduled", 150000);
        if (await open("GE-5570", "colleagues")) {
          say(2, "Cleared without anyone in AP", "Marcus confirmed PO-24111. Code checked the yes came from that PO's owner, the agent attached it, re-ran every control and scheduled payment. Every lookup and question is on the timeline.");
          await sleep(10000);
        }

        say(3, "Fast-forward a day", "GE-5561 billed for 40 breakers; receiving had logged 25. Marcus said the rest were backordered until tomorrow. Moving the company clock on a day...");
        if ((await find("GE-5561"))?.status !== "scheduled") {
          try {
            await api("/api/demo/clock", { method: "POST", json: { hours: 24 } });
          } catch {
            /* rate-limited or at the clock's limit: carry on with what is there */
          }
          await until(async () => (await find("GE-5561"))?.status === "scheduled", 90000);
        }
        if (await open("GE-5561", "colleagues")) {
          say(3, "The delivery arrived; it paid", "Receiving logged the 15 breakers overnight, the agent re-ran the controls and paid, net of the $43.20 the contract's price cap entitles us to.");
          await sleep(9000);
        }

        if (await open("BIS-2090", "fingerprint")) {
          say(4, "A forgery, caught four ways", "Hidden text telling the AI to approve it, found by comparing the PDF's text with its pixels. A bank account that is not on file. Brightline's own statement does not list it. And our own model: this PDF was made in Word, while every Brightline invoice comes out of Sage Intacct.");
          await sleep(13000);
        }

        router.push("/");
        await sleep(1200);
        await focus("briefing");
        say(5, "What is left for people", "Only decisions that need judgment, each with the agent's recommendation: approve a payment, verify a bank change, reject a forgery. The briefing counts what the agent did and how few touches it needed.");
        await sleep(12000);
        alive();
        setCaption({ step: TOTAL, total: TOTAL, title: "That is Tollgate", body: "Try it yourself: the guided demo, the attack lab, or upload your own PDF.", done: true });
      } catch (e) {
        if (!(e instanceof Stopped)) setCaption({ step: 0, total: TOTAL, title: "Stopped", body: (e as Error).message, done: true });
      }
    })();
  }, [router]);

  return (
    <StoryContext.Provider value={{ running: !!caption && !caption.done, start, stop }}>
      {children}
      {caption && (
        <div className="fixed inset-x-0 bottom-4 z-50 flex justify-center px-4" data-testid="story">
          <div className="w-full max-w-2xl rounded-xl bg-slate-900/95 p-4 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-medium uppercase tracking-wide text-indigo-300">
                {caption.done ? "Show me" : `Show me · ${caption.step} of ${caption.total}`}
              </div>
              <button onClick={stop} className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] text-slate-300 hover:bg-white/10">
                <Square className="h-3 w-3" /> {caption.done ? "Close" : "Stop"}
              </button>
            </div>
            <div className="mt-1 text-[15px] font-semibold">{caption.title}</div>
            <p className="mt-0.5 text-[13px] leading-relaxed text-slate-300">{caption.body}</p>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
              <div className={cx("h-full rounded-full bg-indigo-400 transition-all")} style={{ width: `${(caption.step / caption.total) * 100}%` }} />
            </div>
          </div>
        </div>
      )}
    </StoryContext.Provider>
  );
}

export function ShowMeButton({ className }: { className?: string }) {
  const { running, start } = useStory();
  return (
    <button
      onClick={start}
      disabled={running}
      className={cx("inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50", className)}
    >
      <Play className="h-3.5 w-3.5" /> {running ? "Playing..." : "Show me in 2 minutes"}
    </button>
  );
}
