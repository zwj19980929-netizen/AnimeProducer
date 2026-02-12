<template>
  <div class="character-image-gallery">
    <!-- 操作栏 -->
    <div class="flex justify-between items-center mb-4">
      <div class="flex gap-2">
        <n-upload
          :show-file-list="false"
          accept="image/jpeg,image/png,image/webp"
          :multiple="true"
          :max="20"
          @change="handleUploadChange"
        >
          <n-button :loading="uploading">
            上传图片
          </n-button>
        </n-upload>
        <n-button type="primary" @click="showGenerateModal = true" :disabled="!hasAnchor">
          生成变体图
        </n-button>
        <n-button @click="showReferenceModal = true" :disabled="generating">
          生成候选图
        </n-button>
        <n-button
          v-if="selectedImages.length > 0"
          @click="handleMarkForTraining(true)"
        >
          标记训练 ({{ selectedImages.length }})
        </n-button>
        <n-button
          v-if="selectedImages.length > 0"
          type="error"
          ghost
          @click="handleDeleteSelected"
        >
          删除选中
        </n-button>
      </div>
      <div class="flex items-center gap-4">
        <n-button text @click="loadImages" :loading="loading" title="刷新图片列表">
          <span style="display: flex; align-items: center; gap: 4px;">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
            </svg>
            刷新
          </span>
        </n-button>
        <n-select
          v-model:value="filterType"
          :options="filterOptions"
          placeholder="筛选类型"
          clearable
          style="width: 140px"
        />
        <span class="text-gray-400 text-sm">
          共 {{ images.length }} 张 | 训练图 {{ trainingCount }} 张
        </span>
      </div>
    </div>

    <!-- 锚定图提示 -->
    <n-alert v-if="!hasAnchor" type="warning" class="mb-4">
      请先选择一张图片作为锚定图（确定角色形象），之后才能生成变体图用于 LoRA 训练。
    </n-alert>

    <!-- 生成进度卡片 -->
    <n-card v-if="generationJob" class="mb-4" size="small">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4 flex-1">
          <n-spin size="small" v-if="generationJob.status === 'STARTED' || generationJob.status === 'PENDING'" />
          <n-icon v-else-if="generationJob.status === 'SUCCESS'" color="#18a058" size="20">
            <CheckCircleIcon />
          </n-icon>
          <n-icon v-else-if="generationJob.status === 'FAILURE'" color="#d03050" size="20">
            <CloseCircleIcon />
          </n-icon>
          <div class="flex-1">
            <div class="text-sm font-medium">
              {{ generationJob.message || '正在生成图片...' }}
            </div>
            <n-progress
              v-if="generationJob.status === 'STARTED' || generationJob.status === 'PENDING'"
              type="line"
              :percentage="Math.round(generationJob.progress * 100)"
              :show-indicator="false"
              class="mt-1"
            />
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="generationJob.current_image" class="text-sm text-gray-400">
            {{ generationJob.current_image }}/{{ generationJob.total_images }}
          </span>
          <n-button
            v-if="generationJob.status === 'STARTED' || generationJob.status === 'PENDING'"
            size="small"
            type="error"
            ghost
            @click="handleCancelGeneration"
          >
            取消
          </n-button>
          <n-button
            v-else
            size="small"
            @click="clearGenerationJob"
          >
            关闭
          </n-button>
        </div>
      </div>

      <!-- 实时生成的图片预览 -->
      <div v-if="realtimeImages.length > 0" class="mt-3 flex gap-2 flex-wrap">
        <div
          v-for="img in realtimeImages"
          :key="img.id"
          class="w-16 h-16 rounded overflow-hidden border border-gray-600"
        >
          <img
            :src="img.image_url || img.image_path"
            class="w-full h-full object-cover"
          />
        </div>
      </div>
    </n-card>

    <!-- 图片网格 -->
    <n-spin :show="loading">
      <div v-if="filteredImages.length === 0 && !loading" class="text-center py-8 text-gray-400">
        暂无图片，点击"生成候选图"开始
      </div>

      <div v-else class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <div
          v-for="image in filteredImages"
          :key="image.id"
          class="relative group cursor-pointer rounded-lg overflow-hidden border-2 transition-all"
          :class="{
            'border-purple-500': image.is_anchor,
            'border-green-500': image.is_selected_for_training && !image.is_anchor,
            'border-blue-500': selectedImages.includes(image.id),
            'border-gray-700': !image.is_anchor && !image.is_selected_for_training && !selectedImages.includes(image.id)
          }"
          @click="toggleSelect(image.id)"
        >
          <!-- 图片 -->
          <img
            :src="image.image_url || image.image_path"
            :alt="image.prompt"
            class="w-full aspect-square object-cover"
          />

          <!-- 标签 -->
          <div class="absolute top-2 left-2 flex flex-wrap gap-1" style="max-width: calc(100% - 40px);">
            <n-tag v-if="image.is_anchor" type="warning" size="tiny" :bordered="false" style="color: #000; background: rgba(250, 173, 20, 0.9);">锚定图</n-tag>
            <n-tag v-if="image.is_selected_for_training" type="success" size="tiny" :bordered="false" style="color: #000; background: rgba(82, 196, 26, 0.9);">训练</n-tag>
            <n-tag v-if="image.pose" size="tiny" :bordered="false" style="color: #000; background: rgba(64, 158, 255, 0.9);">{{ translatePose(image.pose) }}</n-tag>
            <n-tag v-if="image.expression" size="tiny" :bordered="false" style="color: #000; background: rgba(255, 255, 255, 0.9);">{{ translateExpression(image.expression) }}</n-tag>
            <n-tag v-if="image.angle" size="tiny" :bordered="false" style="color: #000; background: rgba(144, 147, 153, 0.9);">{{ translateAngle(image.angle) }}</n-tag>
          </div>

          <!-- 悬浮操作 -->
          <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <n-button
              v-if="!image.is_anchor"
              size="small"
              type="warning"
              @click.stop="handleSetAnchor(image)"
            >
              设为锚定
            </n-button>
            <n-button
              size="small"
              :type="image.is_selected_for_training ? 'default' : 'success'"
              @click.stop="handleToggleTraining(image)"
            >
              {{ image.is_selected_for_training ? '取消训练' : '标记训练' }}
            </n-button>
            <n-button
              size="small"
              type="error"
              @click.stop="handleDelete(image)"
              :disabled="image.is_anchor"
            >
              删除
            </n-button>
          </div>

          <!-- 选中标记 -->
          <div
            v-if="selectedImages.includes(image.id)"
            class="absolute top-2 right-2 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center"
          >
            <svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
          </div>
        </div>
      </div>
    </n-spin>

    <!-- 生成变体弹窗 -->
    <n-modal v-model:show="showGenerateModal" preset="card" title="生成变体图" class="max-w-lg">
      <div class="space-y-4">
        <n-form-item label="姿态">
          <n-select
            v-model:value="variantForm.pose"
            :options="poseOptions"
            placeholder="选择姿态"
            clearable
          />
        </n-form-item>

        <n-form-item label="表情">
          <n-select
            v-model:value="variantForm.expression"
            :options="expressionOptions"
            placeholder="选择表情"
            clearable
          />
        </n-form-item>

        <n-form-item label="角度">
          <n-select
            v-model:value="variantForm.angle"
            :options="angleOptions"
            placeholder="选择角度"
            clearable
          />
        </n-form-item>

        <n-form-item label="自定义提示词">
          <n-input
            v-model:value="variantForm.custom_prompt"
            type="textarea"
            placeholder="额外的描述（可选）"
            :rows="2"
          />
        </n-form-item>

        <n-form-item label="负面提示词">
          <n-input
            v-model:value="variantForm.negative_prompt"
            type="textarea"
            placeholder="不想要的内容，如 blurry, low quality, deformed（可选）"
            :rows="2"
          />
        </n-form-item>

        <n-form-item label="随机种子">
          <n-input-number
            v-model:value="variantForm.seed"
            :min="0"
            :max="2147483647"
            placeholder="留空则随机"
            clearable
            style="width: 100%"
          />
        </n-form-item>

        <n-form-item label="生成数量">
          <n-input-number v-model:value="variantForm.num_images" :min="1" :max="4" />
        </n-form-item>
      </div>

      <template #footer>
        <div class="flex justify-between">
          <n-button @click="handleBatchGenerate" :loading="generating">
            批量生成（多种组合）
          </n-button>
          <div class="flex gap-2">
            <n-button @click="showGenerateModal = false">取消</n-button>
            <n-button type="primary" @click="handleGenerateVariant" :loading="generating">
              生成
            </n-button>
          </div>
        </div>
      </template>
    </n-modal>

    <!-- 生成候选图弹窗 -->
    <n-modal v-model:show="showReferenceModal" preset="card" title="生成候选图" class="max-w-lg">
      <div class="space-y-4">
        <n-form-item label="生成模型">
          <n-select
            v-model:value="referenceForm.image_provider"
            :options="imageProviderOptions"
            placeholder="使用默认模型"
            clearable
          />
        </n-form-item>

        <n-form-item label="自定义提示词">
          <n-input
            v-model:value="referenceForm.custom_prompt"
            type="textarea"
            placeholder="额外的描述（可选，会追加到角色外貌描述后）"
            :rows="2"
          />
        </n-form-item>

        <n-form-item label="风格预设">
          <n-input
            v-model:value="referenceForm.style_preset"
            placeholder="如 anime style, realistic, watercolor"
          />
        </n-form-item>

        <n-form-item label="负面提示词">
          <n-input
            v-model:value="referenceForm.negative_prompt"
            type="textarea"
            placeholder="不想要的内容，如 blurry, low quality, deformed（可选）"
            :rows="2"
          />
        </n-form-item>

        <n-form-item label="随机种子">
          <n-input-number
            v-model:value="referenceForm.seed"
            :min="0"
            :max="2147483647"
            placeholder="留空则随机"
            clearable
            style="width: 100%"
          />
        </n-form-item>

        <n-form-item label="生成数量">
          <n-input-number v-model:value="referenceForm.num_candidates" :min="1" :max="8" />
        </n-form-item>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showReferenceModal = false">取消</n-button>
          <n-button type="primary" @click="handleGenerateReference" :loading="generating">
            生成
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted, h } from 'vue'
import { NButton, NSelect, NTag, NSpin, NModal, NFormItem, NInput, NInputNumber, NAlert, NCard, NProgress, NIcon, NUpload, useMessage, useDialog } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { CharacterImage, Character, ImageProvider } from '@/types/api'
import { CharacterImageType, IMAGE_PROVIDERS } from '@/types/api'

