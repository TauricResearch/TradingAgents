from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
from openai import OpenAI
from abc import ABC, abstractmethod



class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> str:
        pass


class GoogleSearchProvider(SearchProvider):
    def __init__(self, model: str):
        self.client = genai.Client()
        self.model = model
    
    def search(self, query: str) -> str:
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=query,
            config=GenerateContentConfig(
                tools=[google_search_tool],
                response_modalities=["TEXT"]
            )
        )
        

        result_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text'):
                result_text += part.text
            
        return result_text
    

class OpenAISearchProvider(SearchProvider):
    def __init__(self, model: str, backend_url: str):
        self.client = OpenAI(base_url=backend_url)
        self.model = model
    
    def search(self, query: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": query
                        }
                    ],
                }
            ],
            text={"format": {"type": "text"}},
            reasoning={},
            tools=[
                {
                    "type": "web_search_preview",
                    "user_location": {"type": "approximate"},
                    "search_context_size": "low",
                }
            ],
            temperature=1,
            max_output_tokens=4096,
            top_p=1,
            store=True,
        )

        return response.output[1].content[0].text