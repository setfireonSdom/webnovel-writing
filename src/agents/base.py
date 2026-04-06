"""
Agent 抽象基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..llm.base import BaseLLM


class BaseAgent(ABC):
    """所有 Agent 的基类"""
    
    name: str = "base-agent"
    description: str = "Base Agent"
    
    def __init__(self, llm: BaseLLM, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 4096)
    
    @abstractmethod
    async def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Agent 任务"""
        pass
    
    async def build_prompt(self, context: Dict[str, Any]) -> str:
        """构建提示词"""
        raise NotImplementedError
    
    def parse_response(self, response: str) -> Dict[str, Any]:
        """解析模型响应"""
        # 默认实现：尝试解析 JSON
        import json
        try:
            # 尝试提取 JSON（可能包裹在 markdown 代码块中）
            json_str = self._extract_json(response)
            return json.loads(json_str)
        except Exception as e:
            # 如果解析失败，返回原始文本
            return {"raw_response": response}
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON（可能包裹在 markdown 代码块中）"""
        import json
        
        # 尝试直接解析
        text = text.strip()
        if text.startswith("{"):
            return text
        
        # 尝试从 markdown 代码块中提取
        lines = text.split("\n")
        json_lines = []
        in_code_block = False
        
        for line in lines:
            if line.strip() == "```json":
                in_code_block = True
                continue
            elif line.strip() == "```":
                if in_code_block:
                    break
                continue
            
            if in_code_block:
                json_lines.append(line)
        
        if json_lines:
            return "\n".join(json_lines)
        
        # 尝试找到第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start:end+1]
        
        return text
