"""
逻辑审查 Agent
负责检查生成内容是否存在严重逻辑漏洞（如主角变性、境界倒退等）。
"""

import logging
from typing import Dict, Any

from ..llm.base import BaseLLM, LLMResponse
from ..data.state_manager import StateManager

logger = logging.getLogger(__name__)

CHECKER_PROMPT = """
你是严格的网文逻辑编辑。请审查以下章节初稿是否存在**致命的逻辑错误**。

## 核心事实（必须严格遵守）
{state_summary}

## 待审查正文
{chapter_content}

## 审查标准
1. **主角性别一致性**：检查主角（{protagonist_name}，性别：{protagonist_gender}）是否被错误描述为异性。
2. **状态一致性**：境界是否无故倒退？伤势是否未痊愈就生龙活虎？
3. **逻辑常识**：是否存在违反常识的描述（如"他和她是某人的女儿"）。

请直接输出审查结果。如果没有问题，输出：
【PASS】

如果有严重逻辑错误，输出：
【FAIL】
错误详情：(简述错误原因，例如：主角被描述成了女性)
错误类型：(gender|cultivation|status|logic)
正确值：(说明正确的值应该是什么)
"""


class LogicChecker:
    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager

    async def check(self, chapter_num: int, content: str) -> Dict[str, Any]:
        state = self.state_manager.load_state()

        # 提取关键状态用于校验
        protagonist_name = state.protagonist.get("name", "主角")
        
        # 【关键修复】从 character_states 中查找主角的完整信息，而不是只从 protagonist dict 取
        protagonist_state = None
        for cs in state.character_states:
            if cs.name == protagonist_name:
                protagonist_state = cs
                break
        
        # 性别 - 优先从 character_states 取，确保数据完整
        if protagonist_state and protagonist_state.gender:
            protagonist_gender = protagonist_state.gender
        else:
            protagonist_gender = state.protagonist.get("gender", "男")
        
        # 境界
        if protagonist_state and protagonist_state.cultivation:
            protagonist_cultivation = protagonist_state.cultivation
        else:
            protagonist_cultivation = state.protagonist.get("cultivation", "未知")
        
        # 状态
        if protagonist_state and protagonist_state.status:
            protagonist_status = protagonist_state.status
        else:
            protagonist_status = state.protagonist.get("status", "活跃")

        # 构建状态摘要 - 包含完整角色信息
        char_state_info = f"主角: {protagonist_name}\n"
        char_state_info += f"性别: {protagonist_gender}\n"
        char_state_info += f"境界: {protagonist_cultivation}\n"
        char_state_info += f"状态: {protagonist_status}\n"
        
        # 添加其他角色的关键信息
        for cs in state.character_states:
            if cs.name != protagonist_name:
                char_state_info += f"角色 {cs.name}: 性别{'男' if cs.gender == '男' else '女' if cs.gender == '女' else cs.gender or '未知'}，境界 {cs.cultivation or '未知'}，状态 {cs.status}\n"

        prompt = CHECKER_PROMPT.format(
            state_summary=char_state_info,
            chapter_content=content[:4000],
            protagonist_name=protagonist_name,
            protagonist_gender=protagonist_gender,
        )

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是一个无情的逻辑检查机器，专门寻找 AI 写作中的常识性错误和逻辑矛盾。",
            temperature=0.1,
            max_tokens=512,
        )

        if "【PASS】" in response.text:
            logger.info(f"第 {chapter_num} 章逻辑审查通过。")
            return {"success": True, "reason": ""}

        # 提取错误信息
        reason = response.text.split("错误详情：")[-1].strip() if "错误详情：" in response.text else "存在逻辑错误"
        
        # 【关键修复】提取"正确值"信息，用于反馈给写作LLM
        correct_value = ""
        if "正确值：" in response.text:
            correct_value = response.text.split("正确值：")[-1].split("\n")[0].strip()
        
        logger.warning(f"第 {chapter_num} 章逻辑审查失败: {reason}")
        return {
            "success": False, 
            "reason": reason,
            "correct_value": correct_value,  # 新增：正确的值
            "error_type": response.text.split("错误类型：")[-1].split("\n")[0].strip() if "错误类型：" in response.text else "unknown"
        }
