tradingagents/utils/memory

    def __init__(self, name, config):
        if config["backend_url"] == "http://192.168.0.20:11434/v1":
            self.embedding = "nomic-embed-text"
        elif config["backend_url"] == "http://192.168.0.20:1234/v1":
            self.embedding = "text-embedding-nomic-embed-text-v1.5"
        else:
            self.embedding = "ttext-embedding-nomic-embed-text-v1.5"
            
        self.client = OpenAI(base_url=config["backend_url"], api_key=config["api_key"])

tradingagents/graph/trading_graph.py

        # Initialize LLMs
        if self.config["llm_provider"].lower() == "openai" or self.config["llm_provider"] == "ollama" or self.config["llm_provider"] == "openrouter":
            self.deep_thinking_llm = ChatOpenAI(model=self.config["deep_think_llm"], base_url=self.config["backend_url"],api_key=self.config["api_key"])
            self.quick_thinking_llm = ChatOpenAI(model=self.config["quick_think_llm"], base_url=self.config["backend_url"],api_key=self.config["api_key"])
        elif self.config["llm_provider"].lower() == "anthropic":
            self.deep_thinking_llm = ChatAnthropic(model=self.config["deep_think_llm"], base_url=self.config["backend_url"],api_key=self.config["api_key"])
            self.quick_thinking_llm = ChatAnthropic(model=self.config["quick_think_llm"], base_url=self.config["backend_url"],api_key=self.config["api_key"])
        elif self.config["llm_provider"].lower() == "google":
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"])
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"])
        elif self.config["llm_provider"].lower() == "lmstudio":
            self.deep_thinking_llm = ChatOpenAI(model=self.config["deep_think_llm"], base_url=self.config["backend_url"], api_key=self.config["api_key"])
            self.quick_thinking_llm = ChatOpenAI(model=self.config["quick_think_llm"], base_url=self.config["backend_url"],api_key=self.config["api_key"]) 

default_config.py
    # Default LLM is set to local LMStudio instance
    "llm_provider": "lmstudio",
    "deep_think_llm": "qwen/qwen3-4b-thinking-2507",
    "quick_think_llm": "openai/gpt-oss-20b",
    "backend_url": "http://192.168.0.20/v1",
    "api_key": "blablabla",

utils.py
  BASE_URLS = [
        ("LMStudio", "http://192.168.0.20:1234/v1"),
        ("OpenAI Local", "http://192.168.0.20:1234/v1"),
        ("OpenAI", "https://api.openai.com/v1"),
        ("Anthropic", "https://api.anthropic.com/"),
        ("Google", "https://generativelanguage.googleapis.com/v1"),
        ("Openrouter", "https://openrouter.ai/api/v1"),
        ("Ollama", "http://localhost:11434/v1"),

Anthropic section
("CCR", "openai/gpt-oss-20b"),


both to shallow thinking and deep thinking
,
        "openrouter": [
            ("Meta: Llama 4 Scout", "meta-llama/llama-4-scout:free"),
            ("Meta: Llama 3.3 8B Instruct - A lightweight and ultra-fast variant of Llama 3.3 70B", "meta-llama/llama-3.3-8b-instruct:free"),
            ("google/gemini-2.0-flash-exp:free - Gemini Flash 2.0 offers a significantly faster time to first token", "google/gemini-2.0-flash-exp:free"),
        ],
        "ollama": [
            ("llama3.1 local", "llama3.1"),
            ("qwen3", "qwen3"),
        ],
        "lmstudio": [
            ("LMStudio Qwen 4b Thinking","qwen/qwen3-4b-thinking-2507"),
            ("LMStudio GLM", "glm-4.5-air-mlx"),
            ("LMStudio OSS 120b","openai/gpt-oss-120b"),
            ("LMStudio Kimi","kimi-dev-72b-dwq"),
        ]