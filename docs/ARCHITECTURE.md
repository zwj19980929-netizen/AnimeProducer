# 架构代号：AnimeMatrix (小说转动漫自动化流水线)

## 1. 核心设计哲学
为了解决“人物一致性”和“叙事连贯性”两大难题，本系统不采用线性的“从头生成到尾”模式，而是采用**“资产先行 + 分镜并行”**的影视工业模式。

系统被划分为四个核心层级：

*   **资产层 (The Asset Layer):** 确立人物立绘、世界观设定（这是保证一致性的锚点）。
*   **剧本层 (The Script Layer):** 将小说转化为结构化数据（分镜表）。
*   **生成层 (The Generation Layer):** 并行生成图像、视频、音频。
*   **合成层 (The Composition Layer):** 自动化剪辑与渲染。

## 2. 系统架构图 (System Architecture)

```mermaid
graph TD
    User[用户输入: 小说文本] --> Director

    subgraph "Core System (Python/FastAPI)"
        Director[导演代理 (Orchestrator)]

        subgraph "Phase 1: 资产构建"
            CharAgent[角色设计代理]
            StyleAgent[画风控制代理]
            AssetDB[(资产数据库/Vector DB)]
        end

        subgraph "Phase 2: 剧本拆解"
            StoryAgent[分镜师代理 (LLM)]
            Reviewer[人工/自动 审核]
        end

        subgraph "Phase 3: 视觉工程"
            PromptEng[提示词优化器]
            ImgGen[图像生成器 (Nano Banana/Flux)]
            VidGen[视频生成器 (I2V Model)]
            ConsistencyCheck[一致性校验器]
        end

        subgraph "Phase 4: 音频与后期"
            TTSAgent[配音代理]
            Editor[剪辑引擎 (MoviePy/FFmpeg)]
        end
    end

    Director --> CharAgent
    CharAgent --> AssetDB
    Director --> StoryAgent
    StoryAgent --> PromptEng
    PromptEng --> ImgGen
    AssetDB -.->|注入Reference图| ImgGen
    ImgGen --> VidGen
    VidGen --> Editor
    TTSAgent --> Editor
    Editor --> FinalVideo[最终成品]
```

## 3. 给 Jules 的详细实现规范 (Implementation Specs)
Jules，请严格按照以下模块进行开发，使用 Python 3.10+。

### 模块一：世界观与角色资产库 (The "Bible" Manager)
**目标：** 解决“脸盲”问题。

**功能：** 在处理正文前，先提取小说中的主要角色。

**流程：**

1.  LLM 提取角色特征（姓名、发色、瞳色、服装、性格关键词）。
2.  调用绘图模型生成“三视图”或“标准证件照”。

**关键点：** 保存这张“标准照”的 Seed 和 图像路径。后续所有生成任务，必须将这张图作为 Reference Image (ControlNet/IP-Adapter) 传入，严禁无参考生成。

**数据结构 (JSON)：**

```json
{
  "character_id": "char_001",
  "name": "叶凡",
  "prompt_base": "black hair, determined eyes, ancient chinese robe...",
  "reference_image_path": "./assets/chars/yefan_ref.png",
  "voice_id": "tts_male_hero_01"
}
```

### 模块二：智能分镜引擎 (Storyboard Engine)
**目标：** 将文本转化为机器可执行的指令。

**核心逻辑：** 不要把整章给 LLM，要按场景（Scene）切分。

**Prompt 策略：** 要求 LLM 输出标准 JSON 格式的分镜表。

**Jules 需实现的 Pydantic 模型：**

```python
class Shot(BaseModel):
    shot_id: int
    duration: float  # 预估时长，如 3.0s
    scene_description: str  # 给人类看的
    visual_prompt: str  # 给画图模型看的 (英文)
    camera_movement: str  # zoom_in, pan_right, static
    characters_in_shot: List[str]  # ["char_001"] -> 用于调用资产库
    dialogue: str  # 台词
    action_type: str  # "talking", "fighting", "walking"
```

### 模块三：一致性视觉生成流水线 (Consistency Pipeline)
这是最难的部分，Jules 需要编写复杂的逻辑。

**步骤 A：关键帧生成 (Keyframe Generation)**

*   **输入：** `visual_prompt` + `camera_movement`
*   **注入约束：** 如果 `characters_in_shot` 非空，读取 `AssetDB` 中的 `reference_image`，使用类似 Reactor (换脸) 或 IP-Adapter (风格迁移) 的技术，确保生成的 Keyframe 脸是对应的角色。
*   **Fallback 机制：** 生成 4 张，使用 VLM (如 Gemini Vision/GPT-4o) 自动打分，选最符合描述的一张。

**步骤 B：图生视频 (Image-to-Video)**

*   **输入：** 优选的 Keyframe + `camera_movement` 指令。
*   **工具：** 调用视频生成 API。
*   **技巧：** 不仅生成视频，还要生成“反向”视频（如果支持），或者简单的 Loop 处理，防止视频结束时突然定格。

### 模块四：音频与自动剪辑 (Audio & Assembly)
**目标：** 把碎片拼成片子。

**TTS 对齐：**

1.  根据 `dialogue` 生成音频。
2.  **获取音频时长：** 如果音频长 5 秒，但视频只有 3 秒，必须 **自动将视频慢放（Slow-motion）或循环** 以匹配音频长度。这是自动化的关键细节。

**合成 (MoviePy)：**

1.  加载所有 `VideoClips`。
2.  加载所有 `AudioClips`。
3.  执行 `concatenate_videoclips`。
4.  添加转场（Crossfade）。
5.  添加字幕（利用 TTS 生成的 SRT 文件）。

## 4. 推荐技术栈 (Tech Stack for Jules)
*   **核心框架:** LangChain (用于编排 LLM 流程) + FastAPI (作为后端服务)。
*   **数据库:** SQLite (存分镜元数据) + FileSystem (存图片/视频)。
*   **LLM:** Gemini 1.5 Pro (长文本理解强，用于分镜) + Gemini 2.5 Flash (便宜，用于校验)。
*   **图像/视频:** 你的 Nano Banana 接口 (假设兼容 OpenAI/Diffusers 格式)。
*   **视频处理:** MoviePy (必选，Python 视频编辑库)。
*   **任务队列:** Celery + Redis (必须异步，视频生成很慢，不能阻塞主线程)。

## 5. 项目文件结构 (Project Structure)
Jules，请按照这个结构初始化项目：

```text
/AnimeMatrix
├── /assets
│   ├── /characters       # 存放角色参考图 (Reference Images)
│   ├── /raw_materials    # 生成的原始视频片段
│   └── /output           # 最终合成的成品
├── /core
│   ├── director.py       # 主控逻辑
│   ├── script_parser.py  # 小说转分镜逻辑
│   ├── asset_manager.py  # 角色一致性管理
│   └── editor.py         # MoviePy 剪辑逻辑
├── /integrations
│   ├── llm_client.py     # 调用大模型
│   └── gen_client.py     # 调用 Nano Banana
├── main.py               # 入口
└── requirements.txt
```
