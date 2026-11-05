# Submission kit

## lablab.ai fields

**Title:** Tollgate: the AP agent that pays for itself

**Short description (one line):**
An accounts-payable agent on Vultr that recovers what vendors owe under their contracts, stops fraud and AI prompt injection before payment, and decides when to pay, with an independent AI critic and code-enforced policy around every dollar.

**Long description:**
Paying a vendor invoice means confirming the vendor is real, the bank account is the one on file, it is not a duplicate, the prices match the PO and the contract, and the goods arrived. About one invoice in five fails one of these checks and needs a person; payment-redirection fraud cost US organisations about $3B in 2025 (FBI IC3); and contracts promise service credits, volume prices and price caps that nobody enforces invoice by invoice.

Tollgate does this work end to end, and pays for itself. A Vultr vision model reads each invoice; Tollgate distrusts what it read, grounding every value against the text layer and comparing every text run with the rendered pixels to find instructions hidden for an AI. Twenty-three deterministic controls check vendor, lookalike names, bank account, duplicates, split billing, arithmetic, PO and receipts. Then the vendor's contract: a model reads each contract once and proposes terms with their exact clauses, code rejects any quote that is not verbatim, a controller approves, and code applies the terms to every invoice. In the demo, Polaris owes a $975 SLA credit for an October outage and Ostara owes $1,416 because the PO missed the contract's volume price; both are deducted with remittance advice quoting the clause.

A reasoning model works exceptions (emailing vendors and budget owners, re-reading corrected invoices). Before money moves, a second, independent model recomputes the payment; if it disagrees, the payment goes to the CFO. A policy guard in code allows or refuses every action. A payment-run optimiser pays what is due and spends cash above the floor on early-payment discounts by annualised return. Everything is hash-chained.

It reconciles vendor statements to the cent: invoices we never received, payments the vendor never applied, credit memos we never took (claimed against the next payment), and invoices the vendor's own statement does not list, which is how the demo's forged invoice is confirmed. It also answers vendors' "when will we be paid?" emails from the ledger: only for the vendor's own invoices, only to the registered sender, never changing bank details by email, and with every figure in the model's wording checked before it is sent.

An attack lab lets anyone try to fool it with nine attack types or their own PDF. On the real Vultr models the eval suite passes all 117 cases, including 27/27 attacks stopped before payment. Model usage costs about a third of a cent per invoice.

Built on four Vultr services: Cloud Compute, Serverless Inference (Qwen 3.8 27B, DeepSeek V4.1 Flash, GLM-5.3 Flash, Nemotron 3.5 content safety), Managed PostgreSQL and Object Storage.

**Tags:** Vultr, AI agents, Finance, Accounts Payable, Procurement, Contract compliance, Fraud prevention, Prompt injection, Multi-agent, FastAPI, Next.js, PostgreSQL

**Links:**
- Demo: https://45.32.218.92.sslip.io
- Repository: https://github.com/MYRADhub/tollgate
- Slides: export the deck as PDF and attach it

## Demo video script (about 4.5 minutes)

Record at 1600x1000 or larger, from a reset demo (Invoices, "Reset demo"). Follow the guided demo on the dashboard: its eight steps are this script. Keep the agent activity feed in view on the first screen. One thread runs through it: the forged BIS-2090 is caught three independent ways.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Slide: cover | "Every AP team checks the same things before paying an invoice, and still leaves money on the table: credits vendors owe under their contracts and on their own statements. Tollgate is an AP agent that does that work, claims what you are owed, and is safe to put an AI in front of payments. It runs entirely on Vultr." |
| 0:20 | Dashboard, guided demo step 1: Load the demo inbox | "Ten invoices from seven vendors arrive. A vision model on Vultr reads each one, twenty-three controls in code check it, and the agent decides. About a third of a cent of inference per invoice, against $2.78 for the best AP teams." Point at the cost strip. |
| 0:50 | Step 2: Polaris PNS-55120 | "This invoice matches its PO perfectly. But our monitoring saw 99.31 percent uptime against a 99.95 commitment. Tollgate read the contract, here is the clause, and deducts a 15 percent service credit: $975, with remittance advice quoting it. A second model, the critic, recomputed the payment independently and agrees." |
| 1:25 | Step 3: Brightline BIS-2090, Document tab | "This one hides instructions for the AI in white, one-and-a-half-point type: pre-approve it, change the bank account. Tollgate compares every text run with the rendered pixels, found it, and quarantined the invoice. Even a fooled model could not pay it: the policy guard in code only pays the verified account." |
| 1:55 | Step 4: Ostara OC-7720, act as Rosa Kim, approve | "Ostara's PO used list price; the contract gives a volume price. $1,416 back. It is over the auto-pay limit, so the controller approves, and the critic's figure is right there." |
| 2:15 | Step 5: BIS-2077, Play the vendor (or reply from Gmail) | "Here the vendor overbilled. The agent emailed the exact overcharge; the corrected invoice comes back by reply, is re-read, re-checked and paid." |
| 2:35 | Step 6: Statements, Load demo statements | "Vendors send statements of what they think we owe. Tollgate explains the gap to the cent. Kestrel never applied our payment, which is why they resubmitted an invoice: we send them the remittance. Two credit memos nobody claimed: $476. And look: Brightline's own statement does not list BIS-2090. The real vendor never issued it." Claim Kestrel's credit as Rosa Kim. |
| 3:15 | Step 7: Payment runs, approve | "When to pay is a decision too. Lumen gives two percent for paying within ten days, 149 percent a year, so it is taken; the rest waits until due. Approve, download the bank file." |
| 3:35 | Step 8: Vendor questions, "Why were we short-paid?", then "Impersonates a vendor" | "Vendors ask when they will be paid. Polaris, from its registered address, gets its answer with the deduction explained; the model wrote it and code checked every figure. A lookalike domain gets nothing." |
| 3:55 | Attack lab scorecard | "Anyone can try to fool it, with nine attacks or their own PDF. On the real Vultr models the eval suite passes all 117 cases, every attack stopped." |
| 4:10 | Slide: business, then close | "AP teams spend about ten dollars an invoice. Tollgate charges about a dollar, runs on a third of a cent of inference, and contract and statement recoveries alone can pay for it. Tollgate: every invoice earns its payment. Live on Vultr, code on GitHub." |

## Before submitting

- Export the deck to PDF from the deck's Share > Export menu.
- Cover image: a dashboard screenshot at 16:10 after the inbox is loaded.
- Reset the demo after recording so judges start from an empty inbox (the shared-demo badge shows when it was last reset).
