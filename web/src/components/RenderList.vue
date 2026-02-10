<template>
  <div>
    <n-spin :show="loading">
      <div v-if="jobs.length > 0" class="space-y-4">
        <div
          v-for="job in jobs"
          :key="job.id"
          class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <h4 class="text-lg font-semibold text-white mb-1">{{ formatJobType(job.job_type) }}</h4>
              <div class="flex gap-2 items-center">
                <JobStatusBadge :status="job.status" />
                <span class="text-xs text-gray-500">{{ formatDate(job.created_at) }}</span>
              </div>
            </div>
            <div class="flex gap-2">
              <n-button
                v-if="job.status === JobStatus.FAILURE"
                size="small"
                type="warning"
                :loading="retryingJobId === job.id"
                @click="handleRetryJob(job.id)"
              >
                重试
              </n-button>
              <n-button
                v-if="isJobActive(job)"
                size="small"
                @click="handleCancelJob(job.id)"
              >
                取消
              </n-button>
            </div>
          </div>

          <!-- Progress Bar -->
          <div v-if="job.status === JobStatus.STARTED" class="mb-4">
            <n-progress
              type="line"
              :percentage="Math.round(job.progress * 100)"
              :show-indicator="true"
              processing
            />
          </div>

          <!-- Shot Renders -->
          <div v-if="job.job_type === JobType.FULL_PIPELINE || job.job_type === JobType.SHOT_RENDER">
            <n-button text type="primary" @click="handleViewShotRenders(job.id)">
              查看镜头渲染
            </n-button>
          </div>

          <!-- Error Message -->
          <div v-if="job.error_message" class="mt-3 p-3 bg-red-900/20 rounded-lg">
            <p class="text-red-300 text-sm">{{ job.error_message }}</p>
          </div>
        </div>
      </div>
      <n-empty v-else description="还没有渲染任务。启动流程开始渲染。" class="py-20" />
    </n-spin>

    <!-- Shot Render List Modal -->
    <ShotRenderListModal
      v-model:show="showShotRenderModal"
      :job-id="selectedJobId"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { NSpin, NEmpty, NButton, NProgress, useMessage } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Job } from '@/types/api'
import { JobStatus, JobType, ACTIVE_JOB_STATUSES } from '@/types/api'
import JobStatusBadge from './JobStatusBadge.vue'
import ShotRenderListModal from './ShotRenderListModal.vue'
import { useProjectWebSocket, type WebSocketMessage } from '@/composables/useWebSocket'
import dayjs from 'dayjs'

const POLLING_INTERVAL = parseInt(import.meta.env.VITE_POLLING_INTERVAL || '3000', 10)

const props = defineProps<{
  projectId: string
}>()

const message = useMessage()
const jobs = ref<Job[]>([])
const loading = ref(false)
const pollingIntervalId = ref<number | null>(null)
const showShotRenderModal = ref(false)
const selectedJobId = ref<string | null>(null)
const retryingJobId = ref<string | null>(null)

const hasActiveJobs = computed(() =>
  jobs.value.some(job => ACTIVE_JOB_STATUSES.includes(job.status))
)

// WebSocket for real-time updates
const { isConnected, startListening, stopListening } = useProjectWebSocket(
  props.projectId,
  handleWebSocketMessage
)

function handleWebSocketMessage(msg: WebSocketMessage) {
  if (msg.type === 'job_update' || msg.type === 'shot_render_update') {
    // Update the specific job in our list
    const jobId = msg.job_id as string
    const jobIndex = jobs.value.findIndex(j => j.id === jobId)

    if (jobIndex !== -1) {
      // Update existing job
      const updatedJob = { ...jobs.value[jobIndex] }
      if (msg.status) updatedJob.status = msg.status as JobStatus
      if (msg.progress !== undefined) updatedJob.progress = msg.progress as number
      if (msg.error_message) updatedJob.error_message = msg.error_message as string
      jobs.value[jobIndex] = updatedJob
    } else {
      // New job, reload the list
      loadJobs()
    }
  } else if (msg.type === 'initial_state') {
    // Initial state received, load jobs
    loadJobs()
  }
}

onMounted(async () => {
  await loadJobs()
  // Try WebSocket first, fall back to polling
  startListening()
  // Start polling as fallback (will be less frequent if WebSocket is connected)
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  stopListening()
})

// Watch WebSocket connection status
watch(isConnected, (connected) => {
  if (connected) {
    // WebSocket connected, we can reduce polling frequency or stop it
    stopPolling()
  } else {
    // WebSocket disconnected, resume polling
    startPolling()
  }
})

async function loadJobs() {
  loading.value = true
  try {
    const response = await apiClient.listJobs({ project_id: props.projectId })
    jobs.value = response.items.sort((a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
  } catch (error) {
    console.error('Failed to load jobs:', error)
  } finally {
    loading.value = false
  }
}

async function handleCancelJob(jobId: string) {
  try {
    await apiClient.cancelJob(jobId)
    message.success('任务已取消')
    await loadJobs()
  } catch (error) {
    console.error('Failed to cancel job:', error)
    message.error(`取消任务失败: ${error instanceof Error ? error.message : '未知错误'}`)
  }
}

async function handleRetryJob(jobId: string) {
  retryingJobId.value = jobId
  try {
    await apiClient.retryJob(jobId)
    message.success('任务重试已启动')
    await loadJobs()
  } catch (error) {
    console.error('Failed to retry job:', error)
    message.error(`重试任务失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    retryingJobId.value = null
  }
}

function handleViewShotRenders(jobId: string) {
  selectedJobId.value = jobId
  showShotRenderModal.value = true
}

function isJobActive(job: Job): boolean {
  return ACTIVE_JOB_STATUSES.includes(job.status)
}

function startPolling() {
  stopPolling()
  pollingIntervalId.value = window.setInterval(() => {
    if (hasActiveJobs.value) {
      loadJobs()
    }
  }, POLLING_INTERVAL)
}

function stopPolling() {
  if (pollingIntervalId.value !== null) {
    clearInterval(pollingIntervalId.value)
    pollingIntervalId.value = null
  }
}

function formatJobType(type: JobType): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function formatDate(date: string): string {
  return dayjs(date).format('YYYY年M月D日 HH:mm')
}
</script>
