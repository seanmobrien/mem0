import json
import logging

from httpx import get
from openai import OpenAI

# from openai import OpenAI
from mem0.llms.azure_openai import AzureOpenAI
from mem0.llms.openai import OpenAI
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT
from app.utils.clientConfigFactory import get_parsed_memory_config
from mem0.utils.factory import LlmFactory


load_dotenv()

# openai_client = OpenAI()
openai_client = None

def get_ai_client() -> AzureOpenAI | OpenAI | None:
    """Get the AI client."""    
    global openai_client

    if not openai_client:
        config = get_parsed_memory_config()
        if config is None:
            logging.error('Memory client is not initialized...not sure how we even got here')
        else:
            llmConfig = config.get('llm', None)
            if llmConfig is None:
                logging.error('No LLM configuration found in memory config, returning default OpenAI client')
            else:
                llmProvider = llmConfig.get('provider')
                client = LlmFactory.create(llmProvider, llmConfig.get('config'))
                if llmProvider == 'azure_openai':
                    openai_client = client.client
                elif llmProvider == 'openai':
                    openai_client = client.client
                else:
                    logging.error(f'Unsupported categorization provider: {llmConfig.get("provider")}, returning default OpenAI client')
                    openai_client = AzureOpenAI()           
    return openai_client or AzureOpenAI()

class MemoryCategories(BaseModel):
    categories: List[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    """Get categories for a memory."""
    try:
        response = get_ai_client().responses.parse(
            model="gpt-4o-mini",
            instructions=MEMORY_CATEGORIZATION_PROMPT,
            input=memory,
            temperature=0,
            text_format=MemoryCategories,
        )                      
        categories = [cat.strip().lower() for cat in response.output_parsed.categories]
        # TODO: Validate categories later may be
        return categories
    except Exception as e:
        logging.error('Error in get_categories_for_memory: %s', str(e))
        raise e
