<template>
  <div class="character-image-gallery">
    <!-- 操作栏 -->
    <div class="flex justify-between items-center mb-4">
      <div class="flex gap-2">
        <n-button type="primary" @click="showGenerateModal = true" :disabled="!hasAnchor">
          生成变体图
        </n-button>
        <n-button @click="showReferenceModal = true" :loading="generating">
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
          <div class="absolute top-2 left-2 flex flex-wrap gap-1">
            <n-tag v-if="image.is_anchor" type="warning" size="tiny">锚定图</n-tag>
            <n-tag v-if="image.is_selected_for_training" type="success" size="tiny">训练</n-tag>
            <n-tag v-if="image.pose" type="info" size="tiny">{{ image.pose }}</n-tag>
            <n-tag v-if="image.expression" type="default" size="tiny">{{ image.expression }}</n-tag>
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
import { ref, computed, onMounted, watch } from 'vue'
import { NButton, NSelect, NTag, NSpin, NModal, NFormItem, NInput, NInputNumber, NAlert, useMessage, useDialog } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { CharacterImage, Character } from '@/types/api'
import { CharacterImageType } from '@/types/api'

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
const images = ref<CharacterImage[]>([])
const selectedImages = ref<string[]>([])
const filterType = ref<string | null>(null)
const showGenerateModal = ref(false)
const showReferenceModal = ref(false)

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
  num_candidates: 4
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
  { label: '全部', value: null },
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
]

const angleOptions = [
  { label: '正面', value: 'front view' },
  { label: '侧面', value: 'side view' },
  { label: '四分之三', value: 'three-quarter view' },
  { label: '仰视', value: 'low angle' },
  { label: '俯视', value: 'high angle' },
  { label: '背面', value: 'back view' },
]

onMounted(() => {
  loadImages()
})

watch(() => props.characterId, () => {
  loadImages()
})

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

async function handleGenerateReference() {
  generating.value = true
  try {
    const response = await apiClient.generateCharacterReference(props.characterId, {
      custom_prompt: referenceForm.value.custom_prompt || undefined,
      style_preset: referenceForm.value.style_preset || undefined,
      negative_prompt: referenceForm.value.negative_prompt || undefined,
      seed: referenceForm.value.seed || undefined,
      num_candidates: referenceForm.value.num_candidates
    })
    message.success(`生成了 ${response.total} 张候选图`)
    showReferenceModal.value = false
    await loadImages()
  } catch (error) {
    console.error('Failed to generate reference:', error)
    message.error(`生成失败: ${(error as Error).message}`)
  } finally {
    generating.value = false
  }
}

async function handleGenerateVariant() {
  if (!variantForm.value.pose && !variantForm.value.expression && !variantForm.value.angle && !variantForm.value.custom_prompt) {
    message.warning('请至少选择一个变体选项')
    return
  }

  generating.value = true
  try {
    const response = await apiClient.generateCharacterVariants(props.characterId, {
      pose: variantForm.value.pose || undefined,
      expression: variantForm.value.expression || undefined,
      angle: variantForm.value.angle || undefined,
      custom_prompt: variantForm.value.custom_prompt || undefined,
      negative_prompt: variantForm.value.negative_prompt || undefined,
      seed: variantForm.value.seed || undefined,
      num_images: variantForm.value.num_images
    })
    message.success(`生成了 ${response.total} 张变体图`)
    showGenerateModal.value = false
    await loadImages()
  } catch (error) {
    console.error('Failed to generate variant:', error)
    message.error(`生成失败: ${(error as Error).message}`)
  } finally {
    generating.value = false
  }
}

async function handleBatchGenerate() {
  generating.value = true
  try {
    const response = await apiClient.batchGenerateCharacterVariants(props.characterId, {
      style_preset: 'anime style',
      negative_prompt: variantForm.value.negative_prompt || undefined
    })
    message.success(`批量生成了 ${response.total} 张变体图`)
    showGenerateModal.value = false
    await loadImages()
  } catch (error) {
    console.error('Failed to batch generate:', error)
    message.error(`批量生成失败: ${(error as Error).message}`)
  } finally {
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
