<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="从章节扫描角色"
    class="max-w-4xl"
    :mask-closable="false"
  >
    <div class="space-y-4">
      <!-- 章节选择 -->
      <n-form-item label="选择要扫描的章节（最多10章）">
        <n-checkbox-group v-model:value="selectedChapters">
          <div class="grid grid-cols-5 gap-2 max-h-48 overflow-y-auto">
            <n-checkbox
              v-for="chapter in chapters"
              :key="chapter.chapter_number"
              :value="chapter.chapter_number"
              :label="`第${chapter.chapter_number}章`"
            />
          </div>
        </n-checkbox-group>
      </n-form-item>

      <div class="flex gap-2">
        <n-button size="small" @click="selectAll">全选</n-button>
        <n-button size="small" @click="selectNone">取消全选</n-button>
        <n-button size="small" @click="selectRange">选择范围</n-button>
        <span class="text-gray-400 text-sm ml-2">已选 {{ selectedChapters.length }} 章</span>
      </div>

      <n-form-item label="选项">
        <n-checkbox v-model:checked="autoCreate">
          自动创建新角色（取消则只返回分析结果）
        </n-checkbox>
      </n-form-item>

      <!-- 扫描结果 -->
      <div v-if="scanResult" class="space-y-4">
        <n-divider>扫描结果</n-divider>

        <!-- 新角色 -->
        <div v-if="scanResult.new_characters?.length">
          <h4 class="text-white font-medium mb-2">
            新发现的角色 ({{ scanResult.new_characters.length }})
          </h4>
          <div class="space-y-2">
            <div
              v-for="char in scanResult.new_characters"
              :key="char.name"
              class="bg-gray-800 rounded p-3"
            >
              <div class="flex items-center gap-2 mb-1">
                <span class="text-white font-medium">{{ char.name }}</span>
                <n-tag v-if="char.aliases?.length" size="tiny" type="info">
                  别名: {{ char.aliases.join(', ') }}
                </n-tag>
              </div>
              <p class="text-gray-400 text-sm">
                {{ [char.hair_color, char.eye_color, char.physical_features, char.clothing].filter(Boolean).join(', ') || '无外貌描述' }}
              </p>
            </div>
          </div>
        </div>

        <!-- 别名检测 -->
        <div v-if="scanResult.alias_detections?.length">
          <h4 class="text-white font-medium mb-2">
            检测到的别名 ({{ scanResult.alias_detections.length }})
          </h4>
          <div class="space-y-2">
            <div
              v-for="(alias, idx) in scanResult.alias_detections"
              :key="idx"
              class="bg-blue-900/30 rounded p-3 flex items-center justify-between"
            >
              <div>
                <span class="text-white">{{ alias.character_name }}</span>
                <span class="text-gray-400 mx-2">→</span>
                <span class="text-blue-400">{{ alias.new_alias }}</span>
                <n-tag size="tiny" class="ml-2" :type="getConfidenceType(alias.confidence)">
                  {{ alias.confidence }}
                </n-tag>
              </div>
              <span class="text-gray-500 text-xs">{{ alias.context }}</span>
            </div>
          </div>
        </div>

        <!-- 可疑身份关联 -->
        <div v-if="scanResult.suspected_identities?.length">
          <h4 class="text-yellow-400 font-medium mb-2">
            可疑身份关联 ({{ scanResult.suspected_identities.length }})
            <span class="text-gray-400 text-sm font-normal ml-2">需要人工确认</span>
          </h4>
          <div class="space-y-2">
            <div
              v-for="(suspect, idx) in scanResult.suspected_identities"
              :key="idx"
              class="bg-yellow-900/20 border border-yellow-700/50 rounded p-3"
            >
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-yellow-400">{{ suspect.new_character }}</span>
                  <span class="text-gray-400">可能是</span>
                  <span class="text-white">{{ suspect.existing_character }}</span>
                  <n-tag size="tiny" :type="getConfidenceType(suspect.confidence)">
                    {{ suspect.confidence }}
                  </n-tag>
                </div>
                <n-button
                  size="tiny"
                  type="warning"
                  @click="handleMerge(suspect)"
                  :loading="merging === idx"
                >
                  确认合并
                </n-button>
              </div>
              <p class="text-gray-400 text-sm">{{ suspect.reason }}</p>
              <div v-if="suspect.evidence?.length" class="mt-1">
                <span class="text-gray-500 text-xs">证据: {{ suspect.evidence.join('; ') }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 角色进化 -->
        <div v-if="scanResult.character_evolutions?.length">
          <h4 class="text-purple-400 font-medium mb-2">
            角色形象变化 ({{ scanResult.character_evolutions.length }})
          </h4>
          <div class="space-y-2">
            <div
              v-for="(evo, idx) in scanResult.character_evolutions"
              :key="idx"
              class="bg-purple-900/20 rounded p-3"
            >
              <div class="flex items-center gap-2 mb-1">
                <span class="text-white">{{ evo.character_name }}</span>
                <n-tag size="tiny" type="warning">{{ evo.evolution_type }}</n-tag>
                <span class="text-gray-500 text-xs">第{{ evo.trigger_chapter }}章</span>
              </div>
              <p class="text-gray-400 text-sm">
                {{ Object.entries(evo.new_traits || {}).filter(([k, v]) => v).map(([k, v]) => `${k}: ${v}`).join(', ') }}
              </p>
            </div>
          </div>
        </div>

        <!-- 无结果 -->
        <n-empty
          v-if="!scanResult.new_characters?.length && !scanResult.alias_detections?.length && !scanResult.suspected_identities?.length && !scanResult.character_evolutions?.length"
          description="未发现新角色或变化"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between">
        <span v-if="scanResult" class="text-gray-400 text-sm">
          已创建 {{ scanResult.characters_created?.length || 0 }} 个角色
        </span>
        <div class="flex gap-2">
          <n-button @click="visible = false">关闭</n-button>
          <n-button
            type="primary"
            @click="handleScan"
            :loading="scanning"
            :disabled="selectedChapters.length === 0 || selectedChapters.length > 10"
          >
            {{ scanning ? '扫描中...' : '开始扫描' }}
          </n-button>
        </div>
      </div>
    </template>

    <!-- 范围选择弹窗 -->
    <n-modal v-model:show="showRangeModal" preset="card" title="选择章节范围" class="max-w-sm">
      <div class="flex items-center gap-2">
        <n-input-number v-model:value="rangeStart" :min="1" placeholder="起始章节" />
        <span class="text-gray-400">到</span>
        <n-input-number v-model:value="rangeEnd" :min="rangeStart" placeholder="结束章节" />
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showRangeModal = false">取消</n-button>
          <n-button type="primary" @click="applyRange">确定</n-button>
        </div>
      </template>
    </n-modal>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  NModal, NFormItem, NCheckboxGroup, NCheckbox, NButton, NTag,
  NDivider, NEmpty, NInputNumber, useMessage
} from 'naive-ui'
import { apiClient } from '@/api/client'
import type { Chapter, Character } from '@/types/api'

