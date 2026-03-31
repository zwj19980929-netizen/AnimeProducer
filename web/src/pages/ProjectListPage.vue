<template>
  <div class="workspace-page page-shell studio-shell">
    <section class="surface-card studio-command-bar">
      <div class="studio-command-copy">
        <div class="micro-label muted" style="font-size: 10px;">Studio Board</div>
        <div class="headline-md">项目编排台</div>
        <div class="body-sm muted">首页先看项目本身，再决定今天推进哪条制作线。</div>
      </div>

      <div class="studio-command-actions">
        <div class="studio-mini-stat">
          <span class="micro-label muted" style="font-size: 10px;">Projects</span>
          <span class="headline-sm">{{ projects.length }}</span>
        </div>
        <div class="studio-mini-stat">
          <span class="micro-label muted" style="font-size: 10px;">Blocked</span>
          <span class="headline-sm">{{ blockedProjects }}</span>
        </div>
        <AccountMenu
          :username="authState.user?.username || 'Studio Producer'"
          subtitle="本地工作台账号"
          :show-project-link="false"
          @logout="handleLogout"
        />
      </div>
    </section>

    <section class="studio-control-room">
      <article class="surface-card studio-dock-card">
        <div class="studio-section-heading">
          <div class="micro-label muted" style="font-size: 10px;">Project Dock</div>
          <div class="headline-sm">项目停机坪</div>
          <div class="body-sm muted">先从这里选项目，主视图会立刻切到它的当前阶段和下一步动作。</div>
        </div>

        <div v-if="loading" class="surface-panel section-card body-sm">正在加载项目…</div>

        <EmptyState
          v-else-if="projects.length === 0"
          title="还没有项目"
          description="先在右侧建立一个项目，工作台会自动围绕书源、角色、分集、分镜、渲染和交付组织流程。"
        />

        <div v-else class="studio-project-rail">
          <button
            v-for="project in projects"
            :key="project.id"
            type="button"
            class="studio-rail-item"
            :class="{ 'is-active': selectedProject?.id === project.id }"
            @click="selectedProjectId = project.id"
          >
            <div class="studio-rail-top">
              <div class="micro-label muted" style="font-size: 10px;">{{ project.current_stage_label }}</div>
              <StatusPill :value="project.status" />
            </div>

            <div class="headline-sm">{{ project.name }}</div>
            <div class="body-sm muted">{{ project.description || '继续从当前阶段往下推进制作。' }}</div>

            <div class="progress-track">
              <div class="progress-bar" :style="{ width: `${Math.round(project.completion_rate * 100)}%` }" />
            </div>

            <div class="studio-rail-footer">
              <span>{{ project.next_action?.label || '进入项目' }}</span>
              <span>{{ formatDate(project.updated_at) }}</span>
            </div>
          </button>
        </div>
      </article>

      <article class="studio-feature-card" :class="{ 'is-empty': !selectedProject }">
        <template v-if="selectedProject">
          <div class="studio-feature-top">
            <div class="studio-feature-kicker">
              <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.54);">Selected Project</div>
              <StatusPill :value="selectedProject.status" :label="selectedProject.current_stage_label" />
            </div>

            <div class="headline-lg studio-feature-title">{{ selectedProject.name }}</div>
            <div class="body-lg studio-feature-copy">
              {{ selectedProject.description || '这个项目已经建立，可以直接从当前阶段继续往下推进。' }}
            </div>
          </div>

          <div class="studio-feature-stage-rail">
            <article
              v-for="stage in stageRail"
              :key="stage.key"
              class="studio-feature-stage-item"
              :class="`is-${resolveStageState(stage.key)}`"
            >
              <div class="studio-feature-stage-head">
                <span class="studio-feature-stage-dot" />
                <span class="micro-label" style="font-size: 10px;">{{ stage.label }}</span>
              </div>
              <div class="body-sm studio-feature-stage-copy">{{ stage.copy }}</div>
            </article>
          </div>

          <div class="studio-feature-progress-card">
            <div class="studio-feature-progress-meta">
              <span class="body-sm">当前推进度</span>
              <span class="headline-sm">{{ Math.round(selectedProject.completion_rate * 100) }}%</span>
            </div>
            <div class="progress-track studio-feature-track">
              <div class="progress-bar" :style="{ width: `${Math.round(selectedProject.completion_rate * 100)}%` }" />
            </div>
          </div>

          <div class="studio-feature-stats">
            <article class="studio-feature-stat">
              <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.48);">Chapters</div>
              <div class="headline-sm" style="color: #fff8f0; margin-top: 8px;">{{ metricNumber(selectedProject.metrics, 'chapters_total') }}</div>
            </article>
            <article class="studio-feature-stat">
              <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.48);">Characters</div>
              <div class="headline-sm" style="color: #fff8f0; margin-top: 8px;">{{ metricNumber(selectedProject.metrics, 'characters_total') }}</div>
            </article>
            <article class="studio-feature-stat">
              <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.48);">Episodes</div>
              <div class="headline-sm" style="color: #fff8f0; margin-top: 8px;">{{ metricNumber(selectedProject.metrics, 'episodes_total') }}</div>
            </article>
          </div>

          <article class="studio-feature-blockers">
            <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.48);">Blockers & Next Step</div>

            <div v-if="selectedProject.blockers.length" class="studio-feature-blocker-list">
              <div
                v-for="blocker in selectedProject.blockers.slice(0, 2)"
                :key="blocker"
                class="studio-feature-blocker"
              >
                {{ blocker }}
              </div>
            </div>

            <div v-else class="studio-feature-note">当前没有明显阻塞，可以直接继续推进。</div>

            <div class="studio-feature-next">
              <span class="body-sm">建议动作</span>
              <strong>{{ selectedProject.next_action?.label || '进入项目工作台' }}</strong>
            </div>
          </article>

          <div class="studio-feature-footer">
            <div class="stack" style="gap: 6px;">
              <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.48);">Updated</div>
              <div class="body-sm studio-feature-copy">{{ formatDate(selectedProject.updated_at) }}</div>
            </div>

            <div class="button-row">
              <button type="button" class="btn btn-primary" @click="openProject(selectedProject.id)">
                {{ selectedProject.next_action?.label || '进入项目工作台' }}
              </button>
              <button type="button" class="btn btn-ghost studio-feature-ghost" @click="loadProjects">
                同步项目
              </button>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="studio-feature-empty">
            <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.54);">Ready To Start</div>
            <div class="headline-md" style="color: #fff8f0;">先建立第一个项目，主视图就会变成它的制作控制台。</div>
            <div class="body-sm studio-feature-copy">创建完成后会直接进入该项目的仪表盘，而不是停留在中间页。</div>
          </div>
        </template>
      </article>

      <div class="studio-side-stack">
        <article class="surface-card studio-create-card">
          <form class="stack" @submit.prevent="createProject">
            <div class="stack" style="gap: 10px;">
              <div class="micro-label muted" style="font-size: 10px;">Create Project</div>
              <div class="headline-md">新建项目</div>
              <div class="body-sm muted">先定义项目身份和制作方向，进入项目后再补章节、角色、分镜和交付内容。</div>
            </div>

            <div class="studio-create-note body-sm">
              创建完成后会直接进入该项目，不会把你丢在一个中间页里。
            </div>

            <div class="form-grid">
              <div class="field-group">
                <label class="field-label">项目名称</label>
                <input v-model.trim="form.name" class="text-input" placeholder="凡人修仙传 S1" />
              </div>

              <div class="field-group">
                <label class="field-label">一句话说明</label>
                <textarea v-model="form.description" class="textarea-input" placeholder="例如：第一季改编项目，强调国风热血与角色一致性。" />
              </div>

              <div class="field-group">
                <label class="field-label">风格预设</label>
                <input v-model.trim="form.style_preset" class="text-input" placeholder="Warm Studio Console / 国风热血动画" />
              </div>
            </div>

            <article class="studio-create-preview">
              <div class="micro-label muted" style="font-size: 10px;">Live Preview</div>
              <div class="headline-sm" style="margin-top: 8px;">{{ projectDraftPreview.name }}</div>
              <div class="body-sm muted" style="margin-top: 8px;">{{ projectDraftPreview.description }}</div>
              <div class="chip-row" style="margin-top: 12px;">
                <span class="chip">风格 {{ projectDraftPreview.style }}</span>
                <span class="chip">创建后直达仪表盘</span>
              </div>
            </article>

            <div v-if="error" class="danger-box body-sm">{{ error }}</div>

            <div class="studio-create-foot">
              <button type="submit" class="btn btn-primary" :disabled="submitting">
                {{ submitting ? '创建中…' : '创建并进入仪表盘' }}
              </button>
              <button type="button" class="btn btn-ghost" @click="loadProjects">重新同步</button>
            </div>
          </form>
        </article>

        <article class="surface-card studio-flow-card">
          <div class="studio-section-heading">
            <div class="micro-label muted" style="font-size: 10px;">Workflow</div>
            <div class="headline-sm">制作路线</div>
          </div>

          <div class="studio-flow-compact">
            <article v-for="step in flowSteps" :key="step.title" class="studio-flow-compact-item">
              <div class="studio-flow-index studio-flow-index-compact">{{ step.index }}</div>
              <div class="stack" style="gap: 4px;">
                <div class="headline-sm">{{ step.title }}</div>
                <div class="body-sm muted">{{ step.copy }}</div>
              </div>
            </article>
          </div>
        </article>
      </div>
    </section>

    <section v-if="projects.length > 1 && !loading" class="stack">
      <div class="studio-list-header">
        <div class="stack" style="gap: 8px;">
          <div class="micro-label muted" style="font-size: 10px;">Card View</div>
          <div class="headline-md">全部项目卡片</div>
        </div>

        <div class="chip-row">
          <span class="chip">共 {{ projects.length }} 个项目</span>
          <span class="chip">进行中 {{ activeProjects }}</span>
          <span class="chip">阻塞 {{ blockedProjects }}</span>
        </div>
      </div>

      <div class="project-grid">
        <ProjectCard
          v-for="project in projects"
          :key="project.id"
          :project="project"
          @open="openProject"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import AccountMenu from '@/components/AccountMenu.vue'
