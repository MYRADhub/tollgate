# Submission kit

## lablab.ai fields

**Title:** Tollgate: the AP agent that pays for itself

**Short description (one line):**
An accounts-payable agent on Vultr that clears its own exceptions by asking the people who know, recovers what vendors owe under their contracts, and catches forged invoices with its own per-vendor document model, with an independent AI critic and code-enforced policy around every dollar.

**Long description:**
Paying a vendor invoice means confirming the vendor is real, the bank account is the one on file, it is not a duplicate, the prices match the PO and the contract, and the goods arrived. About one invoice in five fails one of these checks and needs a person; payment-redirection fraud cost US organisations about $3B in 2025 (FBI IC3); and contracts promise service credits, volume prices and price caps that nobody enforces invoice by invoice.

Tollgate does this work end to end, and pays for itself. A Vultr vision model reads each invoice; Tollgate distrusts what it read, grounding every value against the text layer and comparing every text run with the rendered pixels to find instructions hidden for an AI. A per-vendor fingerprint model checks the PDF really came from the vendor's billing system, and twenty-three deterministic controls check vendor, lookalike names, bank account, duplicates, split billing, arithmetic, PO and receipts. Then the vendor's contract: a model reads each contract once and proposes terms with their exact clauses, code rejects any quote that is not verbatim, a controller approves, and code applies the terms to every invoice. In the demo, Polaris owes a $975 SLA credit for an October outage and Ostara owes $1,416 because the PO missed the contract's volume price; both are deducted with remittance advice quoting the clause.

