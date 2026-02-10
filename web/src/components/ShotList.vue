<template>
  <div>
    <n-spin :show="loading">
      <div v-if="shots.length > 0" class="space-y-4">
        <div
          v-for="(shot, index) in shots"
          :key="shot.shot_id"
          class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30"
        >
          <div class="flex items-start gap-6">
            <!-- Shot Number -->
            <div class="flex-shrink-0 w-16 h-16 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <span class="text-2xl font-bold text-blue-400">{{ index + 1 }}</span>
            </div>

            <!-- Shot Details -->
            <div class="flex-1">
              <div class="flex items-start justify-between mb-3">
                <div>
                  <h4 class="text-lg font-semibold text-white mb-1">{{ shot.scene_description }}</h4>
                  <div class="flex gap-2 text-xs text-gray-500">
                    <span>时长: {{ shot.duration }}秒</span>
                    <span v-if="shot.camera_movement">• {{ shot.camera_movement }}</span>
                    <span v-if="shot.action_type">• {{ shot.action_type }}</span>
                  </div>
                </div>
              </div>

              <p v-if="shot.visual_prompt" class="text-gray-400 text-sm mb-3">
                {{ shot.visual_prompt }}
              </p>

              <div v-if="shot.dialogue" class="bg-gray-900/50 rounded-lg p-3 mb-3">
                <p class="text-gray-300 text-sm italic">"{{ shot.dialogue }}"</p>
              </div>

              <div v-if="shot.characters_in_shot && shot.characters_in_shot.length > 0" class="flex gap-2">
                <n-tag
                  v-for="char in shot.characters_in_shot"
                  :key="char"
                  size="small"
                  type="info"
                  :bordered="false"
                >
                  {{ char }}
                </n-tag>
              </div>
            </div>
          </div>
        </div>
      </div>
      <n-empty v-else :description="emptyDescription" class="py-20" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { NSpin, NEmpty, NTag } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Shot } from '@/types/api'

const props = defineProps<{
  projectId: string
  episodeNumber?: number
}>()

const shots = ref<Shot[]>([])
const loading = ref(false)

const emptyDescription = computed(() => {
  if (props.episodeNumber) {
    return `第 ${props.episodeNumber} 集还没有分镜，请先生成分镜。`
  }
  return '还没有故事板。从脚本生成故事板。'
})

async function loadShots() {
  loading.value = true
  try {
    let response
    if (props.episodeNumber) {
      response = await apiClient.listEpisodeShots(props.projectId, props.episodeNumber)
    } else {
      response = await apiClient.listShots(props.projectId)
    }
    shots.value = response.items.sort((a, b) => a.sequence_order - b.sequence_order)
  } catch (error) {
    console.error('Failed to load shots:', error)
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.episodeNumber], () => {
  loadShots()
})

onMounted(() => {
  loadShots()
})
</script>