import EmptyState from '@/components/EmptyState.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { authState, clearAuthState } from '@/state/auth'
import type { ProjectCardSummary } from '@/types/workbench'

const router = useRouter()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const projects = ref<ProjectCardSummary[]>([])
const selectedProjectId = ref('')

const form = reactive({
  name: '',
  description: '',
  style_preset: 'Warm Studio Console'
})

const flowSteps = [
  { index: '01', title: '导入与拆解', copy: '先把原著和章节结构理顺，后面所有动作才有稳定基础。' },
  { index: '02', title: '角色与分集', copy: '角色圣经和分集规划决定后续镜头与语音的一致性。' },
  { index: '03', title: '分镜与交付', copy: '进入项目后，再围绕镜头、渲染和交付往下推进。' }
]

const stageRail = [
  { key: 'SOURCE_IMPORT', label: '书源导入', copy: '导入原著并建立素材入口' },
  { key: 'CHAPTER_ANALYSIS', label: '章节分析', copy: '把原著拆成可处理的章节结构' },
  { key: 'CHARACTER_BIBLE', label: '角色圣经', copy: '固定角色锚点、语音和一致性' },
  { key: 'EPISODE_PLANNING', label: '分集规划', copy: '把章节合并成正式分集' },
  { key: 'STORYBOARD_WORKBENCH', label: '分镜工作台', copy: '围绕单集整理镜头与提示词' },
  { key: 'RENDER_CENTER', label: '渲染中心', copy: '管理批次、失败恢复和队列' },
  { key: 'DELIVERY_OUTPUT', label: '交付输出', copy: '查看成片、版本和输出结果' }
]

