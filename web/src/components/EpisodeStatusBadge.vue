<template>
  <n-tag :type="tagType" size="small">
    {{ label }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NTag } from 'naive-ui'
import { EpisodeStatus } from '@/types/api'

const props = defineProps<{
  status: EpisodeStatus
}>()

const statusConfig: Record<EpisodeStatus, { label: string; type: 'default' | 'info' | 'success' | 'warning' | 'error' }> = {
  [EpisodeStatus.PLANNED]: { label: '已规划', type: 'default' },
  [EpisodeStatus.STORYBOARD_READY]: { label: '分镜就绪', type: 'info' },
  [EpisodeStatus.RENDERING]: { label: '渲染中', type: 'warning' },
  [EpisodeStatus.DONE]: { label: '已完成', type: 'success' },
  [EpisodeStatus.FAILED]: { label: '失败', type: 'error' }
}

const label = computed(() => statusConfig[props.status]?.label || props.status)
const tagType = computed(() => statusConfig[props.status]?.type || 'default')
</script>
