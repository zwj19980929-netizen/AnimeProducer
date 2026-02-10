import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { Job } from '@/types/api'
import { JobStatus } from '@/types/api'
import { apiClient } from '@/api/client'
import { useJobWebSocket, type WebSocketMessage } from '@/composables/useWebSocket'

export function useJob(jobId?: string) {
  const message = useMessage()
  const job = ref<Job | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const pollingInterval = ref<number | null>(null)

  // WebSocket connection
  let wsConnection: ReturnType<typeof useJobWebSocket> | null = null

  function handleWebSocketMessage(msg: WebSocketMessage) {
    if (msg.type === 'job_update' && job.value) {
      // Update job data from WebSocket message
      if (msg.status) job.value.status = msg.status as JobStatus
      if (msg.progress !== undefined) job.value.progress = msg.progress as number
      if (msg.error_message) job.value.error_message = msg.error_message as string
    } else if (msg.type === 'initial_state' && msg.job) {
      // Initial state from WebSocket
      const jobData = msg.job as Record<string, unknown>
      if (job.value) {
        job.value.status = jobData.status as JobStatus
        job.value.progress = jobData.progress as number
        if (jobData.error_message) job.value.error_message = jobData.error_message as string
      }
    }
  }

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

    // Initialize WebSocket connection
    wsConnection = useJobWebSocket(id, handleWebSocketMessage)
    wsConnection.startListening()

    // Start polling as fallback (only when WebSocket is not connected)
    pollingInterval.value = window.setInterval(() => {
      if (!wsConnection?.isConnected.value) {
        fetchJob(id)
      }
    }, intervalMs)
  }

  function stopPolling() {
    if (pollingInterval.value) {
      clearInterval(pollingInterval.value)
      pollingInterval.value = null
    }
    // Stop WebSocket connection
    if (wsConnection) {
      wsConnection.stopListening()
      wsConnection = null
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
