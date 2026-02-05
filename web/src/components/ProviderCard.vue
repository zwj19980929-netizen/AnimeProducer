<template>
  <div class="p-4 bg-gray-700/50 rounded-lg border" :class="borderClass">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <span class="text-white font-medium capitalize">{{ name }}</span>
        <n-tag v-if="isCurrent" type="info" size="small">当前</n-tag>
      </div>
      <n-button
        size="small"
        :type="buttonType"
        :loading="testing"
        @click="$emit('test')"
      >
        测试
      </n-button>
    </div>

    <!-- Config Info -->
    <div class="space-y-1 text-sm">
      <div class="flex items-center gap-2">
        <span :class="providerConfig?.configured ? 'text-green-400' : 'text-red-400'">
          {{ providerConfig?.configured ? '✓' : '✗' }}
        </span>
        <span class="text-gray-400">
          {{ providerConfig?.configured ? '已配置' : '未配置' }}
        </span>
      </div>
      <div v-if="providerConfig?.key" class="text-gray-500 font-mono text-xs">
        Key: {{ providerConfig.key }}
      </div>
      <div v-if="providerConfig?.model" class="text-gray-500 text-xs">
        模型: {{ providerConfig.model }}
      </div>
      <div v-if="providerConfig?.endpoint" class="text-gray-500 text-xs truncate" :title="providerConfig.endpoint">
        端点: {{ providerConfig.endpoint }}
      </div>
      <div v-if="providerConfig?.region" class="text-gray-500 text-xs">
        区域: {{ providerConfig.region }}
      </div>
    </div>

    <!-- Test Result -->
    <div v-if="testResult" class="mt-3 pt-3 border-t border-gray-600">
      <TestResultBadge :result="testResult" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NTag } from 'naive-ui'
import type { ProviderTestResult, ProviderConfig } from '@/types/api'
import TestResultBadge from './TestResultBadge.vue'

const props = defineProps<{
  name: string
  config: ProviderConfig | string | undefined
  testResult?: ProviderTestResult
  testing: boolean
  isCurrent: boolean
}>()

defineEmits<{
  test: []
}>()

const providerConfig = computed(() => {
  if (typeof props.config === 'object') {
    return props.config as ProviderConfig
  }
  return undefined
})

const borderClass = computed(() => {
  if (!props.testResult) {
    return 'border-gray-600'
  }
  switch (props.testResult.status) {
    case 'success':
      return 'border-green-500/50'
    case 'failed':
      return 'border-red-500/50'
    case 'skipped':
      return 'border-gray-500/50'
    default:
      return 'border-gray-600'
  }
})

const buttonType = computed(() => {
  if (!props.testResult) {
    return 'default'
  }
  switch (props.testResult.status) {
    case 'success':
      return 'success'
    case 'failed':
      return 'error'
    default:
      return 'default'
  }
})
</script>
