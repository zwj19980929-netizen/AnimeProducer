<template>
  <n-tag
    :type="statusConfig.type"
    :bordered="false"
    size="small"
    class="font-medium"
  >
    {{ statusConfig.label }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NTag } from 'naive-ui'
import type { ChapterStatus } from '@/types/api'

const props = defineProps<{
  status: ChapterStatus
}>()

const statusConfig = computed(() => {
  const configs: Record<ChapterStatus, { label: string; type: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
    PENDING: { label: '待处理', type: 'default' },
    EXTRACTING: { label: '提取中', type: 'warning' },
    READY: { label: '就绪', type: 'success' },
    FAILED: { label: '失败', type: 'error' }
  }
  return configs[props.status]
})
</script>
