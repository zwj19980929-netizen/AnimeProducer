<template>
  <div
    class="bg-gray-800/50 backdrop-blur-sm rounded-xl p-6 border border-gray-700/50 hover:border-gray-600/50 transition-all cursor-pointer group"
  >
    <div class="flex items-start justify-between mb-4">
      <div class="flex-1">
        <h3 class="text-xl font-semibold text-white mb-2 group-hover:text-blue-400 transition-colors">
          {{ project.name }}
        </h3>
        <p v-if="project.description" class="text-gray-400 text-sm line-clamp-2 mb-3">
          {{ project.description }}
        </p>
        <ProjectStatusBadge :status="project.status" />
      </div>
    </div>

    <!-- Preview Image -->
    <div v-if="project.output_video_path" class="mb-4 rounded-lg overflow-hidden bg-gray-900">
      <div class="aspect-video flex items-center justify-center">
        <n-icon size="48" class="text-gray-600">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
        </n-icon>
      </div>
    </div>

    <!-- Metadata -->
    <div class="flex items-center justify-between text-xs text-gray-500">
      <span>{{ formatDate(project.created_at) }}</span>
      <span v-if="project.style_preset" class="px-2 py-1 bg-gray-700/50 rounded">
        {{ project.style_preset }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NIcon } from 'naive-ui'
import type { Project } from '@/types/api'
import ProjectStatusBadge from './ProjectStatusBadge.vue'
import dayjs from 'dayjs'

defineProps<{
  project: Project
}>()

function formatDate(date: string) {
  return dayjs(date).format('YYYY年M月D日')
}
</script>
