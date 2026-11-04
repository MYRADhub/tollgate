"use client";

import { ReactNode } from "react";
import { ArrowDown, Bot, Cloud, Database, FileSearch, HardDrive, Lock, Mail, Server, ShieldCheck, Users } from "lucide-react";
import { money, useData } from "@/lib/api";
import { Card, Mono } from "@/components/ui";

type Config = {
  auto_pay_limit: number;
  controller_limit: number;
  price_tolerance_pct: number;
  models: { vision: string; reasoning: string; safety: string };
  inference: boolean;
  mail: boolean;
  mailbox: string | null;
  storage: string;
  database: string;
  controls: string[];
};

function Step({ icon, title, who, children }: { icon: ReactNode; title: string; who: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">{icon}</div>
        <div>
          <div className="text-sm font-semibold">{title}</div>
          <div className="text-[11px] uppercase tracking-wide text-slate-500">{who}</div>
        </div>
      </div>
      <div className="mt-2 text-[13px] leading-relaxed text-slate-600">{children}</div>
    </div>
  );
}

const Down = () => (
  <div className="flex justify-center py-1 text-slate-300">
    <ArrowDown className="h-4 w-4" />
  </div>
);

export default function HowItWorks() {
  const { data: c } = useData<Config>("/api/config");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">How Tollgate works</h1>
        <p className="max-w-3xl text-sm text-slate-500">
          The model reads and writes; code decides. A language model is good at reading messy documents and writing a clear email to a vendor. It should never be the thing that decides whether money moves. Tollgate splits those jobs.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div>
          <Step icon={<Mail className="h-4 w-4" />} title="1. Invoice arrives" who="AP mailbox (Gmail IMAP) or upload">
            The worker polls the AP inbox. A PDF is stored in {c?.storage ?? "object storage"} with its SHA-256, and a job is queued. Replies to the agent&apos;s own emails are matched back to their invoice by a tag in the subject.
          </Step>
          <Down />
          <Step icon={<FileSearch className="h-4 w-4" />} title="2. Read, and distrust what was read" who={`Vultr Serverless Inference: ${c?.models.vision ?? "vision model"}`}>
            Pages are rendered to images for the vision model, so scans work. Every key value is then grounded against the PDF text layer. Separately, each text run is compared with the rendered pixels: text that is in the file but invisible on the page (white, microscopic, covered) is surfaced. Instruction-shaped text, the content-safety model ({c?.models.safety ?? "safety model"}) and the reader&apos;s own report of instructions it saw raise a quarantine.
          </Step>
          <Down />
          <Step icon={<ShieldCheck className="h-4 w-4" />} title={`3. ${c?.controls.length ?? 20} deterministic controls`} who="Plain Python, no model">
            Vendor master match, verified bank account, duplicate file, number and resubmission detection, line and total arithmetic, PO existence, ownership and status, currency, item on PO, price within {c?.price_tolerance_pct ?? 2}% of PO, cumulative quantity against ordered and received, payment terms. Each finding carries the evidence and the amount at risk.
          </Step>
          <Down />
          <Step icon={<Bot className="h-4 w-4" />} title="4. The agent plans" who={`Vultr Serverless Inference: ${c?.models.reasoning ?? "reasoning model"}`}>
            The model sees the findings, the PO, the vendor history and the email thread, and returns a plan: email the vendor for a corrected invoice, ask the budget owner whether goods arrived, request approval, open a bank change, hold, reject, or pay. Document and email text is passed as untrusted data.
          </Step>
          <Down />
          <Step icon={<Lock className="h-4 w-4" />} title="5. A policy guard executes, or refuses" who="Code the model cannot change">
            Payment only with no open blocking findings, only to the vendor-master account, only with the approvals the amount needs (auto up to {c ? money(c.auto_pay_limit) : "$10,000"}, controller up to {c ? money(c.controller_limit) : "$50,000"}, CFO above). Emails go only to the contact on file, never to an address printed on the invoice. Blocking findings clear only on new evidence or a person. Refusals are logged and the model re-plans.
          </Step>
          <Down />
          <Step icon={<Users className="h-4 w-4" />} title="6. People, only where they add judgment" who="Clerk, controller, CFO">
            Approvals above the limits; bank changes that need a callback to the number on file and two different approvers; overrides with a written justification. Every decision hands control back to the agent, which picks up where it left off.
          </Step>
        </div>

        <div className="space-y-4">
          <Card title="Running on Vultr">
            <ul className="space-y-3 text-[13px] text-slate-700">
              <li className="flex gap-2.5">
                <Server className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
                <span><b>Cloud Compute VM</b>: Caddy (TLS), the Next.js app, the FastAPI API and the agent worker in Docker. The worker runs continuously, so follow-ups and replies are handled with no one logged in.</span>
              </li>
              <li className="flex gap-2.5">
                <Cloud className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
                <span><b>Serverless Inference</b>: vision extraction, planning and content safety. Invoice data stays on Vultr; no third-party model provider sees it.</span>
              </li>
              <li className="flex gap-2.5">
                <Database className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
                <span><b>{c?.database === "PostgreSQL" ? "Managed PostgreSQL" : "Database"}</b>: vendors, POs, receipts, invoices, findings, approvals, payments, the job queue and the hash-chained audit log.</span>
              </li>
              <li className="flex gap-2.5">
                <HardDrive className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
                <span><b>{c?.storage === "Vultr Object Storage" ? "Object Storage" : "File storage"}</b>: original invoice PDFs and email attachments, addressed by hash.</span>
              </li>
            </ul>
          </Card>
          <Card title="Live configuration">
            <div className="space-y-1.5 text-[12.5px]">
              <div className="flex justify-between"><span className="text-slate-500">Vision model</span><Mono>{c?.models.vision}</Mono></div>
              <div className="flex justify-between"><span className="text-slate-500">Reasoning model</span><Mono>{c?.models.reasoning}</Mono></div>
              <div className="flex justify-between"><span className="text-slate-500">Safety model</span><Mono>{c?.models.safety}</Mono></div>
              <div className="flex justify-between"><span className="text-slate-500">Inference connected</span><span>{c?.inference ? "yes" : "no (rule-based fallback)"}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">AP mailbox</span><span>{c?.mail ? c.mailbox : "simulated"}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Database</span><span>{c?.database}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Files</span><span>{c?.storage}</span></div>
            </div>
          </Card>
          <Card title="Controls run on every invoice">
            <div className="flex flex-wrap gap-1.5">
              {c?.controls.map((x) => (
                <span key={x} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11.5px] text-slate-700">{x}</span>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
