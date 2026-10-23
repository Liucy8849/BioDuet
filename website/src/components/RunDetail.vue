<script setup lang="ts">
import { computed, ref, watch, nextTick } from "vue";
import type { Run, Detail, Locale } from "../schema";
import { ui, type Key } from "../locales";
import StatusBadge from "./StatusBadge.vue";
import ArtifactTable from "./ArtifactTable.vue";
const props = defineProps<{
  run: Run;
  detail: Detail;
  locale: Locale;
  tab: string;
  eventId: string;
}>();
const emit = defineEmits<{
  navigate: [patch: Record<string, string>];
  download: [value: unknown, name: string];
}>();
const t = (key: Key) => ui(props.locale, key);
const actor = ref("all"),
  query = ref("");
const events = computed(() =>
  props.detail.events.filter(
    (e) =>
      (actor.value === "all" || e.actor === actor.value) &&
      `${e.id} ${e.title[props.locale]} ${e.body}`
        .toLowerCase()
        .includes(query.value.toLowerCase()),
  ),
);
const selected = computed(() =>
  props.eventId
    ? props.detail.events.find((e) => e.id === props.eventId)
    : events.value[0],
);
const eventIndex = computed(() =>
  props.detail.events.findIndex((e) => e.id === selected.value?.id),
);
const revisions = computed(() => props.detail.events.filter((e) => e.object));
const tabs = [
  "timeline",
  "objects",
  "artifacts",
  "judgment",
  "provenance",
] as const;
function choose(id: string) {
  emit("navigate", { event: id, tab: "timeline" });
}
watch(
  () => props.eventId,
  async () => {
    await nextTick();
    document
      .getElementById("event-" + props.eventId)
      ?.scrollIntoView({ block: "nearest", behavior: "instant" });
  },
);
</script>
<template>
  <div class="run-overview">
    <div class="outcome-grid">
      <div
        v-for="key in [
          'technical',
          'strict',
          'scientific',
          'authorization',
        ] as const"
        :key="key"
      >
        <span>{{ t(key) }}</span
        ><StatusBadge :value="run[key]" :locale="locale" />
      </div>
    </div>
    <dl class="run-facts">
      <div>
        <dt>{{ t("mode") }}</dt>
        <dd>{{ t(run.mode) }} · {{ t(run.timing) }}</dd>
      </div>
      <div>
        <dt>{{ t("termination") }}</dt>
        <dd>{{ t(run.termination) }}</dd>
      </div>
      <div>
        <dt>{{ t("faults") }}</dt>
        <dd>{{ run.hFaults ?? "—" }} / {{ run.aFaults ?? "—" }}</dd>
      </div>
      <div>
        <dt>{{ t("calls") }}</dt>
        <dd>{{ run.calls ?? "—" }}</dd>
      </div>
    </dl>
  </div>
  <nav
    class="subtabs"
    :aria-label="locale === 'en' ? 'Run sections' : '运行分区'"
  >
    <button
      v-for="item in tabs"
      :key="item"
      :class="{ active: tab === item }"
      :aria-current="tab === item ? 'page' : undefined"
      @click="emit('navigate', { tab: item })"
    >
      {{ t(item) }}
    </button>
  </nav>
  <template v-if="tab === 'timeline'">
    <div class="toolbar">
      <label
        >{{ t("actor")
        }}<select v-model="actor">
          <option value="all">{{ t("all") }}</option>
          <option v-for="a in ['H', 'A', 'world', 'worker', 'oracle']" :key="a">
            {{ a }}
          </option>
        </select></label
      ><label class="grow"
        >{{ t("eventSearch")
        }}<input v-model="query" :placeholder="t('eventSearch')" /></label
      ><span class="muted"
        >{{ events.length }} / {{ detail.events.length }} {{ t("event") }}</span
      >
    </div>
    <div class="timeline-layout">
      <section class="timeline" :aria-label="t('timeline')">
        <div class="lane-labels">
          <span>{{ t("sequence") }}</span
          ><span>{{ t("human") }}</span
          ><span>{{ t("agent") }}</span>
        </div>
        <ol>
          <li
            v-for="e in events"
            :key="e.id"
            :id="'event-' + e.id"
            :class="['lane-' + e.actor, { chosen: selected?.id === e.id }]"
          >
            <span class="event-index mono"
              >{{ String(e.sequence).padStart(2, "0")
              }}<small>t{{ e.tick ?? "—" }}</small></span
            ><button
              class="event-card"
              :aria-pressed="selected?.id === e.id"
              @click="choose(e.id)"
            >
              <span class="event-top"
                ><span class="actor-pill" :class="e.actor">{{ e.actor }}</span
                ><span>{{ t(e.kind) }}</span
                ><span class="mono">{{ e.id }}</span></span
              ><strong>{{ e.title[locale] }}</strong
              ><span v-if="e.object" class="event-change mono"
                >{{ e.object }} · {{ e.before }} → {{ e.after }}</span
              >
            </button>
          </li>
        </ol>
        <p v-if="!events.length" class="empty-small">{{ t("empty") }}</p>
      </section>
      <aside v-if="selected" class="evidence-panel">
        <div class="eyebrow">{{ t("event") }} / {{ selected.id }}</div>
        <h3>{{ selected.title[locale] }}</h3>
        <dl class="compact-meta">
          <div>
            <dt>{{ t("source") }}</dt>
            <dd>{{ t(selected.source) }}</dd>
          </div>
          <div>
            <dt>{{ t("visibility") }}</dt>
            <dd>{{ t(selected.visibility) }}</dd>
          </div>
          <div>
            <dt>{{ t("parents") }}</dt>
            <dd>
              <button
                v-for="p in selected.parents"
                :key="p"
                class="text-button mono"
                @click="choose(p)"
              >
                {{ p }}</button
              ><span v-if="!selected.parents.length">{{ t("none") }}</span>
            </dd>
          </div>
        </dl>
        <h4>{{ t("original") }}</h4>
        <p class="original-text" lang="en">{{ selected.body }}</p>
        <p class="fine">{{ t("translationNote") }}</p>
        <StatusBadge :value="selected.decision" :locale="locale" />
        <div class="button-row">
          <button
            :disabled="eventIndex === 0"
            @click="choose(detail.events[eventIndex - 1]!.id)"
          >
            ← {{ t("event") }}</button
          ><button
            :disabled="eventIndex === detail.events.length - 1"
            @click="choose(detail.events[eventIndex + 1]!.id)"
          >
            {{ t("event") }} →
          </button>
        </div>
      </aside>
      <aside v-else class="evidence-panel">
        <p>{{ t("eventNotFound") }}</p>
        <button @click="emit('navigate', { event: '' })">
          {{ t("reset") }}
        </button>
      </aside>
    </div>
  </template>
  <section v-else-if="tab === 'objects'" class="panel">
    <h2>{{ t("objects") }}</h2>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>{{ t("object") }}</th>
            <th>{{ t("before") }}</th>
            <th>{{ t("after") }}</th>
            <th>{{ t("basis") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in revisions" :key="e.id">
            <td class="mono">{{ e.object }}</td>
            <td>{{ e.before }}</td>
            <td>{{ e.after }}</td>
            <td>
              <button class="text-button" @click="choose(e.id)">
                {{ e.id }} ↗
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <details class="disclosure">
      <summary>{{ t("oldResults") }}</summary>
      <p>{{ t("oldResultsNote") }}</p>
    </details>
  </section>
  <section v-else-if="tab === 'artifacts'" class="artifact-list">
    <template v-for="a in detail.artifacts" :key="a.id"
      ><ArtifactTable :artifact="a" :locale="locale" />
      <div class="button-row">
        <button @click="choose(a.eventId)">{{ t("basis") }} ↗</button
        ><button @click="emit('download', a, a.id)">{{ t("download") }}</button>
      </div></template
    >
    <div v-if="!detail.artifacts.length" class="empty">
      <h2>{{ t("noArtifact") }}</h2>
      <p>{{ t("termination") }}: {{ t(run.termination) }}</p>
    </div>
  </section>
  <section v-else-if="tab === 'judgment'" class="panel prose">
    <h2>{{ t("output") }}</h2>
    <p class="original-text" lang="en">{{ detail.judgment.output }}</p>
    <h2>{{ t("explanation") }}</h2>
    <StatusBadge :locale="locale" :value="detail.judgment.status" />
    <p>{{ detail.judgment.explanation[locale] }}</p>
    <p>
      {{ t("rule") }}: <code>{{ detail.judgment.ruleId }}</code>
    </p>
    <div class="button-row">
      <button
        v-for="id in detail.judgment.evidenceRefs"
        :key="id"
        @click="choose(id)"
      >
        {{ t("basis") }} {{ id }} ↗
      </button>
    </div>
    <details class="disclosure">
      <summary>{{ t("structured") }}</summary>
      <pre>{{ JSON.stringify(detail.judgment, null, 2) }}</pre>
      <button @click="emit('download', detail.judgment, run.id + '-judgment')">
        {{ t("exportJSON") }}
      </button>
    </details>
  </section>
  <section v-else class="panel prose">
    <h2>{{ t("provenance") }}</h2>
    <p>{{ t("reviewNote") }}</p>
    <dl class="definition-list">
      <div>
        <dt>{{ t("sourceCommit") }}</dt>
        <dd>{{ detail.sourceCommit ?? t("not_reported") }}</dd>
      </div>
      <div>
        <dt>{{ t("source") }}</dt>
        <dd>{{ detail.sourceSet }}</dd>
      </div>
      <div>
        <dt>{{ t("coverageLabel") }}</dt>
        <dd>{{ detail.coverage[locale] }}</dd>
      </div>
      <div v-for="(value, key) in run.versions" :key="key">
        <dt>{{ key }}</dt>
        <dd>{{ value }}</dd>
      </div>
    </dl>
    <details class="disclosure">
      <summary>{{ t("fullConfig") }}</summary>
      <pre>{{ JSON.stringify(run, null, 2) }}</pre>
    </details>
  </section>
</template>
