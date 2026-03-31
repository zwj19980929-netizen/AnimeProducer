<template>
  <span :class="classes">
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: string
  label?: string
}>()

const normalized = computed(() => props.value.toLowerCase())

const classes = computed(() => {
  const base = ['status-pill']

  if (normalized.value.includes('success') || normalized.value.includes('done') || normalized.value.includes('completed') || normalized.value.includes('approved') || normalized.value.includes('ready')) {
    base.push('status-success')
  } else if (normalized.value.includes('review') || normalized.value.includes('warning')) {
    base.push('status-warning')
  } else if (normalized.value.includes('progress') || normalized.value.includes('start') || normalized.value.includes('running') || normalized.value.includes('pending')) {
    base.push('status-info')
  } else if (normalized.value.includes('failed') || normalized.value.includes('block')) {
    base.push('status-danger')
  } else {
    base.push('status-muted')
  }

  return base
})

const label = computed(() => props.label ?? props.value.replace(/_/g, ' '))
</script>
