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

      <n-form-item label="语音ID" path="voice_id">
        <n-input
          v-model:value="formData.voice_id"
          placeholder="输入语音合成的语音ID（可选）"
        />
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
import { ref, computed, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NButton, useMessage } from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Character } from '@/types/api'

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

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const isEditing = computed(() => !!props.character)

const formRef = ref<FormInst | null>(null)
const formData = ref({
  character_id: '',
  name: '',
  prompt_base: '',
  reference_image_path: '',
  voice_id: ''
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

watch(() => [props.show, props.character], ([show, character]) => {
  if (show) {
    if (character) {
      formData.value = {
        character_id: character.character_id,
        name: character.name,
        prompt_base: character.prompt_base || '',
        reference_image_path: character.reference_image_path || '',
        voice_id: character.voice_id || ''
      }
    } else {
      formData.value = {
        character_id: '',
        name: '',
        prompt_base: '',
        reference_image_path: '',
        voice_id: ''
      }
    }
  }
}, { immediate: true })

async function handleSubmit() {
  try {
    await formRef.value?.validate()
    loading.value = true

    if (isEditing.value && props.character) {
      await apiClient.updateCharacter(props.character.character_id, {
        name: formData.value.name,
        prompt_base: formData.value.prompt_base || undefined,
        reference_image_path: formData.value.reference_image_path || undefined,
        voice_id: formData.value.voice_id || undefined
      })
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
