# AnimeMatrix 核心优化与工程增强指令集 (agent.md)

## 1. 项目背景与技术上下文 (Context)
AnimeMatrix 是一个将小说转化为动漫视频的自动化流水线。系统采用“资产先行 + 分镜并行”的影视工业模式。目前已具备基础框架，但在长篇处理、动态演变和风格一致性上需要工程强化。

## 2. 当前工程缺陷与优化目标 (Target)

### 任务 A：长篇小说分章节架构 (Multi-Chapter Storage)
* **当前问题**：`Project` 模型仅通过单个 `script_content` 字段存储，无法承载长篇小说。
* **优化要求**：
    * 在 `core/models.py` 中新增 `Chapter` 模型，关联 `project_id`，包含章节序号、内容和状态。
    * 重构 `api/routes/projects.py` 支持按章节增量上传。

### 任务 B：角色动态形象演变 (Character Evolution)
* **当前问题**：`Character` 模型是静态的，无法表现角色随剧情（如升级换装、变身）带来的形象变化。
* **优化要求**：
    * 引入 `CharacterState` 模型存储同一角色不同阶段的视觉特征。
    * 在 `Shot` 分镜模型中增加状态映射，使流水线能自动选择对应的角色状态图。

### 任务 C：增量式角色发现 (Incremental Extraction)
* **当前问题**：目前仅读取小说前 10,000 个字符进行角色识别，无法发现中后期人物。
* **优化要求**：
    * 修改 `core/asset_manager.py`，建立按章节滚动提取新角色的机制。
    * 优化 Prompt，使其具备识别“形象演变”并触发状态更新的能力。

### 任务 D：动态音色自动化绑定 (Dynamic Voice Lookup)
* **当前问题**：渲染任务硬编码了 `voice_id="alloy"`，未与角色设定联动。
* **优化要求**：
    * 修改 `tasks/shots.py`，根据镜头中的角色实时查询 `Character` 表获取对应的 `voice_id`。

### 任务 E：智能画风锁定与题材适配 (Style Consistency & Genre Adaptation)
* **当前问题**：画风目前是手动设置或硬编码的，容易出现日系和古风混杂的情况。
* **优化要求**：
    * **题材自动判定**：在项目启动时，调用 LLM 分析小说开篇内容，自动判定题材（如“东方玄幻”、“赛博朋克”、“日系校园”）。
    * **画风描述生成**：根据题材生成一套详尽的“全局画风提示词约束”（如：`chinese ink painting style, wuxia aesthetic` 或 `classic 90s anime style`）。
    * **全局锁定**：将该描述存入 `Project.style_preset`。所有后续的图像生成（角色图、分镜图）必须强制强制注入该 Preset，严禁 LLM 在生成分镜 Prompt 时私自更改画风。

## 3. 技术约束与开发规范
* **代码完整性**：修改后的代码必须保持完整，严禁省略现有逻辑。
* **数据框架**：严格遵循 SQLModel 的 ORM 规范。
* **批判性态度**：若发现现有架构（如 `integrations/gen_client.py` 中的硬编码提示词）存在冲突，请直接重构。

## 4. 依赖参考
* **数据库定义**：`core/models.py`。
* **主控逻辑**：`core/director.py`。
* **图像集成**：`integrations/gen_client.py`。