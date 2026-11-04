"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Bot, CheckCircle2, CircleAlert, EyeOff, FileText, HandCoins, Hash, Mail, PackageCheck, Scale, ShieldAlert, ShieldCheck, User } from "lucide-react";
import { CriticReview, InvoiceDetail, ROLE_LABEL, api, markSeen, microMoney, money, useActor, useData } from "@/lib/api";
import { BankChangeReview, PaymentApproval } from "@/components/ApprovalControls";
import { useFeedback } from "@/components/Feedback";
import { Button, Card, Empty, Flag, Mono, StatusPill, cx, maskAcct } from "@/components/ui";

function useAct(reload: () => void) {
  const fb = useFeedback();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, ok?: string, okBody?: string) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      if (ok) fb.toast("success", ok, okBody);
      reload();
    } catch (e) {
      setErr((e as Error).message);
      fb.toast("error", "That did not work", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, err, run, fb };
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-[13px]">
      <span className="text-slate-500">{k}</span>
      <span className="text-right text-slate-800">{v}</span>
    </div>
  );
}

function Findings({ inv, reload }: { inv: InvoiceDetail; reload: () => void }) {
  const { actor } = useActor();
  const { busy, err, run } = useAct(reload);
  const [clearing, setClearing] = useState<number | null>(null);
  const [why, setWhy] = useState("");
  if (inv.findings.length === 0)
    return (
      <Card title="Controls">
        <div className="flex items-center gap-2 text-sm text-emerald-700">
          <CheckCircle2 className="h-4 w-4" /> All {inv.controls_count} controls passed, and nothing is owed back under the contract.
        </div>
      </Card>
    );
  return (
    <Card
      title={`Findings (${inv.findings.filter((f) => !f.resolved && f.severity === "block").length} blocking${inv.findings.some((f) => f.severity === "recover") ? `, ${money(inv.findings.filter((f) => f.severity === "recover" && !f.resolved).reduce((a, f) => a + (f.amount_at_risk || 0), 0))} owed to us` : ""})`}
      pad={false}
    >
      <ul className="divide-y divide-slate-100">
        {inv.findings.map((f) => (
          <li key={f.id} className={cx("px-4 py-3", f.resolved && "opacity-60")}>
            <div className="flex items-start gap-2.5">
              {f.severity === "recover" ? (
                <HandCoins className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" />
              ) : f.code === "PROMPT_INJECTION" ? (
                <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
              ) : f.severity === "block" ? (
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
              ) : (
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{f.title}</span>
                  <Flag code={f.code} severity={f.resolved ? "info" : f.severity} />
                  {f.amount_at_risk ? (
                    f.severity === "recover" ? (
                      <span className="text-xs font-medium text-sky-700">{money(f.amount_at_risk)} owed to us</span>
                    ) : (
                      <span className="text-xs font-medium text-rose-700">{money(f.amount_at_risk)} at risk</span>
                    )
                  ) : null}
                </div>
                <p className="mt-0.5 text-[13px] leading-relaxed text-slate-600">{f.detail}</p>
                {f.severity === "recover" && typeof f.evidence?.quote === "string" && (
                  <blockquote className="mt-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-[12px] italic leading-relaxed text-sky-950">
                    <span className="not-italic font-semibold">{String(f.evidence.contract)}:</span> &ldquo;{f.evidence.quote as string}&rdquo;
                  </blockquote>
                )}
                {f.code === "PROMPT_INJECTION" && typeof f.evidence?.excerpt === "string" && (
                  <blockquote className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-[11.5px] leading-relaxed text-rose-900">
                    &ldquo;{f.evidence.excerpt as string}&rdquo;
                  </blockquote>
                )}
                {f.resolved && (
                  <div className="mt-1 text-xs text-emerald-700">
                    Cleared by {f.resolved_by}: {f.resolution}
                  </div>
                )}
                {!f.resolved && f.code !== "BANK_MISMATCH" && (
                  <div className="mt-2">
                    {clearing === f.id ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          value={why}
                          onChange={(e) => setWhy(e.target.value)}
                          placeholder="Why is this OK to clear?"
                          className="min-w-[260px] flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs"
                        />
                        <Button
                          size="sm"
                          variant="primary"
                          disabled={busy || !why.trim()}
                          onClick={() =>
                            run(() => api(`/api/findings/${f.id}/resolve`, { method: "POST", json: { ...actor, justification: why } }), `${f.code.replaceAll("_", " ").toLowerCase()} cleared`).then(() => {
                              setClearing(null);
                              setWhy("");
                            })
                          }
                        >
                          Clear as {actor.user}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setClearing(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <button className="text-xs text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline" onClick={() => setClearing(f.id)}>
                        Override with a justification
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {err && <div className="border-t border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-700">{err}</div>}
    </Card>
  );
}

function ThreeWay({ inv }: { inv: InvoiceDetail }) {
  if (!inv.po) return null;
  const poBySku = Object.fromEntries(inv.po.lines.map((l) => [l.sku, l]));
  return (
    <Card title={`3-way match: invoice vs ${inv.po.number} vs goods received`} pad={false}>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-4 py-2 font-medium">Item</th>
              <th className="px-2 py-2 text-right font-medium">Billed qty</th>
              <th className="px-2 py-2 text-right font-medium">Ordered</th>
              <th className="px-2 py-2 text-right font-medium">Received</th>
              <th className="px-2 py-2 text-right font-medium">Billed price</th>
              <th className="px-4 py-2 text-right font-medium">PO price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {inv.lines.map((ln, i) => {
              const m = inv.line_matches.find((x) => x.line === ln.position);
              const pl = m?.po_sku ? poBySku[m.po_sku] : undefined;
              const priceBad = pl && ln.unit_price > pl.unit_price * 1.02;
              const recvBad = pl && ln.quantity + Number(m?.billed_before || 0) > pl.received;
              return (
                <tr key={i}>
                  <td className="px-4 py-2">
                    <div className="text-slate-800">{ln.description}</div>
                    <Mono className="text-slate-500">{ln.sku || "-"}</Mono>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{ln.quantity}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-slate-600">{pl ? pl.quantity : <span className="text-rose-600">not on PO</span>}</td>
                  <td className={cx("px-2 py-2 text-right tabular-nums", recvBad ? "font-semibold text-rose-700" : "text-slate-600")}>{pl ? pl.received : "-"}</td>
                  <td className={cx("px-2 py-2 text-right tabular-nums", priceBad ? "font-semibold text-rose-700" : "")}>{money(ln.unit_price)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600">{pl ? money(pl.unit_price) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        <span>Budget owner: {inv.po.budget_owner_name} ({inv.po.department})</span>
        <span>Issued {inv.po.issued_on}</span>
      </div>
    </Card>
  );
}

function Actions({ inv, reload }: { inv: InvoiceDetail; reload: () => void }) {
  const { actor } = useActor();
  const { busy, err, run, fb } = useAct(reload);
  const pending = inv.approvals.filter((a) => !a.decision);
  const payAppr = inv.approvals.filter((a) => a.kind === "payment");
  const bankAppr = inv.approvals.filter((a) => a.kind === "bank_change");
  const notReceived = inv.findings.some((f) => f.code === "QTY_NOT_RECEIVED" && !f.resolved);
  const canReplyAsVendor = inv.status === "awaiting_vendor" && inv.emails.some((e) => e.direction === "out");
  const open = !["scheduled", "paid", "rejected", "superseded"].includes(inv.status);
  return (
    <Card title={inv.approvals.some((a) => !a.decision) ? "Waiting for you" : "Decisions"} className={inv.approvals.some((a) => !a.decision) ? "ring-2 ring-indigo-200" : undefined}>
      <div className="space-y-4">
        {inv.payment && (
          <div className="rounded-lg bg-emerald-50 p-3 text-[13px] text-emerald-900 ring-1 ring-emerald-200">
            <div className="flex items-center gap-1.5 font-medium">
              <ShieldCheck className="h-4 w-4" /> {money(inv.payment.amount, inv.payment.currency)} scheduled for {inv.payment.scheduled_for}
            </div>
            <div className="mt-0.5 text-xs">To the verified account {maskAcct(inv.payment.pay_to_account)} on file for {inv.vendor?.name}.</div>
            {(inv.payment.deductions > 0 || inv.payment.discount > 0 || inv.payment.discount_deadline) && (
              <div className="mt-2 space-y-0.5 border-t border-emerald-200 pt-2 text-xs tabular-nums">
                <div className="flex justify-between"><span>Invoice total</span><span>{money(inv.payment.gross)}</span></div>
                {inv.payment.deductions > 0 && <div className="flex justify-between text-sky-800"><span>Owed to us under contract</span><span>-{money(inv.payment.deductions)}</span></div>}
                {inv.payment.discount > 0 && <div className="flex justify-between"><span>Early-payment discount taken</span><span>-{money(inv.payment.discount)}</span></div>}
                <div className="flex justify-between font-semibold"><span>{inv.payment.status === "released" ? "Released" : "To pay"}</span><span>{money(inv.payment.amount)}</span></div>
                {inv.payment.discount_deadline && inv.payment.status === "scheduled" && (
                  <div className="text-emerald-800">{inv.payment.discount_pct}% discount if paid by {inv.payment.discount_deadline}; the payment run decides.</div>
                )}
              </div>
            )}
          </div>
        )}
        {inv.superseded_by && (
          <Link href={`/invoices/${inv.superseded_by}`} className="flex items-center gap-1.5 rounded-lg bg-slate-50 p-3 text-[13px] text-indigo-700 ring-1 ring-slate-200 hover:bg-slate-100">
            Replaced by the vendor&apos;s corrected invoice <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
        {payAppr.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Payment approval</div>
            {payAppr.map((a) => (
              <PaymentApproval key={a.id} a={a} onDone={reload} />
            ))}
          </div>
        )}
        {bankAppr.length > 0 && inv.bank_change && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Bank change review: callback and two people</div>
            <BankChangeReview approvals={bankAppr} change={inv.bank_change} onDone={reload} />
          </div>
        )}
        {open && (
          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
            {notReceived && (
              <Button size="sm" disabled={busy} onClick={() => run(() => api(`/api/invoices/${inv.id}/receipt`, { method: "POST", json: { user: "Receiving dock", role: "clerk" } }), "Goods receipt logged", "The agent is re-checking the invoice.")}>
                <PackageCheck className="h-3.5 w-3.5" /> Log goods received
              </Button>
            )}
            {canReplyAsVendor && (
              <Button size="sm" disabled={busy} onClick={() => run(() => api(`/api/demo/vendor-reply/${inv.id}`, { method: "POST" }), "The vendor replied", "Their email is in the AP inbox; the agent is reading it.")}>
                <Mail className="h-3.5 w-3.5" /> Play the vendor: reply
              </Button>
            )}
            <Button
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={async () => {
                const reason = await fb.prompt({ title: `Reject ${inv.number}?`, body: "It will not be paid. The reason goes into the audit trail.", placeholder: "Reason", confirmLabel: "Reject invoice", danger: true });
                if (reason) run(() => api(`/api/invoices/${inv.id}/reject`, { method: "POST", json: { ...actor, reason } }), "Invoice rejected");
              }}
            >
              Reject invoice
            </Button>
          </div>
        )}
        {!open && pending.length === 0 && !inv.payment && !inv.superseded_by && <div className="text-[13px] text-slate-500">No decisions pending.</div>}
        {err && <div className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">{err}</div>}
      </div>
    </Card>
  );
}

function CriticCard({ reviews }: { reviews: CriticReview[] }) {
  if (!reviews.length) return null;
  const r = reviews[reviews.length - 1];
  const tone =
    r.verdict === "agree" ? "bg-emerald-50 ring-emerald-200 text-emerald-900" : r.verdict === "disagree" ? "bg-rose-50 ring-rose-200 text-rose-900" : "bg-amber-50 ring-amber-200 text-amber-900";
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Scale className="h-4 w-4 text-slate-500" /> Second opinion from the critic
        </span>
      }
      action={<span className="font-mono text-[11px] text-slate-500">{r.model}</span>}
    >
      <div className={cx("rounded-lg p-3 ring-1", tone)}>
        <div className="text-[13px]">
          <b className="uppercase">{r.verdict}</b>: {r.summary}
        </div>
        {r.points.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12.5px]">
            {r.points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-md bg-slate-50 p-2 ring-1 ring-slate-200">
          <div className="text-slate-500">Proposed payment</div>
          <div className="font-semibold tabular-nums">{money(Number(r.proposal.pay))}</div>
        </div>
        <div className="rounded-md bg-slate-50 p-2 ring-1 ring-slate-200">
          <div className="text-slate-500">Critic&apos;s own figure</div>
          <div className="font-semibold tabular-nums">{r.independent_amount !== null ? money(r.independent_amount) : "-"}</div>
        </div>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">A different model recomputes what should be paid from the invoice, PO, receipts, contract and service measurements, without the proposer&apos;s reasoning. Disagreement sends the payment to the CFO.</p>
    </Card>
  );
}

function Emails({ inv }: { inv: InvoiceDetail }) {
  if (!inv.emails.length) return null;
  return (
    <Card title="Correspondence" pad={false}>
      <ul className="divide-y divide-slate-100">
        {inv.emails.map((e) => (
          <li key={e.id} className="px-4 py-3">
            <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
              <span className="flex items-center gap-1.5">
                <Mail className={cx("h-3.5 w-3.5", e.direction === "out" ? "text-indigo-600" : "text-amber-600")} />
                {e.direction === "out" ? `Tollgate → ${e.recipient}` : `${e.sender} → Tollgate`}
              </span>
              <span>
                {e.status === "simulated" ? "simulated send" : e.status} · {new Date(e.created_at).toLocaleString()}
              </span>
            </div>
            <div className="mt-1 text-[13px] font-medium text-slate-800">{e.subject}</div>
            <pre className="mt-1 whitespace-pre-wrap font-sans text-[12.5px] leading-relaxed text-slate-600">{e.body}</pre>
            {e.attachments?.length > 0 && <div className="mt-1 text-xs text-slate-500">Attached: {e.attachments.join(", ")}</div>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Timeline({ inv }: { inv: InvoiceDetail }) {
  const icon = (actor: string, kind: string) => {
    if (actor === "policy") return <ShieldAlert className="h-3.5 w-3.5 text-rose-600" />;
    if (kind === "injection_detected") return <EyeOff className="h-3.5 w-3.5 text-rose-600" />;
    if (actor === "critic") return <Scale className="h-3.5 w-3.5 text-amber-600" />;
    if (actor === "agent") return <Bot className="h-3.5 w-3.5 text-indigo-600" />;
    if (actor === "controls") return <ShieldCheck className="h-3.5 w-3.5 text-slate-600" />;
    if (actor.startsWith("email:")) return <Mail className="h-3.5 w-3.5 text-amber-600" />;
    return <User className="h-3.5 w-3.5 text-slate-500" />;
  };
  return (
    <Card title="What happened, in order" action={<span className="flex items-center gap-1 text-[11px] text-slate-500"><Hash className="h-3 w-3" />hash-chained</span>} pad={false}>
      <ol className="relative px-4 py-3">
        {inv.timeline.map((e) => {
          const plan = e.kind === "plan" ? (e.detail as { actions?: { type: string }[]; model?: string }) : null;
          return (
            <li key={e.id} className="relative flex gap-3 pb-3 last:pb-0">
              <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-50 ring-1 ring-slate-200">{icon(e.actor, e.kind)}</div>
              <div className="min-w-0 flex-1">
                <div className={cx("text-[13px] leading-snug", e.actor === "policy" ? "font-medium text-rose-700" : "text-slate-800")}>{e.summary}</div>
                {plan?.model && <div className="text-[11px] text-slate-400">model: {plan.model}</div>}
                <div className="flex gap-2 text-[11px] text-slate-400">
                  <span>{e.actor}</span>
                  <span>{new Date(e.created_at).toLocaleTimeString()}</span>
                  <Mono className="text-[10px] text-slate-300">{e.hash.slice(0, 10)}</Mono>
                  {e.invoice_id !== inv.id && <span className="text-slate-400">(earlier version)</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {inv.cost && (
        <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
          Model cost for this invoice: <span className="font-medium text-slate-700">{microMoney(inv.cost.usd)}</span> · {inv.cost.calls} call{inv.cost.calls === 1 ? "" : "s"} ·{" "}
          {(inv.cost.prompt_tokens + inv.cost.completion_tokens).toLocaleString()} tokens on Vultr Serverless Inference
        </div>
      )}
    </Card>
  );
}

function DocumentPanel({ inv }: { inv: InvoiceDetail }) {
  const [tab, setTab] = useState<"pdf" | "fields">("pdf");
  const hidden = inv.extraction.hidden_spans || [];
  return (
    <Card
      pad={false}
      title={
        <span className="flex items-center gap-1.5">
          <FileText className="h-4 w-4 text-slate-500" /> {inv.file_name}
        </span>
      }
      action={
        <div className="flex gap-1">
          {(["pdf", "fields"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={cx("rounded px-2 py-0.5 text-xs", tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>
              {t === "pdf" ? "Document" : "What the agent read"}
            </button>
          ))}
        </div>
      }
    >
      {tab === "pdf" ? (
        <div className="max-h-[760px] space-y-2 overflow-y-auto bg-slate-100 p-3">
          {Array.from({ length: Math.min(inv.pages || 1, 4) }).map((_, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={i} src={`/api/invoices/${inv.id}/pages/${i}.png`} alt={`Page ${i + 1} of ${inv.file_name}`} className="w-full rounded shadow-sm ring-1 ring-slate-200" />
          ))}
          <a href={`/api/invoices/${inv.id}/file`} target="_blank" className="block text-center text-xs text-indigo-600 hover:underline">
            Open original PDF
          </a>
        </div>
      ) : (
        <div className="space-y-4 p-4">
          <div>
            <Row k="Vendor on document" v={inv.vendor_name_raw} />
            <Row k="Tax ID" v={<Mono>{inv.extraction.vendor_tax_id || "-"}</Mono>} />
            <Row k="Invoice number" v={<Mono>{inv.number}</Mono>} />
            <Row k="PO referenced" v={<Mono>{inv.po_number || "none"}</Mono>} />
            <Row k="Dated / due" v={`${inv.invoice_date || "-"} / ${inv.due_date || "-"}`} />
            <Row k="Subtotal / tax" v={`${money(inv.subtotal)} / ${money(inv.tax)}`} />
            <Row k="Total" v={<b>{money(inv.total, inv.currency || "USD")}</b>} />
            <Row k="Remit to" v={<span><Mono>{inv.remit_account || "-"}</Mono> <span className="text-slate-500">{inv.remit_bank_name}</span></span>} />
            <Row k="Read with" v={inv.extraction.method === "vision" ? "Vultr vision model, grounded on the text layer" : "text layer"} />
            {inv.extraction.ungrounded && inv.extraction.ungrounded.length > 0 && <Row k="Not confirmed in text" v={inv.extraction.ungrounded.join(", ")} />}
          </div>
          {hidden.length > 0 && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-rose-800">
                <EyeOff className="h-3.5 w-3.5" /> Text in the file that no person can see on the page
              </div>
              {hidden.map((h, i) => (
                <p key={i} className="font-mono text-[11.5px] leading-relaxed text-rose-900">
                  {h}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const { data: inv, error, reload } = useData<InvoiceDetail>(`/api/invoices/${id}`);
  useEffect(() => {
    if (inv?.number) markSeen(inv.number);
  }, [inv?.number]);
  if (error) return <Empty>{error}</Empty>;
  if (!inv) return <Empty>Loading...</Empty>;
  const busy = ["received", "extracting", "checking", "deciding"].includes(inv.status);
  const actionable =
    inv.approvals.some((a) => !a.decision) ||
    (inv.status === "awaiting_vendor" && inv.emails.some((e) => e.direction === "out")) ||
    inv.findings.some((f) => f.code === "QTY_NOT_RECEIVED" && !f.resolved);
  return (
    <div className="space-y-4">
      <Link href="/" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-3.5 w-3.5" /> All invoices
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight">{inv.vendor?.name || inv.vendor_name_raw || inv.file_name}</h1>
            <StatusPill status={inv.status} />
          </div>
          <div className="mt-0.5 font-mono text-xs text-slate-500">
            {inv.number} {inv.po_number && <>· {inv.po_number}</>} · received via {inv.source}
            {inv.supersedes_id && (
              <>
                {" "}
                · replaces{" "}
                <Link className="text-indigo-600 hover:underline" href={`/invoices/${inv.supersedes_id}`}>
                  earlier version
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums">{money(inv.total, inv.currency || "USD")}</div>
          <div className="text-xs text-slate-500">
            due {inv.due_date || "-"}
            {inv.approval_needed && <> · needs {ROLE_LABEL[inv.approval_needed]} approval</>}
          </div>
        </div>
      </div>

      <div className={cx("flex items-start gap-3 rounded-xl p-4 ring-1", busy ? "bg-violet-50 ring-violet-200" : "bg-indigo-50/70 ring-indigo-100")}>
        <Bot className={cx("mt-0.5 h-5 w-5 shrink-0", busy ? "animate-pulse text-violet-600" : "text-indigo-600")} />
        <div className="text-[13.5px] leading-relaxed text-slate-800">
          {busy ? "Working on it: reading the document and running the controls..." : inv.summary || "No summary yet."}
          {inv.agent_state?.waiting_for && !busy && !["scheduled", "rejected", "superseded", "paid"].includes(inv.status) && (
            <div className="mt-1 text-xs text-slate-500">Waiting for: {inv.agent_state.waiting_for}{inv.agent_state.hold_reason ? `. ${inv.agent_state.hold_reason}` : ""}</div>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {actionable && <Actions inv={inv} reload={reload} />}
          <Findings inv={inv} reload={reload} />
          <ThreeWay inv={inv} />
          <CriticCard reviews={inv.critic} />
          {!actionable && <Actions inv={inv} reload={reload} />}
          <Emails inv={inv} />
        </div>
        <div className="space-y-4">
          <DocumentPanel inv={inv} />
          {inv.vendor && (
            <Card title="Vendor master record">
              <Row k="Contact on file" v={inv.vendor.email} />
              <Row k="Verified bank account" v={<span><Mono>{inv.vendor.bank_account}</Mono> <span className="text-slate-500">{inv.vendor.bank_name}</span></span>} />
              <Row k="Verified" v={inv.vendor.bank_verified_at ? new Date(inv.vendor.bank_verified_at).toLocaleDateString() : "never"} />
              <Row k="Terms" v={`net ${inv.vendor.payment_terms_days}`} />
            </Card>
          )}
          <Timeline inv={inv} />
        </div>
      </div>
    </div>
  );
}
