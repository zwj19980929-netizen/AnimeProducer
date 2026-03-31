<template>
  <template v-if="workspace">
    <section class="surface-card hero-card">
      <div class="hero-row">
        <div class="stack" style="gap: 10px; max-width: 760px;">
          <div class="micro-label muted" style="font-size: 10px;">Storyboard Workbench</div>
          <div class="headline-lg">把镜头审核做成轨道工作流，而不是一张难读的长表。</div>
          <div class="body-lg muted">
            现在左边选分集，中间沿时间顺序审核镜头，右边直接改提示词和机位。等镜头过关之后，再进入渲染中心。
          </div>
        </div>

        <div class="stack" style="min-width: 320px; gap: 12px;">
          <StatusPill
            :value="selectedEpisode?.status || 'NOT_STARTED'"
            :label="selectedEpisode ? `EP${selectedEpisode.episode_number.toString().padStart(2, '0')}` : '请先选择分集'"
          />
          <div class="button-row">
            <button class="btn btn-secondary" :disabled="!selectedEpisode || generatingStoryboard" @click="generateStoryboard">
              {{ generatingStoryboard ? '生成中…' : '生成当前分集分镜' }}
            </button>
            <button class="btn btn-ghost" :disabled="!selectedEpisode" @click="loadShots">
              刷新镜头
            </button>
          </div>
        </div>
      </div>

      <div v-if="actionError" class="danger-box body-sm">{{ actionError }}</div>
      <div v-else-if="actionInfo" class="info-box body-sm">{{ actionInfo }}</div>
    </section>

    <section class="split-layout">
      <article class="surface-card section-card stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Episodes Queue</div>
          <div class="headline-md" style="margin-top: 6px;">分集列表</div>
        </div>

        <EmptyState
          v-if="workspace.episodes.length === 0"
          title="还没有分集"
          description="先去分集规划页确认正式分集，这里才会出现可审核的生产单元。"
        />

        <div v-else class="stack">
          <button
            v-for="episode in workspace.episodes"
            :key="episode.id"
            class="list-card"
            :class="{ 'is-active': selectedEpisodeNumber === episode.episode_number }"
            @click="selectedEpisodeNumber = episode.episode_number"
          >
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
              <div class="stack" style="gap: 4px; text-align: left;">
                <div class="headline-sm">EP{{ episode.episode_number.toString().padStart(2, '0') }} · {{ episode.title || '未命名分集' }}</div>
                <div class="body-sm muted">{{ episode.shot_count }} 个镜头 · CH {{ episode.start_chapter }} - {{ episode.end_chapter }}</div>
              </div>
              <StatusPill :value="episode.status" />
            </div>
          </button>
        </div>
      </article>

      <article class="dark-stage stack" style="gap: 18px;">
        <div style="display: flex; justify-content: space-between; align-items: end; gap: 12px; flex-wrap: wrap;">
          <div>
            <div class="micro-label" style="font-size: 10px; color: rgba(255, 248, 240, 0.62);">Shot Timeline</div>
            <div class="headline-md" style="margin-top: 6px; color: #fff8f0;">
              {{ selectedEpisode ? `EP${selectedEpisode.episode_number.toString().padStart(2, '0')} 镜头轨道` : '等待选择分集' }}
            </div>
          </div>
          <div class="chip-row">
            <span class="chip">镜头 {{ shots.length }}</span>
            <span class="chip">键盘上下键切换</span>
          </div>
        </div>

        <div v-if="loadingShots" class="surface-card section-card body-sm">正在整理镜头轨道…</div>

        <EmptyState
          v-else-if="!selectedEpisode"
          title="还没有选中分集"
          description="左边选一集之后，这里会切换成镜头时间线。"
        />

        <EmptyState
          v-else-if="shots.length === 0"
          title="这一集还没有分镜"
          description="点击上方主按钮生成这一集的镜头草案，然后在右侧逐镜头精修。"
        />

        <div v-else class="shot-grid">
          <article
            v-for="shot in shots"
            :key="shot.shot_id"
            class="dark-shot-card"
            :style="{ outline: selectedShotId === shot.shot_id ? '3px solid rgba(217, 93, 57, 0.55)' : 'none' }"
            @click="selectedShotId = shot.shot_id"
          >
            <div class="shot-meta">
              <div style="display: flex; justify-content: space-between; align-items: start; gap: 12px;">
                <div>
                  <div class="micro-label muted" style="font-size: 10px;">Shot {{ shot.sequence_order + 1 }}</div>
                  <div class="headline-sm" style="margin-top: 6px;">{{ shot.scene_description || '待补充镜头描述' }}</div>
                </div>
                <span class="chip">{{ shot.duration }}s</span>
              </div>

              <div class="chip-row">
                <span v-for="character in shot.characters_in_shot" :key="character" class="chip">{{ character }}</span>
                <span v-if="shot.characters_in_shot.length === 0" class="chip">无明确角色</span>
              </div>

              <div class="body-sm muted">{{ shot.visual_prompt || '还没有视觉提示词' }}</div>
              <div class="body-sm muted">机位：{{ shot.camera_movement || '未定义' }}</div>
              <div v-if="shot.dialogue" class="body-sm">台词：{{ shot.dialogue }}</div>
            </div>
          </article>
        </div>
      </article>

      <article class="surface-card section-card stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Shot Inspector</div>
          <div class="headline-md" style="margin-top: 6px;">镜头详情与审核</div>
        </div>

        <EmptyState
          v-if="!selectedShot"
          title="还没有选中镜头"
          description="在中间轨道上点选一个镜头，右侧就会进入可编辑状态。"
        />

        <div v-else class="stack">
          <div class="chip-row">
            <span class="chip">Shot ID {{ selectedShot.shot_id }}</span>
            <span class="chip">顺序 {{ selectedShot.sequence_order + 1 }}</span>
            <span class="chip">{{ selectedShot.duration }} 秒</span>
          </div>

          <div class="form-grid">
            <div class="field-group">
              <label class="field-label">场景说明</label>
              <textarea v-model="shotEditor.scene_description" class="textarea-input" />
            </div>

            <div class="field-group">
              <label class="field-label">视觉提示词</label>
              <textarea v-model="shotEditor.visual_prompt" class="textarea-input" />
            </div>

            <div class="field-group">
              <label class="field-label">机位运动</label>
              <input v-model="shotEditor.camera_movement" class="text-input" />
            </div>

            <div class="form-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
              <div class="field-group">
                <label class="field-label">时长（秒）</label>
                <input v-model.number="shotEditor.duration" type="number" min="0.5" step="0.5" class="text-input" />
              </div>
              <div class="field-group">
                <label class="field-label">动作类型</label>
                <input v-model="shotEditor.action_type" class="text-input" placeholder="fight / reveal / dialogue" />
              </div>
            </div>

            <div class="field-group">
              <label class="field-label">出场角色（逗号分隔）</label>
              <input v-model="shotEditor.characters" class="text-input" placeholder="韩立, 墨彩环" />
            </div>

            <div class="field-group">
              <label class="field-label">台词</label>
              <textarea v-model="shotEditor.dialogue" class="textarea-input" />
            </div>
          </div>

          <div class="button-row">
            <button class="btn btn-primary" :disabled="savingShot" @click="saveShot">
              {{ savingShot ? '保存中…' : '保存当前镜头' }}
            </button>
            <button class="btn btn-ghost" :disabled="selectedShotIndex <= 0" @click="moveSelection(-1)">
              上一个
            </button>
            <button class="btn btn-ghost" :disabled="selectedShotIndex === -1 || selectedShotIndex >= shots.length - 1" @click="moveSelection(1)">
              下一个
            </button>
          </div>

          <div class="info-box body-sm">
            审完这集的镜头后，就可以去渲染中心启动单集渲染，不需要再回旧版全局 pipeline 页面。
          </div>
        </div>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'
