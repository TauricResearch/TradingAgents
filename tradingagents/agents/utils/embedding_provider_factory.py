from .embedding_providers import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    GeminiEmbeddingProvider,
    OllamaEmbeddingProvider
)


class EmbeddingProviderFactory:
    @staticmethod
    def create_provider(config : dict[str, any])->EmbeddingProvider:
        backend_url = config["backend_url"]

        if "generativelanguage.googleapis.com" in backend_url:
            return GeminiEmbeddingProvider(backend_url)
        elif "localhost:11434" in backend_url:
            return OllamaEmbeddingProvider(backend_url)
        else:
            return OpenAIEmbeddingProvider(backend_url)
        