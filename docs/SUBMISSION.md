# Submission kit

## lablab.ai fields

**Title:** Tollgate: the AP agent that pays for itself

**Short description (one line):**
An accounts-payable agent on Vultr that recovers what vendors owe under their contracts, stops fraud and AI prompt injection before payment, and decides when to pay, with an independent AI critic and code-enforced policy around every dollar.

**Long description:**
Paying a vendor invoice means confirming the vendor is real, the bank account is the one on file, it is not a duplicate, the prices match the PO and the contract, and the goods arrived. About one invoice in five fails one of these checks and needs a person; payment-redirection fraud cost US organisations about $3B in 2025 (FBI IC3); and contracts promise service credits, volume prices and price caps that nobody enforces invoice by invoice.

Tollgate does this work end to end, and pays for itself. A Vultr vision model reads each invoice; Tollgate distrusts what it read, grounding every value against the text layer and comparing every text run with the rendered pixels to find instructions hidden for an AI. Twenty-three deterministic controls check vendor, lookalike names, bank account, duplicates, split billing, arithmetic, PO and receipts. Then the vendor's contract: a model reads each contract once and proposes terms with their exact clauses, code rejects any quote that is not verbatim, a controller approves, and code applies the terms to every invoice. In the demo, Polaris owes a $975 SLA credit for an October outage and Ostara owes $1,416 because the PO missed the contract's volume price; both are deducted with remittance advice quoting the clause.

A reasoning model works exceptions (emailing vendors and budget owners, re-reading corrected invoices). Before money moves, a second, independent model recomputes the payment; if it disagrees, the payment goes to the CFO. A policy guard in code allows or refuses every action. A payment-run optimiser pays what is due and spends cash above the floor on early-payment discounts by annualised return. Everything is hash-chained.

It also answers vendors' "when will we be paid?" emails from the ledger: only for the vendor's own invoices, only to the registered sender, never changing bank details by email, and with every figure in the model's wording checked before it is sent.

An attack lab lets anyone try to fool it with nine attack types or their own PDF. On the real Vultr models the eval suite passes 110 of 111 cases, including 27/27 attacks stopped before payment. Model usage costs about a third of a cent per invoice.

Built on four Vultr services: Cloud Compute, Serverless Inference (Qwen 3.8 27B, DeepSeek V4.1 Flash, GLM-5.3 Flash, Nemotron 3.5 content safety), Managed PostgreSQL and Object Storage.

**Tags:** Vultr, AI agents, Finance, Accounts Payable, Procurement, Contract compliance, Fraud prevention, Prompt injection, Multi-agent, FastAPI, Next.js, PostgreSQL

**Links:**
- Demo: https://45.32.218.92.sslip.io
- Repository: https://github.com/MYRADhub/tollgate
- Slides: export the deck as PDF

## Demo video script (about 4.5 minutes)

Record at 1600x1000 or larger. Start from a reset demo (Invoices, "Reset demo"). Keep the Agent activity feed visible on the first screen.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Slide: cover | "Every AP team checks the same five things before paying an invoice, and still leaves money on the table: credits and discounts vendors owe under their contracts. Tollgate is an AP agent that does those checks, claims what you are owed, and is safe to put an AI in front of payments. It runs entirely on Vultr." |
| 0:20 | App, Invoices: Demo inbox, Send all | "Ten invoices from seven vendors land in the AP inbox." |
| 0:30 | Activity feed | "A vision model on Vultr reads each one, twenty-three controls check it, and the agent decides. Under a minute for the batch, about five cents of inference." |
| 0:50 | Open Polaris PNS-55120 | "This invoice matches its PO perfectly. But our monitoring saw 99.31 percent uptime in October against a 99.95 commitment. Tollgate read the contract, here is the clause, and claims a 15 percent credit: 975 dollars, deducted, with remittance advice quoting the clause. A second model, the critic, recomputed the payment independently and agrees." |
| 1:35 | Contracts page | "Each contract is read once by a model that proposes the terms with their exact clauses. Code throws out any quote that is not in the contract word for word, and a controller approves them. After that, code applies them to every invoice." |
| 1:55 | Open Ostara OC-7720 | "Ostara's PO used list price; the contract gives a volume price. Fourteen hundred dollars back. It is over the auto-pay limit, so it waits for the controller." Switch to Rosa Kim, approve. |
| 2:15 | Open Brightline BIS-2090 | "This one hides instructions for the AI in white, one-and-a-half-point type: pre-approve, change the bank account. Tollgate compares the text with the rendered pixels, found it, and quarantined the invoice. Even if a model had been fooled, the policy guard in code only pays the verified account." |
| 2:45 | Open BIS-2077, Play the vendor (or reply from your phone) | "Here the vendor overbilled; the agent emailed the exact overcharge. The corrected invoice comes back by reply, is re-read, re-checked and paid." |
| 3:05 | Payment runs | "When to pay is a decision too. Lumen gives two percent for paying within ten days, that is 149 percent a year, so it is taken. Brightline's one percent waits because cash above the floor ran out. Approve, download the bank file." |
| 3:25 | Attack lab: launch Lookalike vendor and Split to dodge approval | "Judges can try to fool it. A lookalike vendor, an invoice split to stay under the approval limit, or upload your own PDF. Same pipeline as real mail. On the real models our eval suite passes 110 of 111 cases, every attack stopped." |
| 3:55 | Slide: business | "AP teams spend about ten dollars an invoice by hand. Tollgate charges about a dollar, and contract recoveries alone can pay for it. The incumbents capture and route invoices; Tollgate resolves them and enforces the contract." |
| 4:20 | Slide: close | "Tollgate: the AP agent that pays for itself. Live on Vultr, code on GitHub." |

## Before submitting

- Replace `[Your name]` and `[email]` on the cover and closing slides.
- Export the deck to PDF from the deck's Share > Export menu.
- Cover image: the queue screenshot (`deck-img/queue.png`) works at 16:10.
- Reset the demo after recording so judges start from an empty inbox.
