import importlib
from typing import Optional

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.configs.llms.base import BaseLlmConfig
from mem0.embeddings.mock import MockEmbeddings


def load_class(class_type):
    module_path, class_name = class_type.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class LlmFactory:
    provider_to_class = {
        "ollama": "mem0.llms.ollama.OllamaLLM",
        "openai": "mem0.llms.openai.OpenAILLM",
        "groq": "mem0.llms.groq.GroqLLM",
        "together": "mem0.llms.together.TogetherLLM",
        "aws_bedrock": "mem0.llms.aws_bedrock.AWSBedrockLLM",
        "litellm": "mem0.llms.litellm.LiteLLM",
        "azure_openai": "mem0.llms.azure_openai.AzureOpenAILLM",
        "openai_structured": "mem0.llms.openai_structured.OpenAIStructuredLLM",
        "anthropic": "mem0.llms.anthropic.AnthropicLLM",
        "azure_openai_structured": "mem0.llms.azure_openai_structured.AzureOpenAIStructuredLLM",
        "gemini": "mem0.llms.gemini.GeminiLLM",
        "deepseek": "mem0.llms.deepseek.DeepSeekLLM",
        "xai": "mem0.llms.xai.XAILLM",
        "sarvam": "mem0.llms.sarvam.SarvamLLM",
        "lmstudio": "mem0.llms.lmstudio.LMStudioLLM",
        "langchain": "mem0.llms.langchain.LangchainLLM",
    }

    @classmethod
    def create(cls, provider_name, config):
        class_type = cls.provider_to_class.get(provider_name)
        if class_type:
            llm_instance = load_class(class_type)
            base_config = BaseLlmConfig(**config)
            return llm_instance(base_config)
        else:
            raise ValueError(f"Unsupported Llm provider: {provider_name}")


class EmbedderFactory:
    provider_to_class = {
        "openai": "mem0.embeddings.openai.OpenAIEmbedding",
        "ollama": "mem0.embeddings.ollama.OllamaEmbedding",
        "huggingface": "mem0.embeddings.huggingface.HuggingFaceEmbedding",
        "azure_openai": "mem0.embeddings.azure_openai.AzureOpenAIEmbedding",
        "gemini": "mem0.embeddings.gemini.GoogleGenAIEmbedding",
        "vertexai": "mem0.embeddings.vertexai.VertexAIEmbedding",
        "together": "mem0.embeddings.together.TogetherEmbedding",
        "lmstudio": "mem0.embeddings.lmstudio.LMStudioEmbedding",
        "langchain": "mem0.embeddings.langchain.LangchainEmbedding",
        "aws_bedrock": "mem0.embeddings.aws_bedrock.AWSBedrockEmbedding",
    }

    @classmethod
    def create(cls, provider_name, config, vector_config: Optional[dict]):
        if provider_name == "upstash_vector" and vector_config and vector_config.enable_embeddings:
            return MockEmbeddings()
        class_type = cls.provider_to_class.get(provider_name)
        if class_type:
            embedder_instance = load_class(class_type)
            base_config = BaseEmbedderConfig(**config)
            return embedder_instance(base_config)
        else:
            raise ValueError(f"Unsupported Embedder provider: {provider_name}")


class VectorStoreFactory:
    provider_to_class = {
        "qdrant": "mem0.vector_stores.qdrant.Qdrant",
        "chroma": "mem0.vector_stores.chroma.ChromaDB",
        "pgvector": "mem0.vector_stores.pgvector.PGVector",
        "milvus": "mem0.vector_stores.milvus.MilvusDB",
        "upstash_vector": "mem0.vector_stores.upstash_vector.UpstashVector",
        "azure_ai_search": "mem0.vector_stores.azure_ai_search.AzureAISearch",
        "pinecone": "mem0.vector_stores.pinecone.PineconeDB",
        "redis": "mem0.vector_stores.redis.RedisDB",
        "elasticsearch": "mem0.vector_stores.elasticsearch.ElasticsearchDB",
        "vertex_ai_vector_search": "mem0.vector_stores.vertex_ai_vector_search.GoogleMatchingEngine",
        "opensearch": "mem0.vector_stores.opensearch.OpenSearchDB",
        "supabase": "mem0.vector_stores.supabase.Supabase",
        "weaviate": "mem0.vector_stores.weaviate.Weaviate",
        "faiss": "mem0.vector_stores.faiss.FAISS",
        "langchain": "mem0.vector_stores.langchain.Langchain",
    }

    @classmethod
    def create(cls, provider_name, config):
        class_type = cls.provider_to_class.get(provider_name)
        if class_type:
            if not isinstance(config, dict):
                config = config.model_dump()
            vector_store_instance = load_class(class_type)
            instance = vector_store_instance(**config)

            # Instrument provider-level search if OpenTelemetry is available
            try:
                from opentelemetry import trace
                tracer = trace.get_tracer("mem0.vector_store")

                if hasattr(instance, "search"):
                    import inspect

                    original_search = instance.search

                    # Async provider support
                    if inspect.iscoroutinefunction(getattr(original_search, '__func__', original_search)):
                        async def _wrapped_search(*args, **kwargs):
                            with tracer.start_as_current_span("vector_store.provider_search") as span:
                                try:
                                    span.set_attribute("mem0.vector_provider", instance.__class__.__name__)
                                    if len(args) > 0:
                                        span.set_attribute("mem0.search.query", str(args[0]))
                                    if "limit" in kwargs:
                                        try:
                                            span.set_attribute("mem0.search.limit", int(kwargs.get("limit")))
                                        except Exception:
                                            pass
                                    if "filters" in kwargs:
                                        span.set_attribute("mem0.search.filters_present", bool(kwargs.get("filters")))
                                    result = await original_search(*args, **kwargs)
                                    try:
                                        span.set_attribute("mem0.search.results_count", len(result) if result is not None else 0)
                                    except Exception:
                                        pass
                                    return result
                                except Exception as e:
                                    try:
                                        span.record_exception(e)
                                    except Exception:
                                        pass
                                    raise

                        instance.search = _wrapped_search
                    else:
                        def _wrapped_search(*args, **kwargs):
                            with tracer.start_as_current_span("vector_store.provider_search") as span:
                                try:
                                    span.set_attribute("mem0.vector_provider", instance.__class__.__name__)
                                    # capture commonly passed params if available
                                    if len(args) > 0:
                                        span.set_attribute("mem0.search.query", str(args[0]))
                                    if "limit" in kwargs:
                                        try:
                                            span.set_attribute("mem0.search.limit", int(kwargs.get("limit")))
                                        except Exception:
                                            pass
                                    if "filters" in kwargs:
                                        span.set_attribute("mem0.search.filters_present", bool(kwargs.get("filters")))
                                    result = original_search(*args, **kwargs)
                                    try:
                                        # try to capture result count
                                        span.set_attribute("mem0.search.results_count", len(result) if result is not None else 0)
                                    except Exception:
                                        pass
                                    return result
                                except Exception as e:
                                    try:
                                        span.record_exception(e)
                                    except Exception:
                                        pass
                                    raise

                        instance.search = _wrapped_search
            except Exception:
                # opentelemetry not present or instrumentation failed — ignore
                pass

            return instance
        else:
            raise ValueError(f"Unsupported VectorStore provider: {provider_name}")

    @classmethod
    def reset(cls, instance):
        instance.reset()
        return instance
