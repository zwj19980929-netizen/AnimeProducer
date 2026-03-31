<template>
  <template v-if="workspace">
    <section class="surface-card hero-card">
      <div class="hero-row">
        <div class="stack" style="gap: 10px; max-width: 760px;">
          <div class="micro-label muted" style="font-size: 10px;">Delivery Output</div>
          <div class="headline-lg">把输出路径升级成真正可预览、可回看、可交付的版本区。</div>
          <div class="body-lg muted">
            最新版本在上面直接看片，历史版本在下面清晰列出。现在交付页终于承担“看片与导出”的职责，而不是只显示一个文件路径。
          </div>
        </div>

        <div class="stack" style="min-width: 320px; gap: 12px;">
          <StatusPill :value="selectedDelivery ? 'COMPLETED' : 'NOT_STARTED'" :label="selectedDelivery ? selectedDelivery.version_label : '暂无成片'" />
          <div class="button-row">
            <button class="btn btn-primary" :disabled="!selectedVideoUrl" @click="copyVideoLink">
              复制视频链接
            </button>
            <button class="btn btn-ghost" @click="() => refreshWorkspace()">刷新交付</button>
          </div>
        </div>
      </div>

      <div v-if="actionInfo" class="info-box body-sm">{{ actionInfo }}</div>
    </section>

    <EmptyState
      v-if="workspace.deliveries.length === 0"
      title="还没有交付成片"
      description="先去渲染中心启动单集渲染，成功之后这里会自动生成可预览的版本记录。"
    />

    <section v-else class="content-grid">
      <article class="surface-card section-card col-span-8 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Latest Preview</div>
          <div class="headline-md" style="margin-top: 6px;">最新版本播放器</div>
        </div>

        <div class="video-player">
          <video v-if="selectedVideoUrl" :src="selectedVideoUrl" controls playsinline />
          <div class="video-overlay">
            <div class="headline-sm">{{ selectedDelivery?.title || selectedDelivery?.version_label }}</div>
            <div class="body-sm" style="color: rgba(255,255,255,0.8); margin-top: 6px;">
              EP{{ selectedDelivery?.episode_number.toString().padStart(2, '0') }} · {{ selectedDelivery ? formatDate(selectedDelivery.updated_at) : '' }}
            </div>
          </div>
        </div>

        <section class="stack">
          <div class="headline-sm">版本列表</div>
          <div class="project-grid">
            <article
              v-for="delivery in workspace.deliveries"
              :key="delivery.episode_id"
              class="surface-panel project-card"
              :style="{ outline: selectedDelivery?.episode_id === delivery.episode_id ? '2px solid rgba(217, 93, 57, 0.45)' : 'none' }"
              @click="selectedEpisodeId = delivery.episode_id"
            >
              <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
                <div>
                  <div class="micro-label muted" style="font-size: 10px;">EP{{ delivery.episode_number.toString().padStart(2, '0') }}</div>
                  <div class="headline-sm" style="margin-top: 8px;">{{ delivery.title || delivery.version_label }}</div>
                </div>
                <StatusPill value="COMPLETED" label="可预览" />
              </div>

              <div class="body-sm muted">
                {{ formatDate(delivery.updated_at) }}
              </div>

              <div class="chip-row">
                <span class="chip">{{ delivery.version_label }}</span>
                <span class="chip">{{ delivery.duration_minutes || '未知' }} 分钟</span>
              </div>
            </article>
          </div>
        </section>
      </article>

      <article class="surface-card section-card col-span-4 stack">
        <div>
          <div class="micro-label muted" style="font-size: 10px;">Version Meta</div>
          <div class="headline-md" style="margin-top: 6px;">版本信息</div>
        </div>

        <div v-if="selectedDelivery" class="stack">
          <div class="chip-row">
            <span class="chip">EP{{ selectedDelivery.episode_number.toString().padStart(2, '0') }}</span>
            <span class="chip">{{ selectedDelivery.version_label }}</span>
          </div>

          <div class="surface-panel section-card stack">
            <div class="body-sm"><strong>标题：</strong>{{ selectedDelivery.title || '未命名分集' }}</div>
            <div class="body-sm"><strong>时长：</strong>{{ selectedDelivery.duration_minutes || '未知' }} 分钟</div>
            <div class="body-sm"><strong>更新时间：</strong>{{ formatDate(selectedDelivery.updated_at) }}</div>
          </div>

          <a v-if="selectedVideoUrl" class="btn btn-secondary" :href="selectedVideoUrl" target="_blank" rel="noreferrer">
            新窗口打开
          </a>

          <div class="info-box body-sm">
            后续如果需要做“版本历史 / 来源批次 / 下载记录”，这一栏可以继续扩成完整的交付元数据面板。
          </div>
        </div>
      </article>
    </section>
  </template>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import StatusPill from '@/components/StatusPill.vue'
import { resolveAssetUrl } from '@/lib/api'
import { useWorkbench } from '@/lib/useWorkbench'

const { workspace, refreshWorkspace } = useWorkbench()

const selectedEpisodeId = ref<string | null>(null)
const actionInfo = ref('')

const selectedDelivery = computed(() => (
  workspace.value?.deliveries.find((delivery) => delivery.episode_id === selectedEpisodeId.value) || workspace.value?.deliveries[0] || null
))
const selectedVideoUrl = computed(() => resolveAssetUrl(selectedDelivery.value?.video_url))

watch(
  () => workspace.value?.deliveries,
  (deliveries) => {
    if (!deliveries?.length) {
      selectedEpisodeId.value = null
      return
    }

    const firstDelivery = deliveries[0]
    if ((!selectedEpisodeId.value || !deliveries.some((delivery) => delivery.episode_id === selectedEpisodeId.value)) && firstDelivery) {
      selectedEpisodeId.value = firstDelivery.episode_id
    }
  },
  { immediate: true, deep: true }
)

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

async function copyVideoLink() {
  if (!selectedVideoUrl.value) return

  try {
    await navigator.clipboard.writeText(selectedVideoUrl.value)
    actionInfo.value = '视频链接已复制。'
  } catch {
    actionInfo.value = '当前环境不支持自动复制，请直接在新窗口中打开。'
  }
}
</script>
