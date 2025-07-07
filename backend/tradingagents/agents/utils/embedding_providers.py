from abc import ABC, abstractmethod
from openai import OpenAI
from google import genai


class EmbeddingProvider(ABC):
    @abstractmethod
    def get_embedding(self, text: str)->list[float]:
        pass

    @property
    @abstractmethod
    def model_name(self)->str:
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, backend_url: str, embedding_model: str = "text-embedding-3-small"):
        self.client = OpenAI(base_url=backend_url)
        self._embedding_model = embedding_model

    
    def get_embedding(self, text: str)->list[float]:
        response = self.client.embeddings.create(
            model=self._embedding_model,
            input=text
        )
        return response.data[0].embedding
    
    @property
    def model_name(self)->str:
        return self._embedding_model
    

class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, backend_url: str, embedding_model: str = "gemini-embedding-exp-03-07"):
        self.client = genai.Client()
        self._embedding_model = embedding_model

    def get_embedding(self, text: str)->list[float]:
        response = self.client.models.embed_content(
            model=self._embedding_model,
            contents=text
        )
        return response.embeddings[0].values
    
    @property
    def model_name(self)->str:
        return self._embedding_model
    
class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, backend_url: str, embedding_model: str = "nomic-embed-text"):
        self.client = OpenAI(base_url=backend_url)
        self._embedding_model = embedding_model

    def get_embedding(self, text: str)->list[float]:
        response = self.client.embeddings.create(
            model=self._embedding_model,
            input=text
        )
        return response.data[0].embedding
    
    @property
    def model_name(self)->str:
        return self._embedding_model
    