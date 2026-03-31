<template>
  <div class="empty-state">
    <div class="headline-sm" style="margin-bottom: 8px;">{{ title }}</div>
    <div class="body-sm muted">{{ description }}</div>
    <div v-if="$slots.default" style="margin-top: 16px;">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>
