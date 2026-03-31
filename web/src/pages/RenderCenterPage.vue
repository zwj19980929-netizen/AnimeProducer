<template>
  <template v-if="workspace">
    <section class="surface-card hero-card">
      <div class="hero-row">
        <div class="stack" style="gap: 10px; max-width: 760px;">
          <div class="micro-label muted" style="font-size: 10px;">Render Center</div>
          <div class="headline-lg">让渲染从黑盒按钮，变成可追踪的生产批次。</div>
          <div class="body-lg muted">
            只对已经完成分镜的分集开放渲染，运行中、失败和已完成状态会被清楚拆开，不再把所有任务揉在一个列表里。
          </div>
        </div>

        <div class="stack" style="min-width: 320px; gap: 12px;">
          <StatusPill :value="renderActive.length ? 'IN_PROGRESS' : renderFailures.length ? 'FAILED' : workspace.deliveries.length ? 'COMPLETED' : 'NOT_STARTED'" />
          <div class="button-row">
            <button class="btn btn-primary" :disabled="startingEpisodeNumber !== null || !selectedRenderableEpisode" @click="startSelectedRender">
              {{ startingEpisodeNumber !== null ? '启动中…' : '启动选中分集渲染' }}
            </button>
            <button class="btn btn-ghost" @click="() => refreshWorkspace()">刷新状态</button>
          </div>
        </div>
      </div>

      <div v-if="actionError" class="danger-box body-sm">{{ actionError }}</div>
      <div v-else-if="actionInfo" class="info-box body-sm">{{ actionInfo }}</div>
    </section>

    <section class="content-grid">
      <article class="surface-card section-card col-span-5 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Launchpad</div>
          <div class="headline-md" style="margin-top: 6px;">可渲染分集</div>
        </div>

        <EmptyState
          v-if="renderableEpisodes.length === 0"
          title="还没有可渲染的分集"
          description="只有当一集已经拥有分镜时，渲染中心才会允许你启动生产任务。"
        />

        <div v-else class="stack">
          <button
            v-for="episode in renderableEpisodes"
            :key="episode.id"
            class="list-card"
            :class="{ 'is-active': selectedEpisodeNumber === episode.episode_number }"
            @click="selectedEpisodeNumber = episode.episode_number"
          >
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
              <div class="stack" style="gap: 4px; text-align: left;">
                <div class="headline-sm">EP{{ episode.episode_number.toString().padStart(2, '0') }} · {{ episode.title || '未命名分集' }}</div>
                <div class="body-sm muted">{{ episode.shot_count }} 个镜头 · {{ episode.target_duration_minutes }} 分钟目标时长</div>
              </div>
              <StatusPill :value="episode.status" />
            </div>
          </button>

          <article v-if="selectedRenderableEpisode" class="surface-panel section-card stack">
            <div>
              <div class="micro-label muted" style="font-size: 10px;">Selected Episode</div>
              <div class="headline-sm" style="margin-top: 6px;">EP{{ selectedRenderableEpisode.episode_number.toString().padStart(2, '0') }}</div>
            </div>
            <div class="body-sm muted">{{ selectedRenderableEpisode.synopsis || '当前分集还没有补充分集摘要。' }}</div>
            <div class="chip-row">
              <span class="chip">镜头 {{ selectedRenderableEpisode.shot_count }}</span>
              <span class="chip">章节 {{ selectedRenderableEpisode.start_chapter }} - {{ selectedRenderableEpisode.end_chapter }}</span>
              <span class="chip">交付 {{ selectedRenderableEpisode.has_delivery ? '已产出' : '未产出' }}</span>
            </div>
            <button class="btn btn-secondary" :disabled="startingEpisodeNumber !== null" @click="startRender(selectedRenderableEpisode.episode_number)">
              启动这一集渲染
            </button>
          </article>
        </div>
      </article>

      <article class="surface-card section-card col-span-7 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Batches</div>
          <div class="headline-md" style="margin-top: 6px;">批次状态</div>
        </div>

        <section class="stack">
          <div class="headline-sm">运行中批次</div>
          <EmptyState
            v-if="renderActive.length === 0"
            title="没有运行中的渲染任务"
            description="当你启动渲染后，这里会固定置顶显示当前批次和实时进度。"
          />

          <article
            v-for="operation in renderActive"
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
            <button class="btn btn-ghost" @click="cancelOperation(operation.id)">取消任务</button>
          </article>
        </section>

        <section class="stack">
          <div class="headline-sm">失败批次</div>
          <EmptyState
            v-if="renderFailures.length === 0"
            title="没有失败批次"
            description="失败会被单独高亮，这样你能直接定位恢复，而不是在长列表里找错。"
          />

          <article
            v-for="operation in renderFailures"
            :key="operation.id"
            class="surface-panel section-card stack"
            style="gap: 10px;"
          >
            <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
              <div class="stack" style="gap: 4px;">
                <div class="headline-sm">{{ operation.label }}</div>
                <div class="body-sm muted">{{ formatDate(operation.created_at) }}</div>
              </div>
              <StatusPill :value="operation.status" />
            </div>
            <div class="danger-box body-sm">{{ operation.error_message || '任务失败，但没有返回明确错误信息。' }}</div>
          </article>
        </section>

        <section class="stack">
          <div class="headline-sm">已完成交付</div>
          <EmptyState
            v-if="workspace.deliveries.length === 0"
            title="还没有交付产出"
            description="渲染完成后，交付记录会自动进入这里，并同步展示在交付输出页。"
          />

          <article
            v-for="delivery in workspace.deliveries"
            :key="delivery.episode_id"
            class="surface-panel section-card stack"
            style="gap: 8px;"
          >
            <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
              <div class="stack" style="gap: 4px;">
                <div class="headline-sm">EP{{ delivery.episode_number.toString().padStart(2, '0') }} · {{ delivery.title || delivery.version_label }}</div>
                <div class="body-sm muted">{{ formatDate(delivery.updated_at) }}</div>
              </div>
              <StatusPill value="COMPLETED" label="已交付" />
            </div>
            <router-link class="btn btn-ghost" :to="{ name: 'delivery-output', params: { id: workspace.project.id } }">
              去交付页预览
            </router-link>
          </article>
        </section>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'

