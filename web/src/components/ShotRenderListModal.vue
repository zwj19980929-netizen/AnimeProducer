<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="镜头渲染列表"
    class="max-w-4xl"
  >
    <template v-if="loading">
      <div class="flex justify-center py-8">
        <n-spin size="large" />
      </div>
    </template>

    <template v-else-if="shotRenders.length === 0">
      <n-empty description="暂无镜头渲染记录" class="py-8" />
    </template>

    <template v-else>
      <div class="space-y-3 max-h-[60vh] overflow-y-auto">
        <div
          v-for="render in shotRenders"
          :key="render.id"
          class="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-purple-400 font-mono">镜头 #{{ render.shot_id }}</span>
                <ShotRenderStatusBadge :status="render.status" />
              </div>

              <!-- Progress -->
              <div v-if="isRenderActive(render)" class="mb-2">
                <n-progress
                  type="line"
                  :percentage="Math.round(render.progress * 100)"
                  :show-indicator="true"
                  processing
                />
              </div>

              <!-- Output Paths -->
              <div class="text-xs text-gray-500 space-y-1">
                <div v-if="render.image_path">图片: {{ render.image_path }}</div>
                <div v-if="render.video_path">视频: {{ render.video_path }}</div>
                <div v-if="render.audio_path">音频: {{ render.audio_path }}</div>
                <div v-if="render.composited_path">合成: {{ render.composited_path }}</div>
              </div>

              <!-- Error Message -->
              <div v-if="render.error_message" class="mt-2 p-2 bg-red-900/20 rounded">
                <p class="text-red-300 text-sm">{{ render.error_message }}</p>
              </div>
            </div>

            <!-- Retry Button -->
            <n-button
              v-if="render.status === ShotRenderStatus.FAILURE"
              size="small"
              type="warning"
              :loading="retryingId === render.id"
              @click="handleRetry(render)"
            >
              重试
            </n-button>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end">
        <n-button @click="visible = false">关闭</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NButton, NSpin, NEmpty, NProgress, useMessage } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { ShotRender } from '@/types/api'
import { ShotRenderStatus } from '@/types/api'
import ShotRenderStatusBadge from './ShotRenderStatusBadge.vue'

const props = defineProps<{
  show: boolean
  jobId: string | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const message = useMessage()
const loading = ref(false)
const shotRenders = ref<ShotRender[]>([])
const retryingId = ref<string | null>(null)

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const ACTIVE_RENDER_STATUSES = [
  ShotRenderStatus.PENDING,
  ShotRenderStatus.GENERATING_IMAGE,
  ShotRenderStatus.GENERATING_VIDEO,
  ShotRenderStatus.GENERATING_AUDIO,
  ShotRenderStatus.COMPOSITING
]

watch(() => [props.show, props.jobId], async ([show, jobId]) => {
  if (show && jobId) {
    await loadShotRenders()
  }
})

async function loadShotRenders() {
  if (!props.jobId) return

  loading.value = true
  try {
    const response = await apiClient.listShotRenders(props.jobId)
    shotRenders.value = response.items.sort((a, b) => {
      const shotIdA = typeof a.shot_id === 'string' ? parseInt(a.shot_id) : a.shot_id
      const shotIdB = typeof b.shot_id === 'string' ? parseInt(b.shot_id) : b.shot_id
      return shotIdA - shotIdB
    })
  } catch (error) {
    console.error('Failed to load shot renders:', error)
  } finally {
    loading.value = false
  }
}

function isRenderActive(render: ShotRender): boolean {
  return ACTIVE_RENDER_STATUSES.includes(render.status)
}

async function handleRetry(render: ShotRender) {
  retryingId.value = render.id
  try {
    await apiClient.retryShotRender(render.id)
    message.success('镜头渲染重试已启动')
    await loadShotRenders()
  } catch (error) {
    console.error('Failed to retry shot render:', error)
    message.error(`重试失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    retryingId.value = null
  }
}
</script>