const props = defineProps<{
  show: boolean
  projectId: string
  chapters: Chapter[]
  existingCharacters: Character[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'characters-updated': []
}>()

const message = useMessage()

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const selectedChapters = ref<number[]>([])
const autoCreate = ref(true)
const scanning = ref(false)
const merging = ref<number | null>(null)
const scanResult = ref<any>(null)

const showRangeModal = ref(false)
const rangeStart = ref(1)
const rangeEnd = ref(10)

watch(() => props.show, (show) => {
  if (show) {
    scanResult.value = null
    selectedChapters.value = []
  }
})

function selectAll() {
  const maxSelect = Math.min(props.chapters.length, 10)
  selectedChapters.value = props.chapters.slice(0, maxSelect).map(c => c.chapter_number)
}

function selectNone() {
  selectedChapters.value = []
}

function selectRange() {
  rangeStart.value = 1
  rangeEnd.value = Math.min(10, props.chapters.length)
  showRangeModal.value = true
}

function applyRange() {
  const start = rangeStart.value
  const end = Math.min(rangeEnd.value, start + 9) // 最多10章
  selectedChapters.value = props.chapters
    .filter(c => c.chapter_number >= start && c.chapter_number <= end)
    .map(c => c.chapter_number)
  showRangeModal.value = false
}

function getConfidenceType(confidence: string): 'success' | 'warning' | 'error' {
  if (confidence === 'high') return 'success'
  if (confidence === 'medium') return 'warning'
  return 'error'
}

async function handleScan() {
  if (selectedChapters.value.length === 0) {
    message.warning('请选择要扫描的章节')
    return
  }
  if (selectedChapters.value.length > 10) {
    message.warning('一次最多扫描10章')
    return
  }

  scanning.value = true
  try {
    const result = await apiClient.extractCharactersFromChapters(
      props.projectId,
      selectedChapters.value,
      autoCreate.value
    )
    scanResult.value = result

    if (result.characters_created?.length > 0) {
      message.success(`成功创建 ${result.characters_created.length} 个角色`)
      emit('characters-updated')
    }
  } catch (error) {
    console.error('Scan failed:', error)
    message.error(`扫描失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    scanning.value = false
  }
}

async function handleMerge(suspect: any) {
  // 找到对应的角色 ID
  const newChar = props.existingCharacters.find(c => c.name === suspect.new_character)
  const existingChar = props.existingCharacters.find(c => c.name === suspect.existing_character)

  if (!newChar || !existingChar) {
    // 如果是刚创建的角色，需要重新获取
    message.info('请先刷新角色列表后再合并')
    emit('characters-updated')
    return
  }

  const idx = scanResult.value.suspected_identities.indexOf(suspect)
  merging.value = idx

  try {
    await apiClient.mergeCharacters(
      props.projectId,
      existingChar.character_id,
      newChar.character_id
    )
    message.success(`已将「${suspect.new_character}」合并到「${suspect.existing_character}」`)

    // 从结果中移除已处理的项
    scanResult.value.suspected_identities = scanResult.value.suspected_identities.filter(
      (s: any) => s !== suspect
    )

    emit('characters-updated')
  } catch (error) {
    console.error('Merge failed:', error)
    message.error(`合并失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    merging.value = null
  }
}
</script>
