import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  fullyParallel: false,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:4174",
    browserName: "chromium",
    ...(process.env.BIODUET_BROWSER_EXECUTABLE ? { launchOptions: { executablePath: process.env.BIODUET_BROWSER_EXECUTABLE } } : {}),
    locale: "zh-CN",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  outputDir: "./test-results",
  reporter: [
    ["list"],
    ["json", { outputFile: "./test-results/results.json" }],
  ],
  webServer: {
    command: "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4174 --strictPort",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
