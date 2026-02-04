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
import type { ProjectStatus } from '@/types/api'

const props = defineProps<{
  status: ProjectStatus
}>()

const statusConfig = computed(() => {
  const configs: Record<ProjectStatus, { label: string; type: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
    DRAFT: { label: '草稿', type: 'default' },
    ASSETS_READY: { label: '资源就绪', type: 'info' },
    STORYBOARD_READY: { label: '故事板就绪', type: 'info' },
    RENDERING: { label: '渲染中', type: 'warning' },
    COMPOSITED: { label: '合成完成', type: 'warning' },
    DONE: { label: '完成', type: 'success' },
    FAILED: { label: '失败', type: 'error' }
  }
  return configs[props.status]
})
</script>
