<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="isEditing ? '编辑角色' : '创建角色'"
    class="max-w-4xl"
    :mask-closable="false"
  >
    <n-tabs v-model:value="activeTab" type="line">
      <!-- 基本信息 -->
      <n-tab-pane name="basic" tab="基本信息">
        <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
          <n-form-item label="角色ID" path="character_id" v-if="!isEditing">
            <n-input
              v-model:value="formData.character_id"
              placeholder="输入唯一的角色ID（如：protagonist、villain）"
              :maxlength="50"
            />
          </n-form-item>

          <n-form-item label="角色名称" path="name">
            <n-input
              v-model:value="formData.name"
              placeholder="输入角色名称"
              :maxlength="100"
              show-count
            />
          </n-form-item>

          <n-form-item label="外貌描述" path="appearance_prompt">
            <n-input
              v-model:value="formData.appearance_prompt"
              type="textarea"
              placeholder="详细描述角色的外貌特征，用于生成图片（如：黑色长发、蓝色眼睛、穿着白色连衣裙...）"
              :rows="4"
              :maxlength="2000"
              show-count
            />
            <template #feedback>
              <span class="text-gray-500 text-xs">这个描述将用于生成角色图片，请尽量详细</span>
            </template>
          </n-form-item>

          <n-form-item label="角色简介" path="bio">
            <n-input
              v-model:value="formData.bio"
              type="textarea"
              placeholder="角色的背景故事、性格特点等..."
              :rows="3"
              :maxlength="1000"
              show-count
            />
            <template #feedback>
              <span class="text-gray-500 text-xs">角色的背景信息，不影响图片生成</span>
            </template>
          </n-form-item>
        </n-form>
      </n-tab-pane>

      <!-- 图片库 (仅编辑模式) -->
      <n-tab-pane v-if="isEditing" name="gallery" tab="图片库">
        <CharacterImageGallery
          v-if="character"
          ref="galleryRef"
          :character-id="character.character_id"
          :character="character"
          @anchor-changed="handleAnchorChanged"
          @training-count-changed="handleTrainingCountChanged"
        />
      </n-tab-pane>

      <!-- LoRA 训练 (仅编辑模式) -->
      <n-tab-pane v-if="isEditing" name="lora" tab="LoRA 训练">
        <div class="space-y-4">
          <!-- 训练图片统计 -->
          <n-alert type="info">
            <template #header>训练图片</template>
            请先在「图片库」中选择要用于训练的图片（标记为训练图），然后再开始训练。
            建议选择 15-30 张不同姿态/表情的图片。
          </n-alert>

          <div class="flex items-center gap-4">
            <span class="text-gray-400">已选择训练图:</span>
            <span class="text-white font-bold">{{ trainingImageCount }} 张</span>
            <n-button size="small" @click="activeTab = 'gallery'">
              去选择
            </n-button>
          </div>

          <n-divider />

          <!-- LoRA 状态 -->
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-gray-400">状态:</span>
              <n-tag v-if="!activeLora" type="default" size="small">未训练</n-tag>
              <n-tag v-else-if="activeLora.status === 'READY'" type="success" size="small">已就绪</n-tag>
              <n-tag v-else-if="activeLora.status === 'TRAINING' || activeLora.status === 'PENDING' || activeLora.status === 'GENERATING_DATASET' || activeLora.status === 'UPLOADING'" type="warning" size="small">
                {{ getLoraStatusText(activeLora.status) }}
              </n-tag>
              <n-tag v-else-if="activeLora.status === 'FAILED'" type="error" size="small">失败</n-tag>
              <n-tag v-else type="info" size="small">{{ activeLora.status }}</n-tag>
            </div>
            <div class="flex gap-2">
              <!-- 刷新状态按钮 - 用于恢复断开的连接 -->
              <n-button
                v-if="activeLora && (activeLora.status === 'TRAINING' || activeLora.status === 'FAILED')"
                size="small"
                :loading="refreshingLoraStatus"
                @click="handleRefreshLoraStatus"
                title="从云端刷新训练状态"
              >
                刷新状态
              </n-button>
              <!-- 开始/重新训练按钮 -->
              <n-button
                v-if="!activeLora || activeLora.status === 'FAILED' || activeLora.status === 'READY'"
                size="small"
                type="primary"
                :disabled="trainingImageCount < 10"
                @click="showLoraConfig = true"
              >
                {{ activeLora?.status === 'FAILED' ? '重新训练' : (activeLora?.status === 'READY' ? '重新训练' : '开始训练') }}
              </n-button>
              <!-- 取消训练按钮 -->
              <n-button
                v-if="activeLora && (activeLora.status === 'TRAINING' || activeLora.status === 'PENDING' || activeLora.status === 'GENERATING_DATASET' || activeLora.status === 'UPLOADING')"
                size="small"
                type="error"
                :loading="cancellingLora"
                @click="handleCancelLora"
              >
                取消训练
              </n-button>
            </div>
          </div>

          <!-- 训练进度 -->
          <div v-if="activeLora && (activeLora.status === 'TRAINING' || activeLora.status === 'GENERATING_DATASET' || activeLora.status === 'UPLOADING' || activeLora.status === 'PENDING')" class="space-y-2">
            <n-progress
              type="line"
              :percentage="activeLora.progress * 100"
              :show-indicator="true"
              status="info"
            />
            <p class="text-gray-400 text-sm">{{ loraProgressMessage || '准备中...' }}</p>
            <p class="text-gray-500 text-xs">
              触发词: {{ activeLora.trigger_word }} | 提供商: {{ activeLora.training_provider }}
            </p>
          </div>

          <!-- 已就绪的 LoRA 信息 -->
          <div v-if="activeLora && activeLora.status === 'READY'" class="bg-gray-800 rounded-lg p-3 space-y-1">
            <p class="text-sm"><span class="text-gray-400">触发词:</span> <code class="text-green-400">{{ activeLora.trigger_word }}</code></p>
            <p class="text-sm"><span class="text-gray-400">数据集大小:</span> {{ activeLora.dataset_size }} 张图片</p>
            <p class="text-sm"><span class="text-gray-400">提供商:</span> {{ activeLora.training_provider }}</p>
          </div>

          <!-- 错误信息 -->
          <div v-if="activeLora && activeLora.status === 'FAILED' && activeLora.error_message" class="bg-red-900/30 rounded-lg p-3">
            <p class="text-red-400 text-sm">{{ activeLora.error_message }}</p>
          </div>
        </div>

        <!-- LoRA 训练配置弹窗 -->
        <n-modal v-model:show="showLoraConfig" preset="card" title="LoRA 训练配置" class="max-w-md">
          <div class="space-y-4">
            <n-alert type="info" class="mb-4">
              将使用图片库中标记为训练的 {{ trainingImageCount }} 张图片进行训练。
              如果图片不足，系统会基于锚定图自动生成补充图片。
            </n-alert>

            <n-form-item label="补充图片数量（如果需要）">
              <n-input-number
                v-model:value="loraConfig.num_dataset_images"
                :min="10"
                :max="50"
                :step="5"
              />
              <template #feedback>
                <span class="text-gray-500 text-xs">当训练图不足时，会自动生成补充图片</span>
              </template>
            </n-form-item>

            <n-form-item label="训练步数">
              <n-input-number
                v-model:value="loraConfig.training_steps"
                :min="500"
                :max="3000"
                :step="100"
              />
              <template #feedback>
                <span class="text-gray-500 text-xs">建议 1000 步，过多可能过拟合</span>
              </template>
            </n-form-item>

            <n-form-item label="训练提供商">
              <n-select
                v-model:value="loraConfig.provider"
                :options="[
                  { label: 'Fal.ai (推荐)', value: 'fal' },
                  { label: 'Replicate', value: 'replicate' }
                ]"
              />
            </n-form-item>
          </div>

          <template #footer>
            <div class="flex justify-end gap-3">
              <n-button @click="showLoraConfig = false">取消</n-button>
              <n-button type="primary" :loading="startingLora" @click="handleStartLora">
                开始训练
              </n-button>
            </div>
          </template>
        </n-modal>
      </n-tab-pane>

      <!-- 语音配置 -->
      <n-tab-pane name="voice" tab="语音配置">
        <n-form-item label="语音选择">
          <div class="w-full space-y-3">
            <div class="flex gap-2">
              <n-select
                v-model:value="formData.voice_id"
                :options="voiceOptions"
                placeholder="选择语音"
                clearable
                filterable
                class="flex-1"
                :loading="loadingVoices"
              />
              <n-button
                :disabled="!formData.voice_id"
                :loading="previewing"
                @click="handlePreviewVoice"
              >
                试听
              </n-button>
            </div>

            <!-- 语音预览播放器 -->
            <div v-if="previewAudioUrl" class="bg-gray-800 rounded-lg p-3">
              <div class="flex items-center gap-3">
                <audio
                  ref="audioRef"
                  :src="previewAudioUrl"
                  controls
                  class="flex-1 h-8"
                />
                <span class="text-gray-400 text-sm">{{ previewDuration.toFixed(1) }}s</span>
              </div>
            </div>

            <!-- 语音参数 -->
            <div class="grid grid-cols-2 gap-4">
              <n-form-item label="语速" :show-feedback="false">
                <n-slider
                  v-model:value="formData.voice_speed"
                  :min="0.5"
                  :max="2.0"
                  :step="0.1"
                  :format-tooltip="(v: number) => `${v}x`"
                />
              </n-form-item>
              <n-form-item label="音调" :show-feedback="false">
                <n-slider
                  v-model:value="formData.voice_pitch"
                  :min="-12"
                  :max="12"
                  :step="1"
                />
              </n-form-item>
            </div>

            <!-- 预览文本 -->
            <n-form-item label="预览文本" :show-feedback="false">
              <n-input
                v-model:value="previewText"
                type="textarea"
                placeholder="输入要预览的文本..."
                :rows="2"
              />
            </n-form-item>
          </div>
        </n-form-item>
      </n-tab-pane>
    </n-tabs>

    <template #footer>
      <div class="flex justify-end gap-3">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" @click="handleSubmit" :loading="loading">
          {{ isEditing ? '保存' : '创建' }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NTabs, NTabPane, NForm, NFormItem, NInput, NButton, NSelect, NSlider, NDivider, NTag, NProgress, NInputNumber, NAlert, useMessage } from 'naive-ui'
