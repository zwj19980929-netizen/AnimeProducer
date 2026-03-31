<template>
  <template v-if="workspace">
    <section class="surface-card hero-card">
      <div class="hero-row">
        <div class="stack" style="gap: 10px; max-width: 720px;">
          <div class="micro-label muted" style="font-size: 10px;">Episode Planning</div>
          <div class="headline-lg">先看分集草案，再决定正式生产单元。</div>
          <div class="body-lg muted">
            这一页不再直接把章节生硬落库成分集，而是先给你一版可审阅、可微调的草案，再统一确认。
          </div>
        </div>

        <div class="stack" style="min-width: 320px; gap: 12px;">
          <StatusPill
            :value="workspace.episode_plan_draft?.status || (workspace.episodes.length ? 'COMPLETED' : 'NOT_STARTED')"
            :label="workspace.episodes.length ? '已确认分集' : '草案状态'"
          />
          <div class="button-row">
            <button class="btn btn-secondary" :disabled="planning || !analysisReady" @click="generateDraft">
              {{ planning ? '生成中…' : '生成分集草案' }}
            </button>
            <button class="btn btn-primary" :disabled="confirming || localSuggestions.length === 0 || workspace.episodes.length > 0" @click="confirmPlan">
              {{ confirming ? '确认中…' : '整版确认草案' }}
            </button>
            <button class="btn btn-ghost" :disabled="clearing || workspace.episodes.length === 0" @click="clearConfirmedEpisodes">
              {{ clearing ? '清空中…' : '清空当前分集' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="actionError" class="danger-box body-sm">{{ actionError }}</div>
      <div v-else-if="actionInfo" class="info-box body-sm">{{ actionInfo }}</div>
    </section>

    <section class="content-grid">
      <article class="surface-card section-card col-span-4 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Planning Controls</div>
          <div class="headline-md" style="margin-top: 6px;">规划参数</div>
        </div>

        <div class="form-grid">
          <div class="field-group">
            <label class="field-label">目标时长（分钟）</label>
            <input v-model.number="planningForm.target_episode_duration" type="number" min="5" max="120" class="text-input" />
          </div>

          <div class="field-group">
            <label class="field-label">最多分成几集</label>
            <input v-model.number="planningForm.max_episodes" type="number" min="1" max="100" class="text-input" placeholder="留空表示自动推断" />
          </div>

          <div class="field-group">
            <label class="field-label">节奏风格</label>
            <select v-model="planningForm.style" class="select-input">
              <option value="standard">标准番剧节奏</option>
              <option value="movie">电影化推进</option>
              <option value="short">短平快节奏</option>
            </select>
          </div>
        </div>

        <div class="surface-panel section-card stack">
          <div class="micro-label muted" style="font-size: 10px;">Readiness</div>
          <div class="chip-row">
            <span class="chip">章节 {{ workspace.chapters.length }}</span>
            <span class="chip">已分析 {{ analyzedChapterCount }}</span>
            <span class="chip">草案 {{ workspace.episode_plan_draft?.suggestions.length || 0 }}</span>
            <span class="chip">已确认 {{ workspace.episodes.length }}</span>
          </div>
          <div class="body-sm muted">
            {{ analysisReady ? '章节分析已完成，可以开始规划分集。' : '请先把全部章节分析完成，否则分集结果会非常不稳定。' }}
          </div>
        </div>

        <div v-if="workspace.episode_plan_draft?.reasoning" class="surface-panel section-card stack">
          <div class="micro-label muted" style="font-size: 10px;">AI Reasoning</div>
          <div class="body-sm muted">{{ workspace.episode_plan_draft.reasoning }}</div>
        </div>
      </article>

      <article class="surface-card section-card col-span-8 stack">
        <div style="display: flex; justify-content: space-between; align-items: end; gap: 12px;">
          <div>
            <div class="micro-label muted" style="font-size: 10px;">Coverage Strip</div>
            <div class="headline-md" style="margin-top: 6px;">章节覆盖关系图</div>
          </div>
          <div class="body-sm muted">
            {{ workspace.episodes.length ? '当前已确认方案' : '当前草案覆盖' }}
          </div>
        </div>

        <EmptyState
          v-if="chapterCoverage.length === 0"
          title="还没有可展示的覆盖关系"
          description="生成一版分集草案后，这里会直观看到每一章被分配到了哪一集。"
        />

        <div v-else class="stack" style="gap: 14px;">
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(74px, 1fr)); gap: 8px;">
            <article
              v-for="chapter in chapterCoverage"
              :key="chapter.chapter_number"
              class="surface-panel section-card"
              :style="{ padding: '12px', borderColor: chapter.color }"
            >
              <div class="micro-label muted" style="font-size: 10px;">Ch {{ chapter.chapter_number }}</div>
              <div class="headline-sm" style="margin-top: 8px;">{{ chapter.ownerLabel || '未覆盖' }}</div>
              <div class="body-sm muted" style="margin-top: 8px;">{{ chapter.title }}</div>
            </article>
          </div>

          <div class="chip-row">
            <span
              v-for="legend in coverageLegend"
              :key="legend.episode_number"
              class="chip"
              :style="{ border: `1px solid ${coverageColor(legend.episode_number)}` }"
            >
              EP{{ legend.episode_number.toString().padStart(2, '0') }} · {{ legend.title || '未命名分集' }}
            </span>
          </div>
        </div>
      </article>

      <article class="surface-card section-card col-span-7 stack">
        <div style="display: flex; justify-content: space-between; align-items: end; gap: 12px;">
          <div>
            <div class="micro-label muted" style="font-size: 10px;">Planning Draft</div>
            <div class="headline-md" style="margin-top: 6px;">草案卡片</div>
          </div>
          <StatusPill
            v-if="workspace.episode_plan_draft"
            :value="workspace.episode_plan_draft.status"
            :label="workspace.episode_plan_draft.updated_at ? `更新于 ${formatDate(workspace.episode_plan_draft.updated_at)}` : undefined"
          />
        </div>

        <EmptyState
          v-if="localSuggestions.length === 0"
          title="还没有分集草案"
          description="上方生成一版草案之后，你可以逐集改标题、章节范围和时长，再决定是否整体确认。"
        />

        <article
          v-for="suggestion in localSuggestions"
          :key="suggestion.episode_number"
          class="surface-panel section-card stack"
        >
          <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
            <div>
              <div class="micro-label muted" style="font-size: 10px;">Episode {{ suggestion.episode_number }}</div>
              <div class="headline-sm" style="margin-top: 6px;">草案 {{ suggestion.episode_number.toString().padStart(2, '0') }}</div>
            </div>
            <span class="chip" :style="{ border: `1px solid ${coverageColor(suggestion.episode_number)}` }">
              CH {{ suggestion.start_chapter }} - {{ suggestion.end_chapter }}
            </span>
          </div>

          <div class="form-grid" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
            <div class="field-group" style="grid-column: span 3;">
              <label class="field-label">分集标题</label>
              <input v-model.trim="suggestion.title" class="text-input" placeholder="填写这一集的标题" />
            </div>

            <div class="field-group">
              <label class="field-label">起始章节</label>
              <input v-model.number="suggestion.start_chapter" type="number" min="1" class="text-input" />
            </div>

            <div class="field-group">
              <label class="field-label">结束章节</label>
              <input v-model.number="suggestion.end_chapter" type="number" min="1" class="text-input" />
            </div>

            <div class="field-group">
              <label class="field-label">预计时长</label>
              <input v-model.number="suggestion.estimated_duration_minutes" type="number" min="1" class="text-input" />
            </div>

            <div class="field-group" style="grid-column: span 3;">
              <label class="field-label">剧情摘要</label>
              <textarea v-model="suggestion.synopsis" class="textarea-input" />
            </div>
          </div>
        </article>
      </article>

      <article class="surface-card section-card col-span-5 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Confirmed Episodes</div>
          <div class="headline-md" style="margin-top: 6px;">已确认分集</div>
        </div>

        <EmptyState
          v-if="workspace.episodes.length === 0"
          title="还没有正式分集"
          description="确认草案之后，分镜工作台和渲染中心才会获得稳定的生产单元。"
        />

        <div v-else class="stack">
          <button
            v-for="episode in workspace.episodes"
            :key="episode.id"
            class="list-card"
            :class="{ 'is-active': selectedEpisodeNumber === episode.episode_number }"
            @click="selectedEpisodeNumber = episode.episode_number"
          >
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
              <div class="stack" style="gap: 4px; text-align: left;">
                <div class="headline-sm">EP{{ episode.episode_number.toString().padStart(2, '0') }} · {{ episode.title || '未命名分集' }}</div>
                <div class="body-sm muted">CH {{ episode.start_chapter }} - {{ episode.end_chapter }} · {{ episode.shot_count }} 个镜头</div>
              </div>
              <StatusPill :value="episode.status" />
            </div>
          </button>

          <article v-if="selectedEpisode" class="surface-panel section-card stack">
            <div>
              <div class="micro-label muted" style="font-size: 10px;">Episode Editor</div>
              <div class="headline-sm" style="margin-top: 6px;">编辑已确认分集</div>
            </div>

            <div class="form-grid">
              <div class="field-group">
                <label class="field-label">标题</label>
                <input v-model.trim="episodeEditor.title" class="text-input" />
              </div>

              <div class="form-grid" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
                <div class="field-group">
                  <label class="field-label">起始章节</label>
                  <input v-model.number="episodeEditor.start_chapter" type="number" min="1" class="text-input" />
                </div>
                <div class="field-group">
                  <label class="field-label">结束章节</label>
                  <input v-model.number="episodeEditor.end_chapter" type="number" min="1" class="text-input" />
                </div>
                <div class="field-group">
                  <label class="field-label">目标时长</label>
                  <input v-model.number="episodeEditor.target_duration_minutes" type="number" min="1" class="text-input" />
                </div>
              </div>

              <div class="field-group">
                <label class="field-label">摘要</label>
                <textarea v-model="episodeEditor.synopsis" class="textarea-input" />
              </div>
            </div>

            <div class="button-row">
              <button class="btn btn-primary" :disabled="savingEpisode" @click="saveEpisode">
                {{ savingEpisode ? '保存中…' : '保存这一集' }}
              </button>
            </div>
          </article>
        </div>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'
import type { EpisodePlanSuggestionSummary, EpisodeWorkspaceItem } from '@/types/workbench'

interface CoverageItem {
  episode_number: number
  title: string
  start_chapter: number
  end_chapter: number
  duration: number
}

const COVERAGE_COLORS = ['#d95d39', '#2e6bff', '#1d8f6a', '#c68a12', '#b45eff', '#0ea5a3', '#c4473d', '#4c5dff']

const route = useRoute()
const { workspace, refreshWorkspace } = useWorkbench()

const planning = ref(false)
const confirming = ref(false)
const clearing = ref(false)
const savingEpisode = ref(false)
const actionError = ref('')
const actionInfo = ref('')

const localSuggestions = ref<EpisodePlanSuggestionSummary[]>([])
const selectedEpisodeNumber = ref<number | null>(null)

const planningForm = reactive({
  target_episode_duration: 24,
  max_episodes: undefined as number | undefined,
  style: 'standard'
})

const episodeEditor = reactive({
  title: '',
  synopsis: '',
  start_chapter: 1,
  end_chapter: 1,
  target_duration_minutes: 24
})

const projectId = computed(() => route.params.id as string)
const analyzedChapterCount = computed(() => workspace.value?.chapters.filter((chapter) => chapter.status === 'READY').length ?? 0)
const analysisReady = computed(() => {
  const chapters = workspace.value?.chapters || []
  return chapters.length > 0 && chapters.every((chapter) => chapter.status === 'READY')
})

const selectedEpisode = computed(() => (
  workspace.value?.episodes.find((episode) => episode.episode_number === selectedEpisodeNumber.value) || null
))

const coverageLegend = computed(() => chapterAssignments.value)

const chapterAssignments = computed<CoverageItem[]>(() => {
  if (workspace.value?.episodes.length) {
    return workspace.value.episodes.map((episode) => ({
      episode_number: episode.episode_number,
      title: episode.title || '',
      start_chapter: episode.start_chapter,
      end_chapter: episode.end_chapter,
      duration: episode.target_duration_minutes
    }))
  }

  return localSuggestions.value.map((suggestion) => ({
    episode_number: suggestion.episode_number,
    title: suggestion.title || '',
    start_chapter: suggestion.start_chapter,
    end_chapter: suggestion.end_chapter,
    duration: suggestion.estimated_duration_minutes
  }))
})

const chapterCoverage = computed(() => {
  const chapters = workspace.value?.chapters || []
  return chapters.map((chapter) => {
    const owner = chapterAssignments.value.find((item) => chapter.chapter_number >= item.start_chapter && chapter.chapter_number <= item.end_chapter)
    return {
      chapter_number: chapter.chapter_number,
      title: chapter.title || '未命名章节',
      ownerLabel: owner ? `EP${owner.episode_number.toString().padStart(2, '0')}` : '',
      color: owner ? coverageColor(owner.episode_number) : 'rgba(215, 207, 191, 0.85)'
    }
  })
})

watch(
  () => workspace.value?.episode_plan_draft?.updated_at,
  () => {
    const draft = workspace.value?.episode_plan_draft
    localSuggestions.value = draft?.suggestions.map((suggestion) => ({ ...suggestion })) || []
  },
  { immediate: true }
)

watch(
  () => workspace.value?.episodes,
  (episodes) => {
    if (!episodes?.length) {
      selectedEpisodeNumber.value = null
      return
    }

    const firstEpisode = episodes[0]
    if ((!selectedEpisodeNumber.value || !episodes.some((episode) => episode.episode_number === selectedEpisodeNumber.value)) && firstEpisode) {
      selectedEpisodeNumber.value = firstEpisode.episode_number
    }
  },
  { immediate: true, deep: true }
)

watch(
  selectedEpisode,
  (episode) => {
    if (!episode) return
    syncEpisodeEditor(episode)
  },
  { immediate: true }
)

function syncEpisodeEditor(episode: EpisodeWorkspaceItem) {
  episodeEditor.title = episode.title || ''
  episodeEditor.synopsis = episode.synopsis || ''
  episodeEditor.start_chapter = episode.start_chapter
  episodeEditor.end_chapter = episode.end_chapter
  episodeEditor.target_duration_minutes = episode.target_duration_minutes
}

function coverageColor(episodeNumber: number) {
  return COVERAGE_COLORS[(episodeNumber - 1) % COVERAGE_COLORS.length]
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

async function generateDraft() {
  if (!analysisReady.value) {
    actionError.value = '请先完成全部章节分析'
    return
  }

  planning.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.planEpisodes(projectId.value, {
      target_episode_duration: planningForm.target_episode_duration,
      max_episodes: planningForm.max_episodes,
      style: planningForm.style
    })
    actionInfo.value = '分集规划任务已启动，草案会在最近操作和本页自动刷新。'
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '分集规划失败'
  } finally {
    planning.value = false
  }
}

async function confirmPlan() {
  if (workspace.value?.episodes.length) {
    actionError.value = '当前已经有正式分集，请先清空再确认新草案'
    return
  }

  if (localSuggestions.value.length === 0) {
    actionError.value = '当前没有可确认的草案'
    return
  }

  confirming.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.createEpisodesBatch(
      projectId.value,
      localSuggestions.value.map((suggestion) => ({
        episode_number: suggestion.episode_number,
        title: suggestion.title,
        synopsis: suggestion.synopsis,
        start_chapter: suggestion.start_chapter,
        end_chapter: suggestion.end_chapter,
        target_duration_minutes: suggestion.estimated_duration_minutes
      }))
    )
    actionInfo.value = '分集草案已确认，接下来可以进入分镜工作台。'
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '确认草案失败'
  } finally {
    confirming.value = false
  }
}

async function clearConfirmedEpisodes() {
  clearing.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.clearEpisodes(projectId.value)
    actionInfo.value = '当前正式分集已清空，可以重新生成或确认新草案。'
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '清空分集失败'
  } finally {
    clearing.value = false
  }
}

async function saveEpisode() {
  if (!selectedEpisode.value) return

  savingEpisode.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.updateEpisode(projectId.value, selectedEpisode.value.episode_number, {
      title: episodeEditor.title,
      synopsis: episodeEditor.synopsis,
      start_chapter: episodeEditor.start_chapter,
      end_chapter: episodeEditor.end_chapter,
      target_duration_minutes: episodeEditor.target_duration_minutes
    })
    actionInfo.value = `EP${selectedEpisode.value.episode_number.toString().padStart(2, '0')} 已更新。`
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '保存分集失败'
  } finally {
    savingEpisode.value = false
  }
}
</script>
