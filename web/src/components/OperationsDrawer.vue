<template>
  <div v-if="open" class="drawer-backdrop" @click="$emit('close')" />
  <aside class="drawer" :class="{ 'is-open': open }">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
      <div>
        <div class="micro-label muted" style="font-size: 10px;">Production Console</div>
        <div class="headline-md">最近操作</div>
      </div>
      <button class="icon-button" @click="$emit('close')">×</button>
    </div>

    <section class="stack" style="margin-top: 24px;">
      <div class="headline-sm">运行中</div>
      <EmptyState
        v-if="active.length === 0"
        title="没有运行中的任务"
        description="当你开始分集规划、角色图生成或渲染任务时，这里会出现实时进度。"
      />
      <article v-for="operation in active" :key="operation.id" class="surface-card section-card stack" style="gap: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
          <div>
            <div class="headline-sm">{{ operation.label }}</div>
            <div class="body-sm muted">{{ formatDate(operation.created_at) }}</div>
          </div>
          <StatusPill :value="operation.status" />
        </div>
        <div class="progress-track">
          <div class="progress-bar ai" :style="{ width: `${Math.round(operation.progress * 100)}%` }" />
        </div>
      </article>
    </section>

    <section class="stack" style="margin-top: 32px;">
      <div class="headline-sm">最近完成与失败</div>
      <EmptyState
        v-if="recent.length === 0"
        title="还没有操作记录"
        description="工作台会把最近的资产生成、分镜生成和渲染任务都收拢到这里。"
      />
      <article v-for="operation in recent" :key="operation.id" class="surface-card section-card stack" style="gap: 10px;">
        <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
          <div class="stack" style="gap: 4px;">
            <div class="headline-sm">{{ operation.label }}</div>
            <div class="body-sm muted">{{ formatDate(operation.created_at) }}</div>
          </div>
          <StatusPill :value="operation.status" />
        </div>
        <div v-if="operation.error_message" class="danger-box body-sm">{{ operation.error_message }}</div>
      </article>
    </section>
  </aside>
</template>

<script setup lang="ts">
import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import type { OperationSummary } from '@/types/workbench'

defineProps<{
  open: boolean
  active: OperationSummary[]
  recent: OperationSummary[]
}>()

defineEmits<{
  close: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}
</script>
