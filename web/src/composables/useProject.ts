import { computed, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useProjectStore } from '@/stores/project'
import type { Project, ProjectCreate, ProjectUpdate, PipelineStartResponse } from '@/types/api'

const POLLING_INTERVAL = parseInt(import.meta.env.VITE_POLLING_INTERVAL || '3000', 10)

export function useProject(projectId?: string) {
  const message = useMessage()
  const store = useProjectStore()

  const pollingIntervalId = ref<number | null>(null)

  const {
    currentProject: project,
    loading,
    error,
    isProcessing,
    canStartPipeline,
    canBuildAssets,
    canGenerateStoryboard,
    hasOutput,
    isDone,
    isFailed
  } = storeToRefs(store)

  const shouldPoll = computed(() => isProcessing.value)

  async function fetchProject(id: string): Promise<Project | null> {
    const result = await store.fetchProject(id)
    if (!result && store.error) {
      message.error(`加载项目失败: ${store.error}`)
    }
    return result
  }

  async function createProject(data: ProjectCreate): Promise<Project | null> {
    const result = await store.createProject(data)
    if (result) {
      message.success('项目创建成功')
    } else if (store.error) {
      message.error(`创建项目失败: ${store.error}`)
    }
    return result
  }

  async function updateProject(id: string, data: ProjectUpdate): Promise<Project | null> {
    const result = await store.updateProject(id, data)
    if (result) {
      message.success('项目更新成功')
    } else if (store.error) {
      message.error(`更新项目失败: ${store.error}`)
    }
    return result
  }

  async function deleteProject(id: string): Promise<boolean> {
    const success = await store.deleteProject(id)
    if (success) {
      message.success('项目删除成功')
    } else if (store.error) {
      message.error(`删除项目失败: ${store.error}`)
    }
    return success
  }

  async function buildAssets(id: string): Promise<boolean> {
    const success = await store.buildAssets(id)
    if (success) {
      message.success('资源生成已启动')
    } else if (store.error) {
      message.error(`构建资源失败: ${store.error}`)
    }
    return success
  }

  async function generateStoryboard(id: string): Promise<boolean> {
    const success = await store.generateStoryboard(id)
    if (success) {
      message.success('故事板生成已启动')
    } else if (store.error) {
      message.error(`生成故事板失败: ${store.error}`)
    }
    return success
  }

  async function startPipeline(
    id: string,
    skipAssets = false,
    parallelRenders = 4
  ): Promise<PipelineStartResponse | null> {
    const result = await store.startPipeline(id, skipAssets, parallelRenders)
    if (result) {
      message.success('流程启动成功')
    } else if (store.error) {
      message.error(`启动流程失败: ${store.error}`)
    }
    return result
  }

  function startPolling(id: string): void {
    stopPolling()
    pollingIntervalId.value = window.setInterval(() => {
      if (shouldPoll.value) {
        store.fetchProject(id)
      }
    }, POLLING_INTERVAL)
  }

  function stopPolling(): void {
    if (pollingIntervalId.value !== null) {
      clearInterval(pollingIntervalId.value)
      pollingIntervalId.value = null
    }
  }

  onUnmounted(() => {
    stopPolling()
  })

  if (projectId) {
    fetchProject(projectId)
  }

  return {
    // State from store (reactive refs)
    project,
    loading,
    error,

    // Computed status flags from store
    isProcessing,
    canStartPipeline,
    canBuildAssets,
    canGenerateStoryboard,
    hasOutput,
    isDone,
    isFailed,

    // Actions with toast notifications
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    buildAssets,
    generateStoryboard,
    startPipeline,

    // Polling control
    startPolling,
    stopPolling
  }
}
