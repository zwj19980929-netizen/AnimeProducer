<template>
  <div class="space-y-4">
    <!-- Header with Add Button -->
    <div class="flex justify-between items-center">
      <h3 class="text-lg font-semibold text-white">角色列表</h3>
      <n-button type="primary" @click="handleCreateCharacter">
        创建角色
      </n-button>
    </div>

    <n-spin :show="loading">
      <div v-if="characters.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="character in characters"
          :key="character.character_id"
          class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30"
        >
          <!-- Character Image (优先显示锚定图) -->
          <div class="mb-4 rounded-lg overflow-hidden bg-gray-900 aspect-square flex items-center justify-center relative group">
            <img
              v-if="getCharacterImage(character)"
              :src="getCharacterImage(character)"
              :alt="character.name"
              class="w-full h-full object-cover"
            />
            <n-icon v-else size="64" class="text-gray-600">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
              </svg>
            </n-icon>
            <!-- Overlay with Edit Button -->
            <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <n-button
                type="primary"
                size="small"
                @click="handleEditCharacter(character)"
              >
                管理图片库
              </n-button>
            </div>
            <!-- 锚定图标记 -->
            <div v-if="character.anchor_image_id" class="absolute top-2 left-2">
              <n-tag type="warning" size="small">已锚定</n-tag>
            </div>
          </div>

          <!-- Character Info -->
          <h4 class="text-lg font-semibold text-white mb-2">{{ character.name }}</h4>
          <div v-if="character.aliases?.length" class="flex flex-wrap gap-1 mb-2">
            <n-tag v-for="alias in character.aliases" :key="alias" size="tiny" type="info">
              {{ alias }}
            </n-tag>
          </div>
          <p v-if="character.appearance_prompt || character.prompt_base" class="text-gray-400 text-sm mb-2 line-clamp-2">
            {{ character.appearance_prompt || character.prompt_base }}
          </p>
          <p v-if="character.bio" class="text-gray-500 text-xs mb-3 line-clamp-2">
            {{ character.bio }}
          </p>
          <div v-if="character.voice_id" class="text-xs text-gray-500 mb-3">
            语音: {{ character.voice_id }}
          </div>

          <!-- Action Buttons -->
          <div class="flex gap-2">
            <n-button size="small" @click="handleEditCharacter(character)">
              编辑
            </n-button>
            <n-button size="small" type="error" @click="handleDeleteCharacter(character)">
              删除
            </n-button>
          </div>
        </div>
      </div>
      <n-empty v-else description="还没有角色。点击上方按钮创建角色，或构建资源以从脚本中提取角色。" class="py-20" />
    </n-spin>

    <!-- Character Edit Modal -->
    <CharacterEditModal
      v-model:show="showEditModal"
      :project-id="projectId"
      :character="selectedCharacter"
      @saved="loadCharacters"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NSpin, NEmpty, NIcon, NButton, NTag, useDialog, useMessage } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Character } from '@/types/api'
import CharacterEditModal from './CharacterEditModal.vue'

const props = defineProps<{
  projectId: string
}>()

const dialog = useDialog()
const message = useMessage()

const characters = ref<Character[]>([])
const loading = ref(false)
const showEditModal = ref(false)
const selectedCharacter = ref<Character | null>(null)

onMounted(() => {
  loadCharacters()
})

// 获取角色显示图片（优先锚定图，其次参考图）
function getCharacterImage(character: Character): string | null {
  return character.anchor_image_url
    || character.anchor_image_path
    || character.reference_image_url
    || character.reference_image_path
    || null
}

async function loadCharacters() {
  loading.value = true
  try {
    const response = await apiClient.listCharacters(props.projectId)
    characters.value = response.items
  } catch (error) {
    console.error('Failed to load characters:', error)
  } finally {
    loading.value = false
  }
}

function handleCreateCharacter() {
  selectedCharacter.value = null
  showEditModal.value = true
}

function handleEditCharacter(character: Character) {
  selectedCharacter.value = character
  showEditModal.value = true
}

function handleDeleteCharacter(character: Character) {
  dialog.warning({
    title: '删除角色',
    content: `确定要删除角色「${character.name}」吗？此操作无法撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiClient.deleteCharacter(character.character_id)
        message.success('角色删除成功')
        await loadCharacters()
      } catch (error) {
        console.error('Failed to delete character:', error)
        message.error(`删除角色失败: ${error instanceof Error ? error.message : '未知错误'}`)
      }
    }
  })
}

// 暴露方法供父组件调用
defineExpose({
  loadCharacters
})
</script>
