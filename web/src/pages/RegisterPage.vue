<template>
  <div class="auth-shell">
    <div class="auth-card">
      <section class="auth-art">
        <div class="auth-grid" />
        <div class="auth-copy-block">
          <div class="brand-kicker">Warm Studio Console</div>
          <div class="headline-lg auth-hero-title">先建立账号，再把制作线拉起来。</div>
          <div class="body-lg auth-hero-copy">
            注册完成后会直接进入项目总览。后面的项目创建、阶段推进和最近操作，都会围绕同一套工作台展开。
          </div>
        </div>

        <div class="auth-stage-strip">
          <article v-for="item in notes" :key="item.label" class="auth-stage-item">
            <div class="micro-label" style="font-size: 10px; color: rgba(255,255,255,0.52);">{{ item.tag }}</div>
            <div class="headline-sm" style="color: #fff8f0; margin-top: 8px;">{{ item.label }}</div>
            <div class="body-sm" style="color: rgba(255,255,255,0.62); margin-top: 8px;">{{ item.copy }}</div>
          </article>
        </div>
      </section>

      <section class="auth-panel">
        <article class="auth-form-card">
          <div class="stack" style="gap: 10px;">
            <div class="micro-label muted" style="font-size: 10px;">Create Local Account</div>
            <div class="headline-lg">注册账号</div>
            <div class="body-sm muted">用户名支持字母、数字、下划线和连字符，长度 3 到 32。</div>
          </div>

          <form class="form-grid" @submit.prevent="submit">
            <div class="field-group">
              <label class="field-label">用户名</label>
              <input v-model.trim="username" class="text-input" placeholder="hanli_studio" />
            </div>

            <div class="field-group">
              <label class="field-label">密码</label>
              <input v-model="password" class="text-input" type="password" placeholder="至少 6 位" />
            </div>

            <div class="field-group">
              <label class="field-label">确认密码</label>
              <input v-model="confirmPassword" class="text-input" type="password" placeholder="再次输入密码" />
            </div>

            <div v-if="error" class="danger-box body-sm">{{ error }}</div>

            <button class="btn btn-primary" :disabled="submitting" style="width: 100%;">
              {{ submitting ? '创建中…' : '创建并进入工作台' }}
            </button>
          </form>
        </article>

        <div class="auth-panel-footnote">
          <div class="body-sm muted">已经有账号了？</div>
          <router-link class="auth-inline-link" :to="{ name: 'login' }">
            返回登录
          </router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/lib/api'
import { applyTokenResponse } from '@/state/auth'

const router = useRouter()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const submitting = ref(false)

const notes = [
  { tag: 'Flow', label: '项目总览', copy: '先看到所有项目和当前阶段，再决定下一步。' },
  { tag: 'Actions', label: '最近操作', copy: '长任务和失败恢复会统一收在操作抽屉里。' },
  { tag: 'Assets', label: '角色一致性', copy: '角色圣经会在生产前把锚点图和语音固定下来。' }
]

async function submit() {
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }

  error.value = ''
  submitting.value = true

  try {
    const token = await api.register(username.value, password.value)
    await applyTokenResponse(token)
    router.push('/')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '注册失败'
  } finally {
    submitting.value = false
  }
}
</script>
