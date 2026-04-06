"""
Context Agent - 上下文代理
负责生成创作执行包（任务书 + 上下文契约 + 写作提示）
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from .base import BaseAgent

logger = logging.getLogger(__name__)

CONTEXT_AGENT_PROMPT = """
你是专业的网文创作上下文生成专家。根据项目状态、大纲信息和章节要求，生成详细的创作执行包。

## 项目信息
{project_info}

## 主角设定
{protagonist_info}

## 世界观
{world_info}

## 当前进度
已写 {current_chapter} 章，本章是第 {chapter_num} 章

## 本章细纲
{chapter_outline}

## 角色状态面板（必须严格遵守，绝对禁止写错性别/境界/状态）
{character_states}

## 最近剧情摘要
{recent_summaries}

## 历史剧情检索（与本章相关的旧章节片段）
{rag_context}

## 任务
请根据上述**本章细纲**、**角色状态面板**和**最近剧情摘要**，为第 {chapter_num} 章生成创作执行包，包括：

1. **任务书（Mission Brief）**：
   - objectives: 本章目标（2-3个，必须与细纲一致）
   - resistance: 阻力/冲突（来自细纲）
   - cost: 代价/损失
   - character_states: 角色状态变化
   - scene_constraints: 场景约束
   - time_constraints: 时间约束
   - style_guidance: 风格指导
   - foreshadowing_priorities: 伏笔优先级

2. **上下文契约（Context Contract）**：
   - target: 目标
   - resistance: 阻力
   - cost: 代价
   - change: 变化
   - unclosed_question: 未解决问题
   - opening_type: 开篇类型
   - emotional_rhythm: 情感节奏
   - info_density: 信息密度

3. **写作提示（Writing Prompt）**：
   基于细纲的详细写作指导，包括：
   - 开篇方式
   - 冲突升级
   - 爽点设计
   - 结尾钩子

请严格按照以下 JSON 格式输出：

```json
{{
  "mission_brief": {{
    "objectives": ["目标1", "目标2"],
    "resistance": "阻力描述",
    "cost": "代价描述",
    "character_states": ["状态1", "状态2"],
    "scene_constraints": "场景约束",
    "time_constraints": "时间约束",
    "style_guidance": "风格指导",
    "foreshadowing_priorities": "伏笔优先级"
  }},
  "context_contract": {{
    "target": "目标",
    "resistance": "阻力",
    "cost": "代价",
    "change": "变化",
    "unclosed_question": "未解决问题",
    "opening_type": "开篇类型",
    "emotional_rhythm": "情感节奏",
    "info_density": "信息密度"
  }},
  "writing_prompt": "基于细纲的详细写作提示，包含章节节拍、爽点设计、钩子等"
}}
```

**硬约束**：
- 必须严格遵循本章细纲，不得随意更改剧情
- 严格遵循项目设定，不得违背
- 保持中文母语思维，避免英文结构
- 爽点密度：至少1个/章
- 章末必须有钩子（未解决问题或悬念）
- 时间逻辑必须自洽
"""


class ContextAgent(BaseAgent):
    """上下文代理"""
    
    name = "context-agent"
    description = "生成创作执行包（任务书 + 上下文契约 + 写作提示）"
    
    def __init__(self, llm: BaseLLM, state_manager: StateManager, config: Dict[str, Any] = None):
        super().__init__(llm, config)
        self.state_manager = state_manager
    
    async def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """执行上下文生成任务
        
        Args:
            input: {
                "chapter_num": 章节号,
                "outline_info": 细纲 JSON 字符串或字典,
            }
        
        Returns:
            {
                "mission_brief": 任务书,
                "context_contract": 上下文契约,
                "writing_prompt": 写作提示,
            }
        """
        chapter_num = input["chapter_num"]
        outline_info = input.get("outline_info", "")
        
        # 加载项目状态
        state = self.state_manager.load_state()
        
        # 格式化细纲
        if isinstance(outline_info, dict):
            outline_str = json.dumps(outline_info, ensure_ascii=False, indent=2)
        elif isinstance(outline_info, str):
            outline_str = outline_info
        else:
            outline_str = "暂无细纲，请根据项目设定自由发挥。"
        
        # 格式化前情信息
        context_info = input.get("context_info", {})
        char_states = context_info.get("character_states", "（暂无角色状态）")
        recent_summaries = context_info.get("recent_summaries", "（无前序摘要）")
        rag_context = context_info.get("rag_context", "（无检索内容）")
        
        # 构建提示词
        prompt = CONTEXT_AGENT_PROMPT.format(
            project_info=json.dumps(state.project, ensure_ascii=False, indent=2),
            protagonist_info=json.dumps(state.protagonist, ensure_ascii=False, indent=2),
            world_info=json.dumps(state.world, ensure_ascii=False, indent=2),
            current_chapter=state.progress.get("current_chapter", 0),
            chapter_num=chapter_num,
            chapter_outline=outline_str,
            character_states=char_states,
            recent_summaries=recent_summaries,
            rag_context=rag_context,
        )
        
        # 调用 LLM
        logger.info(f"Context Agent 开始生成第 {chapter_num} 章的上下文")
        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是专业的网文创作助手，擅长生成详细的创作执行包。",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        
        # 解析响应
        result = self.parse_response(response.text)
        
        logger.info(f"Context Agent 完成第 {chapter_num} 章的上下文生成")
        return result
