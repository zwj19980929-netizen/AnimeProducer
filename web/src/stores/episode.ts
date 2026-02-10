import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { apiClient } from '@/api/client'
import type {
  Episode,
  EpisodeCreate,
  EpisodeUpdate,
  EpisodePlanRequest,
  EpisodePlanResponse,
  EpisodeSuggestion
} from '@/types/api'
import { EpisodeStatus } from '@/types/api'

export const useEpisodeStore = defineStore('episode', () => {
  // State
  const episodes = ref<Episode[]>([])
  const currentEpisode = ref<Episode | null>(null)
  const episodePlan = ref<EpisodePlanResponse | null>(null)
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
    options?: EpisodePlanRequest
  ): Promise<EpisodePlanResponse | null> {
    loading.value = true
    error.value = null
    try {
      episodePlan.value = await apiClient.planEpisodes(projectId, options)
      return episodePlan.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
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
