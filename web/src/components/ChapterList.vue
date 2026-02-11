<template>
  <div class="space-y-4">
    <!-- Header with Add Button -->
    <div class="flex justify-between items-center">
      <h3 class="text-lg font-semibold text-white">章节列表</h3>
      <div class="flex gap-2">
        <n-button type="primary" @click="showScanModal = true" :disabled="chapters.length === 0">
          扫描角色
        </n-button>
        <n-button @click="showAddModal = true">
          添加章节
        </n-button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex justify-center py-8">
      <n-spin size="large" />
    </div>

    <!-- Empty State -->
    <n-empty
      v-else-if="chapters.length === 0"
      description="暂无章节，点击上方按钮添加或在「书籍」标签页上传整本书"
      class="py-8"
    />

    <!-- Chapter List -->
    <div v-else class="space-y-3">
      <div
        v-for="chapter in chapters"
        :key="chapter.chapter_id"
        class="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50 hover:border-gray-600/50 transition-colors"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1 cursor-pointer" @click="handleViewChapter(chapter)">
            <div class="flex items-center gap-3 mb-2">
              <span class="text-purple-400 font-mono">第 {{ chapter.chapter_number }} 章</span>
              <ChapterStatusBadge :status="chapter.status" />
              <span v-if="chapter.word_count" class="text-gray-500 text-xs">
                {{ formatWordCount(chapter.word_count) }}
              </span>
              <span v-if="chapter.suggested_episode" class="text-blue-400 text-xs">
                → 第 {{ chapter.suggested_episode }} 集
              </span>
            </div>
            <h4 class="text-white font-medium mb-1">{{ chapter.title || '无标题' }}</h4>
            <p class="text-gray-400 text-sm line-clamp-2">{{ chapter.content }}</p>

            <!-- 分析结果 -->
            <div v-if="chapter.key_events?.length" class="mt-2">
              <div class="flex flex-wrap gap-1">
                <n-tag v-if="chapter.emotional_arc" size="tiny" :type="getArcType(chapter.emotional_arc)">
                  {{ getArcLabel(chapter.emotional_arc) }}
                </n-tag>
                <n-tag size="tiny" :type="getImportanceType(chapter.importance_score ?? 0.5)">
                  重要性 {{ ((chapter.importance_score ?? 0.5) * 100).toFixed(0) }}%
                </n-tag>
              </div>
              <p class="text-gray-500 text-xs mt-1 line-clamp-1">
                {{ chapter.key_events.slice(0, 2).join('; ') }}
              </p>
            </div>
          </div>
          <n-button
            quaternary
            circle
            type="error"
            @click.stop="handleDeleteChapter(chapter)"
          >
            <template #icon>
              <n-icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                </svg>
              </n-icon>
            </template>
          </n-button>
        </div>
      </div>
    </div>

    <!-- Add Chapter Modal -->
    <AddChapterModal
      v-model:show="showAddModal"
      :project-id="projectId"
      :next-chapter-number="nextChapterNumber"
      @created="loadChapters"
    />

    <!-- Chapter Detail Modal -->
    <ChapterDetailModal
      v-model:show="showDetailModal"
      :project-id="projectId"
      :chapter-number="selectedChapterNumber"
      @analyzed="loadChapters"
    />

    <!-- Character Scan Modal -->
    <CharacterScanModal
      v-model:show="showScanModal"
      :project-id="projectId"
      :chapters="chapters"
      :existing-characters="existingCharacters"
      @characters-updated="handleCharactersUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NButton, NIcon, NSpin, NEmpty, NTag, useDialog, useMessage } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Chapter, Character } from '@/types/api'
import ChapterStatusBadge from './ChapterStatusBadge.vue'
import AddChapterModal from './AddChapterModal.vue'
import ChapterDetailModal from './ChapterDetailModal.vue'
import CharacterScanModal from './CharacterScanModal.vue'

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  'characters-updated': []
}>()

const dialog = useDialog()
const message = useMessage()

const loading = ref(false)
const chapters = ref<Chapter[]>([])
const existingCharacters = ref<Character[]>([])
const showAddModal = ref(false)
const showDetailModal = ref(false)
const showScanModal = ref(false)
const selectedChapterNumber = ref<number | null>(null)

const nextChapterNumber = computed(() => {
  if (chapters.value.length === 0) return 1
  const maxNumber = Math.max(...chapters.value.map(c => c.chapter_number))
  return maxNumber + 1
})

function formatWordCount(count: number): string {
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + '万字'
  }
  return count + '字'
}

function getArcType(arc: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const types: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    rising: 'warning',
    falling: 'info',
    climax: 'error',
    resolution: 'success',
    neutral: 'default'
  }
  return types[arc] || 'default'
}

function getArcLabel(arc: string): string {
  const labels: Record<string, string> = {
    rising: '上升',
    falling: '下降',
    climax: '高潮',
    resolution: '解决',
    neutral: '平稳'
  }
  return labels[arc] || arc
}

function getImportanceType(score: number): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (score >= 0.8) return 'error'
  if (score >= 0.5) return 'warning'
  return 'default'
}

onMounted(() => {
  loadChapters()
  loadExistingCharacters()
})

async function loadChapters() {
  loading.value = true
  try {
    const response = await apiClient.listChapters(props.projectId)
    chapters.value = response.items.sort((a, b) => a.chapter_number - b.chapter_number)
  } catch (error) {
    console.error('Failed to load chapters:', error)
  } finally {
    loading.value = false
  }
}

async function loadExistingCharacters() {
  try {
    const response = await apiClient.listCharacters(props.projectId)
    existingCharacters.value = response.items
  } catch (error) {
    console.error('Failed to load characters:', error)
  }
}

function handleCharactersUpdated() {
  loadExistingCharacters()
  emit('characters-updated')
}

function handleViewChapter(chapter: Chapter) {
  selectedChapterNumber.value = chapter.chapter_number
  showDetailModal.value = true
}

function handleDeleteChapter(chapter: Chapter) {
  dialog.warning({
    title: '删除章节',
    content: `确定要删除第 ${chapter.chapter_number} 章「${chapter.title || '无标题'}」吗？此操作无法撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.deleteChapter(props.projectId, chapter.chapter_number)
        message.success('章节删除成功')
        await loadChapters()
      } catch (error) {
        console.error('Failed to delete chapter:', error)
        message.error(`删除章节失败: ${error instanceof Error ? error.message : '未知错误'}`)
      }
    }
  })
}

// 暴露方法供父组件调用
defineExpose({
  loadChapters
})
</script>
