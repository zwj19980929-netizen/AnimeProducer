<template>
  <div class="episode-list">
    <!-- 操作栏 -->
    <div class="flex justify-between items-center mb-4">
      <div class="flex gap-2">
        <n-button
          type="primary"
          :loading="planLoading"
          :disabled="!canPlan"
          @click="handlePlanEpisodes"
        >
          AI 规划集数
        </n-button>
        <n-button
          v-if="planLoading"
          type="warning"
          ghost
          @click="handleCancelPlan"
        >
          取消规划
        </n-button>
        <n-button
          v-if="hasEpisodes && !planLoading"
          type="error"
          ghost
          @click="handleDeleteAll"
        >
          清空规划
        </n-button>
      </div>
      <div class="text-gray-400 text-sm">
        共 {{ episodes.length }} 集
      </div>
    </div>

    <!-- 规划进度 -->
    <n-card v-if="planLoading && planningJob" class="mb-4" title="AI 正在规划中...">
      <div class="space-y-3">
        <n-progress
          type="line"
          :percentage="(planningJob.progress || 0) * 100"
          :show-indicator="true"
          status="info"
        />
        <p class="text-gray-400 text-sm">
          {{ getPlanningStatusText(planningJob) }}
        </p>
      </div>
    </n-card>

    <!-- 规划结果预览 -->
    <n-card v-if="episodePlan" class="mb-4" title="AI 规划结果">
      <template #header-extra>
        <div class="flex gap-2">
          <n-button type="primary" size="small" @click="handleConfirmPlan">
            确认规划
          </n-button>
          <n-button size="small" @click="episodePlan = null">
            取消
          </n-button>
        </div>
      </template>
      <p class="text-gray-400 mb-4">{{ episodePlan.reasoning }}</p>
      <p class="text-gray-400 mb-4">
        预计总时长: {{ episodePlan.total_estimated_duration.toFixed(1) }} 分钟
      </p>
      <n-table :bordered="false" :single-line="false" size="small">
        <thead>
          <tr>
            <th>集数</th>
            <th>标题</th>
            <th>章节范围</th>
            <th>预计时长</th>
            <th>简介</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ep in episodePlan.suggested_episodes" :key="ep.episode_number">
            <td>第 {{ ep.episode_number }} 集</td>
            <td>{{ ep.title }}</td>
            <td>{{ ep.start_chapter }} - {{ ep.end_chapter }}</td>
            <td>{{ ep.estimated_duration_minutes.toFixed(1) }} 分钟</td>
            <td class="max-w-xs truncate">{{ ep.synopsis }}</td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- 集列表 -->
    <n-spin :show="loading">
      <div v-if="episodes.length === 0 && !loading" class="text-center py-8 text-gray-400">
        暂无集规划，请先上传章节并使用 AI 规划集数
      </div>

      <div v-else class="space-y-3">
        <n-card
          v-for="episode in episodes"
          :key="episode.id"
          size="small"
          hoverable
        >
          <div class="flex justify-between items-start">
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-2">
                <span class="font-bold">第 {{ episode.episode_number }} 集</span>
                <span v-if="episode.title" class="text-gray-300">{{ episode.title }}</span>
                <EpisodeStatusBadge :status="episode.status" />
              </div>
              <div class="text-sm text-gray-400 space-y-1">
                <p>章节范围: {{ episode.start_chapter }} - {{ episode.end_chapter }}</p>
                <p>目标时长: {{ episode.target_duration_minutes }} 分钟</p>
                <p v-if="episode.actual_duration_minutes">
                  实际时长: {{ episode.actual_duration_minutes.toFixed(1) }} 分钟
                </p>
                <p v-if="episode.synopsis" class="line-clamp-2">{{ episode.synopsis }}</p>
              </div>
            </div>
            <div class="flex gap-2">
              <n-button
                v-if="episode.status === 'PLANNED'"
                size="small"
                type="info"
                :loading="actionLoading === `storyboard-${episode.episode_number}`"
                @click="handleGenerateStoryboard(episode)"
              >
                生成分镜
              </n-button>
              <n-button
                v-if="episode.status === 'STORYBOARD_READY'"
                size="small"
                type="primary"
                :loading="actionLoading === `render-${episode.episode_number}`"
                @click="handleStartRender(episode)"
              >
                开始渲染
              </n-button>
              <n-button
                v-if="episode.output_video_url"
                size="small"
                type="success"
                @click="handlePlayVideo(episode)"
              >
                播放
              </n-button>
              <n-button
                size="small"
                quaternary
                @click="handleViewShots(episode)"
              >
                查看分镜
              </n-button>
              <n-button
                size="small"
                quaternary
                type="error"
                @click="handleDelete(episode)"
              >
                删除
              </n-button>
            </div>
          </div>
        </n-card>
      </div>
    </n-spin>

    <!-- 分镜列表模态框 -->
    <n-modal v-model:show="showShotsModal" preset="card" style="width: 800px" title="分镜列表">
      <ShotList v-if="selectedEpisode" :project-id="projectId" :episode-number="selectedEpisode.episode_number" />
    </n-modal>

    <!-- 视频播放模态框 -->
    <n-modal v-model:show="showVideoModal" preset="card" style="width: 900px" title="视频播放">
      <VideoPlayer v-if="selectedVideoUrl" :src="selectedVideoUrl" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { NButton, NCard, NSpin, NTable, NModal, NProgress, useMessage, useDialog } from 'naive-ui'
