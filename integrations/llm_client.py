import logging
from typing import Type, TypeVar
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from config import settings

# 配置日志记录器
logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class LLMClient:
    def __init__(self):
        """
        初始化 LLM 客户端
        使用 LangChain 的 Google Gemini 集成
        """
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("GOOGLE_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"

        # 初始化 ChatGoogleGenerativeAI
        # 核心配置说明：
        # 1. model: 读取 .env 中的设置 (建议使用 gemini-2.5-flash-lite 以获得最快速度)
        # 2. timeout: 设置为 300秒，这是解决 "Server disconnected" 问题的关键
        # 3. max_retries: 网络波动时自动重试
        self.llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=settings.LLM_MODEL,
            temperature=0.7,
            convert_system_message_to_human=True,
            timeout=300.0,  # <--- [关键修复] 防止分镜生成时 60s 超时
            max_retries=3,
        )

    def generate_structured_output(self, prompt: str, pydantic_model: Type[T], temperature: float = 0.2) -> T | None:
        """
        生成结构化数据 (JSON)
        用于从小说中提取角色、生成分镜等需要严格格式的场景
        """
        # 创建 Pydantic 解析器
        parser = PydanticOutputParser(pydantic_object=pydantic_model)
        format_instructions = parser.get_format_instructions()

        # 构建 Prompt 模板
        chat_prompt = ChatPromptTemplate.from_template(
            "You are a helpful AI assistant.\n{format_instructions}\n\n{prompt}"
        )

        # 绑定特定的 temperature (通常结构化提取需要较低的温度以保证准确性)
        llm_with_temp = self.llm.bind(temperature=temperature)

        # 组装处理链: Prompt -> LLM -> Parser
        chain = chat_prompt | llm_with_temp | parser

        try:
            # 执行调用
            return chain.invoke({"prompt": prompt, "format_instructions": format_instructions})
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            # 返回 None 表示失败，上层逻辑(如 Director) 会据此判断是否需要重试或报错
            return None


# 单例实例
llm_client = LLMClient()