import type { ShotItem } from '@/types/workbench'

const route = useRoute()
const { workspace, refreshWorkspace } = useWorkbench()

const selectedEpisodeNumber = ref<number | null>(null)
const selectedShotId = ref<number | null>(null)
const shots = ref<ShotItem[]>([])

const loadingShots = ref(false)
const generatingStoryboard = ref(false)
const savingShot = ref(false)
const actionError = ref('')
const actionInfo = ref('')

const shotEditor = reactive({
  duration: 3,
  scene_description: '',
  visual_prompt: '',
  camera_movement: '',
  characters: '',
  dialogue: '',
  action_type: ''
})

const projectId = computed(() => route.params.id as string)
const selectedEpisode = computed(() => (
  workspace.value?.episodes.find((episode) => episode.episode_number === selectedEpisodeNumber.value) || null
))
const selectedShot = computed(() => shots.value.find((shot) => shot.shot_id === selectedShotId.value) || null)
const selectedShotIndex = computed(() => shots.value.findIndex((shot) => shot.shot_id === selectedShotId.value))

watch(
  () => workspace.value?.episodes,
  (episodes) => {
    if (!episodes?.length) {
      selectedEpisodeNumber.value = null
      return
    }

    const firstEpisode = episodes[0]
    if ((!selectedEpisodeNumber.value || !episodes.some((episode) => episode.episode_number === selectedEpisodeNumber.value)) && firstEpisode) {
      selectedEpisodeNumber.value = firstEpisode.episode_number
    }
  },
  { immediate: true, deep: true }
)

