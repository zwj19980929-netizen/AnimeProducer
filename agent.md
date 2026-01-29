# 🛠️ AnimeMatrix 代码改进建议汇总

这份文档基于对当前代码库的深度分析，列出了阻碍项目运行、影响生成质量以及潜在的性能风险。

---

## 🚨 一、 严重功能缺陷 (Must Fix)
**如果不修复这些问题，核心功能无法跑通或完全失效。**

### 1. Google 绘图接口参数失效（角色一致性缺失）
* **位置**: `integrations/gen_client.py`
* **问题**: 在 `GoogleGenClient.generate_image` 方法中，虽然接收了 `reference_image_path` 参数，但在调用 API 时**完全忽略了它**。
* **后果**: 生成的每一张分镜图角色长相都会随机变化，项目的核心卖点“角色一致性”失效。
* **建议**: 
    * 查阅 Google Imagen 最新 API 文档，添加对 `reference_image` 或 `control_image` 的支持。
    * 或者，暂时禁用 Google Provider，强制使用支持 `ref_img` 的 `AliyunWanx` 或 `Replicate` 接口。

### 2. Python 依赖包版本冲突
* **位置**: `requirements.txt` vs `integrations/gen_client.py`
* **问题**: 代码中使用了 `from google import genai` (这是 Google GenAI SDK v1.0+ 的写法)，但 `requirements.txt` 中指定的是旧版 `google-generativeai`。
* **后果**: 用户安装依赖后，运行项目会直接报 `ImportError`。
* **建议**: 更新 `requirements.txt`，添加 `google-genai>=1.0.0`。

### 3. HTTP 接口同步阻塞
* **位置**: `api/routes/projects.py` (以及 assets/storyboard 相关接口)
* **问题**: 资产生成 (`build_assets`) 和视频合成 (`render_movie`) 是耗时极长的操作（可能几分钟），但它们在 API 路由中是**同步执行**的。
* **后果**: 请求会在 60秒后超时（Gateway Timeout），前端报错，而后端还在后台“僵尸”运行，导致状态不同步。
* **建议**:
    * API 接口只负责创建 `Job` ID 并返回。
    * 将实际生成逻辑完全放入 Celery Task (已在 `tasks/` 目录中有基础，但需确保 API 只是 `delay()` 调用)。
    * 前端通过轮询 `/jobs/{id}` 获取进度。

---

## ⚡ 二、 架构与稳定性隐患 (High Priority)
**这些问题会导致生产环境报错、死锁或资源泄露。**

### 1. 相对路径陷阱
* **位置**: `config.py`
* **问题**: `ASSETS_DIR = "./assets"` 使用了相对路径。
* **后果**: 当 Celery Worker、API Server 或测试脚本在不同目录下启动时，会找不到文件或在错误的位置创建文件夹。
* **建议**: 使用 `pathlib` 获取绝对路径：
    ```python
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent
    ASSETS_DIR = BASE_DIR / "assets"
    ```

### 2. MoviePy 文件资源未释放
* **位置**: `core/editor.py`
* **问题**: 直接使用 `VideoFileClip(path)` 而未显式关闭 (`close()`) 或使用上下文管理器。
* **后果**: 在 Windows 系统上，这会导致视频文件被 Python 进程锁定，后续步骤（如清理临时文件或重写文件）会报 `PermissionError`。
* **建议**: 使用 `with` 语句：
    ```python
    with VideoFileClip(path) as clip:
        # 处理逻辑
    ```

### 3. SQLite 并发锁死风险
* **位置**: `core/database.py`
* **问题**: 使用 SQLite 且 `check_same_thread=False`。
* **后果**: 当多个 Celery Worker 同时更新任务状态，且 API 正在读取数据时，极易发生 `Database is locked` 错误。
* **建议**: 如果用于演示，请降低 Celery 并发数 (`concurrency=1`)；如果是生产环境，请替换为 PostgreSQL/MySQL。

---

## 🧠 三、 业务逻辑优化 (Optimization)
**优化这些点可以提升生成视频的质量和连贯性。**

### 1. 剧本解析与其缺乏资产联动
* **位置**: `core/script_parser.py`
* **问题**: LLM 在将小说转为分镜 Prompt 时，没有读取 `AssetManager` 中已生成的角色设定。
* **后果**: LLM 可能会根据小说文本生成与角色设定冲突的描述（例如资产是黑发，Prompt 却写了金发），导致画面崩坏。
* **建议**: 在 `ScriptParser.parse()` 中注入 `Asset` 的文本描述到 System Prompt，强制 LLM 生成符合现有资产的视觉描述。

### 2. 清理逻辑过于激进
* **位置**: `core/director.py` -> `generate_storyboard`
* **问题**: 重新生成分镜时会直接清空数据库记录。
* **后果**: 如果磁盘上还有旧的渲染文件，这些文件会变成无法管理的“幽灵文件”，占用磁盘空间。
* **建议**: 在删除数据库记录前，先根据记录路径删除对应的磁盘文件。

---

## ✅ 下一步行动清单

1.  **[Hotfix]** 修改 `requirements.txt` 修复 Google SDK 依赖。
2.  **[Hotfix]** 修改 `config.py` 为绝对路径。
3.  **[Refactor]** 改造 `api/routes`，确保所有耗时操作都通过 `tasks.celery_app` 异步调用。
4.  **[Feature]** 修复 Google 绘图接口的 `reference_image` 逻辑，或切换默认绘图引擎。