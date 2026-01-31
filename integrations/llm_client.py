import logging
from typing import Type, TypeVar
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class LLMClient:
    """LLM 客户端，使用 LangChain 的 Google Gemini 集成。"""

    def __init__(self):
        """初始化 LLM 客户端。"""
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("GOOGLE_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"

        self.llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=settings.LLM_MODEL,
            temperature=0.7,
            convert_system_message_to_human=True,
            timeout=300.0,
            max_retries=3,
        )

    def generate_structured_output(self, prompt: str, pydantic_model: Type[T], temperature: float = 0.2) -> T | None:
        """生成结构化数据 (JSON)，用于从小说中提取角色、生成分镜等场景。"""
        parser = PydanticOutputParser(pydantic_object=pydantic_model)
        format_instructions = parser.get_format_instructions()

        chat_prompt = ChatPromptTemplate.from_template(
            "You are a helpful AI assistant.\n{format_instructions}\n\n{prompt}"
        )

        llm_with_temp = self.llm.bind(temperature=temperature)
        chain = chat_prompt | llm_with_temp | parser

        try:
            return chain.invoke({"prompt": prompt, "format_instructions": format_instructions})
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None


llm_client = LLMClient()