watch(
  selectedEpisodeNumber,
  async (episodeNumber) => {
    if (!episodeNumber) {
      shots.value = []
      selectedShotId.value = null
      return
    }
    await loadShots()
  },
  { immediate: true }
)

watch(
  selectedShot,
  (shot) => {
    if (!shot) return
    shotEditor.duration = shot.duration
    shotEditor.scene_description = shot.scene_description
    shotEditor.visual_prompt = shot.visual_prompt
    shotEditor.camera_movement = shot.camera_movement
    shotEditor.characters = shot.characters_in_shot.join(', ')
    shotEditor.dialogue = shot.dialogue || ''
    shotEditor.action_type = shot.action_type || ''
  },
  { immediate: true }
)

function parseCharacters(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function moveSelection(offset: number) {
  if (selectedShotIndex.value === -1) return
  const nextShot = shots.value[selectedShotIndex.value + offset]
  if (nextShot) {
    selectedShotId.value = nextShot.shot_id
  }
}

function handleKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  const tagName = target?.tagName || ''
  if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT') {
    return
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveSelection(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveSelection(-1)
  }
}

async function loadShots() {
  if (!selectedEpisodeNumber.value) return

  loadingShots.value = true
  actionError.value = ''

  try {
    const response = await api.listEpisodeShots(projectId.value, selectedEpisodeNumber.value)
    shots.value = response.items
    selectedShotId.value = response.items[0]?.shot_id || null
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '加载分镜失败'
  } finally {
    loadingShots.value = false
  }
}

async function generateStoryboard() {
  if (!selectedEpisodeNumber.value) return

  generatingStoryboard.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    const response = await api.generateEpisodeStoryboard(projectId.value, selectedEpisodeNumber.value)
    shots.value = response.items
    selectedShotId.value = response.items[0]?.shot_id || null
    actionInfo.value = `EP${selectedEpisodeNumber.value.toString().padStart(2, '0')} 的分镜已生成，可以开始逐镜头审核。`
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '生成分镜失败'
  } finally {
    generatingStoryboard.value = false
  }
}

async function saveShot() {
  if (!selectedShot.value) return

  savingShot.value = true
  actionError.value = ''
  actionInfo.value = ''

  try {
    await api.updateShot(projectId.value, selectedShot.value.shot_id, {
      duration: shotEditor.duration,
      scene_description: shotEditor.scene_description,
      visual_prompt: shotEditor.visual_prompt,
      camera_movement: shotEditor.camera_movement,
      characters_in_shot: parseCharacters(shotEditor.characters),
      dialogue: shotEditor.dialogue || null,
      action_type: shotEditor.action_type || null
    })
    actionInfo.value = `镜头 ${selectedShot.value.shot_id} 已更新。`
    await loadShots()
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '保存镜头失败'
  } finally {
    savingShot.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>
