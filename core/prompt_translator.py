"""Prompt Translator - 提示词翻译器

将 LLM 生成的自然语言描述转换为 Danbooru 风格的标签，
以提高动漫图像生成模型（SD/SDXL）的生成质量。
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StructuredPrompt:
    """结构化提示词"""
    positive: str                                    # 正面提示词
    negative: str                                    # 负面提示词
    tags: List[str] = field(default_factory=list)   # 提取的标签
    quality_tags: List[str] = field(default_factory=list)   # 质量标签
    style_tags: List[str] = field(default_factory=list)     # 风格标签

    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            "positive": self.positive,
            "negative": self.negative
        }


class DanbooruTagMapper:
    """Danbooru 标签映射器"""

    # 自然语言到 Danbooru 标签的映射
    TAG_MAP: Dict[str, str] = {
        # ========== 人物数量 ==========
        "a boy": "1boy",
        "a girl": "1girl",
        "a man": "1boy",
        "a woman": "1girl",
        "a young man": "1boy",
        "a young woman": "1girl",
        "two boys": "2boys",
        "two girls": "2girls",
        "two men": "2boys",
        "two women": "2girls",
        "three boys": "3boys",
        "three girls": "3girls",
        "group of": "multiple_persons",
        "crowd": "crowd",
        "solo": "solo",

        # ========== 发色 ==========
        "blue hair": "blue_hair",
        "red hair": "red_hair",
        "black hair": "black_hair",
        "blonde hair": "blonde_hair",
        "blonde": "blonde_hair",
        "white hair": "white_hair",
        "silver hair": "silver_hair",
        "pink hair": "pink_hair",
        "purple hair": "purple_hair",
        "green hair": "green_hair",
        "orange hair": "orange_hair",
        "brown hair": "brown_hair",
        "gray hair": "grey_hair",
        "multicolored hair": "multicolored_hair",
        "gradient hair": "gradient_hair",
        "long hair": "long_hair",
        "short hair": "short_hair",
        "medium hair": "medium_hair",
        "ponytail": "ponytail",
        "twintails": "twintails",
        "twin tails": "twintails",
        "braid": "braid",
        "braided hair": "braid",
        "bun": "hair_bun",
        "messy hair": "messy_hair",
        "straight hair": "straight_hair",
        "wavy hair": "wavy_hair",
        "curly hair": "curly_hair",

        # ========== 眼睛 ==========
        "blue eyes": "blue_eyes",
        "red eyes": "red_eyes",
        "green eyes": "green_eyes",
        "brown eyes": "brown_eyes",
        "golden eyes": "yellow_eyes",
        "yellow eyes": "yellow_eyes",
        "purple eyes": "purple_eyes",
        "pink eyes": "pink_eyes",
        "heterochromia": "heterochromia",

        # ========== 表情 ==========
        "smiling": "smile",
        "smile": "smile",
        "happy": "smile, happy",
        "crying": "crying",
        "tears": "tears",
        "angry": "angry",
        "sad": "sad",
        "surprised": "surprised",
        "shocked": "shocked",
        "blushing": "blush",
        "embarrassed": "blush, embarrassed",
        "serious": "serious",
        "calm": "calm",
        "determined": "determined",
        "scared": "scared",
        "nervous": "nervous",
        "laughing": "laughing",

        # ========== 动作/姿势 ==========
        "sitting": "sitting",
        "standing": "standing",
        "running": "running",
        "walking": "walking",
        "lying": "lying",
        "lying down": "lying",
        "sleeping": "sleeping",
        "jumping": "jumping",
        "flying": "flying",
        "fighting": "fighting",
        "kicking": "kicking",
        "punching": "punching",
        "holding": "holding",
        "hugging": "hug",
        "kissing": "kiss",
        "looking at viewer": "looking_at_viewer",
        "looking away": "looking_away",
        "looking back": "looking_back",
        "looking up": "looking_up",
        "looking down": "looking_down",
        "from behind": "from_behind",
        "from side": "from_side",
        "from above": "from_above",
        "from below": "from_below",
        "back view": "from_behind",
        "side view": "from_side",
        "arms crossed": "crossed_arms",
        "hands in pockets": "hands_in_pockets",
        "hand on hip": "hand_on_hip",
        "pointing": "pointing",
        "waving": "waving",

        # ========== 服装 ==========
        "school uniform": "school_uniform",
        "sailor uniform": "sailor_uniform, serafuku",
        "suit": "suit",
        "dress": "dress",
        "kimono": "kimono",
        "yukata": "yukata",
        "armor": "armor",
        "casual clothes": "casual",
        "hoodie": "hoodie",
        "jacket": "jacket",
        "coat": "coat",
        "shirt": "shirt",
        "t-shirt": "t-shirt",
        "sweater": "sweater",
        "skirt": "skirt",
        "pants": "pants",
        "jeans": "jeans",
        "shorts": "shorts",
        "swimsuit": "swimsuit",
        "bikini": "bikini",
        "maid outfit": "maid",
        "military uniform": "military_uniform",
        "cape": "cape",
        "cloak": "cloak",
        "hat": "hat",
        "glasses": "glasses",
        "sunglasses": "sunglasses",

        # ========== 场景/背景 ==========
        "indoor": "indoors",
        "indoors": "indoors",
        "outdoor": "outdoors",
        "outdoors": "outdoors",
        "school": "school",
        "classroom": "classroom",
        "library": "library",
        "bedroom": "bedroom",
        "living room": "living_room",
        "kitchen": "kitchen",
        "bathroom": "bathroom",
        "office": "office",
        "cafe": "cafe",
        "restaurant": "restaurant",
        "street": "street",
        "city": "city, cityscape",
        "town": "town",
        "village": "village",
        "forest": "forest",
        "mountain": "mountain",
        "beach": "beach",
        "ocean": "ocean",
        "sea": "ocean",
        "river": "river",
        "lake": "lake",
        "park": "park",
        "garden": "garden",
        "rooftop": "rooftop",
        "balcony": "balcony",
        "bridge": "bridge",
        "train station": "train_station",
        "airport": "airport",
        "hospital": "hospital",
        "temple": "temple",
        "shrine": "shrine",
        "castle": "castle",
        "ruins": "ruins",
        "cave": "cave",
        "space": "space",
        "sky": "sky",

        # ========== 天气/时间 ==========
        "day": "day",
        "daytime": "day",
        "night": "night",
        "nighttime": "night",
        "evening": "evening",
        "sunset": "sunset",
        "sunrise": "sunrise",
        "dawn": "dawn",
        "dusk": "dusk",
        "morning": "morning",
        "afternoon": "afternoon",
        "rain": "rain",
        "raining": "rain",
        "rainy": "rain",
        "snow": "snow",
        "snowing": "snow",
        "snowy": "snow",
        "cloudy": "cloudy",
        "sunny": "sunny",
        "fog": "fog",
        "foggy": "fog",
        "storm": "storm",
        "lightning": "lightning",
        "thunder": "lightning",
        "wind": "wind",
        "windy": "wind",

        # ========== 光线/氛围 ==========
        "bright": "bright",
        "dark": "dark",
        "dramatic lighting": "dramatic_lighting",
        "soft lighting": "soft_lighting",
        "backlighting": "backlighting",
        "rim lighting": "rim_lighting",
        "sunlight": "sunlight",
        "moonlight": "moonlight",
        "candlelight": "candlelight",
        "neon": "neon_lights",
        "lens flare": "lens_flare",
        "bokeh": "bokeh",
        "depth of field": "depth_of_field",

        # ========== 构图 ==========
        "close-up": "close-up",
        "close up": "close-up",
        "portrait": "portrait",
        "upper body": "upper_body",
        "lower body": "lower_body",
        "full body": "full_body",
        "cowboy shot": "cowboy_shot",
        "wide shot": "wide_shot",
        "panorama": "panorama",
        "dutch angle": "dutch_angle",
        "bird's eye view": "bird's-eye_view",
        "worm's eye view": "worm's-eye_view",
        "pov": "pov",
        "first person": "pov",

        # ========== 物品 ==========
        "sword": "sword",
        "katana": "katana",
        "gun": "gun",
        "pistol": "pistol",
        "rifle": "rifle",
        "bow": "bow_(weapon)",
        "arrow": "arrow",
        "staff": "staff",
        "wand": "wand",
        "book": "book",
        "phone": "phone",
        "smartphone": "smartphone",
        "laptop": "laptop",
        "computer": "computer",
        "umbrella": "umbrella",
        "bag": "bag",
        "backpack": "backpack",
        "flower": "flower",
        "rose": "rose",
        "cherry blossom": "cherry_blossoms",
        "sakura": "cherry_blossoms",
        "food": "food",
        "drink": "drink",
        "cup": "cup",
        "tea": "tea",
        "coffee": "coffee",
        "cake": "cake",
        "car": "car",
        "motorcycle": "motorcycle",
        "bicycle": "bicycle",
        "train": "train",
        "airplane": "airplane",
        "ship": "ship",
        "boat": "boat",
    }

    # 中文到英文的映射（常用词）
    CN_TO_EN_MAP: Dict[str, str] = {
        # 人物
        "男孩": "a boy",
        "女孩": "a girl",
        "男人": "a man",
        "女人": "a woman",
        "少年": "a young man",
        "少女": "a young woman",

        # 发色
        "蓝发": "blue hair",
        "红发": "red hair",
        "黑发": "black hair",
        "金发": "blonde hair",
        "白发": "white hair",
        "银发": "silver hair",
        "粉发": "pink hair",
        "紫发": "purple hair",
        "绿发": "green hair",
        "棕发": "brown hair",
        "长发": "long hair",
        "短发": "short hair",
        "马尾": "ponytail",
        "双马尾": "twintails",

        # 眼睛
        "蓝眼": "blue eyes",
        "红眼": "red eyes",
        "绿眼": "green eyes",
        "金眼": "golden eyes",

        # 表情
        "微笑": "smiling",
        "哭泣": "crying",
        "愤怒": "angry",
        "悲伤": "sad",
        "惊讶": "surprised",
        "害羞": "blushing",
        "认真": "serious",

        # 动作
        "坐着": "sitting",
        "站着": "standing",
        "跑步": "running",
        "走路": "walking",
        "躺着": "lying",
        "睡觉": "sleeping",
        "跳跃": "jumping",
        "战斗": "fighting",

        # 场景
        "室内": "indoor",
        "室外": "outdoor",
        "学校": "school",
        "教室": "classroom",
        "卧室": "bedroom",
        "街道": "street",
        "城市": "city",
        "森林": "forest",
        "海滩": "beach",
        "大海": "ocean",
        "天空": "sky",

        # 天气/时间
        "白天": "day",
        "夜晚": "night",
        "黄昏": "sunset",
        "黎明": "sunrise",
        "下雨": "rain",
        "下雪": "snow",
        "阴天": "cloudy",
        "晴天": "sunny",
    }

    def __init__(self):
        # 预编译正则表达式以提高性能
        self._patterns: List[Tuple[re.Pattern, str]] = []
        for phrase, tag in self.TAG_MAP.items():
            # 使用单词边界匹配
            pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            self._patterns.append((pattern, tag))

    def translate_chinese(self, text: str) -> str:
        """将中文关键词转换为英文"""
        result = text
        for cn, en in self.CN_TO_EN_MAP.items():
            result = result.replace(cn, en)
        return result

    def map_to_tags(self, text: str) -> List[str]:
        """将自然语言文本映射为 Danbooru 标签"""
        # 先转换中文
        text = self.translate_chinese(text)

        tags: List[str] = []
        text_lower = text.lower()

        for pattern, tag in self._patterns:
            if pattern.search(text_lower):
                # 处理包含逗号的多标签
                for t in tag.split(", "):
                    if t not in tags:
                        tags.append(t)

        return tags


class PromptTranslator:
    """提示词翻译器"""

    # 默认质量标签
    DEFAULT_QUALITY_TAGS: List[str] = [
        "masterpiece",
        "best quality",
        "high resolution",
        "highly detailed",
        "sharp focus",
        "anime style",
        "anime coloring",
    ]

    # 默认负面提示词
    DEFAULT_NEGATIVE_TAGS: List[str] = [
        "low quality",
        "worst quality",
        "bad anatomy",
        "bad hands",
        "missing fingers",
        "extra digits",
        "fewer digits",
        "blurry",
        "watermark",
        "signature",
        "text",
        "logo",
        "3d",
        "realistic",
        "photo",
        "photorealistic",
        "deformed",
        "disfigured",
        "mutation",
        "ugly",
        "duplicate",
        "morbid",
        "mutilated",
        "poorly drawn face",
        "poorly drawn hands",
        "extra limbs",
        "cloned face",
        "gross proportions",
        "malformed limbs",
        "missing arms",
        "missing legs",
        "extra arms",
        "extra legs",
        "fused fingers",
        "too many fingers",
        "long neck",
        "username",
        "artist name",
        "bad proportions",
        "cropped",
        "jpeg artifacts",
        "out of frame",
    ]

    # 风格预设
    STYLE_PRESETS: Dict[str, List[str]] = {
        "ghibli": [
            "studio ghibli style",
            "ghibli",
            "soft colors",
            "watercolor style",
            "hand drawn",
            "warm lighting",
        ],
        "makoto_shinkai": [
            "makoto shinkai style",
            "your name style",
            "detailed sky",
            "lens flare",
            "beautiful scenery",
            "vibrant colors",
            "detailed clouds",
        ],
        "kyoani": [
            "kyoto animation style",
            "kyoani",
            "moe",
            "soft lighting",
            "detailed eyes",
            "clean lines",
            "pastel colors",
        ],
        "ufotable": [
            "ufotable style",
            "dynamic lighting",
            "detailed effects",
            "action scene",
            "dramatic",
            "high contrast",
        ],
        "mappa": [
            "mappa style",
            "detailed shading",
            "dynamic poses",
            "cinematic",
            "dark atmosphere",
        ],
        "trigger": [
            "trigger style",
            "bold colors",
            "dynamic angles",
            "exaggerated",
            "energetic",
            "stylized",
        ],
        "wit_studio": [
            "wit studio style",
            "detailed backgrounds",
            "dynamic action",
            "cinematic composition",
        ],
        "cloverworks": [
            "cloverworks style",
            "detailed character design",
            "soft shading",
            "emotional",
        ],
        "default": [
            "anime",
            "2d",
            "illustration",
            "anime style",
        ],
    }

    def __init__(self):
        self.tag_mapper = DanbooruTagMapper()

    def translate(
        self,
        natural_prompt: str,
        character_tags: Optional[List[str]] = None,
        style_preset: Optional[str] = None,
        additional_positive: Optional[List[str]] = None,
        additional_negative: Optional[List[str]] = None,
        include_quality_tags: bool = True,
    ) -> StructuredPrompt:
        """
        将自然语言提示词翻译为结构化提示词

        Args:
            natural_prompt: 自然语言描述
            character_tags: 角色特定标签（如角色名、特征等）
            style_preset: 风格预设名称
            additional_positive: 额外的正面标签
            additional_negative: 额外的负面标签
            include_quality_tags: 是否包含质量标签

        Returns:
            StructuredPrompt: 结构化提示词
        """
        logger.debug(f"Translating prompt: {natural_prompt[:100]}...")

        # 1. 提取标签
        extracted_tags = self.tag_mapper.map_to_tags(natural_prompt)
        logger.debug(f"Extracted tags: {extracted_tags}")

        # 2. 添加角色特定标签
        if character_tags:
            extracted_tags = character_tags + extracted_tags

        # 3. 添加风格标签
        style_tags = self._get_style_tags(style_preset)

        # 4. 添加额外正面标签
        if additional_positive:
            extracted_tags.extend(additional_positive)

        # 5. 构建正面提示词
        all_positive_tags: List[str] = []

        # 质量标签放在最前面
        if include_quality_tags:
            all_positive_tags.extend(self.DEFAULT_QUALITY_TAGS)

        # 然后是提取的标签
        all_positive_tags.extend(extracted_tags)

        # 最后是风格标签
        all_positive_tags.extend(style_tags)

        # 去重保序
        positive_tags = list(dict.fromkeys(all_positive_tags))
        positive = ", ".join(positive_tags)

        # 6. 构建负面提示词
        negative_tags = self.DEFAULT_NEGATIVE_TAGS.copy()
        if additional_negative:
            negative_tags.extend(additional_negative)
        negative_tags = list(dict.fromkeys(negative_tags))
        negative = ", ".join(negative_tags)

        result = StructuredPrompt(
            positive=positive,
            negative=negative,
            tags=extracted_tags,
            quality_tags=self.DEFAULT_QUALITY_TAGS if include_quality_tags else [],
            style_tags=style_tags,
        )

        logger.info(f"Translated prompt: {len(positive_tags)} positive tags, {len(negative_tags)} negative tags")

        return result

    def _get_style_tags(self, style_preset: Optional[str]) -> List[str]:
        """获取风格预设标签"""
        if not style_preset:
            return self.STYLE_PRESETS["default"]

        preset_lower = style_preset.lower().replace(" ", "_").replace("-", "_")

        if preset_lower in self.STYLE_PRESETS:
            return self.STYLE_PRESETS[preset_lower]

        # 尝试模糊匹配
        for key in self.STYLE_PRESETS:
            if key in preset_lower or preset_lower in key:
                return self.STYLE_PRESETS[key]

        logger.warning(f"Unknown style preset: {style_preset}, using default")
        return self.STYLE_PRESETS["default"]

    def enhance_prompt(
        self,
        natural_prompt: str,
        style_preset: Optional[str] = None,
    ) -> str:
        """
        简单增强提示词（只返回正面提示词字符串）

        Args:
            natural_prompt: 自然语言描述
            style_preset: 风格预设

        Returns:
            增强后的提示词字符串
        """
        result = self.translate(natural_prompt, style_preset=style_preset)
        return result.positive

    def get_negative_prompt(self) -> str:
        """获取默认负面提示词"""
        return ", ".join(self.DEFAULT_NEGATIVE_TAGS)


# 全局实例
prompt_translator = PromptTranslator()
