<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center gap-2">
      <span :class="statusClass">{{ statusIcon }}</span>
      <span :class="textClass">{{ statusText }}</span>
      <span v-if="result.latency_ms" class="text-gray-500 text-xs">
        {{ result.latency_ms.toFixed(0) }}ms
      </span>
    </div>
    <div v-if="result.message && result.status !== 'success'" class="text-xs text-gray-400 truncate" :title="result.message">
      {{ result.message }}
    </div>
    <div v-if="result.details" class="text-xs text-gray-500">
      <span v-for="(value, key) in result.details" :key="key" class="mr-2">
        {{ key }}: {{ value }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProviderTestResult } from '@/types/api'

const props = defineProps<{
  result: ProviderTestResult
}>()

const statusIcon = computed(() => {
  switch (props.result.status) {
    case 'success':
      return '✓'
    case 'failed':
      return '✗'
    case 'skipped':
      return '○'
    default:
      return '?'
  }
})

const statusText = computed(() => {
  switch (props.result.status) {
    case 'success':
      return '连接成功'
    case 'failed':
      return '连接失败'
    case 'skipped':
      return '已跳过'
    default:
      return '未知'
  }
})

const statusClass = computed(() => {
  switch (props.result.status) {
    case 'success':
      return 'text-green-400'
    case 'failed':
      return 'text-red-400'
    case 'skipped':
      return 'text-gray-400'
    default:
      return 'text-gray-400'
  }
})

const textClass = computed(() => {
  switch (props.result.status) {
    case 'success':
      return 'text-green-400 text-sm'
    case 'failed':
      return 'text-red-400 text-sm'
    case 'skipped':
      return 'text-gray-400 text-sm'
    default:
      return 'text-gray-400 text-sm'
  }
})
</script>
