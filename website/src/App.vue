<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from "vue";
import type {
  Data,
  Manifest,
  Detail,
  Run,
  Task,
  Locale,
  Text,
  Artifact,
} from "./schema";
import { loadRelease, csv, comparisonIssues } from "./data";
import { ui, type Key } from "./locales";
import StatusBadge from "./components/StatusBadge.vue";
import RunDetail from "./components/RunDetail.vue";
import ArtifactTable from "./components/ArtifactTable.vue";
const data = ref<Data>(),
  manifest = ref<Manifest>(),
  error = ref(""),
  busy = ref(true),
  notice = ref("");
let loader: Awaited<ReturnType<typeof loadRelease>>;
let generation = 0;
const readRoute = () => new URLSearchParams(location.hash.replace(/^#\/?/, ""));
const route = ref(readRoute());
const page = computed(() =>
  ["results", "tasks", "runs", "compare", "methods"].includes(
    route.value.get("page") ?? "",
  )
    ? route.value.get("page")!
    : "results",
);
let preferred = "zh-CN";
try {
  preferred =
    localStorage.getItem("bioduet-locale") ??
    (navigator.language.startsWith("zh") ? "zh-CN" : "en");
} catch {
  /* Optional preference storage. */
}
const locale = ref<Locale>(
  route.value.get("lang") === "en"
    ? "en"
    : route.value.get("lang") === "zh-CN"
      ? "zh-CN"
      : preferred === "en"
        ? "en"
        : "zh-CN",
);
const t = (key: Key) => ui(locale.value, key),
  text = (v: Text) => v[locale.value];
function nav(patch: Record<string, string>, replace = false) {
  const q = new URLSearchParams(route.value);
  for (const [k, v] of Object.entries(patch)) v ? q.set(k, v) : q.delete(k);
  q.set("lang", locale.value);
  const url = "#/" + q.toString();
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  route.value = q;
}
function syncRoute() {
  route.value = readRoute();
  if (["en", "zh-CN"].includes(route.value.get("lang") ?? ""))
    locale.value = route.value.get("lang") as Locale;
}
function go(p: string) {
  nav({ page: p, run: "", tab: "", event: "" });
  window.scrollTo({ top: 0 });
}
function field(key: string, fallback = "") {
  return computed({
    get: () => route.value.get(key) ?? fallback,
    set: (v: string) => nav({ [key]: v, p: "1" }, true),
  });
}
const filtersExpanded = ref(false);
const query = field("q"),
  category = field("category", "all"),
  condition = field("condition", "all"),
  protocol = field("protocol", "all"),
  mode = field("mode", "all"),
  status = field("status", "all"),
  view = field("view", "table"),
  cohort = field("cohort", "development"),
  sort = field("sort", "id"),
  layer = field("layer", "technical");
const selected = computed(() =>
  [
    ...new Set(
      (route.value.get("selected") ?? "")
        .split(",")
        .filter((id) => data.value?.runs.some((r) => r.id === id)),
    ),
  ].slice(0, 4),
);
const chosen = computed(
  () => data.value?.runs.filter((r) => selected.value.includes(r.id)) ?? [],
);
const filtersActive = computed(
  () =>
    query.value ||
    [category, condition, protocol, mode, status].some(
      (f) => f.value !== "all",
    ),
);
const filtered = computed(() => {
  const list = (data.value?.runs ?? []).filter((r) => {
    const task = data.value!.tasks.find((t) => t.id === r.taskId)!;
    return (
      (cohort.value !== "regression" || r.mode === "simulated_replay") &&
      (cohort.value === "regression" || r.mode !== "simulated_replay") &&
      (category.value === "all" || task.category === category.value) &&
      (condition.value === "all" || r.condition === condition.value) &&
      (protocol.value === "all" || r.versions.protocol === protocol.value) &&
      (mode.value === "all" || r.mode === mode.value) &&
      (status.value === "all" || r.technical === status.value) &&
      `${r.id} ${r.taskId} ${system(r).name} ${text(task.title)}`
        .toLowerCase()
        .includes(query.value.toLowerCase())
    );
  });
  return [...list].sort((a, b) =>
    sort.value === "calls"
      ? (b.calls ?? -1) - (a.calls ?? -1)
      : a.id.localeCompare(b.id),
  );
});
const pageNum = computed(() =>
  Math.max(
    1,
    Math.min(
      Math.ceil(filtered.value.length / 6) || 1,
      Number(route.value.get("p")) || 1,
    ),
  ),
);
const visibleRuns = computed(() =>
  filtered.value.slice((pageNum.value - 1) * 6, pageNum.value * 6),
);
const filteredTasks = computed(
  () =>
    data.value?.tasks.filter(
      (task) =>
        (category.value === "all" || task.category === category.value) &&
        `${task.id} ${text(task.title)} ${text(task.question)}`
          .toLowerCase()
          .includes(query.value.toLowerCase()),
    ) ?? [],
);
const categories = [
  "identity",
  "qc",
  "multiomics",
  "statistics",
  "async",
  "governance",
] as const;
const protocols = computed(() => [
  ...new Set(data.value?.runs.map((r) => r.versions.protocol) ?? []),
]);
const currentRun = computed(() =>
  data.value?.runs.find((r) => r.id === route.value.get("run")),
);
const detail = ref<Detail>(),
  detailError = ref(""),
  detailBusy = ref(false),
  compareDetails = ref<Record<string, Detail>>({});
let detailGeneration = 0;
const tab = computed(() =>
  ["timeline", "objects", "artifacts", "judgment", "provenance"].includes(
    route.value.get("tab") ?? "",
  )
    ? route.value.get("tab")!
    : "timeline",
);
const compareTab = field("ctab", "technicalEvidence"),
  costMetric = ref<"tokens" | "seconds" | "cost">("tokens"),
  differencesOnly = ref(false);
const issues = computed(() => comparisonIssues(chosen.value));
const drawer = ref<HTMLDialogElement>(),
  drawerTask = ref<Task>(),
  drawerRun = ref<Run>();
let lastFocus: HTMLElement | null = null;
const highlighted = ref("");
let listScroll = 0;
function backToRuns() {
  nav({ run: "", event: "", tab: "" });
  nextTick(() => window.scrollTo({ top: listScroll, behavior: "instant" }));
}
const matrixRows = computed(() => [
  ...new Map(
    filtered.value.map((r) => [
      r.system + "|" + r.versions.protocol,
      {
        id: r.system + "|" + r.versions.protocol,
        system: r.system,
        protocol: r.versions.protocol,
        name: system(r).name,
      },
    ]),
  ).values(),
]);
const matchKey = (r: Run) =>
  `${r.taskId}|${r.versions.instance}|${r.condition}|${r.repetition}`;
function system(r: Run) {
  return data.value!.systems.find((s) => s.id === r.system)!;
}
function reset() {
  nav(
    {
      q: "",
      category: "",
      condition: "",
      protocol: "",
      mode: "",
      status: "",
      p: "",
      sort: "",
    },
    true,
  );
}
function toggleCheckbox(id: string, event: Event) {
  toggle(id);
  (event.target as HTMLInputElement).checked = selected.value.includes(id);
}
function toggle(id: string) {
  if (selected.value.includes(id))
    nav({ selected: selected.value.filter((x) => x !== id).join(",") });
  else if (selected.value.length < 4)
    nav({ selected: [...selected.value, id].join(",") });
  else announce(t("maxFour"));
}
function inspect(r: Run) {
  listScroll = window.scrollY;
  nav({ page: "runs", run: r.id, tab: "timeline", event: "" });
  closeDrawer();
  window.scrollTo({ top: 0 });
}
function announce(message: string) {
  notice.value = message;
}
function download(value: unknown, name: string, format = "json") {
  const str = format === "csv" ? String(value) : JSON.stringify(value, null, 2);
  const blob = new Blob([str], {
    type: format === "csv" ? "text/csv;charset=utf-8" : "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name + "." + format;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportRuns(format: string) {
  const runs = page.value === "compare" ? chosen.value : filtered.value;
  if (format === "csv")
    download(
      csv([
        [
          "release_id",
          "run_id",
          "task_id",
          "stage",
          "mode",
          "condition",
          "technical",
          "scientific",
          "H_faults",
          "A_faults",
          "calls",
          "tokens",
        ],
        ...runs.map((r) => [
          manifest.value!.release_id,
          r.id,
          r.taskId,
          r.stage,
          r.mode,
          r.condition,
          r.technical,
          r.scientific,
          r.hFaults,
          r.aFaults,
          r.calls,
          r.tokens,
        ]),
      ]),
      "bioduet-" + manifest.value!.release_id,
      "csv",
    );
  else
    download(
      {
        release_id: manifest.value!.release_id,
        audience: manifest.value!.audience,
        runs,
      },
      "bioduet-" + manifest.value!.release_id,
    );
}
async function copy() {
  try {
    await navigator.clipboard.writeText(location.href);
    announce(t("copied"));
  } catch {
    announce(t("copyFailed"));
  }
}
async function openTask(task: Task) {
  lastFocus = document.activeElement as HTMLElement;
  drawerTask.value = task;
  drawerRun.value = undefined;
  await nextTick();
  drawer.value?.showModal();
}
async function openCell(r: Run) {
  lastFocus = document.activeElement as HTMLElement;
  drawerRun.value = r;
  drawerTask.value = data.value!.tasks.find((t) => t.id === r.taskId);
  highlighted.value = matchKey(r);
  await nextTick();
  drawer.value?.showModal();
}
function closeDrawer() {
  drawer.value?.close();
  lastFocus?.focus();
}
function cellRuns(
  systemId: string,
  taskId: string,
  c: string,
  version: string,
) {
  return filtered.value.filter(
    (r) =>
      r.system === systemId &&
      r.taskId === taskId &&
      r.condition === c &&
      r.versions.protocol === version,
  );
}
function cellLabel(r: Run) {
  return layer.value === "hFaults"
    ? `${r.hFaults ?? "—"} H`
    : layer.value === "aFaults"
      ? `${r.aFaults ?? "—"} A`
      : t(r[layer.value as "technical" | "scientific" | "authorization"]);
}
const selectedArtifacts = field("artifacts");
const artifactChoices = computed(() =>
  chosen.value.flatMap((r) =>
    (compareDetails.value[r.id]?.artifacts ?? []).map((a) => ({
      run: r,
      artifact: a,
    })),
  ),
);
const activeArtifacts = computed(() => {
  const ids = selectedArtifacts.value.split(",").filter(Boolean);
  return ids.length
    ? artifactChoices.value
        .filter((x) => ids.includes(x.artifact.id))
        .slice(0, 4)
    : artifactChoices.value.slice(0, 4);
});
const artifactsCompatible = computed(
  () =>
    new Set(
      activeArtifacts.value.map(
        (x) =>
          `${x.run.taskId}|${x.run.versions.instance}|${x.run.versions.dataset}|${x.artifact.type}|${x.artifact.method}|${x.artifact.unit}|${x.artifact.inputVersion}`,
      ),
    ).size <= 1,
);
function toggleArtifact(id: string) {
  const ids = activeArtifacts.value.map((x) => x.artifact.id);
  selectedArtifacts.value =
    (ids.includes(id)
      ? ids.filter((x) => x !== id)
      : [...ids, id].slice(0, 4)
    ).join(",") || "none";
}
function artifactRows(a: Artifact) {
  if (a.type !== "table" || !differencesOnly.value || !artifactsCompatible.value) return a.rows;
  return a.rows.filter((row) =>
    activeArtifacts.value.some(
      (other) =>
        JSON.stringify(other.artifact.rows.find((r) => r[0] === row[0])) !==
        JSON.stringify(row),
    ),
  );
}
const compareLink = computed(() => {
  const q = new URLSearchParams(route.value);
  q.set("page", "compare");
  q.delete("run");
  return "#/" + q.toString();
});
async function init() {
  const token = ++generation;
  busy.value = true;
  error.value = "";
  try {
    const result = await loadRelease();
    if (token !== generation) return;
    loader = result;
    data.value = result.data;
    manifest.value = result.manifest;
  } catch (e) {
    if (token === generation)
      error.value = e instanceof Error ? e.message : "networkError";
  } finally {
    if (token === generation) busy.value = false;
  }
}
watch([currentRun, () => manifest.value], async () => {
  const token = ++detailGeneration;
  detail.value = undefined;
  detailError.value = "";
  const r = currentRun.value;
  if (!r || !loader) return;
  detailBusy.value = true;
  try {
    const d = await loader.loadDetail(r);
    if (token === detailGeneration) detail.value = d;
  } catch (e) {
    if (token === detailGeneration)
      detailError.value = e instanceof Error ? e.message : "networkError";
  } finally {
    if (token === detailGeneration) detailBusy.value = false;
  }
});
watch([chosen, page], async () => {
  if (page.value !== "compare" || !loader) return;
  detailError.value = "";
  for (const r of chosen.value) {
    try {
      compareDetails.value[r.id] = await loader.loadDetail(r);
    } catch (e) {
      detailError.value = e instanceof Error ? e.message : "networkError";
    }
  }
});
watch(
  locale,
  () => {
    document.documentElement.lang = locale.value;
    document.title = `BioDuet · ${t("results")}`;
    try {
      localStorage.setItem("bioduet-locale", locale.value);
    } catch {}
    nav({}, true);
  },
  { immediate: true },
);
onMounted(() => {
  window.addEventListener("popstate", syncRoute);
  window.addEventListener("hashchange", syncRoute);
  init();
});
onUnmounted(() => {
  window.removeEventListener("popstate", syncRoute);
  window.removeEventListener("hashchange", syncRoute);
});
const errorText = (code: string) =>
  t(
    ([
      "missingFile",
      "hashError",
      "schemaError",
      "invalidData",
      "withdrawn",
      "unapproved",
    ].includes(code)
      ? code
      : "networkError") as Key,
  );
const focusMain = () => document.getElementById("main")?.focus();
const scrollMethod = (id: string) =>
  document
    .getElementById("method-" + id)
    ?.scrollIntoView({ behavior: "smooth" });
const format = (v: number | null | undefined) =>
  v == null
    ? t("not_reported")
    : new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(
        v,
      );
</script>
<template>
  <a href="#main" class="skip-link" @click.prevent="focusMain">{{ t("skip") }}</a>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="#/page=results" @click.prevent="go('results')"
        ><img :src="'./mark.svg'" alt="" width="32" height="32" /><span
          >BioDuet<small>BENCHMARK</small></span
        ></a
      >
      <nav
        class="main-nav"
        :aria-label="locale === 'en' ? 'Main navigation' : '主导航'"
      >
        <a
          v-for="p in ['results', 'tasks', 'runs', 'compare', 'methods']"
          :key="p"
          :href="'#/page=' + p"
          :class="{ active: page === p }"
          :aria-current="page === p ? 'page' : undefined"
          @click.prevent="go(p)"
          >{{ t(p as Key)
          }}<span v-if="p === 'compare' && selected.length" class="count">{{
            selected.length
          }}</span></a
        >
      </nav>
      <div class="language" :aria-label="t('language')">
        <button
          :class="{ active: locale === 'zh-CN' }"
          :aria-pressed="locale === 'zh-CN'"
          @click="locale = 'zh-CN'"
        >
          中文</button
        ><span>/</span
        ><button
          :class="{ active: locale === 'en' }"
          :aria-pressed="locale === 'en'"
          @click="locale = 'en'"
        >
          EN
        </button>
      </div>
    </div>
  </header>
  <main id="main" tabindex="-1">
    <div v-if="busy" class="empty" role="status">{{ t("loading") }}</div>
    <div v-else-if="error" class="empty error" role="alert">
      <h1>{{ t("errorTitle") }}</h1>
      <p>{{ errorText(error) }}</p>
      <button @click="init">{{ t("retry") }}</button>
    </div>
    <template v-else-if="data && manifest">
      <div class="breadcrumb">
        <span>BioDuet</span><span>/</span><span>{{ t(page as Key) }}</span
        ><template v-if="currentRun"
          ><span>/</span><span class="mono">{{ currentRun.id }}</span></template
        ><span class="release-label mono"
          >{{ manifest.release_id }} <i>·</i>
          {{
            t(manifest.status === "approved" ? "approved" : "reviewPending")
          }}</span
        >
      </div>
      <div class="page-heading">
        <div>
          <h1>{{ currentRun ? currentRun.id : t(page as Key) }}</h1>
          <p>
            {{
              currentRun
                ? system(currentRun).name +
                  " / " +
                  currentRun.taskId +
                  " / " +
                  currentRun.condition
                : t("subtitle")
            }}
          </p>
        </div>
        <div class="heading-actions">
          <button v-if="currentRun" @click="backToRuns">
            ← {{ t("back") }}</button
          ><button class="quiet" @click="go('methods')">
            {{ t("method") }} ↗</button
          ><button @click="download(manifest, 'bioduet-release-manifest')">
            {{ t("manifest") }} ↓
          </button>
        </div>
      </div>
      <aside v-if="manifest.audience === 'demo'" class="notice-strip">
        <span class="notice-icon" aria-hidden="true">i</span>
        <div>
          <strong>{{ t("demo") }}</strong>
          <p>{{ t("demoNote") }}</p>
        </div>
      </aside>

      <div
        v-if="page === 'runs' && route.get('run') && !currentRun"
        class="empty"
      >
        <h2>{{ t("notFound") }}</h2>
        <button @click="nav({ run: '', event: '' })">{{ t("back") }}</button>
      </div>
      <template
        v-else-if="(page === 'results' || page === 'runs') && !currentRun"
      >
        <div class="metadata-strip">
          <span
            >{{ t("templates") }} <strong>{{ data.tasks.length }}</strong></span
          ><span
            >{{ t("attempts") }} <strong>{{ data.runs.length }}</strong></span
          ><span
            >{{ t("coverage") }}
            <strong>{{
              new Set(data.runs.map((r) => r.taskId)).size
            }}</strong></span
          ><span class="muted">{{ t("noRanking") }}</span>
        </div>
        <nav
          class="subtabs"
          :aria-label="locale === 'en' ? 'Evaluation cohorts' : '评测分区'"
        >
          <button
            v-for="c in ['development', 'regression', 'formal']"
            :key="c"
            :class="{ active: cohort === c }"
            @click="cohort = c"
          >
            {{ t(c as Key)
            }}<span v-if="c === 'formal'" aria-hidden="true"> ↗</span>
          </button>
        </nav>
        <div v-if="cohort === 'formal'" class="empty">
          <span class="empty-symbol">∅</span>
          <h2>{{ t("formalEmpty") }}</h2>
          <p>{{ t("formalNote") }}</p>
          <button @click="go('methods')">{{ t("methods") }} →</button>
        </div>
        <template v-else
          ><button
            class="mobile-filter-toggle"
            :aria-expanded="filtersExpanded"
            @click="filtersExpanded = !filtersExpanded"
          >
            {{ t("filters") }} {{ filtersExpanded ? "−" : "+" }}
          </button>
          <section
            class="filters"
            :class="{ expanded: filtersExpanded }"
            :aria-label="t('filters')"
          >
            <label class="search"
              ><span>{{ t("search") }}</span
              ><input
                v-model="query"
                :placeholder="t('search')"
                type="search" /></label
            ><label
              >{{ t("category")
              }}<select v-model="category">
                <option value="all">{{ t("all") }}</option>
                <option v-for="c in categories" :key="c" :value="c">
                  {{ t(c) }}
                </option>
              </select></label
            ><label
              >{{ t("condition")
              }}<select v-model="condition">
                <option value="all">{{ t("all") }}</option>
                <option>H0</option>
                <option>H1</option>
              </select></label
            ><label
              >{{ t("version")
              }}<select v-model="protocol">
                <option value="all">{{ t("all") }}</option>
                <option v-for="v in protocols" :key="v">{{ v }}</option>
              </select></label
            ><label
              >{{ t("mode")
              }}<select v-model="mode">
                <option value="all">{{ t("all") }}</option>
                <option value="interactive_simulation">
                  {{ t("interactive_simulation") }}
                </option>
                <option value="simulated_replay">
                  {{ t("simulated_replay") }}
                </option>
              </select></label
            ><label
              >{{ t("status")
              }}<select v-model="status">
                <option value="all">{{ t("all") }}</option>
                <option value="passed">{{ t("passed") }}</option>
                <option value="failed">{{ t("failed") }}</option>
              </select></label
            ><button
              class="text-button reset"
              :disabled="!filtersActive"
              @click="reset"
            >
              {{ t("reset") }}
            </button>
          </section>
          <section class="results-panel">
            <div class="table-tools">
              <div class="segmented">
                <button
                  :class="{ active: view === 'table' }"
                  :aria-pressed="view === 'table'"
                  @click="view = 'table'"
                >
                  ☷ {{ t("table") }}</button
                ><button
                  :class="{ active: view === 'matrix' }"
                  :aria-pressed="view === 'matrix'"
                  @click="view = 'matrix'"
                >
                  ▦ {{ t("matrix") }}
                </button>
              </div>
              <div class="button-row">
                <span class="muted"
                  >{{ t("selected") }} {{ selected.length }} / 4</span
                ><button
                  :disabled="selected.length < 2"
                  class="primary"
                  @click="go('compare')"
                >
                  {{ t("compare") }} →
                </button>
                <details class="export-menu">
                  <summary>{{ t("export") }} ↓</summary>
                  <div>
                    <button @click="exportRuns('json')">
                      {{ t("exportJSON") }}</button
                    ><button @click="exportRuns('csv')">
                      {{ t("exportCSV") }}
                    </button>
                  </div>
                </details>
              </div>
            </div>
            <div v-if="!filtered.length" class="empty">
              <h2>{{ t("empty") }}</h2>
              <p>{{ t("emptyNote") }}</p>
              <button @click="reset">{{ t("reset") }}</button>
            </div>
            <template v-else-if="view === 'table'"
              ><div
                class="table-scroll result-table"
                tabindex="0"
                :aria-label="t('table')"
              >
                <table>
                  <thead>
                    <tr>
                      <th>
                        <span class="sr-only">{{ t("selectRun") }}</span>
                      </th>
                      <th>{{ t("system") }}</th>
                      <th>{{ t("task") }}</th>
                      <th>{{ t("technical") }}</th>
                      <th>{{ t("scientific") }}</th>
                      <th>{{ t("authorization") }}</th>
                      <th>{{ t("faults") }}</th>
                      <th>
                        <button
                          class="sort-button"
                          @click="sort = sort === 'calls' ? 'id' : 'calls'"
                        >
                          {{ t("calls") }} {{ sort === "calls" ? "↓" : "↕" }}
                        </button>
                      </th>
                      <th>{{ t("review") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="r in visibleRuns"
                      :key="r.id"
                      :class="{ selected: selected.includes(r.id) }"
                    >
                      <td>
                        <input
                          type="checkbox"
                          :aria-label="t('selectRun') + ' ' + r.id"
                          :checked="selected.includes(r.id)"
                          @change="toggleCheckbox(r.id, $event)"
                        />
                      </td>
                      <td>
                        <button class="row-title" @click="inspect(r)">
                          {{ system(r).name }} <span>↗</span></button
                        ><small class="mono"
                          >{{ r.id }} · {{ system(r).model }}</small
                        >
                      </td>
                      <td>
                        <span class="mono">{{ r.taskId }}</span
                        ><small
                          >{{ r.condition }} <span class="dot">·</span> v{{
                            r.versions.protocol
                          }}</small
                        >
                      </td>
                      <td>
                        <StatusBadge :value="r.technical" :locale="locale" />
                      </td>
                      <td :data-label="t('scientific')">
                        <StatusBadge :value="r.scientific" :locale="locale" />
                      </td>
                      <td :data-label="t('authorization')">
                        <StatusBadge
                          :value="r.authorization"
                          :locale="locale"
                        />
                      </td>
                      <td class="mono" :data-label="t('faults')">
                        <button
                          class="fault-button"
                          @click="
                            nav({ page: 'runs', run: r.id, tab: 'judgment' })
                          "
                        >
                          {{ r.hFaults ?? "—" }} / {{ r.aFaults ?? "—" }}
                        </button>
                      </td>
                      <td class="mono number" :data-label="t('calls')">
                        {{ r.calls ?? "—" }}
                      </td>
                      <td>
                        <StatusBadge :value="r.review" :locale="locale" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="table-footer">
                <span
                  >{{ filtered.length }} {{ t("rows") }}
                  <span class="muted"
                    >/ {{ data.runs.length }} {{ t("attempts") }}</span
                  ></span
                >
                <div class="button-row">
                  <button
                    :disabled="pageNum === 1"
                    @click="nav({ p: String(pageNum - 1) }, true)"
                  >
                    ← {{ t("previous") }}</button
                  ><span
                    >{{ pageNum }} / {{ Math.ceil(filtered.length / 6) }}</span
                  ><button
                    :disabled="pageNum * 6 >= filtered.length"
                    @click="nav({ p: String(pageNum + 1) }, true)"
                  >
                    {{ t("next") }} →
                  </button>
                </div>
              </div></template
            >
            <template v-else
              ><div class="matrix-settings">
                <label
                  >{{ t("layers")
                  }}<select v-model="layer">
                    <option
                      v-for="l in [
                        'technical',
                        'scientific',
                        'authorization',
                        'hFaults',
                        'aFaults',
                      ]"
                      :key="l"
                      :value="l"
                    >
                      {{
                        l === "hFaults"
                          ? "H · " + t("faults")
                          : l === "aFaults"
                            ? "A · " + t("faults")
                            : t(l as Key)
                      }}
                    </option>
                  </select></label
                ><span>{{ t("match") }}</span>
              </div>
              <div class="table-scroll matrix-scroll" tabindex="0">
                <table class="matrix-table">
                  <thead>
                    <tr>
                      <th>{{ t("system") }}</th>
                      <th v-for="task in data.tasks" :key="task.id">
                        <button
                          class="text-button mono"
                          @click="openTask(task)"
                        >
                          {{ task.id }}</button
                        ><small>H0 / H1</small>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in matrixRows" :key="s.id">
                      <th>
                        {{ s.name }}<small>protocol {{ s.protocol }}</small>
                      </th>
                      <td v-for="task in data.tasks" :key="task.id">
                        <div class="matrix-pair">
                          <div v-for="c in ['H0', 'H1']" :key="c">
                            <button
                              v-for="r in cellRuns(
                                s.system,
                                task.id,
                                c,
                                s.protocol,
                              )"
                              :key="r.id"
                              class="matrix-cell"
                              :class="[
                                r.technical,
                                { highlighted: highlighted === matchKey(r) },
                              ]"
                              :aria-label="r.id + ' ' + c + ' ' + cellLabel(r)"
                              @mouseenter="highlighted = matchKey(r)"
                              @focus="highlighted = matchKey(r)"
                              @click="openCell(r)"
                            >
                              {{
                                layer === "technical"
                                  ? r.technical === "passed"
                                    ? "✓"
                                    : "×"
                                  : layer === "hFaults"
                                    ? r.hFaults
                                    : layer === "aFaults"
                                      ? r.aFaults
                                      : "?"
                              }}</button
                            ><span
                              v-if="
                                !cellRuns(s.system, task.id, c, s.protocol)
                                  .length
                              "
                              class="matrix-cell missing"
                              :aria-label="
                                task.id + ' ' + c + ' ' + t('not_run')
                              "
                              >—</span
                            >
                          </div>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="matrix-legend">
                <span>✓ {{ t("passed") }}</span
                ><span>× {{ t("failed") }}</span
                ><span>? {{ t("not_assessed") }}</span
                ><span>— {{ t("not_run") }}</span>
              </div></template
            >
          </section>
          <details class="cost-section">
            <summary>{{ t("costTitle") }}</summary>
            <div class="cost-content">
              <p>{{ t("costNote") }}</p>
              <label
                >{{ t("costTitle")
                }}<select v-model="costMetric">
                  <option value="tokens">{{ t("tokens") }}</option>
                  <option value="seconds">{{ t("seconds") }}</option>
                  <option value="cost">{{ t("cost") }}</option>
                </select></label
              >
              <div class="cost-chart">
                <div v-for="r in filtered" :key="r.id" class="cost-row">
                  <span class="mono">{{ r.id }}</span>
                  <div class="bar-track">
                    <div
                      class="bar"
                      :style="{
                        width:
                          (r[costMetric] === null
                            ? 0
                            : (100 * r[costMetric]!) /
                              Math.max(
                                1,
                                ...filtered.map((x) => x[costMetric] ?? 0),
                              )) + '%',
                      }"
                    ></div>
                  </div>
                  <span>{{ format(r[costMetric]) }}</span>
                </div>
              </div>
            </div>
          </details></template
        >
      </template>

      <template v-else-if="page === 'tasks'"
        ><p class="section-intro">{{ t("taskNote") }}</p>
        <div class="category-tabs">
          <button
            :class="{ active: category === 'all' }"
            @click="category = 'all'"
          >
            {{ t("all") }} <span>24</span></button
          ><button
            v-for="c in categories"
            :key="c"
            :class="{ active: category === c }"
            @click="category = c"
          >
            {{ t(c) }} <span>4</span>
          </button>
        </div>
        <label class="task-search"
          >{{ t("search")
          }}<input type="search" v-model="query" :placeholder="t('search')"
        /></label>
        <div class="task-grid">
          <button
            v-for="task in filteredTasks"
            :key="task.id"
            class="task-card"
            @click="openTask(task)"
          >
            <span class="task-card-top"
              ><span class="mono">{{ task.id }}</span
              ><span>{{ t(task.category) }}</span></span
            >
            <h2>{{ text(task.title) }}</h2>
            <p>{{ text(task.question) }}</p>
            <span class="task-card-bottom"
              ><span>{{ t(task.maturity) }} · v{{ task.version }}</span
              ><span>↗</span></span
            >
          </button>
        </div>
        <div v-if="!filteredTasks.length" class="empty">
          <h2>{{ t("empty") }}</h2>
          <button @click="reset">{{ t("reset") }}</button>
        </div></template
      >

      <template v-else-if="page === 'runs' && currentRun"
        ><div class="run-actions">
          <button @click="toggle(currentRun.id)">
            {{ t(selected.includes(currentRun.id) ? "remove" : "add") }}</button
          ><button @click="copy">{{ t("copy") }}</button
          ><button
            v-if="detail"
            @click="
              download(
                { release_id: manifest.release_id, run: currentRun, detail },
                currentRun.id,
              )
            "
          >
            {{ t("exportJSON") }}
          </button>
        </div>
        <p v-if="detailBusy" role="status">{{ t("loading") }}</p>
        <div v-else-if="detailError" role="alert" class="empty">
          <h2>{{ t("errorTitle") }}</h2>
          <p>{{ errorText(detailError) }}</p>
          <button @click="init">{{ t("retry") }}</button>
        </div>
        <RunDetail
          v-else-if="detail"
          :run="currentRun"
          :detail="detail"
          :locale="locale"
          :tab="tab"
          :event-id="route.get('event') ?? ''"
          @navigate="nav"
          @download="download"
      /></template>

      <template v-else-if="page === 'compare'"
        ><div class="comparison-actions">
          <span>{{ t("selected") }} {{ chosen.length }} / 4</span
          ><button @click="go('results')">{{ t("add") }}</button
          ><button :disabled="!chosen.length" @click="nav({ selected: '' })">
            {{ t("clear") }}</button
          ><button @click="copy">{{ t("copy") }}</button
          ><a class="button" :href="compareLink" target="_blank" rel="noopener"
            >{{ t("newTab") }} ↗</a
          ><button :disabled="!chosen.length" @click="exportRuns('json')">
            {{ t("exportJSON") }}
          </button>
        </div>
        <div v-if="chosen.length < 2" class="empty">
          <h2>{{ t("chooseTwo") }}</h2>
          <button class="primary" @click="go('results')">
            {{ t("results") }} →
          </button>
        </div>
        <template v-else
          ><aside class="comparison-notice">
            <strong>{{ t("descriptive") }}</strong>
            <ul>
              <li v-for="issue in issues" :key="issue">
                {{ t(issue as Key) }}
              </li>
            </ul>
          </aside>
          <nav class="subtabs">
            <button
              v-for="ct in [
                'technicalEvidence',
                'artifactCompare',
                'trajectoryCompare',
              ]"
              :key="ct"
              :class="{ active: compareTab === ct }"
              @click="compareTab = ct"
            >
              {{ t(ct as Key) }}
            </button>
          </nav>
          <div v-if="detailError" class="notice-strip" role="alert">
            {{ errorText(detailError) }}
          </div>
          <div
            v-if="compareTab === 'technicalEvidence'"
            class="table-scroll panel"
          >
            <table class="comparison-table">
              <thead>
                <tr>
                  <th>{{ t("fullConfig") }}</th>
                  <th v-for="r in chosen" :key="r.id">
                    <button class="row-title" @click="inspect(r)">
                      {{ r.id }} ↗</button
                    ><small>{{ system(r).name }} · {{ r.condition }}</small
                    ><button class="text-button" @click="toggle(r.id)">
                      {{ t("remove") }}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="key in [
                    'technical',
                    'scientific',
                    'strict',
                    'authorization',
                  ] as const"
                  :key="key"
                >
                  <th>{{ t(key) }}</th>
                  <td v-for="r in chosen" :key="r.id">
                    <StatusBadge :value="r[key]" :locale="locale" />
                  </td>
                </tr>
                <tr
                  v-for="key in ['calls', 'tokens', 'seconds', 'cost'] as const"
                  :key="key"
                >
                  <th>{{ t(key) }}</th>
                  <td v-for="r in chosen" :key="r.id">{{ format(r[key]) }}</td>
                </tr>
                <tr>
                  <th>{{ t("faults") }}</th>
                  <td v-for="r in chosen" :key="r.id">
                    {{ r.hFaults ?? "—" }} / {{ r.aFaults ?? "—" }}
                  </td>
                </tr>
                <tr
                  v-for="key in [
                    'task',
                    'instance',
                    'oracle',
                    'human',
                    'protocol',
                    'budget',
                    'dataset',
                  ] as const"
                  :key="key"
                >
                  <th>{{ key }}</th>
                  <td v-for="r in chosen" :key="r.id" class="mono">
                    {{ r.versions[key] }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <template v-else-if="compareTab === 'artifactCompare'"
            ><div class="artifact-selector">
              <label v-for="item in artifactChoices" :key="item.artifact.id"
                ><input
                  type="checkbox"
                  :checked="
                    activeArtifacts.some(
                      (a) => a.artifact.id === item.artifact.id,
                    )
                  "
                  @change="toggleArtifact(item.artifact.id)"
                />{{ item.run.id }} · {{ text(item.artifact.title) }}</label
              >
            </div>
            <p v-if="!artifactsCompatible" class="notice-strip">
              {{ t("artifactMismatch") }}
            </p>
            <label class="check-line"
              ><input
                type="checkbox"
                v-model="differencesOnly"
                :disabled="!artifactsCompatible || activeArtifacts.some(x=>x.artifact.type!=='table')"
              />{{ t("differences") }}</label
            >
            <div class="compare-columns">
              <section v-for="item in activeArtifacts" :key="item.artifact.id">
                <h3 class="mono">
                  {{ item.run.id }} · {{ item.run.condition }}
                </h3>
                <ArtifactTable
                  :artifact="item.artifact"
                  :locale="locale"
                  :rows="artifactRows(item.artifact)"
                /><button @click="download(item.artifact, item.artifact.id)">
                  {{ t("download") }}
                </button>
              </section>
            </div>
            <p v-if="!activeArtifacts.length" class="empty">
              {{ t("noArtifact") }}
            </p></template
          >
          <div v-else class="compare-columns">
            <section v-for="r in chosen" :key="r.id" class="mini-timeline">
              <h3 class="mono">{{ r.id }} · {{ r.condition }}</h3>
              <template v-if="compareDetails[r.id]"
                ><button
                  v-for="e in compareDetails[r.id]!.events"
                  :key="e.id"
                  @click="
                    nav({
                      page: 'runs',
                      run: r.id,
                      event: e.id,
                      tab: 'timeline',
                    })
                  "
                >
                  <span class="actor-pill" :class="e.actor">{{ e.actor }}</span
                  ><span class="mono">{{ e.id }}</span
                  ><strong>{{ text(e.title) }}</strong>
                </button></template
              >
              <p v-else>{{ t("loading") }}</p>
            </section>
          </div></template
        ></template
      >

      <template v-else-if="page === 'methods'"
        ><div class="methods-layout">
          <nav class="method-nav">
            <a
              v-for="m in data.methods"
              :key="m.id"
              :href="'#method-' + m.id"
              @click.prevent="scrollMethod(m.id)"
              >{{ text(m.title) }}</a
            >
          </nav>
          <div class="method-body">
            <section
              v-for="m in data.methods"
              :key="m.id"
              :id="'method-' + m.id"
              class="method-section"
            >
              <span class="eyebrow">{{
                String(data.methods.indexOf(m) + 1).padStart(2, "0")
              }}</span>
              <h2>{{ text(m.title) }}</h2>
              <p>{{ text(m.body) }}</p>
            </section>
            <section class="method-section">
              <h2>{{ t("versionHistory") }}</h2>
              <dl class="definition-list">
                <div>
                  <dt>{{ t("release") }}</dt>
                  <dd class="mono">{{ manifest.release_id }}</dd>
                </div>
                <div>
                  <dt>UTC</dt>
                  <dd>{{ manifest.created_at }}</dd>
                </div>
                <div>
                  <dt>{{ t("reviewScope") }}</dt>
                  <dd>{{ t("draft") }}</dd>
                </div>
              </dl>
              <p>{{ t("manifestNote") }}</p>
              <button @click="download(manifest, 'bioduet-release-manifest')">
                {{ t("manifest") }} ↓
              </button>
              <details class="disclosure">
                <summary>
                  SHA-256 · {{ manifest.files.length }}
                  {{ locale === "en" ? "files" : "个文件" }}
                </summary>
                <div
                  v-for="f in manifest.files"
                  :key="f.path"
                  class="file-check"
                >
                  <code>{{ f.path }}</code
                  ><span>{{ format(f.bytes) }} B</span
                  ><code>{{ f.sha256 }}</code>
                </div>
              </details>
            </section>
          </div>
        </div></template
      >
    </template>
    <footer class="site-footer">
      <span
        >BioDuet <span class="muted">/ {{ t("footer") }}</span></span
      ><span>{{ t("noRanking") }}</span>
    </footer>
  </main>
  <div class="toast" role="status" aria-live="polite" v-if="notice">
    <span>{{ notice }}</span
    ><button :aria-label="t('close')" @click="notice = ''">×</button>
  </div>
  <dialog ref="drawer" class="drawer" @close="lastFocus?.focus()">
    <template v-if="drawerTask"
      ><header>
        <span class="mono">{{ drawerTask.id }} / v{{ drawerTask.version }}</span
        ><button @click="closeDrawer" :aria-label="t('close')">×</button>
      </header>
      <div class="drawer-body">
        <span class="eyebrow">{{ t(drawerTask.category) }}</span>
        <h2>{{ text(drawerTask.title) }}</h2>
        <h3>{{ t("taskQuestion") }}</h3>
        <p>{{ text(drawerTask.question) }}</p>
        <div class="role-pair">
          <section>
            <h3>{{ t("human") }}</h3>
            <p>{{ text(drawerTask.human) }}</p>
          </section>
          <section>
            <h3>{{ t("agent") }}</h3>
            <p>{{ text(drawerTask.agent) }}</p>
          </section>
        </div>
        <h3>{{ t("h0") }}</h3>
        <p>{{ text(drawerTask.h0) }}</p>
        <h3>{{ t("h1") }}</h3>
        <p>{{ text(drawerTask.h1) }}</p>
        <template v-if="drawerRun"
          ><hr />
          <h3 class="mono">{{ drawerRun.id }}</h3>
          <dl class="compact-meta">
            <div>
              <dt>{{ t("technical") }}</dt>
              <dd>
                <StatusBadge :value="drawerRun.technical" :locale="locale" />
              </dd>
            </div>
            <div>
              <dt>{{ t("scientific") }}</dt>
              <dd>
                <StatusBadge :value="drawerRun.scientific" :locale="locale" />
              </dd>
            </div>
          </dl>
          <div class="button-row">
            <button class="primary" @click="inspect(drawerRun)">
              {{ t("details") }} →</button
            ><button @click="toggle(drawerRun.id)">
              {{ t(selected.includes(drawerRun.id) ? "remove" : "add") }}
            </button>
          </div></template
        ><template v-else
          ><h3>{{ t("related") }}</h3>
          <div class="related-runs">
            <button
              v-for="r in data?.runs.filter((r) => r.taskId === drawerTask!.id)"
              :key="r.id"
              @click="inspect(r)"
            >
              {{ r.id }} · {{ r.condition }} →
            </button>
            <p v-if="!data?.runs.some((r) => r.taskId === drawerTask!.id)">
              {{ t("not_run") }}
            </p>
          </div></template
        >
        <p class="fine">{{ t("taskNote") }}</p>
      </div></template
    >
  </dialog>
</template>
