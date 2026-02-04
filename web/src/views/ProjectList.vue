<template>
  <div class="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
    <div class="container mx-auto px-6 py-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-4xl font-bold text-white mb-2">AnimeMatrix</h1>
        <p class="text-gray-400">AI 驱动的动画制作工作室</p>
      </div>

      <!-- Create Project Button -->
      <div class="mb-6">
        <n-button type="primary" size="large" @click="showCreateModal = true">
          <template #icon>
            <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2z"/></svg></n-icon>
          </template>
          创建新项目
        </n-button>
      </div>

      <!-- Error State -->
      <div v-if="store.error && !store.loading" class="py-20">
        <n-result
          status="error"
          title="连接失败"
          :description="store.error"
        >
          <template #footer>
            <n-button type="primary" @click="handleRetry">
              重试
            </n-button>
          </template>
        </n-result>
      </div>

      <!-- Loading State -->
      <div v-else-if="store.loading && !initialized" class="py-20">
        <div class="flex flex-col items-center justify-center">
          <n-spin size="large" />
          <p class="mt-4 text-gray-400">正在加载项目...</p>
        </div>
      </div>

      <!-- Content -->
      <template v-else>
        <!-- Projects Grid -->
        <n-spin :show="store.loading">
          <div v-if="store.hasProjects" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <ProjectCard
              v-for="project in store.projects"
              :key="project.id"
              :project="project"
              @click="navigateToProject(project.id)"
            />
          </div>
          <n-empty
            v-else
            description="还没有项目。创建您的第一个动画项目！"
            class="py-20"
          />
        </n-spin>

        <!-- Pagination -->
        <div v-if="store.total > store.pageSize" class="mt-8 flex justify-center">
          <n-pagination
            v-model:page="currentPage"
            :page-count="Math.ceil(store.total / store.pageSize)"
            @update:page="handlePageChange"
          />
        </div>
      </template>
    </div>

    <!-- Create Project Modal -->
    <CreateProjectModal v-model:show="showCreateModal" @created="handleProjectCreated" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NButton, NIcon, NResult } from 'naive-ui'
import { useProjectStore } from '@/stores/project'
import ProjectCard from '@/components/ProjectCard.vue'
import CreateProjectModal from '@/components/CreateProjectModal.vue'

const router = useRouter()
const store = useProjectStore()
const showCreateModal = ref(false)
const currentPage = ref(1)
const initialized = ref(false)

onMounted(async () => {
  await loadProjects()
  initialized.value = true
})

async function loadProjects(params?: { page?: number; page_size?: number }) {
  try {
    await store.fetchProjects(params)
  } catch {
    // Error is already stored in store.error
  }
}

async function handleRetry() {
  store.clearError()
  await loadProjects()
}

function navigateToProject(id: string) {
  router.push({ name: 'project-detail', params: { id } })
}

function handlePageChange(page: number) {
  loadProjects({ page, page_size: store.pageSize })
}

function handleProjectCreated(projectId: string) {
  showCreateModal.value = false
  loadProjects()
  navigateToProject(projectId)
}
</script>
