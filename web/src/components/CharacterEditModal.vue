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
              <n-tag v-else-if="activeLora.status === 'TRAINING'" type="warning" size="small">训练中</n-tag>
              <n-tag v-else-if="activeLora.status === 'FAILED'" type="error" size="small">失败</n-tag>
              <n-tag v-else type="info" size="small">{{ activeLora.status }}</n-tag>
            </div>
            <n-button
              v-if="!activeLora || activeLora.status === 'FAILED'"
              size="small"
              type="primary"
              :disabled="trainingImageCount < 10"
              @click="showLoraConfig = true"
            >
              开始训练
            </n-button>
            <n-button
              v-else-if="activeLora.status === 'TRAINING'"
              size="small"
              type="error"
              :loading="cancellingLora"
              @click="handleCancelLora"
            >
              取消训练
            </n-button>
          </div>

          <!-- 训练进度 -->
          <div v-if="activeLora && activeLora.status === 'TRAINING'" class="space-y-2">
            <n-progress
              type="line"
              :percentage="activeLora.progress * 100"
              :show-indicator="true"
              status="info"
            />
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
const trainingImageCount = ref(0)
const loraConfig = ref({
  num_dataset_images: 20,
  training_steps: 1000,
  provider: 'fal' as 'fal' | 'replicate'
})
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
    const lora = await apiClient.getActiveLoRA(props.character.character_id)
    activeLora.value = lora
    if (lora && (lora.status === 'TRAINING' || lora.status === 'GENERATING_DATASET' || lora.status === 'UPLOADING')) {
      startLoraPolling()
    }
  } catch (error) {
    console.error('Failed to load LoRA:', error)
  }
}

function startLoraPolling() {
  if (loraPollingTimer) return
  loraPollingTimer = setInterval(async () => {
    if (!activeLora.value) {
      stopLoraPolling()
      return
    }
    try {
      const status = await apiClient.getLoRAStatus(activeLora.value.id)
      activeLora.value = { ...activeLora.value, ...status }
      if (status.status === 'READY' || status.status === 'FAILED') {
        stopLoraPolling()
        if (status.status === 'READY') {
          message.success('LoRA 训练完成！')
        } else if (status.status === 'FAILED') {
          message.error(`LoRA 训练失败: ${status.error_message || '未知错误'}`)
        }
      }
    } catch (error) {
      console.error('Failed to poll LoRA status:', error)
    }
  }, 5000)
}

function stopLoraPolling() {
  if (loraPollingTimer) {
    clearInterval(loraPollingTimer)
    loraPollingTimer = null
  }
}

async function handleStartLora() {
  if (!props.character) return
  startingLora.value = true
  try {
    const lora = await apiClient.startLoRATraining({
      character_id: props.character.character_id,
      use_selected_images: true,
      num_dataset_images: loraConfig.value.num_dataset_images,
      training_steps: loraConfig.value.training_steps,
      provider: loraConfig.value.provider
    })
    activeLora.value = lora
    showLoraConfig.value = false
    message.success('LoRA 训练已启动')
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
    await apiClient.cancelLoRATraining(activeLora.value.id)
    stopLoraPolling()
    activeLora.value = { ...activeLora.value, status: 'FAILED' as any, error_message: '用户取消' }
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
