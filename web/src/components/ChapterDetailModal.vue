<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="`章节 ${chapter?.chapter_number}: ${chapter?.title}`"
    class="max-w-4xl"
  >
    <template v-if="loading">
      <div class="flex justify-center py-8">
        <n-spin size="large" />
      </div>
    </template>

    <template v-else-if="chapter">
      <div class="space-y-4">
        <div class="flex items-center gap-4">
          <span class="text-gray-400">状态:</span>
          <ChapterStatusBadge :status="chapter.status" />
        </div>

        <div class="flex items-center gap-4">
          <span class="text-gray-400">创建时间:</span>
          <span class="text-white">{{ formatDate(chapter.created_at) }}</span>
        </div>

        <div class="flex items-center gap-4">
          <span class="text-gray-400">更新时间:</span>
          <span class="text-white">{{ formatDate(chapter.updated_at) }}</span>
        </div>

        <n-divider />

        <div>
          <h4 class="text-gray-400 mb-2">章节内容</h4>
          <div class="bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
            <pre class="text-white whitespace-pre-wrap font-sans text-sm">{{ chapter.content }}</pre>
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
import { NModal, NButton, NSpin, NDivider } from 'naive-ui'
import dayjs from 'dayjs'
import { apiClient } from '@/api/client'
import type { Chapter } from '@/types/api'
import ChapterStatusBadge from './ChapterStatusBadge.vue'

const props = defineProps<{
  show: boolean
  projectId: string
  chapterNumber: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const loading = ref(false)
const chapter = ref<Chapter | null>(null)

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

watch(() => [props.show, props.chapterNumber], async ([show, chapterNum]) => {
  if (show && chapterNum !== null) {
    await loadChapter()
  }
})

async function loadChapter() {
  if (props.chapterNumber === null) return

  loading.value = true
  try {
    chapter.value = await apiClient.getChapter(props.projectId, props.chapterNumber)
  } catch (error) {
    console.error('Failed to load chapter:', error)
  } finally {
    loading.value = false
  }
}

function formatDate(date: string): string {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}
</script>