Exceptions are worked to resolution, not just flagged. The reasoning model investigates with read-only tools (the vendor's open POs, what was ordered, received and billed), then asks the budget owner a structured question, waits, and acts on the answer: an invoice with no PO number is matched to the right PO once its owner confirms; a small unordered charge becomes a change order once the owner agrees; a backordered delivery is waited for and paid when receiving logs it; approvers who sit on a payment are reminded. Code decides what each answer allows. In the demo, on the real models, after one simulated day every exception someone inside the company could settle is cleared without anyone in AP touching it; the rest wait on vendors or, where they need judgment (a bank change, a forged invoice, an unknown vendor), go to a person with the agent's recommendation.

Tollgate also trains its own model: a fingerprint of how each vendor's billing system makes its PDFs (software, fonts, layout, line spacing), learned from the vendor's past invoices. On held-out data it raised no false alarms on 70 genuine invoices and caught all 112 forgeries, including careful ones that copy the vendor's fonts and metadata, and a real invoice edited inside the price tolerance that every field check passes. The demo's forged invoice was made in Word, not in Brightline's Sage Intacct, and the finding says so. And it learns from the team: when a controller confirms that a vendor really did move to a new billing system, the model learns that layout, and the vendor's next invoice passes. Before money moves, a second, independent model recomputes the payment; if it disagrees, the payment goes to the CFO. A policy guard in code allows or refuses every action. A payment-run optimiser pays what is due and spends cash above the floor on early-payment discounts by annualised return. Everything is hash-chained.

It reconciles vendor statements to the cent: invoices we never received, payments the vendor never applied, credit memos we never took (claimed against the next payment), and invoices the vendor's own statement does not list, which is how the demo's forged invoice is confirmed. It also answers vendors' "when will we be paid?" emails from the ledger: only for the vendor's own invoices, only to the registered sender, never changing bank details by email, and with every figure in the model's wording checked before it is sent.

An attack lab lets anyone try to fool it with ten attack types or their own PDF. On the real Vultr models the eval suite passes 135 of 136 cases (the miss is the critic cautiously querying a correct credit), including 30/30 attacks stopped before payment and the demo inbox run through a simulated day of exception work. Model usage costs about a third of a cent per invoice.

Built on four Vultr services: Cloud Compute, Serverless Inference (Qwen 3.8 27B, DeepSeek V4.1 Flash, GLM-5.3 Flash, Nemotron 3.5 content safety), Managed PostgreSQL and Object Storage.

**Tags:** Vultr, AI agents, Finance, Accounts Payable, Procurement, Contract compliance, Fraud prevention, Prompt injection, Multi-agent, FastAPI, Next.js, PostgreSQL

**Links:**
- Demo: https://45.32.218.92.sslip.io
- Repository: https://github.com/MYRADhub/tollgate
- Slides: export the deck as PDF and attach it

## Demo video script (about 4.5 minutes)

Record at 1600x1000 or larger, from a reset demo ("Reset demo" on the Invoices page, which is the dashboard). For a clean first take, **Show me in 2 minutes** on the dashboard plays steps 0:20 to 2:15 by itself with captions; you can narrate over it. The guided demo on the dashboard follows this script. Two threads run through it: the agent clearing exceptions on its own, and the forged BIS-2090, caught four independent ways.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Slide: cover | "One invoice in five needs someone in AP to chase something: a missing PO number, goods that haven't arrived, a charge nobody ordered. Tollgate is an AP agent that does that chasing itself, claims what vendors owe under their contracts, and is safe to put an AI in front of payments. It runs entirely on Vultr." |
| 0:20 | Dashboard, guided demo step 1: Load the demo inbox | "Twelve invoices from seven vendors. A Vultr vision model reads each one; controls in code check it; the agent decides." Let the briefing fill in. |
| 0:40 | Step 2: GE-5570, timeline and "The agent asked colleagues" | "This invoice quotes no PO number. The agent searched Granite's open POs, found the one that covers its lines, and asked Marcus, who owns it. He said yes, so it attached the PO, re-ran every control, and scheduled the payment. Nobody in AP touched it. Code checked that the yes came from that PO's owner before anything changed." |
| 1:15 | Step 3: Fast-forward a day, then the briefing | "Another invoice billed for breakers that hadn't arrived. Marcus said they were backordered until tomorrow. Fast-forward a day: they arrive, receiving logs them, it pays. Here is the briefing: the exceptions it cleared with no human touch, what is still waiting on vendors, the work it did, and the decisions that need my judgment, each with its recommendation." |
| 1:45 | Needs you: BIS-2090 | "This one is a forgery. White, one-and-a-half-point text tells the AI to pre-approve it and change the bank account; Tollgate compared the text with the pixels and found it. The bank account is not the one on file. And our own model says this PDF was made in Microsoft Word, while every Brightline invoice comes out of Sage Intacct." |
| 2:15 | Vendors & POs: Document fingerprints | "That model is ours. One per vendor, trained on its past invoices: the software, fonts, where every label sits. On held-out data: no false alarms on 70 genuine invoices, and all 112 forgeries caught, even ones that copy the vendor's fonts and metadata." |
| 2:40 | Briefing: approve OC-7720 ("Act as Rosa Kim (Controller)", then "Approve as Rosa Kim"; switch to Rosa before recording to make it one click) | "Ostara's PO used list price; the contract gives a volume price. $1,416 back, deducted with the clause quoted. A second model, the critic, recomputed the payment and agrees. I approve it from the briefing." Mention Polaris: "Polaris owes $975 for an outage, same way." |
| 3:05 | Statements, Load demo statements | "Vendors' statements, reconciled to the cent: credit memos nobody claimed, payments they never applied. And Brightline's own statement doesn't list BIS-2090. The fourth independent signal." |
| 3:30 | Attack lab: "A real invoice, quietly edited", then the scorecard | "Anyone can try to fool it. Here a real invoice was edited to raise a price by 1.7 percent, inside tolerance, totals fixed. Every field check passes; the fingerprint holds it. On the real Vultr models the eval suite passes 135 of 136 cases." |
| 3:55 | Slide: business, then close | "AP teams spend about ten dollars an invoice. Tollgate runs on a third of a cent of inference, clears most exceptions by itself, and contract and statement recoveries alone can pay for it. Tollgate: every invoice earns its payment. Live on Vultr, code on GitHub." |

## Before submitting

- Export the deck to PDF from the deck's Share > Export menu: https://claude.ai/artifact/37CHCJ7CjByk9EEhFKrFi3
- Cover image: `docs/cover.jpg` (1600x1000, the live dashboard after the inbox is worked).
- If the critic queries Polaris PNS-55120 during the take (it did once in three eval runs), it appears under Needs you for a controller; approve it as Rosa Kim or retake. It is the safe outcome, not a failure.
- Reset the demo after recording so judges start from an empty inbox (the shared-demo badge shows when it was last reset).
