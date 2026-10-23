import { mkdir, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("../public/data/demo-v1/", import.meta.url));
await mkdir(path.join(root, "runs"), { recursive: true });
const T = (zh, en) => ({ "zh-CN": zh, en });
const names = [
  ["处理组标签修订", "Treatment-label correction"],
  ["供体身份核对", "Donor identity reconciliation"],
  ["采样时间点修订", "Sampling-time correction"],
  ["分装来源确认", "Aliquot lineage confirmation"],
  ["线粒体阈值确认", "Mitochondrial threshold confirmation"],
  ["双细胞复核", "Doublet review"],
  ["批次纳入核验", "Batch inclusion verification"],
  ["细胞注释复审", "Cell-annotation review"],
  ["ATAC 迟到", "Late ATAC delivery"],
  ["跨模态配对", "Cross-modality pairing"],
  ["峰集版本修订", "Peak-set revision"],
  ["模态失败降级", "Modality-failure fallback"],
  ["配对刺激设计", "Paired stimulation design"],
  ["批次混杂核对", "Batch-confounding review"],
  ["协变量缺失", "Missing covariates"],
  ["多重检验范围", "Multiple-testing scope"],
  ["旧 worker 结果晚到", "Late stale-worker results"],
  ["外部结果未知", "Unknown external outcome"],
  ["资源窗口竞争", "Resource-window contention"],
  ["重复乱序回执", "Duplicate and out-of-order receipts"],
  ["批准撤销", "Approval revocation"],
  ["跨班交接", "Shift handover"],
  ["使用范围收缩", "Restricted usage scope"],
  ["撤权与复用", "Revocation and reuse"],
];
const human = [
  [
    "核对原始记录并提交有据修订",
    "Verify source records and submit evidence-based corrections",
  ],
  [
    "确认预设规则并核验最终回执",
    "Confirm specified criteria and verify final receipts",
  ],
  [
    "确认最终模态回执与跨模态映射",
    "Confirm final modality receipts and cross-modality mappings",
  ],
  [
    "核实设计信息与预注册比较范围",
    "Verify design information and preregistered comparison scope",
  ],
  [
    "核对台账、资源和原操作状态",
    "Verify records, resources and original operation status",
  ],
  [
    "确认授权、使用范围与交接记录",
    "Confirm authorization, usage scope and handover records",
  ],
];
const agent = [
  [
    "复核依赖和统计设计，按有效版本分析",
    "Reconcile dependencies and statistical design; analyze valid versions",
  ],
  [
    "核验 QC 依赖并更新下游分析",
    "Check QC dependencies and update downstream analyses",
  ],
  [
    "验证模态版本与配对，限定可支持的结论",
    "Validate modality versions and pairing; limit supported conclusions",
  ],
  [
    "检查统计单位和设计，执行适当分析",
    "Check statistical units and design; perform appropriate analyses",
  ],
  [
    "核查原操作、拒绝过期结果并协调计划",
    "Check original operations, reject stale results and reconcile plans",
  ],
  [
    "核验当前权限和允许用途，完成合法交接",
    "Verify current permissions and allowed uses; perform authorized handover",
  ],
];
import { conditions } from "./task-conditions.mjs";
const sourceRows = (
  await readFile(
    new URL(
      "../../../docs/research/benchmark/task-catalog.md",
      import.meta.url,
    ),
    "utf8",
  )
)
  .split("\n")
  .filter((line) => line.startsWith("| [BW-"))
  .map((line) => line.split("|").map((v) => v.trim()));
if (sourceRows.length !== 24)
  throw Error("Expected exactly 24 source templates");
