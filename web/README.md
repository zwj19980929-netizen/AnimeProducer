# AnimeMatrix Web 前端

AnimeMatrix AI 动画制作平台的现代化 Vue 3 + TypeScript 前端应用。

## 技术栈

- **框架**: Vue 3 (Composition API + `<script setup>` 语法)
- **语言**: TypeScript (严格模式)
- **UI 库**: Naive UI
- **样式**: TailwindCSS
- **状态管理**: Pinia
- **HTTP 客户端**: Axios
- **构建工具**: Vite

## 功能特性

- 🎨 现代化 SaaS 风格 UI，深色主题
- 📦 卡片式布局，清晰的视觉层次
- 🔄 实时项目状态轮询
- 🎬 媒体优先设计，强调视频/图片预览
- ⚡ 乐观 UI 更新
- 🚨 全面的错误处理和用户友好的通知
- 📱 响应式设计
- 🎯 类型安全的 API 客户端，精确匹配后端 Pydantic 模型

## 项目结构

```
web/
├── src/
│   ├── api/
│   │   └── client.ts          # Axios API 客户端
│   ├── components/
│   │   ├── CharacterList.vue       # 角色列表
│   │   ├── CreateProjectModal.vue  # 创建项目模态框
│   │   ├── JobStatusBadge.vue      # 任务状态徽章
│   │   ├── ProjectCard.vue         # 项目卡片
│   │   ├── ProjectOverview.vue     # 项目概览
│   │   ├── ProjectStatusBadge.vue  # 项目状态徽章
│   │   ├── RenderList.vue          # 渲染列表
│   │   ├── ShotList.vue            # 分镜列表
│   │   └── VideoPlayer.vue         # 视频播放器
│   ├── composables/
│   │   ├── useJob.ts          # 任务管理 Composable
│   │   └── useProject.ts      # 项目管理 Composable
│   ├── stores/
│   │   └── project.ts         # Pinia 项目状态管理
│   ├── types/
│   │   └── api.ts             # TypeScript 接口（匹配后端）
│   ├── views/
│   │   ├── ProjectDetail.vue  # 项目详情页
│   │   └── ProjectList.vue    # 项目列表页
│   ├── App.vue
│   └── main.ts
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 安装

```bash
cd web
npm install
```

## 开发

```bash
npm run dev
```

开发服务器将在 `http://localhost:3000` 启动，API 请求会代理到 `http://localhost:8000`。

## 构建

```bash
npm run build
```

## 核心功能

### 类型安全
所有 API 类型都严格匹配后端 Pydantic 模型：
- Project、Character、Shot、Job、ShotRender 类型
- ProjectStatus、JobStatus、JobType 等枚举
- 请求/响应接口

### Composables
可复用逻辑提取到 Composables：
- `useProject`: 项目 CRUD 操作、管道管理
- `useJob`: 任务监控和轮询支持

### 实时更新
- 自动轮询活跃任务和渲染中的项目
- 运行中任务的进度条
- 带颜色编码的状态徽章

### 错误处理
- 所有 API 错误的 Toast 通知
- 用户友好的错误消息
- 缺失数据的优雅降级

### UI/UX
- 针对媒体内容优化的深色主题
- 带微妙阴影的卡片式布局
- 数据加载时的骨架屏
- 响应式网格布局
- 强调媒体预览

## API 集成

前端通过 `/api/v1` 连接后端 API，包含以下端点：

- **Projects（项目）**: CRUD、状态更新、管道操作
- **Characters（角色）**: 列表、创建、更新、删除
- **Shots（分镜）**: 列出故事板分镜
- **Jobs（任务）**: 监控异步任务、取消任务
- **Shot Renders（分镜渲染）**: 查看渲染进度和输出

## 环境配置

在 `vite.config.ts` 中配置 API 基础 URL：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

## 使用流程

### 1. 创建项目
- 点击"创建新项目"按钮
- 填写项目名称、描述、脚本内容和风格预设
- 提交创建

### 2. 构建资产
- 在项目详情页点击"构建资产"
- 系统从脚本中提取角色
- 通过 AI 生成参考图
- 状态变为"资产就绪"

### 3. 生成故事板
- 点击"生成故事板"
- LLM 分析脚本并创建分镜
- 在"故事板"标签页查看分镜
- 状态变为"故事板就绪"

### 4. 启动制作管道
- 点击"启动制作管道"
- 系统并行渲染所有分镜
- 在"渲染"标签页监控进度
- 状态依次变化：渲染中 → 已合成 → 完成

### 5. 查看输出
- 完成后出现"输出"标签页
- 观看最终视频

## 开发指南

### 添加新功能

1. **新 API 端点**：
   - 在 `types/api.ts` 中添加类型
   - 在 `api/client.ts` 中添加方法

2. **新组件**：
   - 在 `components/` 中创建
   - 使用 `<script setup>` 语法
   - 从 `@/types/api` 导入类型

3. **新页面**：
   - 在 `views/` 中创建
   - 在 `main.ts` 中添加路由

### 代码风格

- 使用 Composition API + `<script setup>`
- 严格 TypeScript（禁止 `any`）
- Tailwind 样式
- Naive UI 组件
- 自文档化代码（最少注释）

## 故障排除

### API 连接失败
- 确保后端在 8000 端口运行
- 检查 `vite.config.ts` 代理设置

### 图片加载失败
- 检查后端 `output/` 目录权限
- 验证数据库中的图片路径

### 渲染缓慢
- 减少并行渲染数量
- 检查后端日志中的提供商问题

## 技术亮点

- ✅ 完整的 TypeScript 类型系统
- ✅ 模块化架构（Composables + Stores）
- ✅ 实时轮询和进度更新
- ✅ 全面的错误处理
- ✅ 响应式设计
- ✅ 媒体优先布局
- ✅ 深色主题优化

## 文档

- `README.md` - 本文件
- `IMPLEMENTATION.md` - 详细实现文档
- `QUICKSTART.md` - 快速开始指南

## 许可证

与 AnimeMatrix 项目保持一致
