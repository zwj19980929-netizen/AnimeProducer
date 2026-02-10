<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="isEditing ? '编辑角色' : '创建角色'"
    class="max-w-2xl"
    :mask-closable="false"
  >
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

      <n-form-item label="角色描述" path="prompt_base">
        <n-input
          v-model:value="formData.prompt_base"
          type="textarea"
          placeholder="描述角色的外观、性格等特征..."
          :rows="4"
          :maxlength="2000"
          show-count
        />
      </n-form-item>

      <n-form-item label="参考图片路径" path="reference_image_path">
        <n-input
          v-model:value="formData.reference_image_path"
          placeholder="输入参考图片的路径"
        />
      </n-form-item>

      <!-- 语音配置 -->
      <n-divider>语音配置</n-divider>

      <n-form-item label="语音选择" path="voice_id">
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
    </n-form>

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
import { ref, computed, watch, onMounted } from 'vue'
import { NModal, NForm, NFormItem, NInput, NButton, NSelect, NSlider, NDivider, useMessage } from 'naive-ui'
import type { FormInst, FormRules, SelectOption } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Character, VoiceInfo } from '@/types/api'

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
  prompt_base: '',
  reference_image_path: '',
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
  prompt_base: [
    { required: true, message: '角色描述是必需的', trigger: 'blur' }
  ],
  reference_image_path: [
    { required: true, message: '参考图片路径是必需的', trigger: 'blur' }
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

    // 自动播放
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

watch(() => [props.show, props.character], ([show, character]) => {
  if (show) {
    // 加载语音列表
    if (voices.value.length === 0) {
      loadVoices()
    }

    if (character) {
      const voiceConfig = character.character_metadata?.voice_config as any
      formData.value = {
        character_id: character.character_id,
        name: character.name,
        prompt_base: character.prompt_base || '',
        reference_image_path: character.reference_image_path || '',
        voice_id: character.voice_id || '',
        voice_speed: voiceConfig?.speed || 1.0,
        voice_pitch: voiceConfig?.pitch || 0
      }
    } else {
      formData.value = {
        character_id: '',
        name: '',
        prompt_base: '',
        reference_image_path: '',
        voice_id: '',
        voice_speed: 1.0,
        voice_pitch: 0
      }
    }
    // 清除预览
    previewAudioUrl.value = ''
    previewDuration.value = 0
  }
}, { immediate: true })

async function handleSubmit() {
  try {
    await formRef.value?.validate()
    loading.value = true

    if (isEditing.value && props.character) {
      // 更新角色基本信息
      await apiClient.updateCharacter(props.character.character_id, {
        name: formData.value.name,
        prompt_base: formData.value.prompt_base || undefined,
        reference_image_path: formData.value.reference_image_path || undefined,
        voice_id: formData.value.voice_id || undefined
      })

      // 如果设置了语音，更新语音配置
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
        prompt_base: formData.value.prompt_base,
        reference_image_path: formData.value.reference_image_path,
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
