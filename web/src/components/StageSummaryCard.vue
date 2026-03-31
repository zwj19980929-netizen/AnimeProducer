<template>
  <article class="surface-card stage-card">
    <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
      <div>
        <div class="micro-label muted" style="font-size: 10px;">{{ stage.label }}</div>
        <div class="headline-sm" style="margin-top: 6px;">{{ percent }}%</div>
      </div>
      <StatusPill :value="stage.status" />
    </div>

    <div class="progress-track">
      <div
        class="progress-bar"
        :class="{ ai: stage.key === 'CHAPTER_ANALYSIS' || stage.key === 'EPISODE_PLANNING', success: stage.status === 'COMPLETED' }"
        :style="{ width: `${percent}%` }"
      />
    </div>

    <div class="body-sm muted" v-if="metricText">{{ metricText }}</div>
    <div class="body-sm" v-if="stage.blockers.length" style="color: var(--danger);">{{ stage.blockers[0] }}</div>

    <router-link v-if="stage.primary_action" :to="stage.primary_action.target" class="btn btn-ghost" style="width: 100%;">
      {{ stage.primary_action.label }}
    </router-link>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import StatusPill from '@/components/StatusPill.vue'
import type { StageSummary } from '@/types/workbench'

const props = defineProps<{
  stage: StageSummary
}>()

const percent = computed(() => Math.round(props.stage.progress * 100))

const metricText = computed(() => {
  const entries = Object.entries(props.stage.metrics || {}).filter(([, value]) => value !== null && value !== undefined && value !== false)
  if (!entries.length) return ''
  return entries
    .slice(0, 2)
    .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${value}`)
    .join(' · ')
})
</script>
