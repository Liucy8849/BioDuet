import { z } from "zod";
export const textSchema = z
  .object({ "zh-CN": z.string().min(1), en: z.string().min(1) })
  .strict();
const id = z.string().regex(/^[A-Za-z0-9._-]{1,100}$/);
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const states = [
  "passed",
  "failed",
  "not_assessed",
  "not_reported",
  "not_run",
  "restricted",
  "uncertain",
] as const;
const status = z.enum(states);
const metric = z.number().nonnegative().nullable();
export const taskSchema = z
  .object({
    id,
    category: z.enum([
      "identity",
      "qc",
      "multiomics",
      "statistics",
      "async",
      "governance",
    ]),
    title: textSchema,
    question: textSchema,
    human: textSchema,
    agent: textSchema,
    h0: textSchema,
    h1: textSchema,
    version: z.string(),
    maturity: z.literal("design_only"),
  })
  .strict();
const versionSchema = z
  .object({
    task: z.string(),
    instance: z.string(),
    oracle: z.string(),
    human: z.string(),
    protocol: z.string(),
    budget: z.string(),
    dataset: z.string(),
  })
  .strict();
export const runSchema = z
  .object({
    id,
    taskId: id,
    system: id,
    condition: z.enum(["H0", "H1"]),
    stage: z.enum(["demo", "development_pilot", "engineering_regression"]),
    mode: z.enum(["interactive_simulation", "simulated_replay", "human_study"]),
    sourceMode: z.string(),
    timing: z.enum(["logical_time", "wall_clock"]),
    versions: versionSchema,
    pairId: id.nullable(),
    repetition: z.number().int().nonnegative(),
    technical: status,
    scientific: status,
    authorization: status,
    strict: status,
    termination: z.enum([
      "completed",
      "budget_exhausted",
      "provider_error",
      "aborted",
      "not_reported",
    ]),
    hFaults: metric,
    aFaults: metric,
    calls: metric,
    tokens: metric,
    seconds: metric,
    cost: metric,
    review: z.enum(["demo", "author_checked", "independently_reviewed"]),
    detailFile: z.string().regex(/^runs\/[A-Za-z0-9._-]+\.json$/),
  })
  .strict();
export const eventSchema = z
  .object({
    id,
    sequence: z.number().int().positive(),
    tick: z.number().int().nonnegative().nullable(),
    actor: z.enum(["H", "A", "world", "worker", "oracle"]),
    kind: z.enum([
      "message",
      "action",
      "receipt",
      "revision",
      "judgment",
      "redacted",
    ]),
    title: textSchema,
    body: z.string(),
    source: z.enum([
      "synthetic_demo",
      "model_message",
      "computation",
      "human_receipt",
      "simulated_event",
    ]),
    parents: z.array(id),
    object: id.nullable(),
    before: z.string().nullable(),
    after: z.string().nullable(),
    decision: status,
    visibility: z.enum(["public", "restricted"]),
  })
  .strict();
export const artifactSchema = z
  .object({
    id,
    title: textSchema,
    type: z.enum(["table", "text", "image"]),
    status: z.enum(["candidate", "restricted", "superseded"]),
    method: z.string(),
    unit: z.string(),
    inputVersion: z.string(),
    sha256: hash,
    eventId: id,
    columns: z.array(z.string()),
    rows: z.array(z.array(z.string())),
    text: z.string().max(200000).optional(),
    imageData: z.string().max(2000000).regex(/^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/).optional(),
  })
  .strict()
  .superRefine((a, context) => {
    if ((a.type === 'text' && (a.text === undefined || a.imageData !== undefined)) ||
        (a.type === 'image' && (!a.imageData || a.text !== undefined)) ||
        (a.type === 'table' && (a.text !== undefined || a.imageData !== undefined)) ||
        (a.type !== 'table' && (a.rows.length !== 0 || a.columns.length !== 0))) {
      context.addIssue({code: z.ZodIssueCode.custom, message: 'Artifact payload does not match its declared type'});
    }
  });
export const detailSchema = z
  .object({
    runId: id,
    events: z.array(eventSchema),
    artifacts: z.array(artifactSchema),
    judgment: z
      .object({
        ruleId: id,
        status,
        explanation: textSchema,
        evidenceRefs: z.array(id),
        output: z.string(),
      })
      .strict(),
    sourceCommit: z
      .string()
      .regex(/^[a-f0-9]{40}$/)
      .nullable(),
    sourceSet: z.string(),
    coverage: textSchema,
    originalLocale: z.literal("en"),
  })
  .strict();
export const dataSchema = z
  .object({
    schema_version: z.literal("benchmark-web/0.1"),
    release_id: id,
    tasks: z.array(taskSchema),
    systems: z.array(
      z
        .object({
          id,
          name: z.string(),
          model: z.string(),
          harness: z.string(),
        })
        .strict(),
    ),
    runs: z.array(runSchema),
    methods: z.array(
      z.object({ id, title: textSchema, body: textSchema }).strict(),
    ),
  })
  .strict();
export const manifestSchema = z
  .object({
    schema_version: z.literal("benchmark-web/0.1"),
    release_id: id,
    created_at: z.string().datetime(),
    audience: z.enum(["demo", "public"]),
    status: z.enum(["demo", "approved", "withdrawn"]),
    review_ref: z.string().nullable(),
    translation_review: z.enum(["draft", "reviewed"]),
    files: z.array(
      z
        .object({
          path: z.string().regex(/^(index|runs\/[A-Za-z0-9._-]+)\.json$/),
          sha256: hash,
          bytes: z.number().int().positive(),
        })
        .strict(),
    ),
    supersedes: id.nullable(),
  })
  .strict();
export type Locale = "zh-CN" | "en";
export type Text = z.infer<typeof textSchema>;
export type Task = z.infer<typeof taskSchema>;
export type Run = z.infer<typeof runSchema>;
export type Detail = z.infer<typeof detailSchema>;
export type Artifact = z.infer<typeof artifactSchema>;
export const artifactPayload = (a: Artifact) => a.type === 'table' ? JSON.stringify(a.rows) : a.type === 'text' ? a.text! : a.imageData!;
export type Data = z.infer<typeof dataSchema>;
export type Manifest = z.infer<typeof manifestSchema>;

export function validateRelations(data: Data) {
  for (const group of [data.tasks, data.systems, data.runs])
    if (new Set(group.map((x) => x.id)).size !== group.length)
      throw new Error("invalidData");
  for (const r of data.runs)
    if (
      !data.tasks.some((t) => t.id === r.taskId) ||
      !data.systems.some((s) => s.id === r.system)
    )
      throw new Error("invalidData");
}
export function validateDetail(d: Detail, r: Run) {
  if (new Set(d.artifacts.map((a) => a.id)).size !== d.artifacts.length)
    throw new Error("invalidData");
  if (d.runId !== r.id) throw new Error("invalidData");
  const seen = new Set<string>();
  let seq = 0;
  for (const e of d.events) {
    if (
      seen.has(e.id) ||
      e.sequence <= seq ||
      e.parents.some((p) => !seen.has(p))
    )
      throw new Error("invalidData");
    seen.add(e.id);
    seq = e.sequence;
  }
  if (
    d.artifacts.some(
      (a) =>
        !seen.has(a.eventId) ||
        a.rows.some((row) => row.length !== a.columns.length),
    ) ||
    d.judgment.evidenceRefs.some((e) => !seen.has(e))
  )
    throw new Error("invalidData");
}
