"use client";

import { useState } from "react";
import { ArrowRightLeft, CheckCircle2, Phone, XCircle } from "lucide-react";
import { Approval, PEOPLE, ROLE_LABEL, Role, api, canApprove, personFor, useActor } from "@/lib/api";
import { useFeedback } from "./Feedback";
import { Button, Mono, cx } from "./ui";

function Decided({ a }: { a: Approval }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-600">
      {a.decision === "approved" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <XCircle className="h-3.5 w-3.5 text-rose-600" />}
      {a.decision} by {a.decided_by} {a.decided_role && `(${ROLE_LABEL[a.decided_role]})`}
    </div>
  );
}

function SwitchHint({ required, exclude }: { required: Role; exclude?: string[] }) {
  const { actor, setActor } = useActor();
  const target = PEOPLE.find((p) => canApprove(p.role, required) && !(exclude || []).includes(p.user)) || personFor(required);
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
      <span>
        You are {actor.user} ({ROLE_LABEL[actor.role]}).{" "}
        {exclude?.includes(actor.user) ? "A different person must approve this." : `This needs ${ROLE_LABEL[required]} or above.`}
      </span>
      <button onClick={() => setActor(target)} className="inline-flex items-center gap-1 font-medium text-indigo-700 hover:underline">
        <ArrowRightLeft className="h-3 w-3" /> Act as {target.user} ({ROLE_LABEL[target.role]})
      </button>
    </div>
  );
}

export function PaymentApproval({ a, onDone }: { a: Approval; onDone: () => void }) {
  const { actor } = useActor();
  const fb = useFeedback();
  const [busy, setBusy] = useState(false);
  if (a.decision) return <Decided a={a} />;
  const allowed = canApprove(actor.role, a.required_role);
  const decide = async (decision: "approved" | "rejected") => {
    let comment: string | undefined;
    if (decision === "rejected") {
      const r = await fb.prompt({ title: "Reject this payment?", body: "The invoice is rejected and the vendor is not paid.", placeholder: "Reason", confirmLabel: "Reject payment", danger: true });
      if (r === null) return;
      comment = r;
    }
    setBusy(true);
    try {
      await api(`/api/approvals/${a.id}/decide`, { method: "POST", json: { ...actor, decision, comment } });
      fb.toast("success", decision === "approved" ? "Payment approved" : "Payment rejected", decision === "approved" ? "The agent is scheduling it now." : undefined);
      onDone();
    } catch (e) {
      fb.toast("error", "Not allowed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <p className="text-[13px] leading-relaxed text-slate-700">{a.reason}</p>
      {allowed ? (
        <div className="flex items-center gap-2">
          <Button size="sm" variant="good" disabled={busy} onClick={() => decide("approved")}>
            Approve as {actor.user}
          </Button>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => decide("rejected")}>
            Reject
          </Button>
        </div>
      ) : (
        <SwitchHint required={a.required_role} />
      )}
    </div>
  );
}

export function BankChangeReview({
  approvals,
  change,
  onDone,
}: {
  approvals: Approval[];
  change: { old_account: string; new_account: string; new_bank_name: string; status: string; callback_note: string | null; vendor?: string };
  onDone: () => void;
}) {
  const { actor } = useActor();
  const fb = useFeedback();
  const [callback, setCallback] = useState("");
  const [busy, setBusy] = useState(false);
  const approved = approvals.filter((a) => a.decision === "approved");
  const open = approvals.find((a) => !a.decision);
  const rejected = approvals.some((a) => a.decision === "rejected");
  const approvers = approved.map((a) => a.decided_by || "");
  const needsCallback = !change.callback_note;

  const decide = async (decision: "approved" | "rejected") => {
    if (!open) return;
    if (decision === "rejected") {
      const ok = await fb.confirm({
        title: "Reject the bank change?",
        body: "The account on file stays as it is. Use this when the callback shows the vendor never asked for a change.",
        confirmLabel: "Reject change",
        danger: true,
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      await api(`/api/approvals/${open.id}/decide`, { method: "POST", json: { ...actor, decision, callback_note: needsCallback && callback ? callback : undefined } });
      fb.toast(
        "success",
        decision === "rejected" ? "Bank change rejected" : approved.length === 0 ? "First approval recorded" : "Bank change approved",
        decision === "rejected" ? "The verified account stays on file." : approved.length === 0 ? "A different person must give the second approval." : "The account on file is updated and the invoice is re-checked.",
      );
      setCallback("");
      onDone();
    } catch (e) {
      fb.toast("error", "Not allowed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-md bg-slate-50 p-2 ring-1 ring-slate-200">
          <div className="text-slate-500">On file (verified)</div>
          <Mono>{change.old_account}</Mono>
        </div>
        <div className="rounded-md bg-rose-50 p-2 ring-1 ring-rose-200">
          <div className="text-rose-700">Requested by the document</div>
          <Mono className="text-rose-900">{change.new_account}</Mono>
          <div className="text-[11px] text-rose-700">{change.new_bank_name}</div>
        </div>
      </div>
      <ol className="flex items-center gap-2 text-xs">
        {[0, 1].map((i) => (
          <li
            key={i}
            className={cx(
              "flex items-center gap-1 rounded-full px-2 py-0.5 ring-1",
              approved[i] ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-white text-slate-500 ring-slate-200",
            )}
          >
            {approved[i] ? <CheckCircle2 className="h-3 w-3" /> : <span className="h-3 w-3 rounded-full border border-slate-300" />}
            {approved[i] ? approved[i].decided_by : `Approver ${i + 1}`}
          </li>
        ))}
        {change.callback_note && (
          <li className="flex items-center gap-1 text-slate-600">
            <Phone className="h-3 w-3" /> {change.callback_note}
          </li>
        )}
      </ol>
      {rejected || change.status === "rejected" ? (
        <div className="text-xs font-medium text-rose-700">Rejected: the account on file is unchanged.</div>
      ) : change.status === "approved" ? (
        <div className="text-xs font-medium text-emerald-700">Approved by two people after a callback; the vendor master is updated.</div>
      ) : open ? (
        !canApprove(actor.role, open.required_role) || approvers.includes(actor.user) ? (
          <SwitchHint required={open.required_role} exclude={approvers} />
        ) : (
          <div className="space-y-2">
            {needsCallback && (
              <input
                value={callback}
                onChange={(e) => setCallback(e.target.value)}
                placeholder="Callback record: number dialled from the vendor master, who confirmed"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs"
              />
            )}
            <div className="flex items-center gap-2">
              <Button size="sm" variant="good" disabled={busy || (needsCallback && !callback.trim())} onClick={() => decide("approved")}>
                {approved.length === 0 ? "Record callback and approve" : "Give second approval"}
              </Button>
              <Button size="sm" variant="danger" disabled={busy} onClick={() => decide("rejected")}>
                Reject change
              </Button>
              <span className="text-[11px] text-slate-500">as {actor.user}</span>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
