<template>
  <details ref="menuRef" class="account-menu" :class="`tone-${tone}`">
    <summary class="account-trigger">
      <span class="account-avatar">{{ initials }}</span>
      <span class="account-copy">
        <span class="account-name">{{ username }}</span>
        <span class="account-subtitle">{{ subtitle }}</span>
      </span>
      <span class="account-caret">⌄</span>
    </summary>

    <div class="account-popover">
      <router-link
        v-if="showProjectLink"
        class="account-action"
        :to="{ name: 'project-list' }"
        @click="closeMenu"
      >
        回到项目总览
      </router-link>
      <button type="button" class="account-action account-action-danger" @click="handleLogoutClick">
        退出登录
      </button>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

const props = withDefaults(defineProps<{
  username: string
  subtitle?: string
  showProjectLink?: boolean
  tone?: 'light' | 'dark'
}>(), {
  subtitle: '本地工作台账号',
  showProjectLink: true,
  tone: 'light'
})

const emit = defineEmits<{
  logout: []
}>()

const menuRef = ref<HTMLDetailsElement | null>(null)

const initials = computed(() => {
  const cleaned = props.username.trim()
  if (!cleaned) return 'ST'
  return cleaned.slice(0, 2).toUpperCase()
})

function closeMenu() {
  menuRef.value?.removeAttribute('open')
}

function handleLogoutClick() {
  closeMenu()
  emit('logout')
}
</script>