import type { FormInst, FormRules, SelectOption } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Character, VoiceInfo, CharacterLoRA } from '@/types/api'
import CharacterImageGallery from './CharacterImageGallery.vue'

const props = defineProps<{
  show: boolean
  projectId: string
  character?: Character | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'saved': []
}>()

const message = useMessage()
const loading = ref(false)
const loadingVoices = ref(false)
const previewing = ref(false)
const activeTab = ref('basic')

// LoRA 相关
const activeLora = ref<CharacterLoRA | null>(null)
const showLoraConfig = ref(false)
const startingLora = ref(false)
const cancellingLora = ref(false)
const refreshingLoraStatus = ref(false)
const trainingImageCount = ref(0)
const loraConfig = ref({
  num_dataset_images: 20,
  training_steps: 1000,
  provider: 'fal' as 'fal' | 'replicate'
})
const loraJobId = ref<string | null>(null)
const loraProgressMessage = ref('')
let loraPollingTimer: ReturnType<typeof setInterval> | null = null

const galleryRef = ref<InstanceType<typeof CharacterImageGallery> | null>(null)

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const isEditing = computed(() => !!props.character)

const formRef = ref<FormInst | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)

const formData = ref({
  character_id: '',
  name: '',
  appearance_prompt: '',
  bio: '',
  voice_id: '',
  voice_speed: 1.0,
  voice_pitch: 0
})

