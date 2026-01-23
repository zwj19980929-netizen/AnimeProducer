# AnimeMatrix

**AnimeMatrix** 是一个基于 AI 的自动化流水线，旨在将小说文本直接转化为动漫风格的视频。

本项目采用**“资产先行 + 分镜并行”**的影视工业模式，解决生成视频中常见的“人物不一致”和“叙事不连贯”问题。

## 核心特性

*   **资产一致性 (Asset Consistency):** 通过预先生成角色“标准证件照”并结合 ControlNet/IP-Adapter 技术，确保全片角色形象统一。
*   **智能分镜 (Smart Storyboard):** 使用 LLM (Gemini 1.5 Pro) 将小说文本拆解为专业的 JSON 格式分镜表（包含运镜、视觉提示词、台词等）。
*   **自动化剪辑 (Auto Assembly):** 使用 MoviePy 自动对齐视频与 TTS 音频，支持智能循环与变速处理。

## 快速开始 (Quick Start)

### 1. 环境准备

*   Python 3.10+
*   FFmpeg (用于视频处理)

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
*   `GOOGLE_API_KEY`: 用于 Gemini 分镜生成。
*   `NANO_BANANA_API_KEY`: 用于图像生成 (可选，测试模式下有 Mock 实现)。

### 4. 运行 Demo

我们提供了几个核心模块的测试脚本，帮助您快速验证环境：

**A. 测试小说转分镜 (Script Parser)**
```bash
python tests/test_parser.py
```
*功能：验证 LLM 是否能正确将文本解析为 JSON 分镜对象。*

**B. 测试角色一致性生成 (Consistency Test)**
```bash
python scripts/test_consistency.py
```
*功能：模拟使用参考图生成 5 张不同动作的图像（测试 ControlNet/Reference 流程）。*

**C. 测试视频合成流水线 (MoviePy Pipeline)**
```bash
python scripts/test_moviepy_pipeline.py
```
*功能：生成测试素材，演示视频片段与音频的自动对齐、循环和拼接。*

## 项目结构

```text
/AnimeMatrix
├── /assets
│   ├── /characters       # 角色参考图库
│   ├── /raw_materials    # 生成的原始视频片段
│   └── /output           # 最终成品
├── /core
│   ├── director.py       # 导演代理 (主控逻辑)
│   ├── script_parser.py  # 剧本解析器 (Novel -> Storyboard)
│   ├── asset_manager.py  # 资产管理器
│   ├── models.py         # 数据模型 (SQLModel)
│   └── editor.py         # 剪辑引擎 (MoviePy v2)
├── /integrations
│   ├── llm_client.py     # LLM 客户端 (Google GenAI)
│   └── gen_client.py     # 图像生成客户端
├── /docs                 # 详细架构文档
└── main.py               # API 入口
```

## 更多文档

详细的架构设计与实现规范，请参阅 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。
