import json
import logging

# from openai import OpenAI
from mem0.llms.azure_openai import AzureOpenAI
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT

load_dotenv()

# openai_client = OpenAI()
openai_client = AzureOpenAI()


class MemoryCategories(BaseModel):
    categories: List[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    """Get categories for a memory."""
    try:
        response = openai_client.responses.parse(
            model="gpt-4o-mini",
            instructions=MEMORY_CATEGORIZATION_PROMPT,
            input=memory,
            temperature=0,
            text_format=MemoryCategories,
        )                      
        logging.warn('Response from Azure OpenAI: %s',  json.dumps(response.output))
        response_json =json.loads(response.output[0].content[0].text)
        categories = response_json['categories']
        categories = [cat.strip().lower() for cat in categories]
        # TODO: Validate categories later may be
        return categories
    except Exception as e:
        logging.error('Error in get_categories_for_memory: %s', str(e))
        raise e
