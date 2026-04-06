"""
OpenAI 兼容 LLM 实现
使用官方 openai SDK，支持百炼平台所有模型（包括 glm-5）
"""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseLLM, LLMResponse, TokenUsage, ChatMessage

logger = logging.getLogger(__name__)


class OpenAILLM(BaseLLM):
    """OpenAI 兼容模型（使用官方 SDK）"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "glm-5")
        base_url = config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.timeout = config.get("timeout", 120)
        self.enable_thinking = config.get("enable_thinking", True)  # glm-5 需要
        
        if not self.api_key:
            raise ValueError("API Key 未配置")
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
        )
    
    @property
    def model_name(self) -> str:
        return self.model
    
    @property
    def max_context_length(self) -> int:
        return 128000
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(Exception),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        """生成文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,  # 强制使用流式，避免 glm-5 思考模式导致的长时间无响应
            "stream_options": {"include_usage": True},
        }
        
        # glm-5 等特定模型需要 enable_thinking
        if self.enable_thinking and self.model.lower().startswith("glm"):
            kwargs["extra_body"] = {"enable_thinking": True}
        
        if stop:
            kwargs["stop"] = stop
        
        # 流式获取并拼接
        full_text = ""
        usage = None
        stream = await self.client.chat.completions.create(**kwargs)
        
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_text += delta.content
            
            if chunk.usage:
                usage = chunk.usage
        
        return LLMResponse(
            text=full_text,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason="stop",
            model=self.model,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(Exception),
    )
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """多轮对话"""
        msg_list = [{"role": m.role, "content": m.content} for m in messages]
        
        kwargs = {
            "model": self.model,
            "messages": msg_list,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if self.enable_thinking and self.model.lower().startswith("glm"):
            kwargs["extra_body"] = {"enable_thinking": True}
        
        completion = await self.client.chat.completions.create(**kwargs)
        
        message = completion.choices[0].message
        usage = completion.usage
        
        return LLMResponse(
            text=message.content or "",
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=completion.choices[0].finish_reason or "stop",
            model=completion.model or self.model,
        )
    
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        
        if self.enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": True}
        
        async for chunk in await self.client.chat.completions.create(**kwargs):
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
