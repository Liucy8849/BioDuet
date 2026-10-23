import {
  manifestSchema,
  dataSchema,
  detailSchema,
  validateRelations,
  validateDetail,
  type Manifest,
  type Data,
  type Run,
  type Detail,
} from "./schema";
export async function digest(bytes: ArrayBuffer) {
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
  )
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}
async function get(url: string) {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error("missingFile");
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > 4 * 1024 * 1024) throw new Error("invalidData");
  return bytes;
}
function parse(bytes: ArrayBuffer) {
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error("invalidData");
  }
}
export async function loadRelease(
  base = "./data/" + (import.meta.env.VITE_BIODUET_RELEASE || "demo-v1") + "/",
): Promise<{
  manifest: Manifest;
  data: Data;
  loadDetail: (r: Run) => Promise<Detail>;
}> {
  if (!/^\.\/data\/[A-Za-z0-9._-]+\/$/.test(base))
    throw new Error("invalidData");
  const raw = parse(await get(base + "release.json"));
  if (raw.schema_version !== "benchmark-web/0.1")
    throw new Error("schemaError");
  const m = manifestSchema.safeParse(raw);
  if (!m.success) throw new Error("invalidData");
  const manifest = m.data;
  if (manifest.status === "withdrawn") throw new Error("withdrawn");
  if (
    manifest.audience === "public" &&
    (manifest.status !== "approved" ||
      !manifest.review_ref ||
      manifest.translation_review !== "reviewed")
  )
    throw new Error("unapproved");
  if (new Set(manifest.files.map((f) => f.path)).size !== manifest.files.length)
    throw new Error("invalidData");
  async function verified(path: string) {
    const f = manifest.files.find((f) => f.path === path);
    if (!f) throw new Error("missingFile");
    const bytes = await get(base + f.path);
    if (bytes.byteLength !== f.bytes || (await digest(bytes)) !== f.sha256)
      throw new Error("hashError");
    return parse(bytes);
  }
  const result = dataSchema.safeParse(await verified("index.json"));
  if (!result.success) throw new Error("invalidData");
  const data = result.data;
  if (data.release_id !== manifest.release_id) throw new Error("invalidData");
  validateRelations(data);
  const expected = new Set([
    "index.json",
    ...data.runs.map((r) => r.detailFile),
  ]);
  if (
    expected.size !== manifest.files.length ||
    manifest.files.some((f) => !expected.has(f.path))
  )
    throw new Error("invalidData");
  if (
    manifest.audience === "demo" &&
    data.runs.some((r) => r.stage !== "demo" || r.review !== "demo")
  )
    throw new Error("invalidData");
  const cache = new Map<string, Detail>();
  return {
    manifest,
    data,
    loadDetail: async (r) => {
      if (cache.has(r.id)) return cache.get(r.id)!;
      const parsed = detailSchema.safeParse(await verified(r.detailFile));
      if (!parsed.success) throw new Error("invalidData");
      validateDetail(parsed.data, r);
      cache.set(r.id, parsed.data);
      return parsed.data;
    },
  };
}
export function csv(rows: (string | number | null)[][]) {
  return (
    "\uFEFF" +
    rows
      .map((row) =>
        row
          .map((v) => {
            let s = v === null ? "" : String(v);
            if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
            return '"' + s.replaceAll('"', '""') + '"';
          })
          .join(","),
      )
      .join("\r\n")
  );
}
export function comparisonIssues(runs: Run[]): string[] {
  const issues = new Set<string>();
  if (runs.length < 2) issues.add("chooseTwo");
  if (
    runs.some(
      (r) =>
        r.stage !== "development_pilot" ||
        r.review !== "independently_reviewed" ||
        r.scientific !== "passed",
    )
  )
    issues.add("notFormal");
  if (
    runs.some((r) => !r.pairId) ||
    new Set(runs.map((r) => r.pairId)).size > 1
  )
    issues.add("pairMismatch");
  for (const key of [
    "task",
    "instance",
    "oracle",
    "human",
    "protocol",
    "budget",
    "dataset",
  ] as const)
    if (new Set(runs.map((r) => r.versions[key])).size > 1)
      issues.add("versionMismatch");
  if (
    new Set(runs.map((r) => r.taskId)).size > 1 ||
    new Set(runs.map((r) => r.mode)).size > 1 ||
    new Set(runs.map((r) => r.repetition)).size > 1
  )
    issues.add("instanceMismatch");
  return [...issues];
}
