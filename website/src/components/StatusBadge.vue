<script setup lang="ts">
import { ui, type Key } from "../locales";
import type { Locale } from "../schema";
defineProps<{ value: string; locale: Locale }>();
</script>
<template>
  <span class="badge" :class="value"
    ><span aria-hidden="true">{{
      value === "passed"
        ? "✓"
        : value === "failed"
          ? "×"
          : value === "restricted"
            ? "◇"
            : "·"
    }}</span>
    {{ ui(locale, (value === "demo" ? "demoReview" : value) as Key) }}</span
  >
</template>
