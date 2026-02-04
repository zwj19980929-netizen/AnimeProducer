import logging
from typing import Type, TypeVar
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


def _create_llm() -> BaseChatModel:
    """根据配置创建对应的 LLM 客户端。"""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("GOOGLE_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"
        return ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=settings.LLM_MODEL,
            temperature=0.7,
            convert_system_message_to_human=True,
            timeout=300.0,
            max_retries=3,
        )

    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            logger.warning("DEEPSEEK_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"
        return ChatOpenAI(
            api_key=api_key,
            base_url=settings.DEEPSEEK_ENDPOINT,
            model=settings.DEEPSEEK_MODEL,
            temperature=0.7,
            timeout=300.0,
            max_retries=3,
        )

    elif provider == "doubao":
        from langchain_openai import ChatOpenAI
        api_key = settings.DOUBAO_API_KEY
        if not api_key:
            logger.warning("DOUBAO_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"
        return ChatOpenAI(
            api_key=api_key,
            base_url=settings.DOUBAO_ENDPOINT,
            model=settings.DOUBAO_MODEL,
            temperature=0.7,
            timeout=300.0,
            max_retries=3,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            logger.warning("OPENAI_API_KEY is not set. LLM calls will fail.")
            api_key = "dummy_key_for_init"
        return ChatOpenAI(
            api_key=api_key,
            model=settings.LLM_MODEL,
            temperature=0.7,
            timeout=300.0,
            max_retries=3,
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported: google, deepseek, doubao, openai")


class LLMClient:
    """LLM 客户端，支持多个 LLM 提供商。"""

    def __init__(self):
        """初始化 LLM 客户端。"""
        logger.info(f"Initializing LLM client with provider: {settings.LLM_PROVIDER}")
        self.llm = _create_llm()

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
