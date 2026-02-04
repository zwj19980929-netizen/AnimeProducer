<template>
  <div class="bg-gray-800/30 rounded-xl p-6 border border-gray-700/30">
    <video
      ref="videoRef"
      :src="src"
      controls
      class="w-full rounded-lg"
    >
      您的浏览器不支持视频标签。
    </video>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  src: string
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
</script>
