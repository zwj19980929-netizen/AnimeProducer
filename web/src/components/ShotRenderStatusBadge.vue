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
import type { ShotRenderStatus } from '@/types/api'

const props = defineProps<{
  status: ShotRenderStatus
}>()

const statusConfig = computed(() => {
  const configs: Record<ShotRenderStatus, { label: string; type: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
    PENDING: { label: '待处理', type: 'default' },
    GENERATING_IMAGE: { label: '生成图片', type: 'warning' },
    GENERATING_VIDEO: { label: '生成视频', type: 'warning' },
    GENERATING_AUDIO: { label: '生成音频', type: 'warning' },
    COMPOSITING: { label: '合成中', type: 'warning' },
    SUCCESS: { label: '成功', type: 'success' },
    FAILURE: { label: '失败', type: 'error' }
  }
  return configs[props.status]
})
</script>
