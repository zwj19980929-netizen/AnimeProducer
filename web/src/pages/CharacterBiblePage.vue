<template>
  <template v-if="workspace">
    <section class="content-grid">
      <article class="surface-card section-card col-span-4 stack">
        <div style="display: flex; justify-content: space-between; align-items: end; gap: 12px;">
          <div>
            <div class="micro-label muted" style="font-size: 10px;">Character List</div>
            <div class="headline-md" style="margin-top: 6px;">角色圣经</div>
          </div>
          <button class="btn btn-primary" :disabled="scanning" @click="scanCharacters">
            {{ scanning ? '扫描中…' : '扫描角色' }}
          </button>
        </div>

        <div v-if="actionError" class="danger-box body-sm">{{ actionError }}</div>

        <EmptyState
          v-if="workspace.characters.length === 0"
          title="还没有角色"
          description="完成章节分析后，点击扫描角色，把候选人物拉进角色圣经。"
        />

        <div v-else class="stack">
          <button
            v-for="character in workspace.characters"
            :key="character.character_id"
            class="list-card"
            :class="{ 'is-active': selectedCharacterId === character.character_id }"
            @click="selectedCharacterId = character.character_id"
          >
            <div style="display: flex; gap: 14px; align-items: center;">
              <div class="thumb portrait" style="width: 88px; min-width: 88px; aspect-ratio: 1 / 1; border-radius: 18px;">
                <img v-if="resolveAssetUrl(character.anchor_image_url || character.reference_image_url)" :src="resolveAssetUrl(character.anchor_image_url || character.reference_image_url)!" :alt="character.name" />
              </div>
              <div class="stack" style="gap: 4px; text-align: left;">
                <div class="headline-sm">{{ character.name }}</div>
                <div class="body-sm muted">{{ character.aliases.join(' / ') || '暂无别名' }}</div>
                <StatusPill :value="character.asset_status" />
              </div>
            </div>
          </button>
        </div>
      </article>

      <article v-if="selectedCharacter" class="surface-card section-card col-span-5 stack">
        <div style="display: flex; gap: 18px; align-items: start;">
          <div class="thumb portrait" style="width: 220px; flex-shrink: 0;">
            <img v-if="resolveAssetUrl(selectedCharacter.anchor_image_url || selectedCharacter.reference_image_url)" :src="resolveAssetUrl(selectedCharacter.anchor_image_url || selectedCharacter.reference_image_url)!" :alt="selectedCharacter.name" />
          </div>

          <div class="stack" style="gap: 10px;">
            <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
              <div>
                <div class="headline-lg">{{ selectedCharacter.name }}</div>
                <div class="chip-row" style="margin-top: 10px;">
                  <span class="chip" v-for="alias in selectedCharacter.aliases" :key="alias">{{ alias }}</span>
                </div>
              </div>
              <StatusPill :value="selectedCharacter.review_status" />
            </div>

            <div class="body-sm muted">
              {{ selectedCharacter.bio || selectedCharacter.appearance_prompt || '当前角色还没有完整的人物简介，先从候选图和语音配置开始完善。' }}
            </div>

            <div class="chip-row">
              <span class="chip">首次出场 第 {{ selectedCharacter.first_appearance_chapter || 0 }} 章</span>
              <span class="chip">锚点 {{ selectedCharacter.image_counts.ANCHOR || 0 }}</span>
              <span class="chip">候选 {{ selectedCharacter.image_counts.CANDIDATE || 0 }}</span>
              <span class="chip">变体 {{ selectedCharacter.image_counts.VARIANT || 0 }}</span>
            </div>

            <div v-if="selectedCharacter.issues.length" class="warning-box body-sm">
              {{ selectedCharacter.issues.join('；') }}
            </div>
          </div>
        </div>

        <div class="stack">
          <div style="display: flex; justify-content: space-between; align-items: end; gap: 12px;">
            <div>
              <div class="micro-label muted" style="font-size: 10px;">AI Candidate Gallery</div>
              <div class="headline-md" style="margin-top: 6px;">候选图与锚点图</div>
            </div>
            <div class="button-row">
              <button class="btn btn-secondary" :disabled="generatingReference" @click="generateReference">
                {{ generatingReference ? '生成中…' : '生成候选图' }}
              </button>
              <button class="btn btn-ghost" :disabled="generatingVariants" @click="generateVariants">
                {{ generatingVariants ? '处理中…' : '生成变体图' }}
              </button>
            </div>
          </div>

          <EmptyState
            v-if="images.length === 0"
            title="还没有图片库"
            description="先生成候选图，再把满意的图设为锚点，后续变体和分镜才会更稳定。"
          />

          <div v-else class="project-grid" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
            <article v-for="image in images" :key="image.id" class="surface-panel section-card stack" style="gap: 12px;">
              <div class="thumb portrait" style="aspect-ratio: 1 / 1;">
                <img v-if="resolveAssetUrl(image.image_url || image.image_path)" :src="resolveAssetUrl(image.image_url || image.image_path)!" :alt="image.prompt || selectedCharacter.name" />
              </div>
              <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
                <StatusPill :value="image.image_type" />
                <StatusPill v-if="image.is_anchor" value="COMPLETED" label="当前锚点" />
              </div>
              <div class="button-row" v-if="!image.is_anchor">
                <button class="btn btn-primary" style="flex: 1;" @click="setAnchor(image.id)">设为锚点</button>
              </div>
            </article>
          </div>
        </div>
      </article>

      <article v-if="selectedCharacter" class="surface-card section-card col-span-3 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Voice Profile</div>
          <div class="headline-md" style="margin-top: 6px;">语音配置</div>
        </div>

        <div class="field-group">
          <label class="field-label">选择音色</label>
          <select v-model="selectedVoiceId" class="select-input">
            <option value="">请选择语音</option>
            <option v-for="voice in voices" :key="voice.id" :value="voice.id">
              {{ voice.name }}
            </option>
          </select>
        </div>

        <div class="button-row">
          <button class="btn btn-primary" :disabled="savingVoice || !selectedVoiceId" @click="saveVoice">
            {{ savingVoice ? '保存中…' : '保存语音' }}
          </button>
          <button class="btn btn-ghost" :disabled="previewingVoice || !selectedVoiceId" @click="previewVoice">
            {{ previewingVoice ? '试听中…' : '试听' }}
          </button>
        </div>

        <div class="surface-panel section-card">
          <div class="micro-label muted" style="font-size: 10px;">Voice Wave</div>
          <div class="audio-bars" style="margin-top: 16px;">
            <span style="height: 12px;" />
            <span style="height: 22px;" />
            <span style="height: 38px;" />
            <span style="height: 18px;" />
            <span style="height: 44px;" />
            <span style="height: 28px;" />
            <span style="height: 48px;" />
            <span style="height: 20px;" />
            <span style="height: 32px;" />
            <span style="height: 14px;" />
          </div>
        </div>

        <audio v-if="previewUrl" :src="previewUrl" controls style="width: 100%;" />
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api, resolveAssetUrl } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'
import type { CharacterImage, VoiceOption } from '@/types/workbench'

