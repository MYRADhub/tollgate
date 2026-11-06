"use client";

import { ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { cx } from "./ui";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; body?: string };
const MAX_TOASTS = 4;

type DialogState =
  | null
  | {
      kind: "confirm" | "prompt";
      title: string;
      body?: string;
      confirmLabel: string;
      danger?: boolean;
      placeholder?: string;
      resolve: (v: string | boolean | null) => void;
    };

type Ctx = {
  toast: (tone: Tone, title: string, body?: string) => void;
  confirm: (o: { title: string; body?: string; confirmLabel?: string; danger?: boolean }) => Promise<boolean>;
  prompt: (o: { title: string; body?: string; confirmLabel?: string; placeholder?: string; danger?: boolean }) => Promise<string | null>;
};

const FeedbackContext = createContext<Ctx>({
  toast: () => {},
  confirm: async () => false,
  prompt: async () => null,
});

export function useFeedback() {
  return useContext(FeedbackContext);
}

function Dialog({ d, close }: { d: NonNullable<DialogState>; close: (v: string | boolean | null) => void }) {
  const [value, setValue] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close(d.kind === "confirm" ? false : null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d, close]);
  const ok = d.kind === "confirm" || value.trim().length > 0;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-[2px]" onClick={() => close(d.kind === "confirm" ? false : null)}>
      <div role="dialog" aria-modal="true" aria-labelledby="dlg-title" className="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 id="dlg-title" className="text-base font-semibold text-slate-900">
          {d.title}
        </h2>
        {d.body && <p className="mt-1 text-sm text-slate-600">{d.body}</p>}
        {d.kind === "prompt" && (
          <textarea
            ref={input}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={d.placeholder}
            rows={3}
            className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100" onClick={() => close(d.kind === "confirm" ? false : null)}>
            Cancel
          </button>
          <button
            disabled={!ok}
            onClick={() => close(d.kind === "confirm" ? true : value.trim())}
            className={cx(
              "rounded-lg px-3 py-1.5 text-sm font-medium text-white shadow-sm disabled:opacity-50",
              d.danger ? "bg-rose-600 hover:bg-rose-500" : "bg-indigo-600 hover:bg-indigo-500",
            )}
          >
            {d.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dialog, setDialog] = useState<DialogState>(null);
  const seq = useRef(0);

  const toast = useCallback((tone: Tone, title: string, body?: string) => {
    const id = ++seq.current;
    setToasts((t) => {
      // An error already on screen is not stacked again when the same action fails twice.
      if (tone === "error" && t.some((x) => x.tone === "error" && x.title === title && x.body === body)) return t;
      const next = [...t, { id, tone, title, body }];
      while (next.length > MAX_TOASTS) {
        // Errors wait to be read; the oldest passing message makes room first.
        const i = next.slice(0, -1).findIndex((x) => x.tone !== "error");
        next.splice(i === -1 ? 0 : i, 1);
      }
      return next;
    });
    if (tone !== "error") setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const confirm = useCallback<Ctx["confirm"]>(
    (o) =>
      new Promise<boolean>((resolve) =>
        setDialog({ kind: "confirm", title: o.title, body: o.body, confirmLabel: o.confirmLabel || "Confirm", danger: o.danger, resolve: (v) => resolve(v === true) }),
      ),
    [],
  );
  const prompt = useCallback<Ctx["prompt"]>(
    (o) =>
      new Promise<string | null>((resolve) =>
        setDialog({
          kind: "prompt",
          title: o.title,
          body: o.body,
          confirmLabel: o.confirmLabel || "Submit",
          placeholder: o.placeholder,
          danger: o.danger,
          resolve: (v) => resolve(typeof v === "string" ? v : null),
        }),
      ),
    [],
  );
  const close = useCallback(
    (v: string | boolean | null) => {
      setDialog((d) => {
        d?.resolve(v);
        return null;
      });
    },
    [],
  );

  return (
    <FeedbackContext.Provider value={{ toast, confirm, prompt }}>
      {children}
      {dialog && <Dialog d={dialog} close={close} />}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className={cx(
              "pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-white p-3 shadow-lg",
              t.tone === "error" ? "border-rose-200" : t.tone === "success" ? "border-emerald-200" : "border-slate-200",
            )}
          >
            {t.tone === "error" ? (
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
            ) : t.tone === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-slate-900">{t.title}</div>
              {t.body && <div className="mt-0.5 text-xs text-slate-600">{t.body}</div>}
            </div>
            <button aria-label="Dismiss" className="text-slate-400 hover:text-slate-700" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </FeedbackContext.Provider>
  );
}