// 语音相关
const voices = ref<VoiceInfo[]>([])
const previewText = ref('你好，我是这个角色的声音。')
const previewAudioUrl = ref('')
const previewDuration = ref(0)

const voiceOptions = computed<SelectOption[]>(() => {
  return voices.value.map(v => ({
    label: `${v.name} (${v.gender}) - ${v.description}`,
    value: v.id
  }))
})

const rules: FormRules = {
  character_id: [
    { required: true, message: '角色ID是必需的', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '角色ID只能包含字母、数字、下划线和连字符', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '角色名称是必需的', trigger: 'blur' },
    { min: 1, max: 100, message: '名称必须在1到100个字符之间', trigger: 'blur' }
  ],
  appearance_prompt: [
    { required: true, message: '外貌描述是必需的', trigger: 'blur' }
  ]
}

// 加载可用语音列表
async function loadVoices() {
  loadingVoices.value = true
  try {
    const response = await apiClient.listAvailableVoices()
    voices.value = response.voices
  } catch (error) {
    console.error('Failed to load voices:', error)
  } finally {
    loadingVoices.value = false
  }
}

// 加载训练图片数量
async function loadTrainingImageCount() {
  if (!props.character) return
  try {
    const response = await apiClient.getTrainingImages(props.character.character_id)
    trainingImageCount.value = response.total
  } catch (error) {
    console.error('Failed to load training images:', error)
  }
}

