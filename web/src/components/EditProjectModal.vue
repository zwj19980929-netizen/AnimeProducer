<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="编辑项目"
    class="max-w-2xl"
    :mask-closable="false"
  >
    <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
      <n-form-item label="项目名称" path="name">
        <n-input
          v-model:value="formData.name"
          placeholder="输入项目名称"
          :maxlength="100"
          show-count
        />
      </n-form-item>

      <n-form-item label="描述" path="description">
        <n-input
          v-model:value="formData.description"
          type="textarea"
          placeholder="您的动画项目的简要描述"
          :rows="3"
          :maxlength="500"
          show-count
        />
      </n-form-item>

      <n-form-item label="脚本内容" path="script_content">
        <n-input
          v-model:value="formData.script_content"
          type="textarea"
          placeholder="在此粘贴您的脚本或小说内容..."
          :rows="10"
          :maxlength="50000"
          show-count
        />
      </n-form-item>

      <n-form-item label="风格预设" path="style_preset">
        <n-select
          v-model:value="formData.style_preset"
          :options="styleOptions"
          placeholder="选择动画风格"
        />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="flex justify-end gap-3">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" @click="handleSubmit" :loading="loading">
          保存
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NSelect, NButton, useMessage } from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Project } from '@/types/api'

const props = defineProps<{
  show: boolean
  project: Project | null
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

const formRef = ref<FormInst | null>(null)
const formData = ref({
  name: '',
  description: '',
  script_content: '',
  style_preset: 'anime'
})

const styleOptions = [
  { label: '动画', value: 'anime' },
  { label: '漫画', value: 'manga' },
  { label: '写实', value: 'realistic' },
  { label: 'Q版', value: 'chibi' },
  { label: '水彩', value: 'watercolor' }
]

const rules: FormRules = {
  name: [
    { required: true, message: '项目名称是必需的', trigger: 'blur' },
    { min: 3, max: 100, message: '名称必须在3到100个字符之间', trigger: 'blur' }
  ],
  script_content: [
    { required: true, message: '脚本内容是必需的', trigger: 'blur' },
    { min: 50, message: '脚本必须至少50个字符', trigger: 'blur' }
  ]
}

watch(() => [props.show, props.project], ([show, project]) => {
  if (show && project) {
    formData.value = {
      name: project.name,
      description: project.description || '',
      script_content: project.script_content || '',
      style_preset: project.style_preset || 'anime'
    }
  }
}, { immediate: true })

async function handleSubmit() {
  if (!props.project) return

  try {
    await formRef.value?.validate()
    loading.value = true

    await apiClient.updateProject(props.project.id, {
      name: formData.value.name,
      description: formData.value.description || undefined,
      script_content: formData.value.script_content || undefined,
      style_preset: formData.value.style_preset || undefined
    })

    message.success('项目更新成功')
    emit('saved')
    visible.value = false
  } catch (error) {
    console.error('Failed to update project:', error)
    message.error(`更新项目失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    loading.value = false
  }
}
</script>
