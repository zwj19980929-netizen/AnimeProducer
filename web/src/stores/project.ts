import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Project, ProjectCreate, ProjectUpdate, ProjectListResponse, PipelineStartResponse } from '@/types/api'
import {
  ProjectStatus,
  PROCESSING_STATUSES,
  PIPELINE_READY_STATUSES,
  ASSET_BUILD_STATUSES,
  STORYBOARD_READY_STATUSES
} from '@/types/api'
import { apiClient } from '@/api/client'

export const useProjectStore = defineStore('project', () => {
  // State
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)

  // Computed - List related
  const hasProjects = computed(() => projects.value.length > 0)
  const hasError = computed(() => error.value !== null)

  // Computed - Current project status helpers
  const isProcessing = computed(() => {
    if (!currentProject.value) return false
    return PROCESSING_STATUSES.includes(currentProject.value.status)
  })

  const canStartPipeline = computed(() => {
    if (!currentProject.value) return false
    return PIPELINE_READY_STATUSES.includes(currentProject.value.status)
  })

  const canBuildAssets = computed(() => {
    if (!currentProject.value) return false
    return ASSET_BUILD_STATUSES.includes(currentProject.value.status)
  })

  const canGenerateStoryboard = computed(() => {
    if (!currentProject.value) return false
    return STORYBOARD_READY_STATUSES.includes(currentProject.value.status)
  })

  const hasOutput = computed(() => {
    return !!currentProject.value?.output_video_path
  })

  const isDone = computed(() => {
    return currentProject.value?.status === ProjectStatus.DONE
  })

  const isFailed = computed(() => {
    return currentProject.value?.status === ProjectStatus.FAILED
  })

  // Actions - List operations
  async function fetchProjects(params?: { page?: number; page_size?: number; status?: string }): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response: ProjectListResponse = await apiClient.listProjects(params)
      projects.value = response.items
      total.value = response.total
      page.value = response.page
      pageSize.value = response.page_size
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  // Actions - Single project operations
  async function fetchProject(id: string): Promise<Project | null> {
    loading.value = true
    error.value = null
    try {
      currentProject.value = await apiClient.getProject(id)
      return currentProject.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function createProject(data: ProjectCreate): Promise<Project | null> {
    loading.value = true
    error.value = null
    try {
      const project = await apiClient.createProject(data)
      currentProject.value = project
      return project
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateProject(id: string, data: ProjectUpdate): Promise<Project | null> {
    loading.value = true
    error.value = null
    try {
      const project = await apiClient.updateProject(id, data)
      currentProject.value = project
      return project
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  async function deleteProject(id: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.deleteProject(id)
      currentProject.value = null
      projects.value = projects.value.filter(p => p.id !== id)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  // Actions - Pipeline operations
  async function buildAssets(id: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.buildAssets(id)
      await fetchProject(id)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function generateStoryboard(id: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await apiClient.generateStoryboard(id)
      await fetchProject(id)
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    } finally {
      loading.value = false
    }
  }

  async function startPipeline(
    id: string,
    skipAssets = false,
    parallelRenders = 4
  ): Promise<PipelineStartResponse | null> {
    loading.value = true
    error.value = null
    try {
      const result = await apiClient.startPipeline(id, {
        project_id: id,
        skip_asset_generation: skipAssets,
        parallel_renders: parallelRenders
      })
      await fetchProject(id)
      return result
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      loading.value = false
    }
  }

  // Utility actions
  function setCurrentProject(project: Project | null) {
    currentProject.value = project
  }

  function clearProjects() {
    projects.value = []
    currentProject.value = null
    total.value = 0
    error.value = null
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    projects,
    currentProject,
    loading,
    error,
    total,
    page,
    pageSize,

    // Computed - List
    hasProjects,
    hasError,

    // Computed - Current project status
    isProcessing,
    canStartPipeline,
    canBuildAssets,
    canGenerateStoryboard,
    hasOutput,
    isDone,
    isFailed,

    // Actions - List
    fetchProjects,

    // Actions - Single project
    fetchProject,
    createProject,
    updateProject,
    deleteProject,

    // Actions - Pipeline
    buildAssets,
    generateStoryboard,
    startPipeline,

    // Utility
    setCurrentProject,
    clearProjects,
    clearError
  }
})
