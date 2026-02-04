# AnimeMatrix

**AnimeMatrix** 是一个基于 AI 的自动化流水线，旨在将小说文本直接转化为动漫风格的视频。

本项目采用**"资产先行 + 分镜并行"**的影视工业模式，解决生成视频中常见的"人物不一致"和"叙事不连贯"问题。

## 核心特性

*   **资产一致性 (Asset Consistency):** 通过预先生成角色"标准证件照"并结合 ControlNet/IP-Adapter 技术，确保全片角色形象统一。
*   **智能分镜 (Smart Storyboard):** 使用 LLM (Gemini 1.5 Pro) 将小说文本拆解为专业的 JSON 格式分镜表（包含运镜、视觉提示词、台词等）。
*   **VLM 评分系统:** 使用视觉语言模型对生成的关键帧进行多维度评分，自动选择最佳画面。
*   **自动化剪辑 (Auto Assembly):** 使用 MoviePy 自动对齐视频与 TTS 音频，支持智能循环与变速处理。
*   **异步任务处理:** 使用 Celery 实现镜头并行渲染，支持断点恢复。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AnimeMatrix Pipeline                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   [小说文本] → [Director] → [AssetManager] → [ScriptParser]             │
│                     │              │               │                     │
│                     ▼              ▼               ▼                     │
│              ┌──────────┐  ┌────────────┐  ┌─────────────┐              │
│              │  Project │  │ Characters │  │  Storyboard │              │
│              │  (状态机) │  │ (Reference) │  │   (Shots)   │              │
│              └────┬─────┘  └─────┬──────┘  └──────┬──────┘              │
│                   │              │                │                      │
│                   └──────────────┼────────────────┘                      │
│                                  ▼                                       │
│                    ┌─────────────────────────────┐                       │
│                    │     Celery Task Queue       │                       │
│                    │  (镜头并行 + 断点恢复)        │                       │
│                    └─────────────┬───────────────┘                       │
│                                  │                                       │
│        ┌─────────┬─────────┬─────┴─────┬─────────┬─────────┐            │
│        ▼         ▼         ▼           ▼         ▼         ▼            │
│   [Keyframe] [VLM Score] [I2V]     [TTS]    [Align]   [Compose]         │
│   (4选1)     (多维评分)   (图生视频)  (配音)   (对齐)    (合成)           │
│                                                                         │
│                              ▼                                          │
│                    ┌─────────────────┐                                  │
│                    │   最终动漫视频   │                                  │
│                    └─────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 快速开始 (Quick Start)

### 1. 环境准备

*   Python 3.10+
*   FFmpeg (用于视频处理)
*   Redis (用于 Celery 任务队列)

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境

复制配置文件模板并填入您的 API Key：

```bash
cp .env.example .env
```

在 `.env` 文件中配置以下关键项：
*   `GOOGLE_API_KEY`: 用于 Gemini 分镜生成和 VLM 评分
*   `OPENAI_API_KEY`: 用于 TTS 配音（可选）
*   `NANO_BANANA_API_KEY`: 用于图像生成（可选，有 Mock 实现）

### 4. 启动服务

**A. 启动 FastAPI 服务**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**B. 启动 Celery Worker（异步任务处理）**
```bash
celery -A tasks.celery_app worker --loglevel=info
win
celery -A tasks.celery_app worker --loglevel=info --pool=solo
```

**C. 访问 API 文档**
```
http://localhost:8000/docs
```

### 5. API 使用示例

**创建项目：**
```bash
curl -X POST "http://localhost:8000/api/v1/projects" \
     -H "Content-Type: application/json" \
     -d '{"name": "我的第一部动漫", "description": "测试项目"}'
```

**上传小说文本：**
```bash
curl -X POST "http://localhost:8000/api/v1/projects/{project_id}/novel" \
     -H "Content-Type: application/json" \
     -d '{"content": "第一章 初遇\n叶凡走在古老的街道上..."}'
```

**提取角色资产：**
```bash
curl -X POST "http://localhost:8000/api/v1/projects/{project_id}/characters/extract"
```

**生成分镜：**
```bash
curl -X POST "http://localhost:8000/api/v1/projects/{project_id}/storyboard"
```

**启动渲染任务：**
```bash
curl -X POST "http://localhost:8000/api/v1/projects/{project_id}/render"
```

**查询任务状态：**
```bash
curl "http://localhost:8000/api/v1/jobs/{job_id}"
```

## 项目结构

```text
/AnimeMatrix
├── /api                      # FastAPI 路由层
│   ├── deps.py               # 依赖注入
│   ├── schemas.py            # Pydantic 请求/响应模型
│   └── /routes
│       ├── projects.py       # 项目管理 API
│       ├── assets.py         # 角色资产 API
│       └── jobs.py           # 任务状态 API
├── /assets
│   ├── /projects             # 按项目分桶的资产
│   ├── /characters           # 全局角色参考图库
│   ├── /raw_materials        # 生成的原始视频片段
│   └── /output               # 最终成品
├── /core
│   ├── director.py           # 导演代理 (主控逻辑/编排器)
│   ├── script_parser.py      # 剧本解析器 (Novel -> Storyboard)
│   ├── asset_manager.py      # 资产管理器 (角色一致性 Bible)
│   ├── pipeline.py           # 视觉流水线 (Keyframe/VLM/I2V)
│   ├── editor.py             # 剪辑引擎 (MoviePy v2)
│   ├── models.py             # 数据模型 (SQLModel)
│   ├── database.py           # 数据库连接
│   └── errors.py             # 业务异常定义
├── /integrations
│   ├── llm_client.py         # LLM 客户端 (Google GenAI)
│   ├── gen_client.py         # 图像生成客户端
│   ├── vlm_client.py         # VLM 视觉评分客户端
│   ├── tts_client.py         # TTS 语音合成客户端
│   └── video_client.py       # I2V 视频生成客户端
├── /tasks
│   ├── celery_app.py         # Celery 配置
│   ├── jobs.py               # 项目级任务编排
│   └── shots.py              # 镜头级渲染任务
├── /docs
│   └── ARCHITECTURE.md       # 详细架构文档
├── /tests                    # 测试用例
├── /scripts                  # 工具脚本
├── main.py                   # FastAPI 入口
├── config.py                 # 配置管理
├── requirements.txt          # 依赖清单
└── .env.example              # 环境变量模板
```

## 状态机

### Project 状态流转
```
DRAFT → ASSETS_READY → STORYBOARD_READY → RENDERING → COMPOSITED → DONE
                                              ↓
                                           FAILED
```

### ShotRender 状态流转
```
PENDING → GENERATING_IMAGE → GENERATING_VIDEO → GENERATING_AUDIO → COMPOSITING → SUCCESS
                                                                        ↓
                                                                     FAILURE
```

## 更多文档

详细的架构设计与实现规范，请参阅 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 开发

### 代码检查
```bash
ruff check .
ruff format .
```

### 运行测试
```bash
pytest tests/
```

## License

MIT License
