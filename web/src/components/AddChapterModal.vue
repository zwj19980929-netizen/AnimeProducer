<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="添加章节"
    class="max-w-2xl"
    :mask-closable="false"
  >
    <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
      <n-form-item label="章节编号" path="chapter_number">
        <n-input-number
          v-model:value="formData.chapter_number"
          placeholder="输入章节编号"
          :min="1"
          :max="999"
          class="w-full"
        />
      </n-form-item>

      <n-form-item label="章节标题" path="title">
        <n-input
          v-model:value="formData.title"
          placeholder="输入章节标题"
          :maxlength="200"
          show-count
        />
      </n-form-item>

      <n-form-item label="章节内容" path="content">
        <n-input
          v-model:value="formData.content"
          type="textarea"
          placeholder="输入章节内容..."
          :rows="10"
          :maxlength="50000"
          show-count
        />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="flex justify-end gap-3">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" @click="handleSubmit" :loading="loading">
          添加章节
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NInputNumber, NButton, useMessage } from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { apiClient } from '@/api/client'

const props = defineProps<{
  show: boolean
  projectId: string
  nextChapterNumber: number
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'created': []
}>()

const message = useMessage()
const loading = ref(false)

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const formRef = ref<FormInst | null>(null)
const formData = ref({
  chapter_number: 1,
  title: '',
  content: ''
})

const rules: FormRules = {
  chapter_number: [
    { required: true, type: 'number', message: '章节编号是必需的', trigger: 'blur' }
  ],
  title: [
    { required: true, message: '章节标题是必需的', trigger: 'blur' },
    { min: 1, max: 200, message: '标题必须在1到200个字符之间', trigger: 'blur' }
  ],
  content: [
    { required: true, message: '章节内容是必需的', trigger: 'blur' },
    { min: 10, message: '内容必须至少10个字符', trigger: 'blur' }
  ]
}

watch(visible, (newVal) => {
  if (newVal) {
    formData.value = {
      chapter_number: props.nextChapterNumber,
      title: '',
      content: ''
    }
  }
})

async function handleSubmit() {
  try {
    await formRef.value?.validate()
    loading.value = true
    await apiClient.addChapter(props.projectId, formData.value)
    message.success('章节添加成功')
    emit('created')
    visible.value = false
  } catch (error) {
    console.error('Failed to add chapter:', error)
    message.error(`添加章节失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    loading.value = false
  }
}
</script>
