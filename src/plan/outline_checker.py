"""
大纲自动检查与优化系统
职责：
1. 扫描全卷大纲，检查逻辑、战力、状态连贯性
2. 自动修复不合理的设计（如越级打怪不合理、伤势恢复太快等）
3. 确保全卷逻辑一致性，避免“头痛医头脚痛医脚”
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.prompt import Confirm

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from ..data.world_rules import WorldRulesManager
from ..utils.file_ops import read_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)
console = Console()

OUTLINE_CHECK_PROMPT = """
你是资深的网文主编，拥有 20 年从业经验，最擅长把控剧情逻辑和战力体系。
请对以下大纲进行**全面逻辑体检与优化**。

## ⚠️ 重要约束
**第 1 章到第 {last_written_chapter} 章已经写好了正文！**
- **绝对禁止修改已写章节（1-{last_written_chapter}章）的大纲内容！**
- 你的任务是检查和修复**未写章节（{last_written_chapter+1}章及以后）的大纲**。
- 检查后续大纲时，必须以“已生成的正文内容”作为剧情起点，确保后续剧情和前面正文完美衔接。

## 已生成的正文内容（作为历史依据，不可更改）
{written_chapters_summary}

## 世界观与设定
{world_rules}

## 力量体系等级
{power_system}

## 待检查的大纲（第 {volume_num} 卷）
{outline_json}

## 检查重点（针对未写章节）
1. **与已写正文的衔接性**：后续大纲是否违背了已写正文中的剧情发展？（如正文里主角受了重伤，后续大纲却写他满状态复活？）
2. **战力崩坏**：是否存在严重的越级战斗且无合理铺垫？
3. **状态跳跃**：主角状态是否连续？
4. **逻辑漏洞**：反派是否降智？道具/系统奖励是否突兀？
5. **剧情连贯性**：每一章的 Hook（悬念）是否在下一章得到了接续？

## 任务
1. 找出未写章节中的逻辑硬伤。
2. **微调修复未写章节的大纲**，使其与已写正文无缝衔接。
3. 输出**完整的 JSON 大纲**（已写章节必须保持原样，只修改未写章节）。

请输出修复后的**完整 JSON 大纲**：
```json
{{
  "volume_title": "...",
  "chapters": [ ... ]
}}
```
"""


class OutlineChecker:
    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.project_root = state_manager.project_root

    async def check_and_optimize(self, volume_num: int) -> bool:
        """检查并优化大纲"""
        # 1. 加载大纲
        outline_file = self.project_root / "大纲" / "细纲" / f"卷{volume_num}_细纲.json"
        if not outline_file.exists():
            console.print(f"[red]✗ 未找到第 {volume_num} 卷细纲[/red]")
            return False

        outline_data = json.loads(read_text_file(outline_file))
        chapters = outline_data.get("chapters", [])
        console.print(f"[cyan]🔍 开始检查第 {volume_num} 卷大纲 (共 {len(chapters)} 章)...[/cyan]")

        # 2. 获取已写章节信息（用于保护已写内容）
        written_chapters_summary, last_written = self._get_written_chapters_summary(chapters)

        # 3. 加载设定
        world_rules = ""
        try:
            rules_mgr = WorldRulesManager(self.project_root)
            world_rules = rules_mgr.get_rules_for_context()
        except:
            world_rules = "（暂无明确规则）"

        state = self.state_manager.load_state()
        power_system = ", ".join(state.world.get("realms", ["未知"]))

        # 4. 构建 Prompt
        prompt = OUTLINE_CHECK_PROMPT.format(
            world_rules=world_rules,
            power_system=power_system,
            volume_num=volume_num,
            last_written_chapter=last_written,
            written_chapters_summary=written_chapters_summary,
            outline_json=json.dumps(outline_data, ensure_ascii=False, indent=2)
        )

        # 5. 调用 AI 优化
        console.print("[yellow]⏳ 正在进行深度逻辑分析（可能需要几十秒）...[/yellow]")
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是严格的网文主编，负责修复大纲中的逻辑漏洞。注意：已写章节的大纲绝对不可修改，只修改未写章节。",
                temperature=0.3,  # 低温度保证修改严谨
                max_tokens=16000, # 需要输出完整大纲
            )

            # 解析结果
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                new_outline = json.loads(json_match.group())
                
                # 二次保护：手动覆盖，确保已写章节大纲不被 AI 篡改
                new_outline = self._force_preserve_written_outline(outline_data, new_outline, last_written)
                
                # 确认覆盖
                if Confirm.ask(f"\nAI 检查完成。是否保存优化后的第 {volume_num} 卷大纲？"):
                    atomic_write_json(outline_file, new_outline)
                    console.print(f"[green]✓ 第 {volume_num} 卷大纲已自动修复并保存！[/green]")
                    console.print(f"[dim]（已保护前 {last_written} 章已写大纲不被修改）[/dim]")
                    return True
                else:
                    console.print("[dim]已取消保存。[/dim]")
                    return False
            else:
                console.print("[red]✗ AI 返回格式错误，未找到 JSON[/red]")
                return False

        except Exception as e:
            logger.error(f"大纲检查失败: {e}")
            console.print(f"[red]✗ 检查失败: {e}[/red]")
            return False

    def _get_written_chapters_summary(self, chapters: List[Dict]) -> str:
        """获取已写章节的摘要"""
        content_dir = self.project_root / "正文"
        summaries = []
        last_written = 0

        for ch in chapters:
            ch_num = ch.get("chapter_num", 0)
            ch_file = content_dir / f"ch{ch_num:04d}.md"
            
            if ch_file.exists():
                # 如果正文存在，读取摘要或前 200 字
                try:
                    content = read_text_file(ch_file)
                    summary = content[:300].replace("\n", "")
                    summaries.append(f"第 {ch_num} 章（已写）: {summary}...")
                    last_written = ch_num
                except:
                    pass
            else:
                # 如果正文不存在，说明是未写章节
                summaries.append(f"第 {ch_num} 章（未写）: {ch.get('plot', '无剧情')}")
        
        return "\n".join(summaries), last_written

    def _get_last_written_chapter(self) -> int:
        """获取最后一个已写章节的章节号"""
        content_dir = self.project_root / "正文"
        if not content_dir.exists():
            return 0
        
        written_chapters = []
        for f in content_dir.glob("ch*.md"):
            try:
                num = int(f.stem[2:])
                written_chapters.append(num)
            except:
                pass
        
        return max(written_chapters) if written_chapters else 0

    def _force_preserve_written_outline(self, old_outline, new_outline, last_written: int) -> Dict:
        """强制保护已写章节的大纲，防止 AI 篡改"""
        if not new_outline or 'chapters' not in new_outline:
            return old_outline

        old_chapters = {ch['chapter_num']: ch for ch in old_outline.get('chapters', [])}
        new_chapters = {ch['chapter_num']: ch for ch in new_outline.get('chapters', [])}

        # 遍历已写章节，强制用旧大纲覆盖新大纲
        for ch_num in range(1, last_written + 1):
            if ch_num in old_chapters and ch_num in new_chapters:
                new_chapters[ch_num] = old_chapters[ch_num]
        
        # 重新组装
        final_chapters = sorted(new_chapters.values(), key=lambda x: x.get('chapter_num', 0))
        new_outline['chapters'] = final_chapters
        return new_outline