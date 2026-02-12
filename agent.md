# 🚀 Phase 2 升级方案：构建智能导演 Agent (Smart Director Upgrade)

## 1. 核心愿景 (Core Vision)

**从“自动化流水线”进化为“闭环智能系统”。**

* **当前状态 (Phase 1 - Automation):**
    * 流程：剧本 -> 视频 -> 音频 -> 输出。
    * 特点：**线性执行**。系统“盲目”地完成任务，无法感知生成质量。如果 AI 画崩了（如多指、穿模），错误会被保留。
    * 局限：缺乏对上一个镜头的“记忆”，导致同一场景下光影、位置不连贯。

* **目标状态 (Phase 2 - Intelligence):**
    * 流程：剧本 -> 视频 -> **AI 观看并评分** -> **(不合格? 重画) / (合格? 继续)** -> 音频 -> 输出。
    * 特点：**闭环反馈** + **上下文记忆**。系统拥有“自我反思”能力和“场景连续性”控制。

---

## 2. 模块一：AI 影评人 (The AI Critic Loop)

**目标：** 引入一个 VLM (Vision Language Model) 扮演“质检员”，在合成音频前拦截低质量画面。

### 2.1 工作流程 (Workflow)

1.  **初次生成：** `Pipeline` 生成视频文件 `v1.mp4`。
2.  **VLM 介入：** 调用视觉大模型（Gemini 1.5 Pro / GPT-4o）观看该视频。
3.  **结构化评分：** 要求 VLM 返回 JSON 格式评价：
    * `score` (0-10分)
    * `issues` (问题列表：如 "hand distortion", "flickering")
    * `suggestion` (修正建议：如 "hide hands", "reduce motion")
4.  **决策逻辑：**
    * **Score >= 8:** 通过，进入 Lip-Sync 环节。
    * **Score < 8:** 驳回。将 `suggestion` 添加到原来的 Prompt 中，触发 **Re-roll (重绘)**。
    * *熔断机制：* 最多重试 3 次，防止死循环。

### 2.2 核心代码设计 (Core Design)

建议新建文件 `core/critic.py`:

```python
import json
from typing import Dict, Any
# from integrations.vlm_client import vlm_client  # 假设你已有 VLM 客户端

class VideoCritic:
    def evaluate_shot(self, video_path: str, original_prompt: str) -> Dict[str, Any]:
        """
        让 VLM 扮演导演，逐帧审查视频质量
        """
        system_prompt = """
        You are a top-tier anime director. Critical Review Mode.
        Analyze the video for specific visual glitches:
        1. Anatomy errors (extra fingers, twisted limbs).
        2. Temporal flickering (inconsistent background).
        3. Prompt adherence (does it match the script?).
        
        Return ONLY a JSON object:
        {
            "score": <int 0-10>,
            "has_glitches": <bool>,
            "feedback": "<short, actionable fix for the prompt>"
        }
        """
        
        # 调用 VLM (Gemini 1.5 Pro 视频理解能力极强)
        # response = vlm_client.analyze_video(video_path, prompt=system_prompt)
        
        # 模拟返回
        # return json.loads(response)
        pass

# 实例化单例
video_critic = VideoCritic()
```

### 2.3 集成逻辑 (tasks/shots.py)
在 render_shot 函数中修改：
```python
# ... (视频生成后，LipSync 前) ...
    
    current_video = artifact.video_path
    retry_count = 0
    max_retries = 2
    
    while retry_count <= max_retries:
        # 1. 评分
        review = video_critic.evaluate_shot(current_video, shot.visual_prompt)
        logger.info(f"Critic Score: {review['score']} - {review['feedback']}")
        
        if review['score'] >= 8:
            break # 质量达标
            
        # 2. 质量不达标，准备重绘
        retry_count += 1
        logger.warning(f"Quality check failed. Retrying ({retry_count}/{max_retries})...")
        
        # 3. 动态修正 Prompt
        # new_prompt = f"{shot.visual_prompt}, {review['feedback']}"
        # artifact = pipeline.process_shot(..., visual_prompt=new_prompt)
        # current_video = artifact.video_path
```