const route = useRoute()
const { workspace, refreshWorkspace } = useWorkbench()

const actionError = ref('')
const scanning = ref(false)
const generatingReference = ref(false)
const generatingVariants = ref(false)
const savingVoice = ref(false)
const previewingVoice = ref(false)

const images = ref<CharacterImage[]>([])
const voices = ref<VoiceOption[]>([])
const previewUrl = ref<string | null>(null)

const selectedCharacterId = ref<string | null>(null)
const selectedVoiceId = ref('')

const projectId = computed(() => route.params.id as string)
const selectedCharacter = computed(() => workspace.value?.characters.find((item) => item.character_id === selectedCharacterId.value) || null)

watch(workspace, (next) => {
  if (!next) return
  const firstCharacter = next.characters[0]
  if (!selectedCharacterId.value && firstCharacter) {
    selectedCharacterId.value = firstCharacter.character_id
  }
}, { immediate: true })

watch(selectedCharacterId, async (characterId) => {
  previewUrl.value = null
  images.value = []

  if (!characterId) return

  const response = await api.listCharacterImages(characterId)
  images.value = response.items

  const current = workspace.value?.characters.find((item) => item.character_id === characterId)
  selectedVoiceId.value = current?.voice_id || ''
})

async function ensureVoices() {
  if (voices.value.length > 0) return
  const response = await api.listVoices()
  voices.value = response.voices
}

async function scanCharacters() {
  if (!workspace.value?.chapters.length) {
    actionError.value = '请先导入并分析章节'
    return
  }

  scanning.value = true
  actionError.value = ''

  try {
    await api.extractCharacters(projectId.value, workspace.value.chapters.map((chapter) => chapter.chapter_number))
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '角色扫描失败'
  } finally {
    scanning.value = false
  }
}

async function generateReference() {
  if (!selectedCharacter.value) return
  generatingReference.value = true
  actionError.value = ''

  try {
    await api.generateReferenceImages(selectedCharacter.value.character_id, { num_candidates: 4 })
    await refreshWorkspace()
    const response = await api.listCharacterImages(selectedCharacter.value.character_id)
    images.value = response.items
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '候选图生成失败'
  } finally {
    generatingReference.value = false
  }
}

async function generateVariants() {
  if (!selectedCharacter.value) return
  generatingVariants.value = true
  actionError.value = ''

  try {
    await api.generateVariants(selectedCharacter.value.character_id, {
      num_images: 2,
      pose: 'standing',
      expression: 'determined'
    })
    const response = await api.listCharacterImages(selectedCharacter.value.character_id)
    images.value = response.items
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '变体图生成失败'
  } finally {
    generatingVariants.value = false
  }
}

async function setAnchor(imageId: string) {
  if (!selectedCharacter.value) return

  actionError.value = ''
  try {
    await api.setAnchorImage(selectedCharacter.value.character_id, imageId)
    const response = await api.listCharacterImages(selectedCharacter.value.character_id)
    images.value = response.items
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '设置锚点失败'
  }
}

async function saveVoice() {
  if (!selectedCharacter.value || !selectedVoiceId.value) return
  savingVoice.value = true
  actionError.value = ''

  try {
    await api.setCharacterVoice(selectedCharacter.value.character_id, {
      voice_id: selectedVoiceId.value,
      speed: 1,
      pitch: 0,
      emotion: null
    })
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '保存语音失败'
  } finally {
    savingVoice.value = false
  }
}

async function previewVoice() {
  if (!selectedVoiceId.value) return
  previewingVoice.value = true
  actionError.value = ''

  try {
    const preview = await api.previewVoice(selectedVoiceId.value, `你好，我是${selectedCharacter.value?.name ?? '角色'}的试音。`)
    previewUrl.value = resolveAssetUrl(preview.audio_url)
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '试听失败'
  } finally {
    previewingVoice.value = false
  }
}

onMounted(() => {
  ensureVoices().catch(() => undefined)
})
</script>
