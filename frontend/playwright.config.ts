import { defineConfig, devices } from "@playwright/test";

const API = Number(process.env.E2E_API_PORT || 8100);
const WEB = Number(process.env.E2E_WEB_PORT || 3200);
// E2E_BASE_URL points the suite at a running deployment (API on the same origin) instead of local servers.
const REMOTE = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: REMOTE || `http://localhost:${WEB}`, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, grepInvert: /@mobile/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: REMOTE ? undefined : [
    { command: "./e2e/start-backend.sh", url: `http://127.0.0.1:${API}/api/health`, reuseExistingServer: !process.env.CI, timeout: 120_000, env: { E2E_API_PORT: String(API) } },
    {
      command: `npx next dev --port ${WEB}`,
      url: `http://localhost:${WEB}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { BACKEND_URL: `http://127.0.0.1:${API}` },
    },
  ],
});
