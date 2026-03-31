<template>
  <template v-if="workspace">
    <section class="content-grid">
      <article class="surface-card section-card col-span-4 stack">
        <div class="thumb portrait">
          <div style="width: 100%; height: 100%; background:
            linear-gradient(160deg, rgba(31,36,48,0.82), rgba(31,36,48,0.58)),
            radial-gradient(circle at top, rgba(217,93,57,0.22), transparent 36%);
            display: grid; place-items: center; color: #fff8f0; padding: 24px; text-align: center;">
            <div>
              <div class="micro-label" style="font-size: 10px; color: rgba(255,248,240,0.72);">Original Source</div>
              <div class="headline-md" style="margin-top: 12px;">{{ workspace.book?.title || workspace.project.name }}</div>
              <div class="body-sm" style="margin-top: 12px; color: rgba(255,248,240,0.72);">
                {{ workspace.book?.author || '尚未识别作者信息' }}
              </div>
            </div>
          </div>
        </div>

        <div class="stack" style="gap: 8px;">
          <div class="headline-md">{{ workspace.book?.title || '还没有导入原著' }}</div>
          <div class="body-sm muted">
            {{ workspace.book?.ai_summary || '上传 TXT 后，系统会自动拆分章节，并为后续的章节分析、角色扫描和分集规划提供骨架。' }}
          </div>
        </div>

        <div class="chip-row">
          <span class="chip">上传状态 {{ workspace.book?.upload_status || 'EMPTY' }}</span>
          <span class="chip">章节 {{ workspace.book?.uploaded_chapters || 0 }}</span>
          <span class="chip">总字数 {{ workspace.book?.total_words || 0 }}</span>
        </div>

        <input ref="fileInput" type="file" accept=".txt" style="display: none" @change="onFileSelected" />

        <div class="button-row">
          <button class="btn btn-primary" :disabled="uploading" @click="fileInput?.click()">
            {{ uploading ? '上传中…' : '更新书源文本' }}
          </button>
          <button class="btn btn-secondary" :disabled="analyzing" @click="analyzeAll">
            {{ analyzing ? '分析中…' : '分析全部章节' }}
          </button>
        </div>

        <div v-if="actionError" class="danger-box body-sm">{{ actionError }}</div>

        <div class="surface-panel section-card stack">
          <div class="micro-label muted" style="font-size: 10px;">Extraction Health</div>
          <div class="stack" style="gap: 12px;">
            <div>
              <div style="display: flex; justify-content: space-between; gap: 12px;">
                <span class="body-sm">Logical Consistency</span>
                <span class="mono body-sm">{{ analysisPercent }}%</span>
              </div>
              <div class="progress-track" style="margin-top: 8px;">
                <div class="progress-bar ai" :style="{ width: `${analysisPercent}%` }" />
              </div>
            </div>
            <div>
              <div style="display: flex; justify-content: space-between; gap: 12px;">
                <span class="body-sm">Story Structure Readiness</span>
                <span class="mono body-sm">{{ chapterCoveragePercent }}%</span>
              </div>
              <div class="progress-track" style="margin-top: 8px;">
                <div class="progress-bar success" :style="{ width: `${chapterCoveragePercent}%` }" />
              </div>
            </div>
          </div>
        </div>
      </article>

      <article class="surface-card section-card col-span-8 stack">
        <div style="display: flex; justify-content: space-between; gap: 12px; align-items: end;">
          <div>
            <div class="micro-label muted" style="font-size: 10px;">Chapters Index</div>
            <div class="headline-md" style="margin-top: 6px;">章节目录与解析状态</div>
          </div>
          <div class="body-sm muted">{{ workspace.chapters.length }} 章</div>
        </div>

        <EmptyState
          v-if="workspace.chapters.length === 0"
          title="还没有章节"
          description="上传一本 TXT 小说后，这里会变成章节索引和结构化解析入口。"
        />

        <div v-else class="table-shell">
          <table class="table">
            <thead>
              <tr>
                <th>章节</th>
                <th>标题</th>
                <th>字数</th>
                <th>情绪</th>
                <th>关键事件</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="chapter in workspace.chapters" :key="chapter.chapter_id">
                <td class="mono">CH {{ chapter.chapter_number.toString().padStart(3, '0') }}</td>
                <td>{{ chapter.title || '未命名章节' }}</td>
                <td>{{ chapter.word_count }}</td>
                <td>{{ chapter.emotional_arc || '未分析' }}</td>
                <td>{{ chapter.key_events.slice(0, 2).join(' / ') || '等待分析' }}</td>
                <td><StatusPill :value="chapter.status" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { api } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'

const route = useRoute()
const { workspace, refreshWorkspace } = useWorkbench()

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const analyzing = ref(false)
const actionError = ref('')

const projectId = computed(() => route.params.id as string)

const analysisPercent = computed(() => {
  if (!workspace.value?.chapters.length) return 0
  const analyzed = workspace.value.chapters.filter((chapter) => chapter.status === 'READY').length
  return Math.round((analyzed / workspace.value.chapters.length) * 100)
})

const chapterCoveragePercent = computed(() => {
  if (!workspace.value?.book?.total_chapters) return 0
  return Math.round((workspace.value.book.uploaded_chapters / workspace.value.book.total_chapters) * 100)
})

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  actionError.value = ''

  try {
    await api.uploadBook(projectId.value, file, true)
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function analyzeAll() {
  analyzing.value = true
  actionError.value = ''

  try {
    await api.analyzeAllChapters(projectId.value)
    await api.analyzeBook(projectId.value)
    await refreshWorkspace()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '章节分析失败'
  } finally {
    analyzing.value = false
  }
}
</script>