const categories = [
  "identity",
  "qc",
  "multiomics",
  "statistics",
  "async",
  "governance",
];
const tasks = names.map((n, i) => ({
  id: `BW-${String(i + 1).padStart(2, "0")}`,
  category: categories[Math.floor(i / 4)],
  title: T(...n),
  question: T(
    `在「${n[0]}」情境中，双方能否依据有效证据协调科研状态，并限制不受支持的结果使用？`,
    `In the ${n[1].toLowerCase()} scenario, can both parties reconcile scientific state using valid evidence and constrain unsupported result use?`,
  ),
  human: T(...human[Math.floor(i / 4)]),
  agent: T(...agent[Math.floor(i / 4)]),
  h0: T(sourceRows[i][4], conditions[i][0]),
  h1: T(sourceRows[i][5], conditions[i][1]),
  version: "0.3",
  maturity: "design_only",
}));
const systems = [
  {
    id: "reference-demo",
    name: "Reference agent · DEMO",
    model: "Fictional model A",
    harness: "Demo harness 0.1",
  },
  {
    id: "alternative-demo",
    name: "Alternative agent · DEMO",
    model: "Fictional model B",
    harness: "Demo harness 0.1",
  },
];
const runs = [];
const files = [];
const sha = (s) => createHash("sha256").update(s).digest("hex");
async function save(p, obj) {
  const bytes = JSON.stringify(obj, null, 2) + "\n";
  await writeFile(path.join(root, p), bytes);
  files.push({ path: p, bytes: Buffer.byteLength(bytes), sha256: sha(bytes) });
}
for (let i = 0; i < 8; i++) {
  const id = `demo-${String(i + 1).padStart(3, "0")}`,
    condition = i % 2 ? "H1" : "H0",
    taskId = i < 4 ? "BW-01" : i < 6 ? "BW-09" : "BW-17",
    failed = i === 3 || i === 7;
  const run = {
    id,
    taskId,
    system: i < 2 || i === 4 || i === 6 ? "reference-demo" : "alternative-demo",
    condition,
    stage: "demo",
    mode: i === 6 ? "simulated_replay" : "interactive_simulation",
    sourceMode: i === 6 ? "simulated_replay" : "interactive_model",
    timing: "logical_time",
    versions: {
      task: "0.3",
      instance: `demo-instance-${taskId}`,
      oracle: "demo-rule/0.1",
      human: "demo-human/0.1",
      protocol: i === 3 ? "0.1" : "0.2",
      budget: "demo-budget/0.1",
      dataset: "synthetic-demo/0.1",
    },
    pairId: null,
    repetition: 0,
    technical: failed ? "failed" : "passed",
    scientific: "not_assessed",
    authorization: "not_assessed",
    strict: "not_assessed",
    termination: failed
      ? i === 3
        ? "budget_exhausted"
        : "provider_error"
      : "completed",
    hFaults: i === 3 ? 2 : 0,
    aFaults: i % 2 ? 1 : 0,
    calls: [12, 15, 18, 27, 14, 21, 8, 4][i],
    tokens: [18560, 24274, 29000, 38000, 21000, 31200, 12400, null][i],
    seconds: [24.2, 31.5, 39.1, 62.8, 28.4, 44.9, 12.3, null][i],
    cost: null,
    review: "demo",
    detailFile: `runs/${id}.json`,
  };
  runs.push(run);
  const event = (j, actor, kind, zh, en, body, extra = {}) => ({
    id: `e${String(j).padStart(2, "0")}`,
    sequence: j,
    tick: Math.floor(j / 2),
    actor,
    kind,
    title: T(zh, en),
    body,
    source: "synthetic_demo",
    parents: j > 1 ? [`e${String(j - 1).padStart(2, "0")}`] : [],
    object: null,
    before: null,
    after: null,
    decision: "not_assessed",
    visibility: "public",
    ...extra,
  });
  const events = [
    event(
      1,
      "A",
      "action",
      "读取公开任务与版本",
      "Read public task and versions",
      "SYNTHETIC DEMO. Read the released task specification and current object versions.",
    ),
    event(
      2,
      "H",
      "message",
      "核对来源记录",
      "Check source records",
      "SYNTHETIC DEMO. The human-side simulator reviews a source record. This is not a real human participant.",
    ),
    event(
      3,
      "H",
      "revision",
      "提交有据修订",
      "Submit an evidence-based revision",
      "SYNTHETIC DEMO. A correction is submitted with a source reference.",
      { object: "sample-labels", before: "v1", after: "v2" },
    ),
    event(
      4,
      "world",
      "receipt",
      "接收版本修订",
      "Accept version revision",
      "SYNTHETIC DEMO. The revision is accepted; this receipt alone does not establish scientific validity.",
      { decision: "passed" },
    ),
    event(
      5,
      "A",
      "action",
      "更新分析设计",
      "Update analysis design",
      "SYNTHETIC DEMO. Prepare a donor-level design using the current labels.",
      { object: "analysis-design", before: "v1", after: "v2" },
    ),
    event(
      6,
      "A",
      "redacted",
      "受限事件占位",
      "Restricted event placeholder",
      "Content is not released. This placeholder preserves sequence coverage.",
      { visibility: "restricted", decision: "restricted" },
    ),
    event(
      7,
      "worker",
      "receipt",
      failed ? "分析未完成" : "生成候选分析产物",
      failed ? "Analysis incomplete" : "Produce candidate analysis artifact",
      failed
        ? "SYNTHETIC DEMO. The operation did not complete. No artifact was produced."
        : "SYNTHETIC DEMO. Candidate output generated. Numeric execution does not establish scientific validity.",
      { decision: failed ? "failed" : "passed" },
    ),
    event(
      8,
      "oracle",
      "judgment",
      "独立判定区域",
      "Separate judgment stage",
      "SYNTHETIC DEMO. Formal scientific validity has not been assessed.",
    ),
  ];
  const rows = [
    ["donor-01", "control", "v2"],
    [
      "donor-02",
      condition === "H1" ? "corrected-stimulated" : "stimulated",
      "v2",
    ],
    ["donor-03", "control", "v2"],
  ];
  const artifacts = failed
    ? []
    : [
        {
          id: `artifact-${id}`,
          title: T("供体层设计表（演示）", "Donor-level design table (demo)"),
          type: "table",
          status: "candidate",
          method: "synthetic-design-table",
          unit: "donor",
          inputVersion: "v2",
          sha256: sha(JSON.stringify(rows)),
          eventId: "e07",
          columns: ["donor_id", "condition", "source_version"],
          rows,
        },
      ];
  await save(run.detailFile, {
    runId: id,
    events,
    artifacts,
    judgment: {
      ruleId: "demo-rule-01",
      status: "not_assessed",
      explanation: T(
        "仅验证界面与引用关系。此记录不能用于科学有效性或模型能力结论。",
        "Validates the interface and reference relationships only. This record cannot support scientific-validity or model-capability claims.",
      ),
      evidenceRefs: ["e07", "e08"],
      output: "SYNTHETIC DEMO. No scientific conclusion is released.",
    },
    sourceCommit: null,
    sourceSet: "fictional-ui-fixture/0.1",
    coverage: T(
      "8 个合成事件；1 个受限占位。不对应真实实验轨迹。",
      "8 synthetic events; 1 restricted placeholder. Not a real experimental trajectory.",
    ),
    originalLocale: "en",
  });
}
const methods = [
  [
    "scope",
    "研究范围",
    "Research scope",
    "研究人、Agent 与执行环境在信息、权限和操作能力不对称时的科研协作。网站是只读证据浏览器，不执行模型、实验或裁判。",
    "The benchmark studies scientific collaboration when humans, agents and execution environments differ in information, permissions and capabilities. This website is a read-only evidence browser, not an execution or judging service.",
  ],
  [
    "tasks",
    "任务与条件",
    "Tasks and conditions",
    "24 个设计模板覆盖身份、质量控制、多组学、统计、异步协作和治理。H0/H1 是指定正常与善意失误条件。模板、实例、重复和运行尝试分别记录。",
    "24 design templates cover identity, quality control, multiomics, statistics, asynchronous work and governance. H0/H1 denote specified normal and unintentional-error conditions. Templates, instances, repetitions and attempts are distinct.",
  ],
  [
    "modes",
    "模式与时间",
    "Modes and time",
    "交互式模拟、确定性回放与真人研究分区呈现。浏览轨迹不改变实验模式。逻辑 tick 不是实际耗时；累计调用时间不能当作 episode 墙钟。",
    "Interactive simulation, deterministic replay and human studies are separate modes. Browsing a trace does not change its experimental mode. Logical ticks are not elapsed time; cumulative call time is not episode wall-clock duration.",
  ],
  [
    "metrics",
    "指标与分母",
    "Metrics and denominators",
    "技术轨迹、严格完成、科学有效性、授权合规、H/A 协议问题独立展示。未评不填零。没有冻结统计包时，不在前端计算成功率、置信区间、因果效应或名次。",
    "Technical trajectory, strict completion, scientific validity, authorization and H/A protocol issues are separate outcomes. Not assessed is not zero. Without a frozen statistical release, the frontend computes no success rates, confidence intervals, causal effects or ranks.",
  ],
  [
    "review",
    "审查与公开范围",
    "Review and release scope",
    "作者自验、独立工程核验、科学方法审阅及公开批准不是同一种审查。本演示数据与英文工程译稿均不具备真实科学审阅身份。真实数据仅允许通过审核的白名单发布包进入网站。",
    "Author checks, independent engineering verification, scientific-method review and release approval are distinct. This demo and its engineering translations have no real scientific review status. Real data must enter through a reviewed, allowlisted release.",
  ],
  [
    "reproduction",
    "复现与更正",
    "Reproduction and corrections",
    "发布包包含明确契约版本、精确文件清单、SHA-256 和审查身份。任何重跑作为新尝试保留，不能覆盖失败。更正通过新版本与替代/撤回记录表达。",
    "Releases contain explicit schema versions, exact file inventories, SHA-256 checksums and review provenance. Reruns remain separate attempts and never overwrite failures. Corrections use new releases with replacement or withdrawal records.",
  ],
].map(([id, zh, en, bodyZh, bodyEn]) => ({
  id,
  title: T(zh, en),
  body: T(bodyZh, bodyEn),
}));
await save("index.json", {
  schema_version: "benchmark-web/0.1",
  release_id: "demo-v1",
  tasks,
  systems,
  runs,
  methods,
});
await writeFile(
  path.join(root, "release.json"),
  JSON.stringify(
    {
      schema_version: "benchmark-web/0.1",
      release_id: "demo-v1",
      created_at: "2026-10-20T00:00:00Z",
      audience: "demo",
      status: "demo",
      review_ref: null,
      translation_review: "draft",
      files,
      supersedes: null,
    },
    null,
    2,
  ) + "\n",
);
console.log(
  "Wrote fictional demo release: 24 templates, 8 runs. No experimental results.",
);
