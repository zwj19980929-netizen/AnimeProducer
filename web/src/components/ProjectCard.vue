<template>
  <article class="surface-card project-card" @click="$emit('open', project.id)">
    <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
      <div class="stack" style="gap: 8px;">
        <div class="micro-label muted" style="font-size: 10px;">{{ project.current_stage_label }}</div>
        <div class="headline-md">{{ project.name }}</div>
        <div class="body-sm muted">{{ project.description || '围绕章节拆解、角色一致性、分集分镜与交付组织整条制作线。' }}</div>
      </div>
      <StatusPill :value="project.status" :label="project.current_stage_label" />
    </div>

    <div class="progress-track">
      <div class="progress-bar" :style="{ width: `${Math.round(project.completion_rate * 100)}%` }" />
    </div>

    <div class="chip-row">
      <span class="chip">章节 {{ project.metrics.chapters_total ?? 0 }}</span>
      <span class="chip">角色 {{ project.metrics.characters_total ?? 0 }}</span>
      <span class="chip">分集 {{ project.metrics.episodes_total ?? 0 }}</span>
    </div>

    <div class="danger-box" v-if="project.blockers.length">
      <div class="body-sm">{{ project.blockers[0] }}</div>
    </div>

    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
      <div class="body-sm muted">更新于 {{ formatDate(project.updated_at) }}</div>
      <div class="btn btn-primary" style="padding-inline: 14px;">
        {{ project.next_action?.label || '进入项目' }}
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import StatusPill from '@/components/StatusPill.vue'
import type { ProjectCardSummary } from '@/types/workbench'

defineEmits<{
  open: [projectId: string]
}>()

defineProps<{
  project: ProjectCardSummary
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}
</script>
