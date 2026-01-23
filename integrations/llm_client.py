import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from config import settings

class LLMClient:
    def __init__(self):
        # Using Google Generative AI integration for Gemini models
        # Requires GOOGLE_API_KEY env var (managed via settings)
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            print("Warning: GOOGLE_API_KEY is not set. Using dummy key for initialization.")
            api_key = "dummy_key_for_init"

        self.llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model="gemini-1.5-pro",
            temperature=0.7,
            convert_system_message_to_human=True
        )

    def generate_structured_output(self, prompt: str, pydantic_model: BaseModel):
        parser = PydanticOutputParser(pydantic_object=pydantic_model)
        format_instructions = parser.get_format_instructions()

        chat_prompt = ChatPromptTemplate.from_template(
            "You are a helpful AI assistant.\n{format_instructions}\n\n{prompt}"
        )

        chain = chat_prompt | self.llm | parser

        try:
            return chain.invoke({"prompt": prompt, "format_instructions": format_instructions})
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None

llm_client = LLMClient()
