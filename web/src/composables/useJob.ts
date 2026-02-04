import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { Job } from '@/types/api'
import { apiClient } from '@/api/client'

export function useJob(jobId?: string) {
  const message = useMessage()
  const job = ref<Job | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const pollingInterval = ref<number | null>(null)

  async function fetchJob(id: string) {
    loading.value = true
    error.value = null
    try {
      job.value = await apiClient.getJob(id)
    } catch (e) {
      error.value = (e as Error).message
      message.error(`Failed to load job: ${error.value}`)
    } finally {
      loading.value = false
    }
  }

  async function cancelJob(id: string) {
    loading.value = true
    error.value = null
    try {
      await apiClient.cancelJob(id)
      message.success('Job cancelled successfully')
      await fetchJob(id)
    } catch (e) {
      error.value = (e as Error).message
      message.error(`Failed to cancel job: ${error.value}`)
      throw e
    } finally {
      loading.value = false
    }
  }

  function startPolling(id: string, intervalMs = 2000) {
    stopPolling()
    fetchJob(id)
    pollingInterval.value = window.setInterval(() => {
      fetchJob(id)
    }, intervalMs)
  }

  function stopPolling() {
    if (pollingInterval.value) {
      clearInterval(pollingInterval.value)
      pollingInterval.value = null
    }
  }

  if (jobId) {
    fetchJob(jobId)
  }

  return {
    job,
    loading,
    error,
    fetchJob,
    cancelJob,
    startPolling,
    stopPolling
  }
}
