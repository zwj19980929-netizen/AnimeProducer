<template>
  <div class="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
    <div class="container mx-auto px-6 py-8">
      <!-- Header -->
      <div class="mb-8 flex items-center justify-between">
        <div>
          <h1 class="text-4xl font-bold text-white mb-2">API 连接测试</h1>
          <p class="text-gray-400">测试所有 AI 服务提供商的 API 连接状态</p>
        </div>
        <n-button quaternary @click="$router.push('/')">
          <template #icon>
            <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 19l-7-7 7-7v4h8v6h-8v4z"/></svg></n-icon>
          </template>
          返回首页
        </n-button>
      </div>

      <!-- Actions -->
      <div class="mb-6 flex gap-4">
        <n-button type="primary" size="large" @click="loadConfig" :loading="loadingConfig">
          刷新配置
        </n-button>
        <n-button type="info" size="large" @click="testAll" :loading="testingAll">
          测试全部 API
        </n-button>
      </div>

      <!-- Summary Card -->
      <div v-if="testSummary" class="mb-6">
        <n-card title="测试结果摘要" :bordered="false" class="bg-gray-800/50">
          <div class="flex gap-8">
            <div class="text-center">
              <div class="text-3xl font-bold text-white">{{ testSummary.total }}</div>
              <div class="text-gray-400">总计</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-green-500">{{ testSummary.success }}</div>
              <div class="text-gray-400">成功</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-red-500">{{ testSummary.failed }}</div>
              <div class="text-gray-400">失败</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-gray-500">{{ testSummary.skipped }}</div>
              <div class="text-gray-400">跳过</div>
            </div>
          </div>
        </n-card>
      </div>

      <!-- Loading State -->
      <div v-if="loadingConfig && !config" class="py-20">
        <div class="flex flex-col items-center justify-center">
          <n-spin size="large" />
          <p class="mt-4 text-gray-400">正在加载配置...</p>
        </div>
      </div>

      <!-- Provider Categories -->
      <div v-else-if="config" class="space-y-6">
        <!-- LLM Providers -->
        <n-card title="LLM (大语言模型)" :bordered="false" class="bg-gray-800/50">
          <template #header-extra>
            <n-tag :type="config.providers.llm.current_provider ? 'success' : 'default'">
              当前: {{ config.providers.llm.current_provider }}
            </n-tag>
          </template>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <ProviderCard
              v-for="provider in ['google', 'openai', 'deepseek', 'doubao']"
              :key="provider"
              :name="provider"
              :config="config.providers.llm[provider as keyof typeof config.providers.llm]"
              :test-result="getTestResult('llm', provider)"
              :testing="testingProvider === `llm-${provider}`"
              :is-current="config.providers.llm.current_provider === provider"
              @test="testProvider('llm', provider)"
            />
          </div>
        </n-card>

        <!-- Image Providers -->
        <n-card title="图像生成" :bordered="false" class="bg-gray-800/50">
          <template #header-extra>
            <n-tag :type="config.providers.image.current_provider ? 'success' : 'default'">
              当前: {{ config.providers.image.current_provider }}
            </n-tag>
          </template>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <ProviderCard
              v-for="provider in ['google', 'aliyun', 'replicate']"
              :key="provider"
              :name="provider"
              :config="config.providers.image[provider as keyof typeof config.providers.image]"
              :test-result="getTestResult('image', provider)"
              :testing="testingProvider === `image-${provider}`"
              :is-current="config.providers.image.current_provider === provider"
              @test="testProvider('image', provider)"
            />
          </div>
        </n-card>

        <!-- Video Providers -->
        <n-card title="视频生成" :bordered="false" class="bg-gray-800/50">
          <template #header-extra>
            <n-tag :type="config.providers.video.current_provider ? 'success' : 'default'">
              当前: {{ config.providers.video.current_provider }}
            </n-tag>
          </template>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <ProviderCard
              v-for="provider in ['google', 'aliyun', 'replicate', 'volcengine']"
              :key="provider"
              :name="provider"
              :config="config.providers.video[provider as keyof typeof config.providers.video]"
              :test-result="getTestResult('video', provider)"
              :testing="testingProvider === `video-${provider}`"
              :is-current="config.providers.video.current_provider === provider"
              @test="testProvider('video', provider)"
            />
          </div>
        </n-card>

        <!-- TTS Providers -->
        <n-card title="TTS (语音合成)" :bordered="false" class="bg-gray-800/50">
          <template #header-extra>
            <n-tag :type="config.providers.tts.current_provider ? 'success' : 'default'">
              当前: {{ config.providers.tts.current_provider }}
            </n-tag>
          </template>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <ProviderCard
              v-for="provider in ['openai', 'doubao', 'aliyun', 'minimax', 'zhipu']"
              :key="provider"
              :name="provider"
              :config="config.providers.tts[provider as keyof typeof config.providers.tts]"
              :test-result="getTestResult('tts', provider)"
              :testing="testingProvider === `tts-${provider}`"
              :is-current="config.providers.tts.current_provider === provider"
              @test="testProvider('tts', provider)"
            />
          </div>
        </n-card>

        <!-- VLM -->
        <n-card title="VLM (视觉语言模型)" :bordered="false" class="bg-gray-800/50">
          <template #header-extra>
            <n-tag :type="config.providers.vlm.configured ? 'success' : 'warning'">
              {{ config.providers.vlm.configured ? '已配置' : '未配置' }}
            </n-tag>
          </template>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-4 bg-gray-700/50 rounded-lg">
              <div class="flex items-center justify-between mb-2">
                <span class="text-white font-medium">{{ config.providers.vlm.backend }}</span>
                <n-button size="small" @click="testProvider('vlm', config.providers.vlm.backend)" :loading="testingProvider === `vlm-${config.providers.vlm.backend}`">
                  测试
                </n-button>
              </div>
              <div class="text-sm text-gray-400">模型: {{ config.providers.vlm.model }}</div>
              <div v-if="getTestResult('vlm', config.providers.vlm.backend)" class="mt-2">
                <TestResultBadge :result="getTestResult('vlm', config.providers.vlm.backend)!" />
              </div>
            </div>
          </div>
        </n-card>
      </div>

      <!-- Error State -->
      <div v-if="error" class="py-10">
        <n-result status="error" title="加载失败" :description="error">
          <template #footer>
            <n-button type="primary" @click="loadConfig">重试</n-button>
          </template>
        </n-result>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NCard, NIcon, NSpin, NTag, NResult, useMessage } from 'naive-ui'
