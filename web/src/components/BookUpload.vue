<template>
  <div class="book-upload">
    <!-- 书籍信息卡片 -->
    <n-card v-if="book" class="mb-4" title="书籍信息">
      <template #header-extra>
        <n-button size="small" @click="showEditModal = true">编辑</n-button>
      </template>
      <n-descriptions :column="2" label-placement="left">
        <n-descriptions-item label="书名">
          {{ book.original_title || '未设置' }}
        </n-descriptions-item>
        <n-descriptions-item label="作者">
          {{ book.author || '未设置' }}
        </n-descriptions-item>
        <n-descriptions-item label="类型">
          {{ book.genre || '未设置' }}
        </n-descriptions-item>
        <n-descriptions-item label="上传状态">
          <n-tag :type="uploadStatusType">{{ uploadStatusLabel }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="章节数">
          {{ book.uploaded_chapters }} / {{ book.total_chapters || '?' }}
        </n-descriptions-item>
        <n-descriptions-item label="总字数">
          {{ formatNumber(book.total_words) }}
        </n-descriptions-item>
        <n-descriptions-item v-if="book.suggested_episodes" label="建议集数">
          {{ book.suggested_episodes }} 集
        </n-descriptions-item>
      </n-descriptions>

      <!-- AI 摘要 -->
      <div v-if="book.ai_summary" class="mt-4">
        <h4 class="text-sm font-bold mb-2">AI 摘要</h4>
        <p class="text-gray-400 text-sm">{{ book.ai_summary }}</p>
      </div>

      <!-- 主要情节点 -->
      <div v-if="book.main_plot_points?.length" class="mt-4">
        <h4 class="text-sm font-bold mb-2">主要情节点</h4>
        <ul class="list-disc list-inside text-gray-400 text-sm">
          <li v-for="(point, index) in book.main_plot_points" :key="index">
            {{ point }}
          </li>
        </ul>
      </div>
    </n-card>

    <!-- 上传区域 -->
    <n-card title="上传整本书">
      <n-upload
        :custom-request="handleUpload"
        :show-file-list="false"
        accept=".txt"
        :disabled="uploading"
      >
        <n-upload-dragger>
          <div class="py-4">
            <n-icon size="48" :depth="3">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
              </svg>
            </n-icon>
            <p class="text-gray-400 mt-2">
              点击或拖拽 TXT 文件到此处上传
            </p>
            <p class="text-gray-500 text-sm mt-1">
              支持自动识别章节，支持 UTF-8/GBK 编码
            </p>
          </div>
        </n-upload-dragger>
      </n-upload>

      <div v-if="uploading" class="mt-4">
        <n-progress type="line" :percentage="uploadProgress" :show-indicator="true" />
        <p class="text-gray-400 text-sm mt-2">正在解析书籍...</p>
      </div>

      <div class="mt-4 flex gap-2">
        <n-checkbox v-model:checked="replaceExisting">
          替换现有章节
        </n-checkbox>
      </div>
    </n-card>

    <!-- 分析按钮 -->
    <div class="mt-4 flex gap-2">
      <n-button
        type="primary"
        :loading="analyzing"
        :disabled="!book || book.uploaded_chapters === 0"
        @click="handleAnalyzeBook"
      >
        AI 分析整本书
      </n-button>
      <n-button
        :loading="analyzingChapters"
        :disabled="!book || book.uploaded_chapters === 0"
        @click="handleAnalyzeChapters"
      >
        分析所有章节
      </n-button>
    </div>

    <!-- 编辑书籍信息模态框 -->
    <n-modal v-model:show="showEditModal" preset="dialog" title="编辑书籍信息">
      <n-form ref="formRef" :model="editForm" label-placement="left" label-width="80">
        <n-form-item label="书名">
          <n-input v-model:value="editForm.original_title" placeholder="输入书名" />
        </n-form-item>
        <n-form-item label="作者">
          <n-input v-model:value="editForm.author" placeholder="输入作者" />
        </n-form-item>
        <n-form-item label="类型">
          <n-input v-model:value="editForm.genre" placeholder="如：玄幻、都市、言情" />
        </n-form-item>
        <n-form-item label="总章节数">
          <n-input-number v-model:value="editForm.total_chapters" :min="0" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showEditModal = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="handleSaveBook">保存</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  NUpload,
  NUploadDragger,
  NIcon,
  NProgress,
  NCheckbox,
  NButton,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  useMessage,
  type UploadCustomRequestOptions
} from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Book, BookUpdate } from '@/types/api'
import { BookUploadStatus } from '@/types/api'

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'chaptersUpdated'): void
}>()

const message = useMessage()

const book = ref<Book | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const replaceExisting = ref(false)
const analyzing = ref(false)
const analyzingChapters = ref(false)
const showEditModal = ref(false)
const saving = ref(false)

const editForm = ref<BookUpdate>({
  original_title: '',
  author: '',
  genre: '',
  total_chapters: 0
})

const uploadStatusType = computed(() => {
  if (!book.value) return 'default'
  switch (book.value.upload_status) {
    case BookUploadStatus.COMPLETE:
      return 'success'
    case BookUploadStatus.PARTIAL:
      return 'warning'
    default:
      return 'default'
  }
})

const uploadStatusLabel = computed(() => {
  if (!book.value) return '未知'
  switch (book.value.upload_status) {
    case BookUploadStatus.COMPLETE:
      return '已完成'
    case BookUploadStatus.PARTIAL:
      return '部分上传'
    default:
      return '未上传'
  }
})

function formatNumber(num: number): string {
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + ' 万'
  }
  return num.toLocaleString()
}

async function loadBook() {
  try {
    book.value = await apiClient.getBook(props.projectId)
    editForm.value = {
      original_title: book.value.original_title || '',
      author: book.value.author || '',
      genre: book.value.genre || '',
      total_chapters: book.value.total_chapters || 0
    }
  } catch (e) {
    // 书籍可能不存在，忽略错误
  }
}

async function handleUpload(options: UploadCustomRequestOptions) {
  const file = options.file.file
  if (!file) {
    options.onError()
    return
  }

  uploading.value = true
  uploadProgress.value = 0

  try {
    // 模拟进度
    const progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += 10
      }
    }, 500)

    const result = await apiClient.uploadBook(props.projectId, file, replaceExisting.value)

    clearInterval(progressInterval)
    uploadProgress.value = 100

    message.success(`成功解析 ${result.total} 个章节`)
    await loadBook()
    emit('chaptersUpdated')
    options.onFinish()
  } catch (e) {
    message.error((e as Error).message)
    options.onError()
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

async function handleAnalyzeBook() {
  analyzing.value = true
  try {
    book.value = await apiClient.analyzeBook(props.projectId)
    message.success('书籍分析完成')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    analyzing.value = false
  }
}

async function handleAnalyzeChapters() {
  analyzingChapters.value = true
  try {
    const result = await apiClient.analyzeAllChapters(props.projectId)
    message.success(`已分析 ${result.analyzed_count} 个章节`)
    emit('chaptersUpdated')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    analyzingChapters.value = false
  }
}

async function handleSaveBook() {
  saving.value = true
  try {
    book.value = await apiClient.updateBook(props.projectId, editForm.value)
    showEditModal.value = false
    message.success('保存成功')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

watch(() => props.projectId, () => {
  loadBook()
})

onMounted(() => {
  loadBook()
})
</script>