// 预览语音
async function handlePreviewVoice() {
  if (!formData.value.voice_id) return

  previewing.value = true
  try {
    const response = await apiClient.previewVoice({
      text: previewText.value || '你好，我是这个角色的声音。',
      voice_id: formData.value.voice_id,
      speed: formData.value.voice_speed
    })
    previewAudioUrl.value = response.audio_url
    previewDuration.value = response.duration

    setTimeout(() => {
      audioRef.value?.play()
    }, 100)
  } catch (error) {
    console.error('Failed to preview voice:', error)
    message.error(`语音预览失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    previewing.value = false
  }
}

function handleAnchorChanged(character: Character) {
  // 更新本地角色数据
  if (props.character) {
    Object.assign(props.character, character)
  }
  emit('saved')
}

function handleTrainingCountChanged(count: number) {
  trainingImageCount.value = count
}

watch(() => [props.show, props.character], ([show, character]) => {
  if (show) {
    activeTab.value = 'basic'

    if (voices.value.length === 0) {
      loadVoices()
    }

    if (character) {
      const voiceConfig = character.character_metadata?.voice_config as any
      formData.value = {
        character_id: character.character_id,
        name: character.name,
        appearance_prompt: character.appearance_prompt || character.prompt_base || '',
        bio: character.bio || '',
        voice_id: character.voice_id || '',
        voice_speed: voiceConfig?.speed || 1.0,
        voice_pitch: voiceConfig?.pitch || 0
      }
      loadActiveLora()
      loadTrainingImageCount()
    } else {
      formData.value = {
        character_id: '',
        name: '',
        appearance_prompt: '',
        bio: '',
        voice_id: '',
        voice_speed: 1.0,
        voice_pitch: 0
      }
      activeLora.value = null
      trainingImageCount.value = 0
    }

    previewAudioUrl.value = ''
    previewDuration.value = 0
  } else {
    stopLoraPolling()
  }
}, { immediate: true })

// LoRA 相关函数
async function loadActiveLora() {
  if (!props.character) return
  try {
    // 先获取所有 LoRA，找到正在训练的
    const loras = await apiClient.listCharacterLoRAs(props.character.character_id)
    const trainingLora = loras.find(l =>
      l.status === 'TRAINING' ||
      l.status === 'GENERATING_DATASET' ||
      l.status === 'UPLOADING' ||
      l.status === 'PENDING'
    )

    if (trainingLora) {
      activeLora.value = trainingLora
      startLoraPolling()
    } else {
      // 获取已就绪的 LoRA
      const lora = await apiClient.getActiveLoRA(props.character.character_id)
      activeLora.value = lora
    }
  } catch (error) {
    console.error('Failed to load LoRA:', error)
  }
}

function startLoraPolling() {
  if (loraPollingTimer) return

  // 立即查询一次
  pollLoraStatus()

  loraPollingTimer = setInterval(pollLoraStatus, 3000)
}

async function pollLoraStatus() {
  if (!activeLora.value) {
    stopLoraPolling()
    return
  }

  try {
    // 如果有 job_id，通过 Job API 获取进度
    if (loraJobId.value) {
      const job = await apiClient.getJob(loraJobId.value)
      activeLora.value = {
        ...activeLora.value,
        progress: job.progress,
        status: mapJobStatusToLoraStatus(job.status) as any,
        error_message: job.error_message || undefined,
        lora_url: (job.result as any)?.lora_url || activeLora.value.lora_url,
      }

      // 从 job result 获取消息
      const result = job.result as any
      if (result?.message) {
        loraProgressMessage.value = result.message
      } else if (job.status === 'STARTED') {
        const pct = Math.round(job.progress * 100)
        loraProgressMessage.value = `训练中... ${pct}%`
      }

      if (job.status === 'SUCCESS') {
        stopLoraPolling()
        loraProgressMessage.value = 'LoRA 训练完成！'
        message.success('LoRA 训练完成！')
        // 重新加载 LoRA 信息
        await loadActiveLora()
      } else if (job.status === 'FAILURE') {
        stopLoraPolling()
        loraProgressMessage.value = job.error_message || '训练失败'
        message.error(`LoRA 训练失败: ${job.error_message || '未知错误'}`)
      } else if (job.status === 'REVOKED') {
        stopLoraPolling()
        loraProgressMessage.value = '训练已取消'
        message.info('训练已取消')
      }
    } else {
      // 没有 job_id，通过 LoRA status API 获取
      const status = await apiClient.getLoRAStatus(activeLora.value.id)
      activeLora.value = { ...activeLora.value, ...status }

      if (status.status === 'READY') {
        stopLoraPolling()
        loraProgressMessage.value = 'LoRA 训练完成！'
        message.success('LoRA 训练完成！')
      } else if (status.status === 'FAILED') {
        stopLoraPolling()
        loraProgressMessage.value = status.error_message || '训练失败'
        message.error(`LoRA 训练失败: ${status.error_message || '未知错误'}`)
      }
    }
  } catch (error) {
    console.error('Failed to poll LoRA status:', error)
  }
}

function mapJobStatusToLoraStatus(jobStatus: string): string {
  switch (jobStatus) {
    case 'PENDING': return 'PENDING'
    case 'STARTED': return 'TRAINING'
    case 'SUCCESS': return 'READY'
    case 'FAILURE': return 'FAILED'
    case 'REVOKED': return 'FAILED'
    default: return 'PENDING'
  }
}

function stopLoraPolling() {
  if (loraPollingTimer) {
    clearInterval(loraPollingTimer)
    loraPollingTimer = null
  }
}

function getLoraStatusText(status: string): string {
  switch (status) {
    case 'PENDING': return '等待中'
    case 'GENERATING_DATASET': return '生成数据集'
    case 'DATASET_READY': return '数据集就绪'
    case 'UPLOADING': return '上传中'
    case 'TRAINING': return '训练中'
    case 'READY': return '已就绪'
    case 'FAILED': return '失败'
    default: return status
  }
}

async function handleRefreshLoraStatus() {
  if (!activeLora.value) return
  refreshingLoraStatus.value = true

  try {
    // 通过 LoRA status API 从云端刷新状态
    const status = await apiClient.getLoRAStatus(activeLora.value.id)
    activeLora.value = { ...activeLora.value, ...status }

    if (status.status === 'READY') {
      loraProgressMessage.value = 'LoRA 训练完成！'
      message.success('LoRA 训练已完成！')
      stopLoraPolling()
    } else if (status.status === 'FAILED') {
      loraProgressMessage.value = status.error_message || '训练失败'
      message.warning(`训练状态: 失败 - ${status.error_message || '未知错误'}`)
      stopLoraPolling()
    } else if (status.status === 'TRAINING') {
      const pct = Math.round(status.progress * 100)
      loraProgressMessage.value = `训练中... ${pct}%`
      message.info(`训练仍在进行中 (${pct}%)，已恢复状态轮询`)
      // 恢复轮询
      startLoraPolling()
    } else {
      message.info(`当前状态: ${getLoraStatusText(status.status)}`)
    }
  } catch (error) {
    console.error('Failed to refresh LoRA status:', error)
    message.error(`刷新状态失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    refreshingLoraStatus.value = false
  }
}

async function handleStartLora() {
  if (!props.character) return
  startingLora.value = true
  try {
    const response = await apiClient.startLoRATraining({
      character_id: props.character.character_id,
      use_selected_images: true,
      num_dataset_images: loraConfig.value.num_dataset_images,
      training_steps: loraConfig.value.training_steps,
      provider: loraConfig.value.provider
    })

    // 保存 job_id 用于轮询
    loraJobId.value = response.job_id
    loraProgressMessage.value = response.message

    // 创建临时的 activeLora 对象
    activeLora.value = {
      id: response.lora_id,
      character_id: response.character_id,
      trigger_word: '',
      status: 'PENDING' as any,
      progress: 0,
      lora_url: undefined,
      dataset_size: loraConfig.value.num_dataset_images,
      training_provider: loraConfig.value.provider,
      error_message: undefined,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    showLoraConfig.value = false
    message.success('LoRA 训练任务已创建')
    startLoraPolling()
  } catch (error) {
    console.error('Failed to start LoRA training:', error)
    message.error(`启动训练失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    startingLora.value = false
  }
}

async function handleCancelLora() {
  if (!activeLora.value) return
  cancellingLora.value = true
  try {
    // 如果有 job_id，取消 job
    if (loraJobId.value) {
      await apiClient.cancelJob(loraJobId.value)
    } else {
      await apiClient.cancelLoRATraining(activeLora.value.id)
    }
    stopLoraPolling()
    activeLora.value = { ...activeLora.value, status: 'FAILED' as any, error_message: '用户取消' }
    loraProgressMessage.value = '训练已取消'
    message.success('训练已取消')
  } catch (error) {
    console.error('Failed to cancel LoRA training:', error)
    message.error(`取消失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    cancellingLora.value = false
  }
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
    loading.value = true

    if (isEditing.value && props.character) {
      await apiClient.updateCharacter(props.character.character_id, {
        name: formData.value.name,
        appearance_prompt: formData.value.appearance_prompt || undefined,
        bio: formData.value.bio || undefined,
        voice_id: formData.value.voice_id || undefined
      })

      if (formData.value.voice_id) {
        await apiClient.setCharacterVoice(props.character.character_id, {
          voice_id: formData.value.voice_id,
          speed: formData.value.voice_speed,
          pitch: formData.value.voice_pitch
        })
      }

      message.success('角色更新成功')
    } else {
      await apiClient.createCharacter({
        character_id: formData.value.character_id,
        name: formData.value.name,
        appearance_prompt: formData.value.appearance_prompt,
        bio: formData.value.bio,
        voice_id: formData.value.voice_id || undefined
      }, props.projectId)
      message.success('角色创建成功')
    }

    emit('saved')
    visible.value = false
  } catch (error) {
    console.error('Failed to save character:', error)
    message.error(`保存角色失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    loading.value = false
  }
}
</script>
