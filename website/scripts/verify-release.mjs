import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import ts from "typescript";
// Transpile this standalone schema in memory: no application, backend or DB setup.
const schemaSource = await fs.readFile(
  new URL("../src/schema.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(schemaSource, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
  },
}).outputText;
const { createRequire } = await import("node:module");
const require = createRequire(import.meta.url);
const mod = { exports: {} };
new Function("require", "exports", "module", compiled)(
  require,
  mod.exports,
  mod,
);
const {
  manifestSchema,
  dataSchema,
  detailSchema,
  validateRelations,
  validateDetail,
} = mod.exports;
const target = process.argv
  .find((x) => x.startsWith("--directory="))
  ?.slice(12);
const root = target
  ? path.resolve(target)
  : fileURLToPath(new URL("../public/data/demo-v1/", import.meta.url));
const production = process.argv.includes("--production");
const read = async (p) =>
  JSON.parse(await fs.readFile(path.join(root, p), "utf8"));
try {
  const m = manifestSchema.parse(await read("release.json"));
  if (m.status === "withdrawn") throw Error("Withdrawn release");
  if (
    production &&
    (m.audience !== "public" ||
      m.status !== "approved" ||
      !m.review_ref ||
      m.translation_review !== "reviewed")
  )
    throw Error(
      "Production requires an approved public release and reviewed translations; this demo is not eligible.",
    );
  if (new Set(m.files.map((f) => f.path)).size !== m.files.length)
    throw Error("Duplicate file entries");
  const paths = [];
  async function walk(dir) {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) throw Error("Symlink forbidden");
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(p);
      else paths.push(path.relative(root, p).split(path.sep).join("/"));
    }
  }
  await walk(root);
  if (
    paths.sort().join("|") !==
    ["release.json", ...m.files.map((f) => f.path)].sort().join("|")
  )
    throw Error("File inventory mismatch");
  for (const f of m.files) {
    const bytes = await fs.readFile(path.join(root, f.path));
    if (
      bytes.length !== f.bytes ||
      createHash("sha256").update(bytes).digest("hex") !== f.sha256
    )
      throw Error("Checksum mismatch: " + f.path);
    if (
      /(?:-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY|sk-[A-Za-z0-9]{24,}|\/opt\/labweave\/private-custody|\/data1\/|[A-Z]:\\Users\\)/.test(
        bytes.toString(),
      )
    )
      throw Error("Potential private material detected: " + f.path);
  }
  const data = dataSchema.parse(await read("index.json"));
  validateRelations(data);
  if (data.release_id !== m.release_id)
    throw Error("Release identity mismatch");
  const expected = new Set([
    "index.json",
    ...data.runs.map((r) => r.detailFile),
  ]);
  if (
    m.files.length !== expected.size ||
    m.files.some((f) => !expected.has(f.path))
  )
    throw Error("Referenced file closure mismatch");
  for (const r of data.runs) {
    if (m.audience === "demo" && (r.stage !== "demo" || r.review !== "demo"))
      throw Error("Demo identity mismatch");
    const d = detailSchema.parse(await read(r.detailFile));
    validateDetail(d, r);
    for (const a of d.artifacts) {
      if (
        createHash("sha256").update(mod.exports.artifactPayload(a)).digest("hex") !==
        a.sha256
      )
        throw Error("Artifact payload hash mismatch");
    }
  }
  console.log(
    JSON.stringify(
      {
        verified: true,
        release: m.release_id,
        audience: m.audience,
        files: m.files.length,
        tasks: data.tasks.length,
        runs: data.runs.length,
        productionEligible:
          m.audience === "public" &&
          m.status === "approved" &&
          !!m.review_ref &&
          m.translation_review === "reviewed",
        scope:
          "Schema, exact inventory, checksums, references and basic secret signatures. Human content review is still required.",
      },
      null,
      2,
    ),
  );
} catch (e) {
  console.error(e.message);
  process.exitCode = 1;
}
