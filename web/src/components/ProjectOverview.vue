<template>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <!-- Script Content -->
    <div class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30">
      <h3 class="text-lg font-semibold text-white mb-4">脚本内容</h3>
      <div class="bg-gray-900/50 rounded-lg p-4 max-h-96 overflow-y-auto">
        <pre class="text-gray-300 text-sm whitespace-pre-wrap font-mono">{{ project.script_content || '没有脚本内容' }}</pre>
      </div>
    </div>

    <!-- Project Metadata -->
    <div class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30">
      <h3 class="text-lg font-semibold text-white mb-4">项目详情</h3>
      <div class="space-y-4">
        <div>
          <span class="text-gray-400 text-sm">风格预设</span>
          <p class="text-white font-medium">{{ project.style_preset || '未设置' }}</p>
        </div>
        <div>
          <span class="text-gray-400 text-sm">创建时间</span>
          <p class="text-white font-medium">{{ formatDate(project.created_at) }}</p>
        </div>
        <div>
          <span class="text-gray-400 text-sm">最后更新</span>
          <p class="text-white font-medium">{{ formatDate(project.updated_at) }}</p>
        </div>
        <div v-if="project.error_message">
          <span class="text-red-400 text-sm">错误</span>
          <p class="text-red-300 text-sm">{{ project.error_message }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Project } from '@/types/api'
import dayjs from 'dayjs'

defineProps<{
  project: Project
}>()

function formatDate(date: string) {
  return dayjs(date).format('YYYY年M月D日 HH:mm')
}
</script>
