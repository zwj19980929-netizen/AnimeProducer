"""Core - 核心业务逻辑模块

包含以下组件：
- pipeline: 视觉流水线（Audio-First Pipeline）
- duration_planner: 时长规划器
- prompt_translator: 提示词翻译器（自然语言 -> Danbooru 标签）
- character_registry: 角色资产注册系统
- audio_layers: 多轨音频系统（对白、BGM、音效、环境音）
- transitions: 智能转场系统
- editor: 视频编辑器
- script_parser: 剧本解析器
"""

from core.pipeline import (
    ShotPipeline,
    KeyframeGenerator,
    VideoGenerator,
    AudioGenerator,
    VLMScorer,
    ShotAligner,
    KeyframeRequest,
    KeyframeResult,
    VideoGenRequest,
    VideoGenResult,
    AudioGenRequest,
    AudioGenResult,
    VLMScoreRequest,
    VLMScoreResult,
    AlignmentRequest,
    AlignmentResult,
)

from core.duration_planner import (
    DurationPlanner,
    DurationPlan,
    get_audio_duration,
    duration_planner,
)

from core.prompt_translator import (
    PromptTranslator,
    StructuredPrompt,
    DanbooruTagMapper,
    prompt_translator,
)

from core.character_registry import (
    CharacterRegistry,
    CharacterAsset,
    create_character_from_description,
    character_registry,
)

from core.audio_layers import (
    AudioLayerType,
    AudioClip,
    AudioLayer,
    AudioMixRequest,
    AudioMixResult,
    SFXLibrary,
    BGMLibrary,
    AudioMixer,
    sfx_library,
    bgm_library,
    audio_mixer,
)

from core.transitions import (
    TransitionType,
    TransitionConfig,
    TransitionSelector,
    TransitionApplier,
    transition_selector,
    transition_applier,
)

__all__ = [
    # Pipeline
    "ShotPipeline",
    "KeyframeGenerator",
    "VideoGenerator",
    "AudioGenerator",
    "VLMScorer",
    "ShotAligner",
    "KeyframeRequest",
    "KeyframeResult",
    "VideoGenRequest",
    "VideoGenResult",
    "AudioGenRequest",
    "AudioGenResult",
    "VLMScoreRequest",
    "VLMScoreResult",
    "AlignmentRequest",
    "AlignmentResult",
    # Duration Planner
    "DurationPlanner",
    "DurationPlan",
    "get_audio_duration",
    "duration_planner",
    # Prompt Translator
    "PromptTranslator",
    "StructuredPrompt",
    "DanbooruTagMapper",
    "prompt_translator",
    # Character Registry
    "CharacterRegistry",
    "CharacterAsset",
    "create_character_from_description",
    "character_registry",
    # Audio Layers
    "AudioLayerType",
    "AudioClip",
    "AudioLayer",
    "AudioMixRequest",
    "AudioMixResult",
    "SFXLibrary",
    "BGMLibrary",
    "AudioMixer",
    "sfx_library",
    "bgm_library",
    "audio_mixer",
    # Transitions
    "TransitionType",
    "TransitionConfig",
    "TransitionSelector",
    "TransitionApplier",
    "transition_selector",
    "transition_applier",
]
