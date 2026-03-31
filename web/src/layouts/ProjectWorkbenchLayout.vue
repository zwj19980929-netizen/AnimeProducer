<template>
  <div class="app-shell page-shell">
    <aside class="app-sidebar">
      <div class="brand">
        <div class="brand-kicker">Warm Studio Console</div>
        <div class="headline-md" style="color: #fff8f0; margin-top: 8px;">AnimeProducer</div>
        <div class="body-sm" style="color: rgba(255, 248, 240, 0.62); margin-top: 10px;">
          从原著到分集动画的阶段式生产工作台
        </div>
      </div>

      <nav class="nav-group">
        <router-link class="nav-link" :to="{ name: 'project-list' }">
          <span class="headline-sm">项目总览</span>
          <small>回到工作台首页</small>
        </router-link>

        <router-link
          v-for="item in navItems"
          :key="item.label"
          class="nav-link"
          :to="item.to"
        >
          <span class="headline-sm">{{ item.label }}</span>
          <small>{{ item.hint }}</small>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.5);">Account</div>
        <AccountMenu
          :username="authState.user?.username || 'Studio Producer'"
          :subtitle="workspace?.project.current_stage_label || '当前工作台账号'"
          tone="dark"
          @logout="handleLogout"
        />
      </div>
    </aside>

    <div class="app-content">
      <header class="topbar">
        <div class="topbar-title">
          <div class="topbar-meta">
            <div class="micro-label muted" style="font-size: 10px;">{{ workspace?.project.current_stage_label || '加载中' }}</div>
            <div v-if="isRefreshing" class="sync-pill">后台同步中</div>
          </div>
          <div class="headline-lg">{{ workspace?.project.name || '加载项目中…' }}</div>
          <div class="body-sm muted">{{ workspace?.project.description || '围绕当前阶段组织信息，不让关键动作淹没在页面里。' }}</div>
        </div>

        <div class="topbar-actions">
          <router-link class="btn btn-ghost" :to="{ name: 'project-list' }">回到项目总览</router-link>
          <StatusPill v-if="workspace" :value="workspace.project.status" :label="workspace.project.current_stage_label" />
          <button class="btn btn-ghost" @click="() => refreshWorkspace()">刷新数据</button>
          <button class="btn btn-primary" @click="operationsOpen = true">最近操作</button>
        </div>
      </header>

      <main class="workspace-page">
        <div v-if="loading" class="surface-card section-card body-lg">正在整理项目工作台…</div>
        <div v-else-if="error" class="danger-box">{{ error }}</div>
        <router-view v-else />
      </main>
    </div>

    <OperationsDrawer
      :open="operationsOpen"
      :active="workspace?.active_operations || []"
      :recent="workspace?.recent_operations || []"
      @close="operationsOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import AccountMenu from '@/components/AccountMenu.vue'
import OperationsDrawer from '@/components/OperationsDrawer.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { clearAuthState, authState } from '@/state/auth'
import { workbenchKey } from '@/state/workbench'
import type { WorkspaceResponse } from '@/types/workbench'

const route = useRoute()
const router = useRouter()

const workspace = ref<WorkspaceResponse | null>(null)
const loading = ref(true)
const error = ref('')
const operationsOpen = ref(false)
const isRefreshing = ref(false)

let pollTimer: number | undefined

const projectId = computed(() => route.params.id as string)

const navItems = computed(() => [
  { to: { name: 'project-dashboard', params: { id: projectId.value } }, label: '仪表盘', hint: '看见进度、阻塞与下一步' },
  { to: { name: 'source-chapters', params: { id: projectId.value } }, label: '书源与章节', hint: '导入原著并完成章节分析' },
  { to: { name: 'character-bible', params: { id: projectId.value } }, label: '角色圣经', hint: '确认锚点图、语音与变体' },
  { to: { name: 'episode-planning', params: { id: projectId.value } }, label: '分集规划', hint: '生成草案并确认正式集数' },
  { to: { name: 'storyboard-workbench', params: { id: projectId.value } }, label: '分镜工作台', hint: '围绕单集整理镜头与提示词' },
  { to: { name: 'render-center', params: { id: projectId.value } }, label: '渲染中心', hint: '批次、队列、失败恢复' },
  { to: { name: 'delivery-output', params: { id: projectId.value } }, label: '交付输出', hint: '预览成片与历史版本' }
])

async function refreshWorkspace(options: { silent?: boolean } = {}) {
  const hadWorkspace = workspace.value !== null
  const backgroundSync = options.silent || hadWorkspace

  if (backgroundSync) {
    isRefreshing.value = true
  } else {
    loading.value = true
    error.value = ''
  }

  try {
    workspace.value = await api.getWorkspace(projectId.value)
    error.value = ''
  } catch (err) {
    if (!backgroundSync || workspace.value === null) {
      error.value = err instanceof Error ? err.message : '加载项目失败'
    }
  } finally {
    if (!hadWorkspace) {
      loading.value = false
    }
    isRefreshing.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(() => {
    refreshWorkspace({ silent: true }).catch(() => undefined)
  }, 8000)
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

function handleLogout() {
  clearAuthState()
  router.push({ name: 'login' })
}

provide(workbenchKey, {
  workspace,
  loading,
  error,
  operationsOpen,
  refreshWorkspace
})

watch(projectId, async () => {
  await refreshWorkspace()
  startPolling()
}, { immediate: true })

onUnmounted(stopPolling)
</script>
