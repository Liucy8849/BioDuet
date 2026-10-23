import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
const root = path.resolve("public/data/demo-v1");
test("selection cap and Unicode filters retain state across navigation", async ({
  page,
}) => {
  await page.goto("/#/page=results&lang=en");
  for (const id of ["001", "002", "003", "004"])
    await page.getByLabel("Select run demo-" + id, { exact: true }).check();
  await page.getByLabel("Select run demo-005", { exact: true }).click();
  await expect(page.getByRole("status")).toContainText("up to 4");
  await expect(
    page.getByLabel("Select run demo-005", { exact: true }),
  ).not.toBeChecked();
  await page.getByRole("button", { name: "中文", exact: true }).click();
  await expect(
    page.getByLabel("选择运行 demo-004", { exact: true }),
  ).toBeChecked();
  await page.getByRole("searchbox").fill("标签");
  await expect(page.locator(".result-table tbody tr")).toHaveCount(4);
  await page.getByRole("link", { name: "对比 4", exact: true }).click();
  await page.goBack();
  await expect(page.getByRole("searchbox")).toHaveValue("标签");
});
test("untrusted message text is escaped and sparse event sequences navigate correctly", async ({
  page,
}) => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(root, "release.json"), "utf8"),
  );
  const detail = JSON.parse(
    fs.readFileSync(path.join(root, "runs/demo-001.json"), "utf8"),
  );
  detail.events[0].body = '<img src=x onerror="window.__unsafe=true">';
  detail.events.forEach(
    (e: { sequence: number }, i: number) => (e.sequence = (i + 1) * 10),
  );
  const body = JSON.stringify(detail);
  const f = manifest.files.find(
    (f: { path: string }) => f.path === "runs/demo-001.json",
  );
  f.bytes = Buffer.byteLength(body);
  f.sha256 = createHash("sha256").update(body).digest("hex");
  await page.route("**/release.json", (route) =>
    route.fulfill({ json: manifest }),
  );
  await page.route("**/runs/demo-001.json", (route) =>
    route.fulfill({ body, contentType: "application/json" }),
  );
  await page.goto("/#/page=runs&run=demo-001&lang=en");
  await expect(page.locator(".original-text")).toContainText("<img src=x");
  expect(await page.evaluate(() => "__unsafe" in window)).toBe(false);
  await expect(page.locator(".evidence-panel img")).toHaveCount(0);
  await page.getByRole("button", { name: "Event →", exact: true }).click();
  await expect(page.locator(".evidence-panel h3")).toHaveText(
    "Check source records",
  );
});
test("accessibility checks on all five views and mobile horizontal layout", async ({
  page,
}, testInfo) => {
  const results = [];
  for (const suffix of [
    "page=results",
    "page=tasks",
    "page=runs&run=demo-002",
    "page=compare&selected=demo-001,demo-002",
    "page=methods",
  ]) {
    await page.goto("about:blank");
    await page.goto("/#/" + suffix + "&lang=en");
    await expect(page.locator(".notice-strip").first()).toBeVisible();
    if (suffix.includes("run="))
      await expect(page.locator(".evidence-panel")).toBeVisible();
    const report = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    results.push({ page: suffix, violations: report.violations });
  }
  fs.writeFileSync(
    testInfo.outputPath("accessibility.json"),
    JSON.stringify(results, null, 2),
  );
  expect(
    results
      .flatMap((r) => r.violations)
      .map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => n.target),
      })),
  ).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const suffix of [
    "page=results",
    "page=tasks",
    "page=runs&run=demo-002",
    "page=compare&selected=demo-001,demo-002",
    "page=methods",
  ]) {
    await page.goto("about:blank");
    await page.goto("/#/" + suffix + "&lang=en");
    await expect(page.locator(".notice-strip").first()).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});


test("unknown deep links and mobile filter disclosure are explicit",async({page})=>{
 await page.goto('/#/page=runs&run=unknown&lang=en');await expect(page.getByRole('heading',{name:'This run is not part of the current release.'})).toBeVisible();
 await page.goto('about:blank');await page.goto('/#/page=runs&run=demo-001&event=absent&lang=en');await expect(page.locator('.evidence-panel')).toContainText('This event is not part of this run.');await page.locator('.evidence-panel').getByRole('button',{name:'Reset',exact:true}).click();await expect(page.locator('.evidence-panel h3')).toHaveText('Read public task and versions');
 await page.setViewportSize({width:390,height:844});await page.getByRole('link',{name:'Results',exact:true}).click();await expect(page.locator('.filters')).not.toBeVisible();await page.getByRole('button',{name:'Filters +',exact:true}).click();await expect(page.locator('.filters')).toBeVisible();await page.getByRole('combobox',{name:'Condition',exact:true}).selectOption('H1');await expect(page.locator('.result-table tbody tr')).toHaveCount(4);
});


test("skip link preserves the active run and focuses main content",async({page})=>{
 await page.goto('/#/page=runs&run=demo-002&lang=en');await expect(page.locator('.evidence-panel')).toBeVisible();const before=page.url();
 await page.getByRole('link',{name:'Skip to main content',exact:true}).focus();await page.keyboard.press('Enter');await expect(page.locator('#main')).toBeFocused();expect(page.url()).toBe(before);await expect(page.getByRole('heading',{name:'demo-002',exact:true})).toBeVisible();
});


test("released text and PNG artifacts render safely alongside tables",async({page})=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'release.json'),'utf8'));const d=JSON.parse(fs.readFileSync(path.join(root,'runs/demo-001.json'),'utf8'));const base=d.artifacts[0];
 const text='<script>window.__unsafe=true</script>\nSYNTHETIC TEST REPORT';const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
 const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
 d.artifacts.push({...base,id:'test-text',type:'text',columns:[],rows:[],text,sha256:hash(text)},{...base,id:'test-png',type:'image',columns:[],rows:[],imageData:png,sha256:hash(png)});
 const body=JSON.stringify(d);const f=manifest.files.find((f:{path:string})=>f.path==='runs/demo-001.json');f.bytes=Buffer.byteLength(body);f.sha256=hash(body);
 await page.route('**/release.json',route=>route.fulfill({json:manifest}));await page.route('**/runs/demo-001.json',route=>route.fulfill({body,contentType:'application/json'}));await page.goto('/#/page=runs&run=demo-001&tab=artifacts&lang=en');
 await expect(page.locator('.artifact')).toHaveCount(3);await expect(page.locator('.artifact-text')).toContainText('<script>');expect(await page.evaluate(()=>('__unsafe' in window))).toBe(false);await expect(page.locator('.artifact-image')).toBeVisible();await expect.poll(()=>page.locator('.artifact-image').evaluate((img:HTMLImageElement)=>img.naturalWidth)).toBe(1);
});
