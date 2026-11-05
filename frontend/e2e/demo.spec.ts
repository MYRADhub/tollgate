import { APIRequestContext, Page, expect, test } from "@playwright/test";

const API = process.env.E2E_BASE_URL || `http://127.0.0.1:${process.env.E2E_API_PORT || 8100}`;
const WEB = process.env.E2E_BASE_URL || `http://localhost:${process.env.E2E_WEB_PORT || 3200}`;

async function settle(request: APIRequestContext) {
  for (let i = 0; i < 180; i++) {
    const s = await (await request.get(`${API}/api/stats`)).json();
    if (s.queue === 0) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("agent did not settle");
}

async function invoiceId(request: APIRequestContext, number: string) {
  const rows = await (await request.get(`${API}/api/invoices`)).json();
  const r = rows.find((x: { number: string }) => x.number === number);
  if (!r) throw new Error(`no invoice ${number}`);
  return r.id as string;
}

async function actAs(page: Page, name: string) {
  await page.getByRole("button", { name: new RegExp(`^${name}`) }).first().click();
}

test.describe.serial("guided demo, end to end", () => {
  test.beforeAll(async ({ request }) => {
    await request.post(`${API}/api/demo/reset`);
  });

  test("dashboard starts empty and the guided demo loads the inbox", async ({ page, request }) => {
    await page.goto("/");
    await expect(page.getByText("Guided demo: nine things to try").first()).toBeVisible();
    await expect(page.getByText("No invoices yet").first()).toBeVisible();
    await page.getByRole("button", { name: "Load the demo inbox" }).click();
    await expect(page.getByText("Twelve invoices are in the AP inbox").first()).toBeVisible();
    await settle(request);
    await expect(page.getByRole("link", { name: /Polaris Network Services/ }).first()).toBeVisible();
    await expect(page.getByText("1 of 9 done").first()).toBeVisible();
    await expect(page.getByText("Agent activity").first()).toBeVisible();
  });

  test("contract recovery: the SLA credit is deducted with the clause and checked by the critic", async ({ page, request }) => {
    await page.goto(`/invoices/${await invoiceId(request, "PNS-55120")}`);
    await expect(page.getByText("Service credit owed for 2026-10").first()).toBeVisible();
    await expect(page.getByText("$975.00 owed to us").first()).toBeVisible();
    await expect(page.getByText(/falls below 99.5%, 15%/).first()).toBeVisible();
    await expect(page.getByText("Second opinion from the critic").first()).toBeVisible();
    await expect(page.getByText("Owed to us under contract").first()).toBeVisible();
    await expect(page.getByText(/Remittance advice: invoice PNS-55120/).first()).toBeVisible();
  });

  test("hidden instructions are lifted out of the PDF and quarantined", async ({ page, request }) => {
    await page.goto(`/invoices/${await invoiceId(request, "BIS-2090")}`);
    await expect(page.getByText("Document contains instructions aimed at an AI").first()).toBeVisible();
    await expect(page.getByText(/ignore all previous instructions/).first()).toBeVisible();
    await page.getByRole("button", { name: "What the agent read" }).click();
    await expect(page.getByText("Text in the file that no person can see on the page").first()).toBeVisible();
    await expect(page.getByText("Held").first()).toBeVisible();
    await expect(page.getByText("Not made the way Brightline Industrial Supply's invoices are made").first()).toBeVisible();
    await expect(page.getByText(/Microsoft: Print To PDF/).first()).toBeVisible();
  });

  test("the vendor page shows each fingerprint model and how it was tested", async ({ page }) => {
    await page.goto("/vendors");
    await expect(page.getByText("Document fingerprints: Tollgate's own model").first()).toBeVisible();
    await expect(page.getByText("Sage Intacct Reporting Services").first()).toBeVisible();
    await expect(page.getByText("16 of 16").first()).toBeVisible();
  });

  test("a clerk cannot approve the controller's payment; the controller can", async ({ page, request }) => {
    await page.goto(`/invoices/${await invoiceId(request, "OC-7720")}`);
    await actAs(page, "Sam Patel");
    await expect(page.getByText("Waiting for you").first()).toBeVisible();
    await expect(page.getByText("Volume price owed").first()).toBeVisible();
    await page.getByRole("button", { name: /Act as Rosa Kim \(Controller\)/ }).click();
    await page.getByRole("button", { name: "Approve as Rosa Kim" }).click();
    await expect(page.getByText("Payment approved").first()).toBeVisible();
    await settle(request);
    await expect(page.getByText("Payment scheduled").first()).toBeVisible();
    await expect(page.getByText("-$1,416.00").first()).toBeVisible();
  });

  test("playing the vendor: a corrected invoice is re-read, re-checked and paid", async ({ page, request }) => {
    await page.goto(`/invoices/${await invoiceId(request, "BIS-2077")}`);
    await expect(page.getByText("Line 1 billed above the PO price").first()).toBeVisible();
    await page.getByRole("button", { name: "Play the vendor: reply" }).click();
    await expect(page.getByText("The vendor replied").first()).toBeVisible();
    await settle(request);
    await page.getByRole("link", { name: /Replaced by the vendor.s corrected invoice/ }).click();
    await expect(page.getByText("Payment scheduled").first()).toBeVisible();
    await expect(page.getByText(/removing the 118.80 overcharge/).first()).toBeVisible();
  });

  test("the agent clears exceptions by asking colleagues, and the briefing says so", async ({ page, request }) => {
    const id = await invoiceId(request, "GE-5570");
    await expect.poll(async () => (await (await request.get(`${API}/api/invoices/${id}`)).json()).status, { timeout: 60_000 }).toBe("scheduled");
    await page.goto("/");
    await expect(page.getByText("While you were away").first()).toBeVisible();
    await expect(page.getByText(/Exceptions cleared \(\d+\)/).first()).toBeVisible();
    await expect(page.getByText("Verify a bank account change").first()).toBeVisible();
    await page.goto(`/invoices/${id}`);
    await expect(page.getByText("The agent asked colleagues").first()).toBeVisible();
    await expect(page.getByText(/Searched Granite Electrical Co\.'s open POs/).first()).toBeVisible();
    await expect(page.getByText(/Attached PO-24111 to GE-5570/).first()).toBeVisible();
  });

  test("fast-forward a day: the backorder arrives and the held invoice pays, net of the price cap", async ({ page, request }) => {
    const id = await invoiceId(request, "GE-5561");
    await expect.poll(async () => (await (await request.get(`${API}/api/invoices/${id}`)).json()).agent_state.waiting_for, { timeout: 60_000 }).toBe("receipt");
    await page.goto(`/invoices/${id}`);
    await expect(page.getByText("Waiting for goods").first()).toBeVisible();
    await page.getByRole("button", { name: "Fast-forward a day" }).click();
    await expect(page.getByText(/It is now/).first()).toBeVisible();
    await expect.poll(async () => (await (await request.get(`${API}/api/invoices/${id}`)).json()).status, { timeout: 60_000 }).toBe("scheduled");
    await page.reload();
    await expect(page.getByText("Payment scheduled").first()).toBeVisible();
    await expect(page.getByText("-$43.20").first()).toBeVisible();
    await expect(page.getByText(/Receiving dock logged receipt/).first()).toBeVisible();
  });

  test("a bank change needs a callback and two different people", async ({ page, request }) => {
    await page.goto("/approvals");
    await actAs(page, "Rosa Kim");
    const card = page.locator("li", { hasText: "Bank change for Vantage Cloud Services" });
    await expect(card).toBeVisible();
    await expect(card.getByRole("button", { name: "Record callback and approve" })).toBeDisabled();
    await card.getByPlaceholder(/Callback record/).fill("Called 415-555-0100 from the vendor master; CFO Ana Ruiz confirmed the change");
    await card.getByRole("button", { name: "Record callback and approve" }).click();
    await expect(page.getByText("First approval recorded").first()).toBeVisible();
    await expect(card.getByText("A different person must approve this.")).toBeVisible();
    await card.getByRole("button", { name: /Act as Theo Grant/ }).click();
    await card.getByRole("button", { name: "Give second approval" }).click();
    await expect(page.getByText("Bank change approved").first()).toBeVisible();
    await settle(request);
    await page.goto(`/invoices/${await invoiceId(request, "VCS-10488")}`);
    await expect(page.getByText("Payment scheduled").first()).toBeVisible();
  });

  test("the payment run takes the best discount and the controller releases it", async ({ page, request }) => {
    await page.goto("/payments");
    await actAs(page, "Sam Patel");
    await page.getByRole("button", { name: "Plan a run now" }).click();
    const planned = page.getByText(/^Run \d+ planned$/);
    await expect(planned).toBeVisible();
    const runId = (await planned.textContent())!.match(/\d+/)![0];
    await expect(page.getByText(`Payment run ${runId}`, { exact: false }).first()).toBeVisible();
    await expect(page.getByText(/worth 149% a year/).first()).toBeVisible();
    await page.getByRole("button", { name: /Act as Rosa Kim \(Controller\) to approve/ }).click();
    await page.getByRole("button", { name: /Approve run as Rosa Kim/ }).click();
    await expect(page.getByText(/approved by Rosa Kim/).first()).toBeVisible();
    const file = page.getByRole("link", { name: /Bank file/ });
    await expect(file).toBeVisible();
    const res = await request.get(new URL((await file.getAttribute("href"))!, WEB).toString());
    expect(await res.text()).toContain("TG-RUN-");
    await settle(request);
  });

  test("contracts show each term with its clause highlighted", async ({ page }) => {
    await page.goto("/contracts");
    const polaris = page.locator("section", { hasText: "Managed WAN Services Agreement" });
    await expect(polaris.getByText("Service credit", { exact: true })).toBeVisible();
    await expect(polaris.getByText(/99.31%/)).toBeVisible();
    await polaris.getByRole("button", { name: "Show contract" }).click();
    await expect(polaris.locator("mark").first()).toContainText("If Monthly Availability");
  });

  test("the attack lab catches a lookalike vendor and stays out of the real queue", async ({ page, request }) => {
    await page.goto("/lab");
    const before = (await (await request.get(`${API}/api/invoices`)).json()).length;
    await page.locator("div", { hasText: /^Lookalike vendor/ }).getByRole("button", { name: "Launch" }).first().click();
    await expect(page.getByText(/Lookalike vendor: sent/).first()).toBeVisible();
    await settle(request);
    await page.reload();
    await expect(page.locator("li", { hasText: "Lookalike vendor" }).getByText("caught", { exact: true })).toBeVisible();
    expect((await (await request.get(`${API}/api/invoices`)).json()).length).toBe(before);
  });

  test("statements: every cent explained, a forged invoice exposed, a credit claimed", async ({ page, request }) => {
    await page.goto("/statements");
    await actAs(page, "Sam Patel");
    await page.getByRole("button", { name: "Load demo statements" }).click();
    await expect(page.getByText("Two vendor statements arrived").first()).toBeVisible();
    await settle(request);
    await page.reload();
    await expect(page.getByText("Every cent of the difference is explained below.")).toHaveCount(2);
    const bis2090 = page.locator("li", { hasText: "BIS-2090" });
    await expect(bis2090.getByText("Not on their statement")).toBeVisible();
    await expect(page.locator("li", { hasText: "KFL-88812" }).getByText("Paid; they did not apply it").first()).toBeVisible();
    const credit = page.locator("li", { hasText: "CM-4471" });
    await credit.getByRole("button", { name: /Act as Rosa Kim \(Controller\) to claim/ }).click();
    await credit.getByRole("button", { name: "Claim as Rosa Kim" }).click();
    await expect(page.getByText("Credit CM-4471 claimed").first()).toBeVisible();
    await expect(credit.getByText(/will come off their next invoice/)).toBeVisible();
  });

  test("vendor questions: the ledger answers its own vendor, a lookalike gets nothing", async ({ page, request }) => {
    await page.goto("/inquiries");
    await page.getByRole("button", { name: "Why were we short-paid?" }).click();
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Question sent to the AP inbox").first()).toBeVisible();
    await settle(request);
    const first = page.locator("li", { hasText: "Short payment on PNS-55120" });
    await expect(first.getByText("Registered address", { exact: true })).toBeVisible();
    await expect(first.getByText(/975\.00/).first()).toBeVisible();
    await page.getByRole("button", { name: "Impersonates a vendor" }).click();
    await page.getByRole("button", { name: "Send" }).click();
    await settle(request);
    const spoof = page.locator("li", { hasText: "Account statement request" });
    await expect(spoof.getByText("Lookalike domain", { exact: true })).toBeVisible();
    await expect(spoof.getByText(/could not match this address/)).toBeVisible();
    await expect(spoof.getByText("Impersonation attempt")).toBeVisible();
  });

  test("the fingerprint learns a vendor's new billing system once a controller confirms it", async ({ page, request }) => {
    await page.goto("/vendors");
    await page.getByRole("button", { name: "1. Polaris sends its first Zuora invoice" }).click();
    await page.getByRole("link", { name: /open it, then clear the finding/ }).click();
    await settle(request);
    await page.reload();
    await expect(page.getByText("Not made the way Polaris Network Services's invoices are made").first()).toBeVisible();
    await actAs(page, "Rosa Kim");
    const finding = page.locator("li", { hasText: "Not made the way Polaris" }).first();
    await finding.getByRole("button", { name: "Override with a justification" }).click();
    await finding.getByPlaceholder("Why is this OK to clear?").fill("Called Polaris on the number on file: they moved to Zuora");
    await finding.getByRole("button", { name: /^Clear as/ }).click();
    await expect(page.getByText(/learned this layout/).first()).toBeVisible();
    await page.goto("/vendors");
    await expect(page.getByText(/Zuora Invoice Renderer 7, confirmed by Rosa Kim/).first()).toBeVisible();
    await page.getByRole("button", { name: "2. Polaris sends the next one" }).click();
    await page.getByRole("link", { name: "open it" }).click();
    await settle(request);
    await page.reload();
    await expect(page.getByText(/Matches a second layout Polaris Network Services uses/).first()).toBeVisible();
  });

  test("the audit chain verifies and the guided demo is complete", async ({ page, request }) => {
    // "seen" steps live in this browser's storage; each test starts with a fresh one
    for (const n of ["PNS-55120", "BIS-2090", "GE-5570"]) {
      await page.goto(`/invoices/${await invoiceId(request, n)}`);
      await expect(page.getByText(n).first()).toBeVisible();
    }
    await page.goto("/audit");
    await page.getByRole("button", { name: "Verify chain" }).click();
    await expect(page.getByText(/events verified/).first()).toBeVisible();
    await page.goto("/");
    await expect(page.getByText("All done. Reset the demo to start again.").first()).toBeVisible();
  });

  test("rejecting a payment asks for a reason in a dialog", async ({ page, request }) => {
    await request.post(`${API}/api/demo/reset`);
    await request.post(`${API}/api/demo/inbox`, { data: [3] });
    await settle(request);
    await page.goto("/approvals");
    await actAs(page, "Rosa Kim");
    const card = page.locator("li", { hasText: "Pay Ostara Components GmbH" });
    await card.getByRole("button", { name: "Reject" }).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByText("Reject this payment?")).toBeVisible();
    await expect(dlg.getByRole("button", { name: "Reject payment" })).toBeDisabled();
    await dlg.getByPlaceholder("Reason").fill("Order was cancelled");
    await dlg.getByRole("button", { name: "Reject payment" }).click();
    await expect(page.getByText("Payment rejected").first()).toBeVisible();
    await expect(page.getByText("Recently decided").first()).toBeVisible();
  });

  test("uploading a PDF puts it through the pipeline", async ({ page, request }) => {
    const pdf = await (await request.get(`${API}/api/demo/inbox/0/file`)).body();
    await page.goto("/");
    await page.locator('input[type="file"]').setInputFiles({ name: "lumen.pdf", mimeType: "application/pdf", buffer: pdf });
    await expect(page.getByText("1 invoice received").first()).toBeVisible();
    await settle(request);
    await page.reload();
    await expect(page.getByRole("link", { name: /Lumen Office Supply/ }).first()).toBeVisible();
  });
});

test.describe("show me", () => {
  test("plays the whole story by itself from an empty demo", async ({ page, request }) => {
    test.setTimeout(300_000);
    await request.post(`${API}/api/demo/reset`);
    await page.goto("/");
    await page.getByRole("button", { name: "Show me in 2 minutes" }).click();
    const story = page.getByTestId("story");
    await expect(story.getByText("Twelve invoices arrive in the AP inbox")).toBeVisible();
    await expect(story.getByText("Cleared without anyone in AP")).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText("The agent asked colleagues").first()).toBeVisible();
    await expect(story.getByText("The delivery arrived; it paid")).toBeVisible({ timeout: 120_000 });
    await expect(story.getByText("A forgery, caught four ways")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("Not made the way Brightline Industrial Supply's invoices are made").first()).toBeVisible();
    await expect(story.getByText("What is left for people")).toBeVisible({ timeout: 60_000 });
    await expect(story.getByText("That is Tollgate")).toBeVisible({ timeout: 60_000 });
  });
});

test.describe("mobile @mobile", () => {
  test("@mobile the queue renders as cards and invoices open", async ({ page, request }) => {
    await request.post(`${API}/api/demo/reset`);
    await request.post(`${API}/api/demo/inbox`, { data: [2] });
    await settle(request);
    await page.goto("/");
    await expect(page.getByRole("navigation").getByRole("link", { name: "Approvals" })).toBeVisible();
    await page.getByRole("link", { name: /Polaris Network Services/ }).last().click();
    await expect(page.getByText("Service credit owed for 2026-10").first()).toBeVisible();
  });
});
