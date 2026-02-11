<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="`第 ${chapter?.chapter_number} 章: ${chapter?.title || '无标题'}`"
    class="max-w-4xl"
  >
    <template v-if="loading">
      <div class="flex justify-center py-8">
        <n-spin size="large" />
      </div>
    </template>

    <template v-else-if="loadError">
      <div class="flex flex-col items-center justify-center py-8 text-red-400">
        <p>加载失败: {{ loadError }}</p>
        <n-button class="mt-4" @click="loadChapter">重试</n-button>
      </div>
    </template>

    <template v-else-if="chapter">
      <div class="space-y-4">
        <!-- 基本信息 -->
        <div class="grid grid-cols-2 gap-4">
          <div class="flex items-center gap-2">
            <span class="text-gray-400">状态:</span>
            <ChapterStatusBadge :status="chapter.status" />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">字数:</span>
            <span class="text-white">{{ formatWordCount(chapter.word_count) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">创建时间:</span>
            <span class="text-white">{{ formatDate(chapter.created_at) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">更新时间:</span>
            <span class="text-white">{{ formatDate(chapter.updated_at) }}</span>
          </div>
        </div>

        <!-- 分析结果 -->
        <template v-if="chapter.status === 'READY'">
          <n-divider>AI 分析结果</n-divider>

          <div class="grid grid-cols-2 gap-4">
            <div class="flex items-center gap-2">
              <span class="text-gray-400">情感曲线:</span>
              <n-tag :type="getArcType(chapter.emotional_arc)" size="small">
                {{ getArcLabel(chapter.emotional_arc) }}
              </n-tag>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-gray-400">重要性:</span>
              <n-progress
                type="line"
                :percentage="(chapter.importance_score ?? 0.5) * 100"
                :show-indicator="false"
                :height="8"
                style="width: 100px"
                :color="getImportanceColor(chapter.importance_score ?? 0.5)"
              />
              <span class="text-white text-sm">{{ ((chapter.importance_score ?? 0.5) * 100).toFixed(0) }}%</span>
            </div>
            <div v-if="chapter.suggested_episode" class="flex items-center gap-2">
              <span class="text-gray-400">建议归属:</span>
              <span class="text-blue-400">第 {{ chapter.suggested_episode }} 集</span>
            </div>
          </div>

          <!-- 关键事件 -->
          <div v-if="chapter.key_events?.length">
            <h4 class="text-gray-400 mb-2">关键事件</h4>
            <ul class="list-disc list-inside space-y-1">
              <li v-for="(event, index) in chapter.key_events" :key="index" class="text-white text-sm">
                {{ event }}
              </li>
            </ul>
          </div>

          <!-- 出场角色 -->
          <div v-if="chapter.characters_appeared?.length">
            <h4 class="text-gray-400 mb-2">出场角色</h4>
            <div class="flex flex-wrap gap-2">
              <n-tag
                v-for="char in chapter.characters_appeared"
                :key="char"
                type="info"
                size="small"
              >
                {{ char }}
              </n-tag>
            </div>
          </div>
        </template>

        <n-divider />

        <!-- 章节内容 -->
        <div>
          <h4 class="text-gray-400 mb-2">章节内容</h4>
          <div class="bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
            <pre class="text-white whitespace-pre-wrap font-sans text-sm">{{ chapter.content }}</pre>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-between">
        <n-button
          v-if="chapter && chapter.status !== 'READY'"
          type="primary"
          :loading="analyzing"
          @click="handleAnalyze"
        >
          分析此章节
        </n-button>
        <div v-else></div>
        <n-button @click="visible = false">关闭</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NButton, NSpin, NDivider, NTag, NProgress, useMessage } from 'naive-ui'
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
  'analyzed': []
}>()

const message = useMessage()
const loading = ref(false)
const analyzing = ref(false)
const chapter = ref<Chapter | null>(null)
const loadError = ref<string | null>(null)

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
  loadError.value = null
  try {
    console.log('Loading chapter:', props.projectId, props.chapterNumber)
    chapter.value = await apiClient.getChapter(props.projectId, props.chapterNumber)
    console.log('Chapter loaded:', chapter.value)
  } catch (error) {
    console.error('Failed to load chapter:', error)
    loadError.value = (error as Error).message
    message.error(`加载章节失败: ${(error as Error).message}`)
  } finally {
    loading.value = false
  }
}

async function handleAnalyze() {
  if (props.chapterNumber === null) return

  analyzing.value = true
  try {
    await apiClient.analyzeChapter(props.projectId, props.chapterNumber)
    // 分析完成后重新加载完整的章节数据
    chapter.value = await apiClient.getChapter(props.projectId, props.chapterNumber)
    message.success('章节分析完成')
    // 通知父组件刷新列表
    emit('analyzed')
  } catch (error) {
    message.error(`分析失败: ${(error as Error).message}`)
  } finally {
    analyzing.value = false
  }
}

function formatDate(date: string): string {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

function formatWordCount(count?: number): string {
  if (count === undefined || count === null) return '未知'
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + ' 万字'
  }
  return count.toLocaleString() + ' 字'
}

function getArcType(arc?: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const types: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    rising: 'warning',
    falling: 'info',
    climax: 'error',
    resolution: 'success',
    neutral: 'default'
  }
  return types[arc || ''] || 'default'
}

function getArcLabel(arc?: string): string {
  const labels: Record<string, string> = {
    rising: '上升',
    falling: '下降',
    climax: '高潮',
    resolution: '解决',
    neutral: '平稳'
  }
  return labels[arc || ''] || arc || '未分析'
}

function getImportanceColor(score: number): string {
  if (score >= 0.8) return '#d03050'
  if (score >= 0.5) return '#f0a020'
  return '#63e2b7'
}
</script>
