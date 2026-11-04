# Submission kit

## lablab.ai fields

**Title:** Tollgate: every invoice earns its payment

**Short description (one line):**
An autonomous accounts-payable agent on Vultr that reads vendor invoices, runs 3-way match and fraud controls, works exceptions with vendors by email, and pays only what is owed.

**Long description:**
Paying a vendor invoice means confirming the vendor is real, the bank account is the one on file, it is not a duplicate, the prices match the purchase order and the goods arrived. About one invoice in five fails one of these checks and needs a person, and that is also where payment-redirection fraud gets through (about $3B in US business email compromise losses in 2025, FBI IC3).

Tollgate is an AP agent that does this work end to end. Invoices arrive by email or upload. A Vultr vision model reads each one; Tollgate then distrusts what it read, grounding every value against the PDF text layer and comparing every text run with the rendered pixels to find text that is in the file but invisible on the page. Twenty deterministic controls check the vendor master, verified bank account, duplicates, arithmetic, PO, receipts and terms. A Vultr reasoning model plans the response: email the vendor for a corrected invoice, ask the budget owner whether goods arrived, request approval, open a two-person bank-change review, hold, reject or pay. A policy guard written in code executes each action or refuses it, so the model can never pay a blocked invoice, change a bank account, or email an address printed on the document. The agent runs in a background worker: it follows up, reacts to vendor replies, re-reads corrected invoices and pays them with no one logged in. Every step is written to a hash-chained audit log.

Built on four Vultr services: Cloud Compute (Docker Compose with Caddy, Next.js, FastAPI and the agent worker), Serverless Inference (Qwen 3.8 27B vision, DeepSeek V4.1 Flash planning, Nemotron 3.5 content safety), Managed PostgreSQL and Object Storage. On the live deployment, a nine-invoice inbox of realistic exceptions is read, checked and decided in about 30 seconds for $0.03 of inference, with zero wrong payments.

**Tags:** Vultr, AI agents, Finance, Accounts Payable, Procurement, Fraud prevention, Prompt injection, FastAPI, Next.js, PostgreSQL

**Links:**
- Demo: https://45.32.218.92.sslip.io
- Repository: https://github.com/MYRADhub/tollgate
- Slides: export the deck as PDF

## Demo video script (about 4 minutes)

Record at 1600x1000 or larger, browser zoom 100%. Start with a reset demo (Invoices page, "Reset demo"). Keep the Agent activity feed visible.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Slide: cover | "Paying a vendor invoice is five checks: is the vendor real, is this the bank account on file, have we paid it already, does it match the purchase order, did the goods arrive. One invoice in five fails one, and that is where fraud gets through: about three billion dollars in the US last year. This is Tollgate, an AP agent that does those checks and works the exceptions, running entirely on Vultr." |
| 0:25 | App, Invoices, empty | "This is Halden Robotics' AP inbox. Here is this week's mail: nine invoices from six vendors." Click Demo inbox, Send all. |
| 0:35 | Activity feed scrolling | "Each one is read by a vision model on Vultr Serverless Inference, checked by twenty deterministic controls, and decided. That took about thirty seconds." |
| 0:55 | Queue | "Two are clean and already scheduled to pay, with nobody touching them. The Ostara motors are clean too, but over the ten-thousand-dollar limit, so they wait for the controller." |
| 1:10 | Open Brightline BIS-2090 | "This one is interesting. The findings show text the agent lifted from the PDF: instructions to the AI, telling it to pre-approve the invoice and change the bank account. Switch to the document: you cannot see it. It is white, one-and-a-half-point type. Tollgate compares every piece of text with the rendered pixels, so it found it, quarantined the invoice, and opened a bank-change review. The model could not have paid this even if it had been fooled: payments go through a policy guard in code." |
| 1:55 | Open Brightline BIS-2077 | "Here the vendor billed bearings thirteen percent above the PO. The agent emailed them the exact overcharge, a hundred and ten dollars plus tax, and asked for a corrected invoice." (With Gmail connected: show the email arriving on your phone, reply with BIS-2077-C.pdf attached. Without: click Play the vendor.) "The reply comes back with a corrected PDF. Tollgate reads it, re-runs every control, and pays the corrected amount." |
| 2:35 | Open Granite GE-5561 | "Granite billed for forty breakers; receiving logged twenty-five. The agent asked the budget owner and is holding. When the rest arrive" (click Log goods received) "it re-checks and pays." |
| 2:55 | Approvals, switch to Rosa Kim | "People only see judgment calls. As the AP clerk I cannot approve the thirty-three-thousand-dollar motors; as the controller I can. A bank change needs a recorded callback and two different approvers; the agent can open that review but never complete it." |
| 3:20 | Audit trail, Verify chain | "Every read, plan, refusal, email and approval is in a hash-chained log. Change one entry and verification fails." |
| 3:30 | Slide: business | "AP teams spend about ten dollars an invoice by hand. Tollgate would charge about a dollar, with inference under a cent on Vultr. The market for AP automation is three to five billion dollars and growing. The incumbents capture and route invoices; Tollgate resolves the exceptions, and it is built to be safe to put an AI in front of payments." |
| 3:55 | Slide: close | "Tollgate. Every invoice earns its payment. The demo is live and the code is on GitHub." |

## Before submitting

- Replace `[Your name]` and `[email]` on the cover and closing slides.
- Export the deck to PDF from the deck's Share > Export menu.
- Cover image: the queue screenshot (`deck-img/queue.png`) works at 16:10.
- Reset the demo after recording so judges start from an empty inbox.