import { storeToRefs } from 'pinia'
import { useEpisodeStore } from '@/stores/episode'
import EpisodeStatusBadge from './EpisodeStatusBadge.vue'
import ShotList from './ShotList.vue'
import VideoPlayer from './VideoPlayer.vue'
import type { Episode, EpisodePlanResponse, Job } from '@/types/api'

const props = defineProps<{
  projectId: string
  chapterCount: number
}>()

const message = useMessage()
const dialog = useDialog()
const episodeStore = useEpisodeStore()
const { episodes, loading, error, planningJob } = storeToRefs(episodeStore)

const planLoading = ref(false)
const actionLoading = ref<string | null>(null)
const episodePlan = ref<EpisodePlanResponse | null>(null)
const showShotsModal = ref(false)
const showVideoModal = ref(false)
const selectedEpisode = ref<Episode | null>(null)
const selectedVideoUrl = ref<string | null>(null)

const hasEpisodes = computed(() => episodes.value.length > 0)
const canPlan = computed(() => props.chapterCount > 0 && !planLoading.value)

async function loadEpisodes() {
  await episodeStore.fetchEpisodes(props.projectId)
}

async function handlePlanEpisodes() {
  planLoading.value = true
  try {
    const result = await episodeStore.planEpisodes(props.projectId, {
      target_episode_duration: 24,
      style: 'standard'
    })
    if (result) {
      episodePlan.value = result
      message.success(`AI 建议分为 ${result.suggested_episodes.length} 集`)
    } else if (error.value) {
      message.error(error.value)
    }
  } finally {
    planLoading.value = false
  }
}

function handleCancelPlan() {
  episodeStore.cancelPlanning()
  planLoading.value = false
  message.info('已取消规划')
}

function getPlanningStatusText(job: Job): string {
  const progress = (job.progress || 0) * 100
  if (progress < 30) {
    return '正在加载章节数据...'
  } else if (progress < 80) {
    return '正在调用 AI 分析章节并规划集数...'
  } else {
    return '正在整理规划结果...'
  }
}

async function handleConfirmPlan() {
  if (!episodePlan.value) return

  const success = await episodeStore.confirmEpisodePlan(
    props.projectId,
    episodePlan.value.suggested_episodes
  )

  if (success) {
    episodePlan.value = null
    message.success('集规划已确认')
  } else if (error.value) {
    message.error(error.value)
  }
}

async function handleGenerateStoryboard(episode: Episode) {
  actionLoading.value = `storyboard-${episode.episode_number}`
  try {
    const success = await episodeStore.generateStoryboard(props.projectId, episode.episode_number)
    if (success) {
      message.success(`第 ${episode.episode_number} 集分镜生成完成`)
      await loadEpisodes()
    } else if (error.value) {
      message.error(error.value)
    }
  } finally {
    actionLoading.value = null
  }
}

async function handleStartRender(episode: Episode) {
  actionLoading.value = `render-${episode.episode_number}`
  try {
    const jobId = await episodeStore.startRender(props.projectId, episode.episode_number)
    if (jobId) {
      message.success(`第 ${episode.episode_number} 集渲染已启动`)
      await loadEpisodes()
    } else if (error.value) {
      message.error(error.value)
    }
  } finally {
    actionLoading.value = null
  }
}

function handleViewShots(episode: Episode) {
  selectedEpisode.value = episode
  showShotsModal.value = true
}

function handlePlayVideo(episode: Episode) {
  if (episode.output_video_url) {
    selectedVideoUrl.value = episode.output_video_url
    showVideoModal.value = true
  }
}

function handleDelete(episode: Episode) {
  dialog.warning({
    title: '确认删除',
    content: `确定要删除第 ${episode.episode_number} 集吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const success = await episodeStore.deleteEpisode(props.projectId, episode.episode_number)
      if (success) {
        message.success('已删除')
      } else if (error.value) {
        message.error(error.value)
      }
    }
  })
}

function handleDeleteAll() {
  dialog.warning({
    title: '确认清空',
    content: '确定要清空所有集规划吗？这将删除所有集及其分镜。',
    positiveText: '清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      const success = await episodeStore.deleteAllEpisodes(props.projectId)
      if (success) {
        message.success('已清空')
      } else if (error.value) {
        message.error(error.value)
      }
    }
  })
}

watch(() => props.projectId, () => {
  loadEpisodes()
})

onMounted(() => {
  loadEpisodes()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
