"""
LLM 抽象基类
所有 LLM 提供商必须实现此接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel


@dataclass
class TokenUsage:
    """Token 使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """LLM 响应"""
    text: str
    usage: TokenUsage
    finish_reason: str
    model: str


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str  # "system" | "user" | "assistant"
    content: str


class BaseLLM(ABC):
    """所有 LLM 提供商必须实现的基类"""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        """同步生成文本"""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        pass
    
    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """多轮对话"""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回模型名称"""
        pass
    
    @property
    @abstractmethod
    def max_context_length(self) -> int:
        """返回最大上下文长度"""
        pass


def create_llm(config: Dict[str, Any]) -> BaseLLM:
    """根据配置创建 LLM 实例
    
    注意：每次调用都会自动重新加载 .env 文件，确保使用最新的 API Key
    """
    # 重新加载 .env 文件，确保使用最新的 API Key
    from ..utils.config import _load_env_file
    _load_env_file()
    
    provider = config.get("provider", "qwen")
    
    if provider == "qwen":
        from .qwen import QwenLLM
        return QwenLLM(config)
    elif provider == "ollama":
        from .ollama import OllamaLLM
        return OllamaLLM(config)
    elif provider == "openai":
        from .openai_llm import OpenAILLM
        return OpenAILLM(config)
    else:
        raise ValueError(f"不支持的 LLM 提供商: {provider}")