const RENDER_OPERATION_TYPES = new Set(['SHOT_RENDER', 'VIDEO_COMPOSITION', 'FULL_PIPELINE'])

const { workspace, refreshWorkspace } = useWorkbench()

const selectedEpisodeNumber = ref<number | null>(null)
const startingEpisodeNumber = ref<number | null>(null)
const actionError = ref('')
const actionInfo = ref('')

const renderableEpisodes = computed(() => (workspace.value?.episodes || []).filter((episode) => episode.shot_count > 0))
const selectedRenderableEpisode = computed(() => (
  renderableEpisodes.value.find((episode) => episode.episode_number === selectedEpisodeNumber.value) || null
))
const renderActive = computed(() => (workspace.value?.active_operations || []).filter((operation) => RENDER_OPERATION_TYPES.has(operation.type)))
const renderFailures = computed(() => (workspace.value?.recent_operations || []).filter((operation) => (
  RENDER_OPERATION_TYPES.has(operation.type) && operation.status === 'FAILURE'
)))

watch(
  renderableEpisodes,
  (episodes) => {
    if (!episodes.length) {
      selectedEpisodeNumber.value = null
      return
    }

    const firstEpisode = episodes[0]
    if ((!selectedEpisodeNumber.value || !episodes.some((episode) => episode.episode_number === selectedEpisodeNumber.value)) && firstEpisode) {
      selectedEpisodeNumber.value = firstEpisode.episode_number
    }
  },
  { immediate: true }
)

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

function startSelectedRender() {
  if (!selectedRenderableEpisode.value) return
  startRender(selectedRenderableEpisode.value.episode_number)
}

async function startRender(episodeNumber: number) {
  startingEpisodeNumber.value = episodeNumber
  actionError.value = ''
  actionInfo.value = ''

  try {
    const response = await api.startEpisodeRender(workspace.value!.project.id, episodeNumber)
    actionInfo.value = response.message || `EP${episodeNumber.toString().padStart(2, '0')} 的渲染任务已启动。`
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '启动渲染失败'
  } finally {
    startingEpisodeNumber.value = null
  }
}

async function cancelOperation(jobId: string) {
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.cancelJob(jobId)
    actionInfo.value = '渲染任务已取消。'
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '取消任务失败'
  }
}
</script>
