"""
逻辑审查 Agent
负责检查生成内容是否存在严重逻辑漏洞（如主角变性、境界倒退等）。
"""

import json
import logging
import re
from typing import Dict, Any

from ..llm.base import BaseLLM, LLMResponse
from ..data.state_manager import StateManager

logger = logging.getLogger(__name__)

CHECKER_PROMPT = """
你是严格的网文逻辑编辑。请审查以下章节初稿是否存在**致命的逻辑错误**。

## 核心事实（必须严格遵守）
{state_summary}

## 待审查正文（前 4000 字）
{chapter_content}

## 审查标准
1. **性别一致性**：检查每个角色的性别代词是否与设定一致（男=他，女=她）。
2. **境界一致性**：境界是否无故倒退？
3. **状态一致性**：伤势是否未痊愈就生龙活虎？
4. **逻辑常识**：是否存在违反常识的描述。

请严格按照以下 JSON 格式输出：

```json
{{
  "pass": true,
  "issues": []
}}
```

或者如果有问题：

```json
{{
  "pass": false,
  "issues": [
    {{
      "error_type": "gender|cultivation|status|logic",
      "description": "错误详情",
      "correct_value": "正确的值应该是什么"
    }}
  ]
}}
```

**注意**：
- 如果没有问题，pass 为 true，issues 为空数组
- 如果有多个问题，每个问题都单独列出
- 只输出 JSON，不要输出其他内容
"""


class LogicChecker:
    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager

    async def check(self, chapter_num: int, content: str) -> Dict[str, Any]:
        state = self.state_manager.load_state()

        # 提取关键状态用于校验
        protagonist_name = state.protagonist.get("name", "主角")

        # 从 character_states 中查找主角的完整信息
        protagonist_state = None
        for cs in state.character_states:
            if cs.name == protagonist_name:
                protagonist_state = cs
                break

        # 性别 - 优先从 character_states 取
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
        )

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是一个无情的逻辑检查机器，专门寻找 AI 写作中的常识性错误和逻辑矛盾。只输出JSON，不要输出其他内容。",
            temperature=0.1,
            max_tokens=1024,
        )

        try:
            # 尝试解析 JSON
            result = self._parse_response(response.text)
        except Exception as e:
            # 回退到旧的文本解析方式
            logger.warning(f"第 {chapter_num} 章逻辑审查 JSON 解析失败，使用回退解析: {e}")
            result = self._fallback_parse(response.text)

        if result.get("pass"):
            logger.info(f"第 {chapter_num} 章逻辑审查通过。")
            return {"success": True, "reason": ""}

        # 有 issues，返回第一个问题的详细信息
        issues = result.get("issues", [])
        if issues:
            first_issue = issues[0]
            reason = first_issue.get("description", "存在逻辑错误")
            correct_value = first_issue.get("correct_value", "")
            error_type = first_issue.get("error_type", "unknown")
        else:
            reason = "存在逻辑错误（未提供详细信息）"
            correct_value = ""
            error_type = "unknown"

        # 如果有多个问题，合并描述
        if len(issues) > 1:
            extra_issues = [f"- {i.get('description', '')}" for i in issues[1:]]
            reason += "\n\n其他问题:\n" + "\n".join(extra_issues)

        logger.warning(f"第 {chapter_num} 章逻辑审查失败: {reason}")
        return {
            "success": False,
            "reason": reason,
            "correct_value": correct_value,
            "error_type": error_type,
        }

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """解析 LLM 的 JSON 响应"""
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("未找到 JSON 对象")

    def _fallback_parse(self, text: str) -> Dict[str, Any]:
        """回退的文本解析方式（兼容旧格式）"""
        # 检查是否有 PASS 标记
        if "【PASS】" in text or "PASS" in text:
            return {"pass": True, "issues": []}

        # 尝试提取 FAIL 信息
        reason = text.split("错误详情：")[-1].strip() if "错误详情：" in text else "存在逻辑错误"
        if "错误详情:" in text:  # 也支持英文冒号
            reason = text.split("错误详情:")[-1].strip()

        correct_value = ""
        if "正确值：" in text:
            correct_value = text.split("正确值：")[-1].split("\n")[0].strip()
        elif "正确值:" in text:
            correct_value = text.split("正确值:")[-1].split("\n")[0].strip()

        error_type = "unknown"
        if "错误类型：" in text:
            error_type = text.split("错误类型：")[-1].split("\n")[0].strip()
        elif "错误类型:" in text:
            error_type = text.split("错误类型:")[-1].split("\n")[0].strip()

        return {
            "pass": False,
            "issues": [{
                "error_type": error_type,
                "description": reason,
                "correct_value": correct_value,
            }]
        }
