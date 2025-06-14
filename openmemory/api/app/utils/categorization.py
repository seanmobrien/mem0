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
from app.models import (
   Config as ConfigModel
)


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
            if 'llm' not in config or config.llm is None:
                logging.error('No LLM configuration found in memory config, returning default OpenAI client')
            else:
                if 'llm' in config.llm and config.llm is not None: 
                    client = LlmFactory.create(config.llm.provider, config.llm.config)
                    if config.llm.provider == 'azure_openai':
                        openai_client = client.client
                    elif config.llm.provider == 'openai':
                        openai_client = client.client
                    else:
                        logging.error(f'Unsupported categorization provider: {config.llm.provider}, returning default OpenAI client')
                        openai_client = OpenAI()       
    return openai_client or OpenAI()

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
        logging.warning('Response from Azure OpenAI: %s',  json.dumps(response.output))
        response_json =json.loads(response.output[0].content[0].text)
        categories = response_json['categories']
        categories = [cat.strip().lower() for cat in categories]
        # TODO: Validate categories later may be
        return categories
    except Exception as e:
        logging.error('Error in get_categories_for_memory: %s', str(e))
        raise e
