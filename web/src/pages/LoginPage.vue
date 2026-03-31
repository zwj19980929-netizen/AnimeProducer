<template>
  <div class="auth-shell">
    <div class="auth-card">
      <section class="auth-art">
        <div class="auth-grid" />
        <div class="auth-copy-block">
          <div class="brand-kicker">Storyboard Workbench</div>
          <div class="headline-lg auth-hero-title">进入工作台之前，先让你看见制作线索。</div>
          <div class="body-lg auth-hero-copy">
            这版首页不是“先看到一排空按钮”，而是把书源、角色、分集、分镜、渲染和交付串成一条真正的制作路径。
          </div>
        </div>

        <div class="auth-stage-strip">
          <article v-for="item in stages" :key="item.label" class="auth-stage-item">
            <div class="micro-label" style="font-size: 10px; color: rgba(255,255,255,0.52);">{{ item.index }}</div>
            <div class="headline-sm" style="color: #fff8f0; margin-top: 8px;">{{ item.label }}</div>
            <div class="body-sm" style="color: rgba(255,255,255,0.62); margin-top: 8px;">{{ item.copy }}</div>
          </article>
        </div>

        <div class="auth-note-panel">
          <div class="micro-label" style="font-size: 10px; color: rgba(255,255,255,0.52);">Why This Version</div>
          <div class="auth-mini-grid">
            <article class="auth-mini-card">
              <div class="headline-sm" style="color: #fff8f0;">阶段入口</div>
              <div class="body-sm" style="color: rgba(255,255,255,0.62);">先看到当前阶段和下一步，不再在 tab 里猜路。</div>
            </article>
            <article class="auth-mini-card">
              <div class="headline-sm" style="color: #fff8f0;">制作语境</div>
              <div class="body-sm" style="color: rgba(255,255,255,0.62);">像分镜台和控制台，而不是通用 SaaS 后台。</div>
            </article>
          </div>
        </div>
      </section>

      <section class="auth-panel">
        <article class="auth-form-card">
          <div class="stack" style="gap: 10px;">
            <div class="micro-label muted" style="font-size: 10px;">Welcome Back</div>
            <div class="headline-lg">登录工作台</div>
            <div class="body-sm muted">用你的本地账号回到项目视图和阶段式工作台。</div>
          </div>

          <form class="form-grid" @submit.prevent="submit">
            <div class="field-group">
              <label class="field-label">用户名</label>
              <input v-model.trim="username" class="text-input" placeholder="studio_owner" />
            </div>

            <div class="field-group">
              <label class="field-label">密码</label>
              <input v-model="password" class="text-input" type="password" placeholder="请输入密码" />
            </div>

            <div v-if="error" class="danger-box body-sm">{{ error }}</div>

            <button class="btn btn-primary" :disabled="submitting" style="width: 100%;">
              {{ submitting ? '登录中…' : '进入工作台' }}
            </button>
          </form>
        </article>

        <div class="auth-panel-footnote">
          <div class="body-sm muted">还没有本地账号？</div>
          <router-link
            v-if="authState.bootstrap?.allow_registration"
            class="auth-inline-link"
            :to="{ name: 'register' }"
          >
            创建一个账号
          </router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/lib/api'
import { applyTokenResponse, authState } from '@/state/auth'

const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

const stages = [
  { index: '01', label: '书源与章节', copy: '上传原著后，先把章节结构理顺。' },
  { index: '02', label: '角色圣经', copy: '确认锚点图和语音，后面才会稳。' },
  { index: '03', label: '分集与分镜', copy: '围绕单集组织镜头，而不是一次铺满。' }
]

async function submit() {
  error.value = ''
  submitting.value = true

  try {
    const token = await api.login(username.value, password.value)
    await applyTokenResponse(token)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>
