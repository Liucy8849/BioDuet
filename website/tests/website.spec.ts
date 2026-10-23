import { test, expect } from "@playwright/test";
import { csv, comparisonIssues } from "../src/data";
import {
  dataSchema,
  detailSchema,
  validateRelations,
  validateDetail,
} from "../src/schema";
import fs from "node:fs";
import path from "node:path";
const root = path.resolve("public/data/demo-v1");
const data = dataSchema.parse(
  JSON.parse(fs.readFileSync(path.join(root, "index.json"), "utf8")),
);
const qa = path.resolve("../../.local/qa/benchmark-website");
test("contracts: duplicates, broken references, causality and CSV injection are rejected", () => {
  validateRelations(data);
  expect(() =>
    validateRelations({ ...data, tasks: [...data.tasks, data.tasks[0]!] }),
  ).toThrow();
  expect(() =>
    validateRelations({
      ...data,
      runs: [{ ...data.runs[0]!, taskId: "missing" }],
    }),
  ).toThrow();
  const r = data.runs[0]!,
    d = detailSchema.parse(
      JSON.parse(fs.readFileSync(path.join(root, r.detailFile), "utf8")),
    );
  validateDetail(d, r);
  const bad = structuredClone(d);
  bad.events[0]!.parents = ["e08"];
  expect(() => validateDetail(bad, r)).toThrow();
  expect(csv([["=1+1", " @SUM(A1)", 'a"b', null]])).toContain("'=1+1");
  expect(csv([["=1+1", " @SUM(A1)", 'a"b', null]])).toContain("' @SUM");
  expect(comparisonIssues(data.runs.slice(0, 2))).toContain("notFormal");
  expect(comparisonIssues(data.runs.slice(0, 2))).toContain("pairMismatch");
});
test("results, filters, language persistence and CSV export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#/page=results&lang=zh-CN");
  await expect(
    page.getByRole("heading", { level: 1, name: "结果", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("界面演示 · 非实验结果", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "条件", exact: true })
    .selectOption("H1");
  await expect(page.locator(".result-table tbody tr")).toHaveCount(4);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(
    page.getByRole("combobox", { name: "Condition", exact: true }),
  ).toHaveValue("H1");
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Condition", exact: true }),
  ).toHaveValue("H1");
  await page.locator(".export-menu summary").click();
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const download = await dl;
  await download.saveAs(path.join(qa, "filtered-runs.csv"));
  const content = fs.readFileSync(path.join(qa, "filtered-runs.csv"), "utf8");
  expect(content).toContain('"demo-002"');
  expect(content).not.toContain('"demo-001"');
  expect(errors).toEqual([]);
});
test("matrix keyboard drawer, cross-system matching and task directory", async ({
  page,
}) => {
  await page.goto("/#/page=results&lang=zh-CN&view=matrix");
  const cell = page.getByRole("button", {
    name: "demo-001 H0 通过",
    exact: true,
  });
  await cell.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(cell).toBeFocused();
  await page.screenshot({path:path.join(qa,"matrix-1440.png"),fullPage:true});
  expect(await page.locator(".matrix-cell.highlighted").count()).toBe(2);
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await expect(page.locator(".task-card")).toHaveCount(24);
  await page.screenshot({path:path.join(qa,"tasks-1440.png"),fullPage:true});
  await page.getByRole("button", { name: "多组学 4", exact: true }).click();
  await expect(page.locator(".task-card")).toHaveCount(4);
  await page.locator(".task-card").first().click();
  await expect(page.getByRole("dialog")).toContainText("ATAC 迟到");
});
test("run deep link, version evidence, judgment and artifact download", async ({
  page,
}) => {
  await page.goto(
    "/#/page=runs&run=demo-002&tab=timeline&event=e05&lang=zh-CN",
  );
  await expect(page.locator(".evidence-panel h3")).toHaveText("更新分析设计");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.locator(".evidence-panel h3")).toHaveText(
    "Update analysis design",
  );
  expect(page.url()).toContain("event=e05");
  await page
    .getByRole("button", { name: "Object versions", exact: true })
    .click();
  await expect(page.locator(".panel")).toContainText("sample-labels");
  await page
    .getByRole("button", { name: "Judgment & attribution", exact: true })
    .click();
  await expect(page.locator(".prose")).toContainText(
    "No scientific conclusion",
  );
  await page
    .getByRole("button", { name: "Analysis & artifacts", exact: true })
    .click();
  const dl = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download released record", exact: true })
    .click();
  expect((await dl).suggestedFilename()).toBe("artifact-demo-002.json");
  await page
    .getByRole("button", { name: "Provenance & review", exact: true })
    .click();
  await expect(page.locator(".definition-list")).toContainText(
    "fictional-ui-fixture",
  );
});
test("selection limit, comparison, artifact differences and back navigation", async ({
  page,
}) => {
  await page.goto("/#/page=results&lang=en");
  await page.getByLabel("Select run demo-001", { exact: true }).check();
  await page.getByLabel("Select run demo-002", { exact: true }).check();
  await page.getByRole("button", { name: "Compare →", exact: true }).click();
  await expect(page.locator(".comparison-notice")).toContainText("Descriptive");
  await expect(page.locator(".comparison-table thead th")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Artifact comparison", exact: true })
    .click();
  await expect(page.locator(".artifact")).toHaveCount(2);
  await page.getByLabel("Differing rows", { exact: true }).check();
  await expect(page.locator(".artifact tbody tr")).toHaveCount(2);
  await page.screenshot({path:path.join(qa,"artifacts-en-1440.png"),fullPage:true});
  await page
    .getByRole("button", { name: "Side-by-side timelines", exact: true })
    .click();
  await expect(page.locator(".mini-timeline")).toHaveCount(2);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await page.reload();
  await expect(page.locator(".mini-timeline")).toHaveCount(2);
  await page.getByRole("link", { name: "Results", exact: true }).click();
  await expect(
    page.getByLabel("Select run demo-001", { exact: true }),
  ).toBeChecked();
});
test("formal empty state, no-results recovery, mobile layouts and screenshots", async ({
  page,
}) => {
  await page.goto("/#/page=results&lang=zh-CN");
  await page.screenshot({
    path: path.join(qa, "results-1440.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "正式结果", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "正式结果尚未发布" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "开发运行", exact: true }).click();
  await page.getByRole("searchbox").fill("no-match-xyz");
  await expect(
    page.getByRole("heading", { name: "没有匹配的记录" }),
  ).toBeVisible();
  await page.locator(".empty button").click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(qa, "results-390.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.goto("/#/page=runs&run=demo-002&lang=zh-CN");
  await expect(page.locator(".evidence-panel")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.join(qa, "timeline-390.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: path.join(qa, "timeline-1280.png"),
    fullPage: true,
  });
  await page.goto("/#/page=methods&lang=en");
  await expect(page.locator(".method-section")).toHaveCount(7);
  await page.screenshot({
    path: path.join(qa, "methods-en-1280.png"),
    fullPage: true,
  });
});
test("tampering, unsupported schema, withdrawn and absent files fail closed", async ({
  page,
}) => {
  await page.route("**/data/demo-v1/index.json", (route) =>
    route.fulfill({ status: 200, body: "{}" }),
  );
  await page.goto("/#/lang=en");
  await expect(page.getByRole("alert")).toContainText("checksum");
  await page.unrouteAll();
  const manifest = JSON.parse(
    fs.readFileSync(path.join(root, "release.json"), "utf8"),
  );
  await page.route("**/release.json", (route) =>
    route.fulfill({ json: { ...manifest, schema_version: "future/9" } }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("not supported");
  await page.unrouteAll();
  await page.route("**/release.json", (route) =>
    route.fulfill({ json: { ...manifest, status: "withdrawn" } }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("withdrawn");
  await page.unrouteAll();
  await page.route("**/index.json", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("missing");
});
