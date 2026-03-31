<template>
  <div class="metric-card">
    <div class="micro-label muted" style="font-size: 10px;">{{ label }}</div>
    <div class="headline-md" style="margin-top: 10px;">{{ value }}</div>
    <div v-if="hint" class="body-sm muted" style="margin-top: 8px;">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
}>()
</script>
