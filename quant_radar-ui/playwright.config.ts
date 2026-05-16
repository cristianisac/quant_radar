import { defineConfig, devices } from "@playwright/test";

// The visual E2E expects the app to already be reachable at
// http://127.0.0.1:8000 (scripts/visual_e2e.sh boots a Docker
// container before invoking `playwright test`). We don't use
// playwright's webServer hook because the launcher needs to manage
// Docker lifecycle, which the script does more cleanly.
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,            // tests touch shared dashboard state
  workers: 1,
  forbidOnly: true,
  retries: 0,
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
    viewport: { width: 1600, height: 1000 },
    screenshot: "off",             // we screenshot explicitly per test
    trace: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