import { apiClient } from '@/api/client'
import type { ConfigStatusResponse, ProviderTestResult, ProviderConfig } from '@/types/api'
import ProviderCard from '@/components/ProviderCard.vue'
import TestResultBadge from '@/components/TestResultBadge.vue'

const message = useMessage()

const config = ref<ConfigStatusResponse | null>(null)
const loadingConfig = ref(false)
const error = ref<string | null>(null)

const testResults = ref<Map<string, ProviderTestResult>>(new Map())
const testingProvider = ref<string | null>(null)
const testingAll = ref(false)
const testSummary = ref<{ total: number; success: number; failed: number; skipped: number } | null>(null)

async function loadConfig() {
  loadingConfig.value = true
  error.value = null
  try {
    config.value = await apiClient.getApiConfig()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载配置失败'
    message.error(error.value)
  } finally {
    loadingConfig.value = false
  }
}

async function testProvider(category: string, provider: string) {
  const key = `${category}-${provider}`
  testingProvider.value = key
  try {
    const result = await apiClient.testProvider(category, provider)
    testResults.value.set(key, result)
    if (result.status === 'success') {
      message.success(`${provider} 连接成功`)
    } else if (result.status === 'failed') {
      message.error(`${provider} 连接失败: ${result.message}`)
    } else {
      message.warning(`${provider} 跳过: ${result.message}`)
    }
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : '测试失败'
    testResults.value.set(key, {
      provider,
      category,
      status: 'failed',
      message: errorMsg
    })
    message.error(`${provider} 测试失败: ${errorMsg}`)
  } finally {
    testingProvider.value = null
  }
}

async function testAll() {
  testingAll.value = true
  testResults.value.clear()
  testSummary.value = null
  try {
    const response = await apiClient.testAllProviders()
    for (const result of response.results) {
      testResults.value.set(`${result.category}-${result.provider}`, result)
    }
    testSummary.value = response.summary
    message.success(`测试完成: ${response.summary.success} 成功, ${response.summary.failed} 失败, ${response.summary.skipped} 跳过`)
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : '测试失败'
    message.error(`批量测试失败: ${errorMsg}`)
  } finally {
    testingAll.value = false
  }
}

function getTestResult(category: string, provider: string): ProviderTestResult | undefined {
  return testResults.value.get(`${category}-${provider}`)
}

onMounted(() => {
  loadConfig()
})
</script>
