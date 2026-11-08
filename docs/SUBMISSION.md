# Submission kit

## lablab.ai fields

**Title:** Tollgate: the AP agent that pays for itself

**Short description (one line):**
An accounts-payable agent on Vultr that works invoice exceptions to resolution, recovers what vendors owe under contract, and catches forged invoices with its own per-vendor document model.

**Long description:**
About one vendor invoice in five needs someone in accounts payable to chase something. Payment-redirection fraud cost US organisations about $3B in 2025 (FBI IC3), and contract credits go unclaimed because nobody checks them invoice by invoice.

Tollgate works those invoices end to end for mid-market finance teams. A Vultr vision model reads each one; code grounds every value against the PDF, compares text with pixels to find instructions hidden for an AI, and runs 23 controls. Exceptions are worked, not just flagged: the agent looks up open POs, asks the PO's owner a structured question, waits for the answer or the delivery, and acts. Code decides what each answer allows.

It recovers money. Contract terms are extracted with verbatim clauses, approved by a controller and applied by code: $2,434 in the demo, plus $476 in unclaimed credit memos from vendor statements. A second model recomputes judged payments, and a policy guard in code can refuse any action.

Tollgate trains its own per-vendor model of how each billing system builds its PDFs: 0 false alarms on 70 held-out genuine invoices and 112 of 112 forgeries caught, on generated archives.

On the real models, evals pass 135 of 136 cases, including 30/30 attacks stopped before payment. Model usage is about $0.0033 per invoice. Anyone can try to fool it in the attack lab with their own PDF.

Limits: colleagues are simulated in the demo, vendor archives are generated, and it is a shared demo without real login. Built on Vultr Cloud Compute, Serverless Inference (four models), Managed PostgreSQL and Object Storage; the AP mailbox is Gmail.

**Tags:** Vultr, AI agents, Finance, Accounts Payable, Procurement, Contract compliance, Fraud prevention, Prompt injection, Multi-agent, FastAPI, Next.js, PostgreSQL

**Links:**
- Demo: https://45.32.218.92.sslip.io
- Repository: https://github.com/MYRADhub/tollgate
- Slides: export the deck as PDF and attach it

## Demo video script (about 4.5 minutes)

Record at 1600x1000 or larger, from a reset demo ("Reset demo" on the Invoices page, which is the dashboard). For a clean first take, **Show me in 2 minutes** on the dashboard plays steps 0:20 to 2:15 by itself with captions; you can narrate over it. The guided demo on the dashboard follows this script. Two threads run through it: the agent clearing exceptions on its own, and the forged BIS-2090, caught four independent ways.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Slide: cover | "One invoice in five needs someone in AP to chase something: a missing PO number, goods that haven't arrived, a charge nobody ordered. Tollgate is an AP agent that does that chasing itself, claims what vendors owe under their contracts, and is safe to put an AI in front of payments." |
| 0:20 | Dashboard, guided demo step 1: Load the demo inbox | "Twelve invoices from seven vendors. A Vultr vision model reads each one; controls in code check it; the agent decides." Let the briefing fill in. |
| 0:40 | Step 2: GE-5570, timeline and "The agent asked colleagues" | "This invoice quotes no PO number. The agent searched Granite's open POs, found the one that covers its lines, and asked Marcus, who owns it. He said yes, so it attached the PO, re-ran every control, and scheduled the payment. Nobody in AP touched it. Code checked that the yes came from that PO's owner before anything changed." |
| 1:15 | Step 3: Fast-forward a day, then the briefing | "Another invoice billed for breakers that hadn't arrived. Marcus said they were backordered until tomorrow. Fast-forward a day: they arrive, receiving logs them, it pays. Here is the briefing: the exceptions it cleared with no human touch, what is still waiting on vendors, the work it did, and the decisions that need my judgment, each with its recommendation." |
| 1:45 | Needs you: BIS-2090 | "This one is a forgery. White, one-and-a-half-point text tells the AI to pre-approve it and change the bank account; Tollgate compared the text with the pixels and found it. The bank account is not the one on file. And our own model says this PDF was made in Microsoft Word, while every Brightline invoice comes out of Sage Intacct." |
| 2:15 | Vendors & POs: Document fingerprints | "That model is ours. One per vendor, trained on its past invoices: the software, fonts, where every label sits. On held-out data: no false alarms on 70 genuine invoices, and all 112 forgeries caught, even ones that copy the vendor's fonts and metadata." |
| 2:40 | Briefing: approve OC-7720 ("Act as Rosa Kim (Controller)", then "Approve as Rosa Kim"; switch to Rosa before recording to make it one click) | "Ostara's PO used list price; the contract gives a volume price. $1,416 back, deducted with the clause quoted. A second model, the critic, recomputed the payment and agrees. I approve it from the briefing." Mention Polaris: "Polaris owes $975 for an outage, same way." |
| 3:05 | Statements, Load demo statements | "Vendors' statements, reconciled to the cent: credit memos nobody claimed, payments they never applied. And Brightline's own statement doesn't list BIS-2090. The fourth independent signal." |
| 3:30 | Attack lab: "A real invoice, quietly edited", then the scorecard | "Anyone can try to fool it. Here a real invoice was edited to raise a price by 1.7 percent, inside tolerance, totals fixed. Every field check passes; the fingerprint holds it. On the real Vultr models the eval suite passes 135 of 136 cases." |
| 3:55 | Slide: business, then close | "AP teams spend about ten dollars an invoice. Tollgate runs on a third of a cent of inference, clears every exception someone inside the company can settle, and contract and statement recoveries alone can pay for it. Tollgate: every invoice earns its payment. Live on Vultr, code on GitHub." |

## Before submitting

- Export the deck to PDF from the deck's Share > Export menu: https://claude.ai/artifact/37CHCJ7CjByk9EEhFKrFi3
- Cover image: `docs/cover.jpg` (1600x1000, the live dashboard after the inbox is worked).
- If the critic queries Polaris PNS-55120 during the take (it did once in three eval runs), it appears under Needs you for a controller; approve it as Rosa Kim or retake. It is the safe outcome, not a failure.
- Reset the demo after recording so judges start from an empty inbox (the shared-demo badge shows when it was last reset).
