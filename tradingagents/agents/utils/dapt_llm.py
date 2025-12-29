"""
LangChain wrapper for DAPTed Llama 3.1 8B model (PEFT adapter)
"""
import torch
from typing import List, Optional, Any, Dict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.runnables import Runnable
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os


class DAPTLlamaChatModel(BaseChatModel):
    """LangChain-compatible wrapper for DAPTed Llama 3.1 8B model"""
    
    model_id: str = "meta-llama/Llama-3.1-8B"
    dapt_adapter_path: str
    device: Optional[str] = None
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    
    _model: Optional[Any] = None
    _tokenizer: Optional[Any] = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_model()
    
    def _load_model(self):
        """Load the DAPTed model with PEFT adapters"""
        if self._model is not None:
            return  # Already loaded
        
        print(f"Loading DAPTed Llama model from {self.dapt_adapter_path}...")
        
        # Detect device
        if self.device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        
        # Setup quantization for CUDA
        bnb_config = None
        if self.device == "cuda":
            try:
                from transformers import BitsAndBytesConfig
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
            except ImportError:
                print("bitsandbytes not available, loading in full precision")
        
        # Determine torch dtype
        if self.device == "cuda":
            torch_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            torch_dtype = torch.float32
        
        # Get HF token
        hf_token = (
            os.getenv("HF_TOKEN") 
            or os.getenv("HUGGINGFACE_HUB_TOKEN") 
            or os.getenv("HUGGING_FACE_HUB_TOKEN")
        )
        
        # Load base model
        base_model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto" if self.device == "cuda" else None,
            torch_dtype=torch_dtype,
            quantization_config=bnb_config,
            low_cpu_mem_usage=True,
            token=hf_token,
        )
        
        # Load PEFT adapters
        if not os.path.exists(self.dapt_adapter_path):
            raise ValueError(f"DAPT adapter path not found: {self.dapt_adapter_path}")
        
        self._model = PeftModel.from_pretrained(base_model, self.dapt_adapter_path)
        self._model.eval()
        
        # Load tokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, token=hf_token)
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        
        print(f"DAPTed model loaded successfully on {self.device}")
    
    def _format_messages(self, messages: List[BaseMessage]) -> str:
        """Convert LangChain messages to Llama 3.1 chat format"""
        # Use tokenizer's chat template if available
        if hasattr(self._tokenizer, 'apply_chat_template') and self._tokenizer.chat_template:
            # Convert to format expected by tokenizer
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    formatted_messages.append({"role": "system", "content": msg.content})
                elif isinstance(msg, HumanMessage):
                    formatted_messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    formatted_messages.append({"role": "assistant", "content": msg.content})
                else:
                    formatted_messages.append({"role": "user", "content": str(msg.content)})
            
            # Apply chat template
            prompt = self._tokenizer.apply_chat_template(
                formatted_messages,
                tokenize=False,
                add_generation_prompt=True
            )
            return prompt
        else:
            # Fallback to Llama 3 style manual formatting using header tokens
            # <|begin_of_text|>
            # <|start_header_id|>system<|end_header_id|>
            # {content}<|eot_id|> ...
            bos = "<|begin_of_text|>"
            start_header = "<|start_header_id|>"
            end_header = "<|end_header_id|>"
            eot = "<|eot_id|>"
            parts: List[str] = [bos]
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    parts.append(f"{start_header}system{end_header}\n{msg.content}{eot}\n")
                elif isinstance(msg, HumanMessage):
                    parts.append(f"{start_header}user{end_header}\n{msg.content}{eot}\n")
                elif isinstance(msg, AIMessage):
                    parts.append(f"{start_header}assistant{end_header}\n{msg.content}{eot}\n")
                else:
                    parts.append(f"{start_header}user{end_header}\n{str(msg.content)}{eot}\n")
            # Add assistant header to cue generation
            parts.append(f"{start_header}assistant{end_header}\n")
            return "".join(parts)
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a response from the model"""
        if self._model is None or self._tokenizer is None:
            self._load_model()
        
        # Format messages
        prompt = self._format_messages(messages)
        
        # Tokenize
        inputs = self._tokenizer(prompt, return_tensors="pt")
        if self.device != "cpu":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Generate
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        
        # Decode
        generated_text = self._tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:], 
            skip_special_tokens=True
        )
        
        # Create response
        message = AIMessage(content=generated_text)
        generation = ChatGeneration(message=message)
        
        return ChatResult(generations=[generation])
    
    @property
    def _llm_type(self) -> str:
        return "dapt_llama"
    
    def bind_tools(self, tools: List[Any], **kwargs: Any):
        """Bind tools - returns a runnable that handles tool calling"""
        # Store tools for potential use in prompt enhancement
        self._bound_tools = tools
        return DAPTLlamaWithTools(self, tools)
    
    def _invoke(self, messages: List[BaseMessage], **kwargs: Any) -> AIMessage:
        """Internal invoke that returns AIMessage with tool_calls attribute"""
        chat_result = self._generate(messages, **kwargs)
        ai_message = chat_result.generations[0].message
        
        # Add tool_calls attribute (empty list for now - DAPT model doesn't natively support tool calling)
        # The analyst node will check len(tool_calls) == 0 and use content directly
        if not hasattr(ai_message, 'tool_calls'):
            ai_message.tool_calls = []
        
        return ai_message


class DAPTLlamaWithTools(Runnable):
    """Wrapper to make DAPT LLM compatible with bind_tools interface"""
    
    def __init__(self, llm: DAPTLlamaChatModel, tools: List[Any]):
        self.llm = llm
        self.tools = tools
    
    def invoke(self, input: Any, config: Optional[Any] = None, **kwargs: Any) -> AIMessage:
        """Invoke the LLM and return result with tool_calls attribute"""
        if isinstance(input, dict) and "messages" in input:
            messages = input["messages"]
        elif isinstance(input, list):
            messages = input
        else:
            messages = [input] if isinstance(input, BaseMessage) else [HumanMessage(content=str(input))]
        
        return self.llm._invoke(messages, **kwargs)