<template>
  <template v-if="workspace">
    <section class="surface-card hero-card">
      <div class="hero-row">
        <div class="stack" style="gap: 10px; max-width: 720px;">
          <div class="micro-label muted" style="font-size: 10px;">Project Dashboard</div>
          <div class="headline-lg">{{ workspace.project.name }}</div>
          <div class="body-lg muted">{{ workspace.project.description || '这里先看阶段、风险和下一步，再决定今天推进哪一环。' }}</div>
        </div>

        <div class="stack" style="min-width: 280px; gap: 12px;">
          <StatusPill :value="workspace.project.status" :label="workspace.project.current_stage_label" />
          <router-link
            v-if="workspace.project.next_action"
            class="btn btn-primary"
            :to="workspace.project.next_action.target"
          >
            {{ workspace.project.next_action.label }}
          </router-link>
        </div>
      </div>

      <div class="metric-grid">
        <MetricCard
          label="章节分析"
          :value="`${workspace.metrics.chapters_analyzed ?? 0} / ${workspace.metrics.chapters_total ?? 0}`"
          hint="解析后的章节是分集和角色扫描的基础。"
        />
        <MetricCard
          label="角色圣经"
          :value="`${workspace.metrics.anchors_ready ?? 0} / ${workspace.metrics.characters_total ?? 0}`"
          hint="锚点图决定了后续角色一致性。"
        />
        <MetricCard
          label="分镜进度"
          :value="`${workspace.metrics.episodes_storyboarded ?? 0} / ${workspace.metrics.episodes_total ?? 0}`"
          hint="分镜未齐时，渲染中心不应该成为主入口。"
        />
        <MetricCard
          label="交付输出"
          :value="String(workspace.metrics.deliveries_total ?? 0)"
          hint="只有形成交付资产，项目才算真正闭环。"
        />
      </div>
    </section>

    <section class="stage-grid">
      <StageSummaryCard
        v-for="stage in workspace.stage_summaries"
        :key="stage.key"
        :stage="stage"
      />
    </section>

    <section class="content-grid">
      <article class="surface-card section-card col-span-7 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Recent Operations</div>
          <div class="headline-md" style="margin-top: 6px;">最近操作与失败恢复</div>
        </div>

        <EmptyState
          v-if="workspace.recent_operations.length === 0"
          title="还没有操作记录"
          description="开始分析章节、生成角色图、规划分集或渲染后，这里会形成时间线。"
        />

        <article
          v-for="operation in workspace.recent_operations"
          :key="operation.id"
          class="surface-panel section-card stack"
          style="gap: 12px;"
        >
          <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
            <div class="stack" style="gap: 4px;">
              <div class="headline-sm">{{ operation.label }}</div>
              <div class="body-sm muted">{{ formatDate(operation.created_at) }}</div>
            </div>
            <StatusPill :value="operation.status" />
          </div>
          <div class="progress-track">
            <div class="progress-bar ai" :style="{ width: `${Math.round(operation.progress * 100)}%` }" />
          </div>
          <div v-if="operation.error_message" class="danger-box body-sm">{{ operation.error_message }}</div>
        </article>
      </article>

      <article class="surface-card section-card col-span-5 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Blockers</div>
          <div class="headline-md" style="margin-top: 6px;">当前卡点</div>
        </div>

        <EmptyState
          v-if="workspace.blockers.length === 0"
          title="没有明显阻塞"
          description="继续沿着当前阶段推进即可。"
        />

        <div
          v-for="blocker in workspace.blockers"
          :key="blocker"
          class="danger-box body-sm"
        >
          {{ blocker }}
        </div>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import MetricCard from '@/components/MetricCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import StageSummaryCard from '@/components/StageSummaryCard.vue'
import StatusPill from '@/components/StatusPill.vue'
import { useWorkbench } from '@/lib/useWorkbench'

const { workspace } = useWorkbench()

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
