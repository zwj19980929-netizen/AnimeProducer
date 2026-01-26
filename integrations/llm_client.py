import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        # Using Google Generative AI integration for Gemini models
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            print("Warning: GOOGLE_API_KEY is not set. Using dummy key for initialization.")
            api_key = "dummy_key_for_init"

        # 配置参数：增加超时时间到 300秒 (5分钟)
        # 不同的 langchain 版本对 timeout 的传递方式略有不同，
        # 通常直接传 timeout 或 transport_kwargs
        self.llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=settings.LLM_MODEL,
            temperature=0.7,
            convert_system_message_to_human=True,
            # [核心修复] 强制设置超长超时时间，防止分镜生成中断
            timeout=300.0,
            max_retries=3,
            transport="rest", # 有时 rest 比 grpc 在代理下更稳定
        )

    def generate_structured_output(self, prompt: str, pydantic_model: BaseModel, temperature: float = 0.2):
        parser = PydanticOutputParser(pydantic_object=pydantic_model)
        format_instructions = parser.get_format_instructions()

        chat_prompt = ChatPromptTemplate.from_template(
            "You are a helpful AI assistant.\n{format_instructions}\n\n{prompt}"
        )

        # Bind temperature to the model for this call
        llm_with_temp = self.llm.bind(temperature=temperature)
        chain = chat_prompt | llm_with_temp | parser

        try:
            return chain.invoke({"prompt": prompt, "format_instructions": format_instructions})
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            # [建议] 这里最好抛出异常而不是返回 None，以便上层知道是网络挂了还是解析挂了
            # raise e
            return None

llm_client = LLMClient()