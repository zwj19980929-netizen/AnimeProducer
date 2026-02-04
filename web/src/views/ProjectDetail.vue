<template>
  <div class="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
    <div class="container mx-auto px-6 py-8">
      <!-- Back Button -->
      <n-button text @click="router.push('/')" class="mb-6 text-gray-400 hover:text-white">
        <template #icon>
          <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg></n-icon>
        </template>
        返回项目列表
      </n-button>

      <!-- Error State -->
      <div v-if="error && !loading" class="py-20">
        <n-result
          status="error"
          title="加载项目失败"
          :description="error"
        >
          <template #footer>
            <n-space>
              <n-button @click="router.push('/')">
                返回项目列表
              </n-button>
              <n-button type="primary" @click="handleRetry">
                重试
              </n-button>
            </n-space>
          </template>
        </n-result>
      </div>

      <!-- Loading State (initial load) -->
      <div v-else-if="loading && !project" class="py-20">
        <div class="flex flex-col items-center justify-center">
          <n-spin size="large" />
          <p class="mt-4 text-gray-400">正在加载项目...</p>
        </div>
      </div>

      <!-- Project Content -->
      <template v-else-if="project">
        <n-spin :show="loading">
          <!-- Project Header -->
          <div class="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-8 mb-6 border border-gray-700/50">
            <div class="flex items-start justify-between mb-4">
              <div class="flex-1">
                <h1 class="text-3xl font-bold text-white mb-2">{{ project.name }}</h1>
                <p v-if="project.description" class="text-gray-400 mb-4">{{ project.description }}</p>
                <ProjectStatusBadge :status="project.status" />
              </div>
              <n-dropdown :options="actionOptions" @select="handleAction">
                <n-button circle quaternary>
                  <template #icon>
                    <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg></n-icon>
                  </template>
                </n-button>
              </n-dropdown>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-3 flex-wrap">
              <n-button
                v-if="canStartPipeline"
                type="primary"
                size="large"
                @click="handleStartPipeline"
                :loading="loading"
              >
                启动制作流程
              </n-button>
              <n-button
                v-if="canBuildAssets"
                type="info"
                @click="handleBuildAssets"
                :loading="loading"
              >
                构建资源
              </n-button>
              <n-button
                v-if="canGenerateStoryboard"
                type="info"
                @click="handleGenerateStoryboard"
                :loading="loading"
              >
                生成故事板
              </n-button>
            </div>
          </div>

          <!-- Tabs -->
          <n-tabs type="line" animated>
            <n-tab-pane name="overview" tab="概览">
              <ProjectOverview :project="project" />
            </n-tab-pane>
            <n-tab-pane name="chapters" tab="章节">
              <ChapterList :project-id="project.id" />
            </n-tab-pane>
            <n-tab-pane name="characters" tab="角色">
              <CharacterList :project-id="project.id" />
            </n-tab-pane>
            <n-tab-pane name="shots" tab="故事板">
              <ShotList :project-id="project.id" />
            </n-tab-pane>
            <n-tab-pane name="renders" tab="渲染">
              <RenderList :project-id="project.id" />
            </n-tab-pane>
            <n-tab-pane name="output" tab="输出" v-if="hasOutput">
              <VideoPlayer :src="project.output_video_path!" />
            </n-tab-pane>
          </n-tabs>
        </n-spin>
      </template>

      <!-- Not Found State -->
      <div v-else class="py-20">
        <n-result
          status="404"
          title="项目未找到"
          description="您查找的项目不存在或已被删除。"
        >
          <template #footer>
            <n-button type="primary" @click="router.push('/')">
              返回项目列表
            </n-button>
          </template>
        </n-result>
      </div>

      <!-- Edit Project Modal -->
      <EditProjectModal
        v-model:show="showEditModal"
        :project="project"
        @saved="handleProjectSaved"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NSpin, NButton, NIcon, NTabs, NTabPane, NDropdown, NResult, NSpace, useDialog } from 'naive-ui'
import { useProject } from '@/composables/useProject'
import ProjectStatusBadge from '@/components/ProjectStatusBadge.vue'
import ProjectOverview from '@/components/ProjectOverview.vue'
import CharacterList from '@/components/CharacterList.vue'
import ChapterList from '@/components/ChapterList.vue'
import ShotList from '@/components/ShotList.vue'
import RenderList from '@/components/RenderList.vue'
import VideoPlayer from '@/components/VideoPlayer.vue'
import EditProjectModal from '@/components/EditProjectModal.vue'

const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const projectId = route.params.id as string

const {
  project,
  loading,
  error,
  canStartPipeline,
  canBuildAssets,
  canGenerateStoryboard,
  hasOutput,
  fetchProject,
  deleteProject,
  buildAssets,
  generateStoryboard,
  startPipeline,
  startPolling,
  stopPolling
} = useProject(projectId)

const showEditModal = ref(false)

const actionOptions = computed(() => [
  {
    label: '编辑项目',
    key: 'edit'
  },
  {
    label: '删除项目',
    key: 'delete',
    props: {
      style: 'color: #d03050;'
    }
  }
])

onMounted(() => {
  startPolling(projectId)
})

onUnmounted(() => {
  stopPolling()
})

async function handleRetry() {
  await fetchProject(projectId)
}

async function handleBuildAssets() {
  await buildAssets(projectId)
}

async function handleGenerateStoryboard() {
  await generateStoryboard(projectId)
}

async function handleStartPipeline() {
  await startPipeline(projectId)
}

function handleAction(key: string) {
  if (key === 'edit') {
    showEditModal.value = true
  } else if (key === 'delete') {
    dialog.warning({
      title: '删除项目',
      content: '您确定要删除此项目吗？这将同时删除该项目的所有关联数据，包括：章节、角色、分镜、渲染任务等。此操作无法撤销。',
      positiveText: '删除',
      negativeText: '取消',
      onPositiveClick: async () => {
        await deleteProject(projectId)
        router.push('/')
      }
    })
  }
}

async function handleProjectSaved() {
  await fetchProject(projectId)
}
</script>