## 3. 模块二：空间连贯性引擎 (Context-Aware Consistency)
目标： 解决“角色瞬移”和“光影突变”问题，让连续的镜头看起来像是在同一个物理空间拍摄的。

3.1 技术原理
利用 Image-to-Video (I2V) 的特性，将 上一镜头 (Shot N-1) 的最后一帧，作为 当前镜头 (Shot N) 的首帧参考 (First Frame Condition) 或 风格参考 (Style Reference)。

3.2 实现策略
场景分组 (Scene Grouping):

在解析剧本时，将属于同一场戏的镜头标记为同一 scene_id。

上下文传递 (Context Passing):

渲染 Shot N 时，查询数据库寻找 scene_id 相同且 order == N-1 的镜头。

如果 Shot N-1 状态为 COMPLETED，读取其视频文件的最后一帧。

条件注入 (Injection):

调用视频生成 API 时，传入这张截图。

关键点： 设置 image_strength (或类似参数) 为 0.3 - 0.4。

解释： 我们不需要 Shot N 的第一帧跟 Shot N-1 的最后一帧完全重合（那样就变成定格动画了），我们需要它继承构图、色调和站位。

### 3.3 代码修改建议 (tasks/shots.py)
```Python
def get_previous_shot_last_frame(current_shot: Shot, session: Session) -> Optional[str]:
    """获取同一场景下，前一个镜头的最后一帧路径"""
    prev_shot = session.query(Shot).filter(
        Shot.project_id == current_shot.project_id,
        Shot.scene_id == current_shot.scene_id, # 需确保数据库有此字段
        Shot.order == current_shot.order - 1
    ).first()
    
    if prev_shot and prev_shot.video_path:
        # 使用 ffmpeg 提取最后一帧
        # frame_path = extract_frame(prev_shot.video_path, time=-1)
        # return frame_path
        pass
    return None

# 在 render_shot 中使用:
# context_image = get_previous_shot_last_frame(shot, session)
# artifact = pipeline.process_shot(..., first_frame_image=context_image, image_strength=0.3)
```
## 4. 实施路线图 (Implementation Roadmap)
为了保证系统稳定性，建议按以下阶段开发：

🟢 阶段 1: 基础设施 (Week 1)
[ ] 编写 core/critic.py，打通 Gemini/GPT-4o 的视频分析接口。

[ ] 编写 tests/test_critic.py，手动上传几个好/坏视频，测试 AI 评分的准确性。

[ ] 在 Shot 表中添加 scene_id 字段（如果还没有），优化 ScriptParser 以识别场景边界（通常通过 "EXT." / "INT." 关键词）。

🟡 阶段 2: 影评人上线 (Week 2)
[ ] 修改 tasks/shots.py，接入 VideoCritic。

[ ] 初期策略： 只记录评分日志 (Log Mode)，不触发重绘。观察 50 个镜头的评分分布，校准 Prompt。

[ ] 后期策略： 开启自动重绘 (Active Mode)。

🔵 阶段 3: 连贯性增强 (Week 3)
[ ] 实现 extract_last_frame 工具函数。

[ ] 修改 render_shot 逻辑，支持读取上一镜头缓存。

[ ] 注意： 这可能会降低并行渲染的速度（因为 Shot 2 必须等 Shot 1 渲染完）。建议实现**“混合调度”**：不同场景并行，同一场景串行。

## 5. 总结 (Summary)
通过引入 Critic Loop，你的 Agent 学会了**“审美”； 通过引入 Context Consistency，你的 Agent 学会了“场面调度”**。

这两步走完，你的 AnimeMatrix 将不再是一个简单的生成脚本，而是一个具备初级导演思维的 AI 创作者。