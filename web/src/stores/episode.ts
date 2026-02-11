import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { apiClient } from '@/api/client'
import type {
  Episode,
  EpisodeCreate,
  EpisodeUpdate,
  EpisodePlanRequest,
  EpisodePlanResponse,
  EpisodeSuggestion,
  Job
} from '@/types/api'
import { EpisodeStatus, JobStatus } from '@/types/api'

export const useEpisodeStore = defineStore('episode', () => {
  // State
  const episodes = ref<Episode[]>([])
  const currentEpisode = ref<Episode | null>(null)
  const episodePlan = ref<EpisodePlanResponse | null>(null)
  const planningJob = ref<Job | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const hasEpisodes = computed(() => episodes.value.length > 0)
  const hasError = computed(() => error.value !== null)
  const totalEpisodes = computed(() => episodes.value.length)

  const plannedEpisodes = computed(() =>
    episodes.value.filter(e => e.status === EpisodeStatus.PLANNED)
  )

  const renderingEpisodes = computed(() =>
    episodes.value.filter(e => e.status === EpisodeStatus.RENDERING)
  )

  const completedEpisodes = computed(() =>
    episodes.value.filter(e => e.status === EpisodeStatus.DONE)
  )

  // Actions
  async function fetchEpisodes(projectId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient.listEpisodes(projectId)
      episodes.value = response.items.sort((a, b) => a.episode_number - b.episode_number)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchEpisode(projectId: string, episodeNumber: number): Promise<Episode | null> {
    loading.value = true
    error.value = null
    try {
      currentEpisode.value = await apiClient.getEpisode(projectId, episodeNumber)
      return currentEpisode.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function planEpisodes(
    projectId: string,
    options?: EpisodePlanRequest,
    onProgress?: (job: Job) => void
  ): Promise<EpisodePlanResponse | null> {
    loading.value = true
    error.value = null
    planningJob.value = null
    episodePlan.value = null

    try {
      // 启动异步规划任务
      const job = await apiClient.planEpisodes(projectId, options)
      planningJob.value = job

      // 轮询等待任务完成
      const result = await pollPlanningJob(projectId, job.id, onProgress)
      if (result) {
        episodePlan.value = result
      }
      return result
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
      planningJob.value = null
    }
  }

  async function pollPlanningJob(
    projectId: string,
    jobId: string,
    onProgress?: (job: Job) => void
  ): Promise<EpisodePlanResponse | null> {
    const maxAttempts = 120 // 最多轮询 10 分钟 (120 * 5s)
    const pollInterval = 5000 // 5 秒

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const job = await apiClient.getJob(jobId)
        planningJob.value = job

        if (onProgress) {
          onProgress(job)
        }

        if (job.status === JobStatus.SUCCESS) {
          // 获取规划结果
          return await apiClient.getPlanResult(projectId, jobId)
        } else if (job.status === JobStatus.FAILURE) {
          error.value = job.error_message || '规划失败'
          return null
        } else if (job.status === JobStatus.REVOKED) {
          error.value = '任务已取消'
          return null
        }

        // 等待下一次轮询
        await new Promise(resolve => setTimeout(resolve, pollInterval))
      } catch (e) {
        error.value = (e as Error).message
        return null
      }
    }

    error.value = '规划超时'
    return null
  }

  function cancelPlanning() {
    if (planningJob.value) {
      apiClient.cancelJob(planningJob.value.id).catch(console.error)
      planningJob.value = null
    }
  }

  async function confirmEpisodePlan(
    projectId: string,
    suggestions: EpisodeSuggestion[]
  ): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const episodeCreates: EpisodeCreate[] = suggestions.map(s => ({
        episode_number: s.episode_number,
        title: s.title,
        synopsis: s.synopsis,
        start_chapter: s.start_chapter,
        end_chapter: s.end_chapter,
        target_duration_minutes: s.estimated_duration_minutes
      }))
      const response = await apiClient.createEpisodesBatch(projectId, episodeCreates)
      episodes.value = response.items.sort((a, b) => a.episode_number - b.episode_number)
      episodePlan.value = null
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function createEpisode(projectId: string, data: EpisodeCreate): Promise<Episode | null> {
    loading.value = true
    error.value = null
    try {
      const episode = await apiClient.createEpisode(projectId, data)
      episodes.value.push(episode)
      episodes.value.sort((a, b) => a.episode_number - b.episode_number)
      return episode
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateEpisode(
    projectId: string,
    episodeNumber: number,
    data: EpisodeUpdate
  ): Promise<Episode | null> {
    loading.value = true
    error.value = null
    try {
      const updated = await apiClient.updateEpisode(projectId, episodeNumber, data)
      const index = episodes.value.findIndex(e => e.episode_number === episodeNumber)
      if (index !== -1) {
        episodes.value[index] = updated
      }
      if (currentEpisode.value?.episode_number === episodeNumber) {
        currentEpisode.value = updated
      }
      return updated
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function deleteEpisode(projectId: string, episodeNumber: number): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.deleteEpisode(projectId, episodeNumber)
      episodes.value = episodes.value.filter(e => e.episode_number !== episodeNumber)
      if (currentEpisode.value?.episode_number === episodeNumber) {
        currentEpisode.value = null
      }
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function deleteAllEpisodes(projectId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.deleteAllEpisodes(projectId)
      episodes.value = []
      currentEpisode.value = null
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function generateStoryboard(projectId: string, episodeNumber: number): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.generateEpisodeStoryboard(projectId, episodeNumber)
      // 刷新集状态
      await fetchEpisode(projectId, episodeNumber)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function startRender(projectId: string, episodeNumber: number): Promise<string | null> {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient.startEpisodeRender(projectId, episodeNumber)
      // 刷新集状态
      await fetchEpisode(projectId, episodeNumber)
      return response.job_id
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  function clearEpisodes() {
    episodes.value = []
    currentEpisode.value = null
    episodePlan.value = null
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    episodes,
    currentEpisode,
    episodePlan,
    planningJob,
    loading,
    error,
    // Getters
    hasEpisodes,
    hasError,
    totalEpisodes,
    plannedEpisodes,
    renderingEpisodes,
    completedEpisodes,
    // Actions
    fetchEpisodes,
    fetchEpisode,
    planEpisodes,
    cancelPlanning,
    confirmEpisodePlan,
    createEpisode,
    updateEpisode,
    deleteEpisode,
    deleteAllEpisodes,
    generateStoryboard,
    startRender,
    clearEpisodes,
    clearError
  }
})
