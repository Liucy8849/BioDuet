<script setup lang="ts">
import type { Artifact, Locale } from "../schema";
import { ui } from "../locales";
import StatusBadge from "./StatusBadge.vue";
import {ref,watch} from "vue";
const props=defineProps<{ artifact: Artifact; locale: Locale; rows?: string[][] }>();
const imageError=ref(false);
watch(()=>props.artifact.id,()=>{imageError.value=false;});
</script>
<template>
  <article class="artifact">
    <div class="artifact-head">
      <h3>{{ artifact.title[locale] }}</h3>
      <StatusBadge :locale="locale" :value="artifact.status" />
    </div>
    <dl class="compact-meta">
      <div>
        <dt>{{ ui(locale, "method") }}</dt>
        <dd>{{ artifact.method }}</dd>
      </div>
      <div>
        <dt>{{ ui(locale, "unit") }}</dt>
        <dd>{{ artifact.unit }}</dd>
      </div>
      <div>
        <dt>{{ ui(locale, "input") }}</dt>
        <dd>{{ artifact.inputVersion }}</dd>
      </div>
    </dl>
    <div v-if="artifact.type==='table'" class="table-scroll" tabindex="0">
      <table>
        <thead>
          <tr>
            <th v-for="col in artifact.columns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows ?? artifact.rows" :key="i">
            <td v-for="(cell, j) in row" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <pre v-else-if="artifact.type==='text'" class="artifact-text">{{artifact.text}}</pre>
    <p v-else-if="imageError" role="alert">{{ui(locale,'previewError')}}</p><img v-else class="artifact-image" :src="artifact.imageData" :alt="artifact.title[locale]" loading="lazy" @error="imageError=true">
    <p class="hash">SHA-256 {{ artifact.sha256 }}</p>
  </article>
</template>