// Simple SVG icons as render functions
const CheckCircleIcon = () => h('svg', { viewBox: '0 0 24 24', fill: 'currentColor', width: '1em', height: '1em' }, [
  h('path', { d: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z' })
])
const CloseCircleIcon = () => h('svg', { viewBox: '0 0 24 24', fill: 'currentColor', width: '1em', height: '1em' }, [
  h('path', { d: 'M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z' })
])

// 图片生成模型选项
const imageProviderOptions = IMAGE_PROVIDERS.map(p => ({
  label: p.label,
  value: p.value,
  description: p.description,
}))

const props = defineProps<{
  characterId: string
  character: Character
}>()

const emit = defineEmits<{
  'anchor-changed': [character: Character]
  'images-changed': []
  'training-count-changed': [count: number]
}>()

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const generating = ref(false)
const uploading = ref(false)
const images = ref<CharacterImage[]>([])
const selectedImages = ref<string[]>([])
const filterType = ref<string>('')
const showGenerateModal = ref(false)
const showReferenceModal = ref(false)

// 异步生成相关状态
const generationJob = ref<{
  job_id: string
  status: string
  progress: number
  message?: string
  current_image?: number
  total_images?: number
} | null>(null)
const realtimeImages = ref<CharacterImage[]>([])

const variantForm = ref({
  pose: null as string | null,
  expression: null as string | null,
  angle: null as string | null,
  custom_prompt: '',
  negative_prompt: '',
  seed: null as number | null,
  num_images: 1
})

const referenceForm = ref({
  custom_prompt: '',
  style_preset: 'anime style',
  negative_prompt: '',
  seed: null as number | null,
  num_candidates: 4,
  image_provider: null as ImageProvider | null,
})

const hasAnchor = computed(() => !!props.character.anchor_image_id)

const trainingCount = computed(() =>
  images.value.filter(img => img.is_selected_for_training).length
)

const filteredImages = computed(() => {
  if (!filterType.value) return images.value
  return images.value.filter(img => img.image_type === filterType.value)
})

const filterOptions = [
  { label: '全部', value: '' },
  { label: '候选图', value: CharacterImageType.CANDIDATE },
  { label: '锚定图', value: CharacterImageType.ANCHOR },
  { label: '变体图', value: CharacterImageType.VARIANT },
  { label: '训练图', value: CharacterImageType.TRAINING },
]

const poseOptions = [
  { label: '站立', value: 'standing' },
  { label: '坐着', value: 'sitting' },
  { label: '走路', value: 'walking' },
  { label: '跑步', value: 'running' },
  { label: '双手交叉', value: 'arms crossed' },
  { label: '双手叉腰', value: 'hands on hips' },
  { label: '挥手', value: 'waving' },
  { label: '战斗姿态', value: 'fighting stance' },
]

const expressionOptions = [
  { label: '中性', value: 'neutral' },
  { label: '微笑', value: 'smiling' },
  { label: '大笑', value: 'laughing' },
  { label: '严肃', value: 'serious' },
  { label: '惊讶', value: 'surprised' },
  { label: '思考', value: 'thinking' },
  { label: '悲伤', value: 'sad' },
  { label: '愤怒', value: 'angry' },
  { label: '害羞', value: 'shy' },
]

const angleOptions = [
  { label: '正面', value: 'front view' },
  { label: '侧面', value: 'side view' },
  { label: '四分之三', value: 'three-quarter view' },
  { label: '仰视', value: 'low angle' },
  { label: '俯视', value: 'high angle' },
  { label: '背面', value: 'back view' },
]

// 翻译映射
const poseMap: Record<string, string> = {
  'standing': '站立',
  'sitting': '坐姿',
  'walking': '走路',
  'running': '跑步',
  'arms crossed': '双手交叉',
  'hands on hips': '双手叉腰',
  'waving': '挥手',
  'fighting stance': '战斗姿态',
}

const expressionMap: Record<string, string> = {
  'neutral': '中性',
  'smiling': '微笑',
  'laughing': '大笑',
  'serious': '严肃',
  'surprised': '惊讶',
  'thinking': '思考',
  'sad': '悲伤',
  'angry': '愤怒',
  'shy': '害羞',
  'happy': '开心',
}

const angleMap: Record<string, string> = {
  'front view': '正面',
  'side view': '侧面',
  'three-quarter view': '斜侧',
  'low angle': '仰视',
  'high angle': '俯视',
  'back view': '背面',
}

function translatePose(pose: string): string {
  return poseMap[pose] || pose
}

function translateExpression(expression: string): string {
  return expressionMap[expression] || expression
}

function translateAngle(angle: string): string {
  return angleMap[angle] || angle
}

onMounted(async () => {
  await loadImages()
  // 检查是否有正在进行的生成任务
  await checkPendingJobs()
})

onUnmounted(() => {
  stopPollingJob()
})

watch(() => props.characterId, async () => {
  // 清理之前的轮询
  stopPollingJob()
  generationJob.value = null
  realtimeImages.value = []
  await loadImages()
  await checkPendingJobs()
})

async function checkPendingJobs() {
  try {
    const jobs = await apiClient.listCharacterGenerationJobs(props.characterId, 1)
    console.log('Checking pending jobs:', jobs)
    const pendingJob = jobs.find(j => String(j.status) === 'PENDING' || String(j.status) === 'STARTED')
    if (pendingJob) {
      console.log('Found pending job:', pendingJob)
      // 恢复正在进行的任务
      const result = pendingJob.result as { num_candidates?: number; num_images?: number; generation_type?: string; variants?: unknown[] } | null
      const genType = result?.generation_type
      let jobMessage = '正在生成候选图...'
      if (genType === 'variant') {
        jobMessage = '正在生成变体图...'
      } else if (genType === 'batch_variant') {
        jobMessage = '正在批量生成变体图...'
      }
      generationJob.value = {
        job_id: pendingJob.id,
        status: String(pendingJob.status),
        progress: pendingJob.progress || 0,
        message: jobMessage,
        total_images: result?.num_images || result?.variants?.length || result?.num_candidates || 4
      }
      generating.value = true
      // 开始轮询任务状态
      startPollingJob(pendingJob.id)
    }
  } catch (error) {
    console.error('Failed to check pending jobs:', error)
  }
}

let pollingTimer: number | null = null

function startPollingJob(jobId: string) {
  // 清理之前的轮询
  stopPollingJob()

  console.log('Start polling job:', jobId)

  // 立即查询一次
  pollJobStatus(jobId)

  // 每 2 秒轮询一次
  pollingTimer = window.setInterval(() => {
    pollJobStatus(jobId)
  }, 2000)
}

function stopPollingJob() {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

async function pollJobStatus(jobId: string) {
  try {
    const job = await apiClient.getJob(jobId)
    console.log('Poll job status:', job)

    if (!generationJob.value) return

    // 更新进度
    generationJob.value.status = String(job.status)
    generationJob.value.progress = job.progress || 0

    // 从 result 中获取详细信息
    const result = job.result as {
      generated_count?: number
      num_images?: number
      num_candidates?: number
      variants?: unknown[]
    } | null

    const total = generationJob.value.total_images || result?.num_images || result?.variants?.length || result?.num_candidates || 4
    const current = Math.round(job.progress * total)

    if (job.status === 'STARTED' || job.status === 'PENDING') {
      generationJob.value.message = `正在生成第 ${current}/${total} 张图片...`
      generationJob.value.current_image = current
    }

    // 任务完成
    if (job.status === 'SUCCESS') {
      stopPollingJob()
      generating.value = false
      const count = (job.result as { generated_count?: number })?.generated_count || 0
      generationJob.value.message = `生成完成，共 ${count} 张图片`
      message.success(`生成完成，共 ${count} 张图片`)
      await loadImages()
    } else if (job.status === 'FAILURE') {
      stopPollingJob()
      generating.value = false
      generationJob.value.message = job.error_message || '生成失败'
      message.error(job.error_message || '生成失败')
    } else if (job.status === 'REVOKED') {
      stopPollingJob()
      generating.value = false
      generationJob.value.message = '生成已取消'
      message.info('生成已取消')
    }
  } catch (error) {
    console.error('Failed to poll job status:', error)
  }
}

async function loadImages() {
  loading.value = true
  try {
    const response = await apiClient.listCharacterImages(props.characterId)
    images.value = response.items
    // 通知父组件训练图片数量变化
    emit('training-count-changed', trainingCount.value)
  } catch (error) {
    console.error('Failed to load images:', error)
    message.error('加载图片失败')
  } finally {
    loading.value = false
  }
}

function toggleSelect(imageId: string) {
  const index = selectedImages.value.indexOf(imageId)
  if (index === -1) {
    selectedImages.value.push(imageId)
  } else {
    selectedImages.value.splice(index, 1)
  }
}

async function handleUploadChange(options: { fileList: UploadFileInfo[] }) {
  const files: File[] = []
  for (const f of options.fileList) {
    if (f.file && f.status !== 'error') {
      files.push(f.file)
    }
  }

  if (files.length === 0) return

  uploading.value = true
  try {
    if (files.length === 1) {
      await apiClient.uploadCharacterImage(props.characterId, files[0]!, true)
      message.success('图片上传成功，已标记为训练图')
    } else {
      const result = await apiClient.uploadCharacterImagesBatch(props.characterId, files, true)
      message.success(`成功上传 ${result.total} 张图片，已标记为训练图`)
    }
    await loadImages()
  } catch (error) {
    console.error('Failed to upload images:', error)
    message.error(`上传失败: ${(error as Error).message}`)
  } finally {
    uploading.value = false
  }
}

async function handleGenerateReference() {
  generating.value = true
  realtimeImages.value = []

  try {
    const response = await apiClient.generateCharacterReference(props.characterId, {
      custom_prompt: referenceForm.value.custom_prompt || undefined,
      style_preset: referenceForm.value.style_preset || undefined,
      negative_prompt: referenceForm.value.negative_prompt || undefined,
      seed: referenceForm.value.seed ?? undefined,
      num_candidates: referenceForm.value.num_candidates,
      image_provider: referenceForm.value.image_provider || undefined,
    })

    // 设置生成任务状态
    generationJob.value = {
      job_id: response.job_id,
      status: String(response.status),
      progress: 0,
      message: response.message,
      total_images: referenceForm.value.num_candidates
    }

    showReferenceModal.value = false

    // 开始轮询任务状态
    startPollingJob(response.job_id)

    message.info('图片生成任务已创建，请等待...')
  } catch (error) {
    console.error('Failed to start generation:', error)
    message.error(`创建生成任务失败: ${(error as Error).message}`)
    generating.value = false
  }
}

async function handleCancelGeneration() {
  if (!generationJob.value) return

  try {
    await apiClient.cancelJob(generationJob.value.job_id)
    message.info('正在取消生成任务...')
  } catch (error) {
    console.error('Failed to cancel job:', error)
    message.error(`取消失败: ${(error as Error).message}`)
  }
}

function clearGenerationJob() {
  stopPollingJob()
  generationJob.value = null
  realtimeImages.value = []
}

async function handleGenerateVariant() {
  if (!variantForm.value.pose && !variantForm.value.expression && !variantForm.value.angle && !variantForm.value.custom_prompt) {
    message.warning('请至少选择一个变体选项')
    return
  }

  generating.value = true
  realtimeImages.value = []

  try {
    const response = await apiClient.generateCharacterVariants(props.characterId, {
      pose: variantForm.value.pose || undefined,
      expression: variantForm.value.expression || undefined,
      angle: variantForm.value.angle || undefined,
      custom_prompt: variantForm.value.custom_prompt || undefined,
      negative_prompt: variantForm.value.negative_prompt || undefined,
      seed: variantForm.value.seed ?? undefined,
      num_images: variantForm.value.num_images
    })

    // 设置生成任务状态
    generationJob.value = {
      job_id: response.job_id,
      status: String(response.status),
      progress: 0,
      message: response.message,
      total_images: variantForm.value.num_images
    }

    showGenerateModal.value = false

    // 开始轮询任务状态
    startPollingJob(response.job_id)

    message.info('变体图生成任务已创建，请等待...')
  } catch (error) {
    console.error('Failed to generate variant:', error)
    message.error(`生成失败: ${(error as Error).message}`)
    generating.value = false
  }
}

async function handleBatchGenerate() {
  generating.value = true
  realtimeImages.value = []

  try {
    const response = await apiClient.batchGenerateCharacterVariants(props.characterId, {
      style_preset: 'anime style',
      negative_prompt: variantForm.value.negative_prompt || undefined
    })

    // 设置生成任务状态（默认 21 张变体图：8表情正面 + 3斜侧 + 2侧面 + 2仰俯 + 3坐姿 + 2走路 + 1害羞）
    generationJob.value = {
      job_id: response.job_id,
      status: String(response.status),
      progress: 0,
      message: response.message,
      total_images: 21
    }

    showGenerateModal.value = false

    // 开始轮询任务状态
    startPollingJob(response.job_id)

    message.info('批量变体图生成任务已创建，请等待...')
  } catch (error) {
    console.error('Failed to batch generate:', error)
    message.error(`批量生成失败: ${(error as Error).message}`)
    generating.value = false
  }
}

async function handleSetAnchor(image: CharacterImage) {
  try {
    const character = await apiClient.setAnchorImage(props.characterId, image.id)
    message.success('已设为锚定图')
    emit('anchor-changed', character)
    await loadImages()
  } catch (error) {
    console.error('Failed to set anchor:', error)
    message.error(`设置失败: ${(error as Error).message}`)
  }
}

async function handleToggleTraining(image: CharacterImage) {
  try {
    await apiClient.markTrainingImages(
      props.characterId,
      [image.id],
      !image.is_selected_for_training
    )
    await loadImages()
  } catch (error) {
    console.error('Failed to toggle training:', error)
    message.error(`操作失败: ${(error as Error).message}`)
  }
}

async function handleMarkForTraining(selected: boolean) {
  if (selectedImages.value.length === 0) return

  try {
    await apiClient.markTrainingImages(props.characterId, selectedImages.value, selected)
    message.success(selected ? '已标记为训练图' : '已取消训练标记')
    selectedImages.value = []
    await loadImages()
  } catch (error) {
    console.error('Failed to mark training:', error)
    message.error(`操作失败: ${(error as Error).message}`)
  }
}

async function handleDelete(image: CharacterImage) {
  dialog.warning({
    title: '删除图片',
    content: '确定要删除这张图片吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.deleteCharacterImage(props.characterId, image.id)
        message.success('已删除')
        await loadImages()
      } catch (error) {
        console.error('Failed to delete:', error)
        message.error(`删除失败: ${(error as Error).message}`)
      }
    }
  })
}

async function handleDeleteSelected() {
  if (selectedImages.value.length === 0) return

  dialog.warning({
    title: '删除图片',
    content: `确定要删除选中的 ${selectedImages.value.length} 张图片吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      for (const imageId of selectedImages.value) {
        try {
          await apiClient.deleteCharacterImage(props.characterId, imageId)
        } catch (error) {
          console.error(`Failed to delete ${imageId}:`, error)
        }
      }
      message.success('已删除选中图片')
      selectedImages.value = []
      await loadImages()
    }
  })
}

defineExpose({
  loadImages
})
</script>