const selectedProject = computed(() => {
  return projects.value.find((project) => project.id === selectedProjectId.value) ?? projects.value[0] ?? null
})

const blockedProjects = computed(() => projects.value.filter((project) => {
  const status = project.status.toLowerCase()
  return project.blockers.length > 0 || status.includes('blocked') || status.includes('failed')
}).length)

const completedProjects = computed(() => projects.value.filter((project) => {
  const status = project.status.toLowerCase()
  return status.includes('completed') || status.includes('done')
}).length)

const activeProjects = computed(() => Math.max(projects.value.length - completedProjects.value, 0))

const projectDraftPreview = computed(() => ({
  name: form.name || '未命名项目',
  description: form.description || '项目说明会显示在首页项目视图里，帮助你快速识别当前制作线索。',
  style: form.style_preset || 'Warm Studio Console'
}))

watch(projects, (items) => {
  if (items.length === 0) {
    selectedProjectId.value = ''
    return
  }

  if (!items.some((project) => project.id === selectedProjectId.value)) {
    const firstProject = items[0]
    if (firstProject) {
      selectedProjectId.value = firstProject.id
    }
  }
}, { immediate: true })

async function loadProjects() {
  loading.value = true
  error.value = ''

  try {
    const response = await api.listWorkbenchProjects()
    projects.value = response.items
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载项目失败'
  } finally {
    loading.value = false
  }
}

async function createProject() {
  if (!form.name) {
    error.value = '请先填写项目名称'
    return
  }

  submitting.value = true
  error.value = ''

  try {
    const project = await api.createProject(form)
    await router.push({ name: 'project-dashboard', params: { id: project.id } })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建项目失败'
  } finally {
    submitting.value = false
  }
}

function openProject(projectId: string) {
  router.push({ name: 'project-dashboard', params: { id: projectId } })
}

function metricNumber(metrics: Record<string, unknown>, key: string) {
  const value = metrics[key]
  return typeof value === 'number' ? value : 0
}

function resolveStageState(stageKey: string) {
  if (!selectedProject.value) {
    return 'pending'
  }

  const currentIndex = stageRail.findIndex((stage) => stage.key === selectedProject.value?.current_stage)
  const targetIndex = stageRail.findIndex((stage) => stage.key === stageKey)

  if (currentIndex < 0 || targetIndex < 0) {
    return 'pending'
  }

  if (targetIndex < currentIndex) {
    return 'done'
  }

  if (targetIndex === currentIndex) {
    return 'active'
  }

  return 'pending'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

function handleLogout() {
  clearAuthState()
  router.push({ name: 'login' })
}

onMounted(loadProjects)
</script>
