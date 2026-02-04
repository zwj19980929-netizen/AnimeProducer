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
import type { JobStatus } from '@/types/api'

const props = defineProps<{
  status: JobStatus
}>()

const statusConfig = computed(() => {
  const configs: Record<JobStatus, { label: string; type: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
    PENDING: { label: '待处理', type: 'default' },
    STARTED: { label: '运行中', type: 'warning' },
    SUCCESS: { label: '成功', type: 'success' },
    FAILURE: { label: '失败', type: 'error' },
    REVOKED: { label: '已取消', type: 'default' }
  }
  return configs[props.status]
})
</script>
