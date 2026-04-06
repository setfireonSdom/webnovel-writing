"""
自动细纲生成系统 - 基于卷大纲自动生成全部章节细纲
职责：
1. 根据卷大纲自动规划章节细纲
2. 批量生成，保持节奏连贯
3. 自动检测断点并续写
4. 集成世界观规则和角色弧光
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from ..data.world_rules import WorldRulesManager
from ..data.character_arc_tracker import CharacterArcTracker
from ..utils.file_ops import read_text_file, write_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)
console = Console()

AUTO_OUTLINE_PROMPT = """
你是专业的网文主编。请根据以下信息，为第 {volume_num} 卷生成**第 {start_chapter} 章到第 {end_chapter} 章**的详细细纲。

## 项目总纲
{master_outline}

## 世界观规则（必须遵守，绝对不能违反）
{world_rules}

## 主角弧光与当前状态
{character_arcs}

## 前情细纲回顾（必须保持剧情连贯，接续这里的剧情）
{prev_outline_summary}

## 任务
请输出这几章的细纲。

### 要求
1. **剧情连贯**：每一章都要有明确的目标和阻碍，接续前情。如果无前情，则是开篇引入。
2. **爽点清晰**：每章必须设计至少一个爽点或期待感（打脸、收获、反转、暧昧等）。
3. **节奏紧凑**：开头要快，迅速切入冲突，不要大段背景介绍。
4. **遵循世界观**：不得违反世界观规则和力量体系。
5. **角色弧光**：符合角色当前成长阶段和心理状态。
6. **格式要求**：请严格按照 JSON 格式输出。

### 节奏规划建议
- 第1-3章：开篇引入主角，建立目标，第一次小冲突/爽点
- 第4-7章：冲突升级，遇到阻碍/对手，展示金手指/能力
- 第8-10章：第一次高潮，解决冲突，收获/突破，留下新悬念
- 以此类推，每5-10章一个小高潮

请输出如下 JSON（只包含这几章）：

```json
{{
  "volume_title": "卷名（根据题材和内容自拟）",
  "chapters": [
    {{
      "chapter_num": {start_chapter},
      "title": "章节标题（4-8字，有吸引力）",
      "plot": "本章剧情概要（发生了什么，具体事件，不要写空话）",
      "conflict": "本章冲突/阻碍（具体是什么人/事/困境）",
      "payoff": "爽点/收获（读者为什么爽，如：打脸XX、获得XX、XX真相揭露）",
      "hook": "结尾悬念/钩子（让读者想继续看的具体悬念）",
      "characters": ["出场角色列表"],
      "location": "地点",
      "strand_type": "quest|fire|constellation",
      "world_rules_notes": "需要注意的世界观规则（如有）"
    }}
  ]
}}
```

**注意**：
- 确保 JSON 格式合法，不要有多余的解释性文字。
- 内容要具体，不要写空话套话（如"主角经历了考验"这种废话不要）。
- 每章剧情必须不同，避免重复套路。
- 爽点要具体（如"主角用XX能力打脸了看不起他的XX"）。
"""


class AutoOutlineGenerator:
    """自动细纲生成器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.project_root = state_manager.project_root
        
        # 加载世界观规则
        try:
            self.world_rules_manager = WorldRulesManager(self.project_root)
        except:
            self.world_rules_manager = None
        
        # 加载角色弧光
        try:
            self.character_arc_tracker = CharacterArcTracker(self.project_root)
        except:
            self.character_arc_tracker = None

    async def generate(
        self, 
        volume_num: int, 
        target_chapters: int,
        batch_size: int = 5,
        auto_continue: bool = True
    ) -> Dict[str, Any]:
        """自动生成细纲
        
        Args:
            volume_num: 卷号
            target_chapters: 目标章节数（如100）
            batch_size: 每批生成章节数（默认5章）
            auto_continue: 是否自动续写（如已有部分细纲）
        
        Returns:
            生成的细纲数据
        """
        console.print(f"\n[bold cyan]🚀 开始自动生成第 {volume_num} 卷细纲（目标: {target_chapters} 章）[/bold cyan]\n")
        
        # 检查已有细纲
        start_chapter = self._get_start_chapter(volume_num, auto_continue)
        
        if start_chapter > target_chapters:
            console.print(f"[green]✓ 第 {volume_num} 卷细纲已完成（已有 {target_chapters} 章）[/green]")
            return {"status": "already_complete", "chapters": target_chapters}
        
        console.print(f"[dim]从第 {start_chapter} 章开始生成[/dim]\n")
        
        all_chapters = []
        
        # 批量生成
        for batch_start in range(start_chapter, target_chapters + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, target_chapters)
            
            console.print(f"[cyan]📝 正在生成第 {batch_start}-{batch_end} 章细纲...[/cyan]")
            
            try:
                batch_result = await self._generate_batch(
                    volume_num=volume_num,
                    start_chapter=batch_start,
                    end_chapter=batch_end,
                    existing_chapters=all_chapters
                )
                
                if batch_result and 'chapters' in batch_result:
                    all_chapters.extend(batch_result['chapters'])
                    console.print(f"[green]✓ 第 {batch_start}-{batch_end} 章生成完成[/green]\n")
                    
                    # 保存进度（防止中断丢失）
                    if all_chapters:
                        self._save_outline(volume_num, {
                            "volume_title": batch_result.get("volume_title", f"第 {volume_num} 卷"),
                            "chapters": all_chapters
                        })
                else:
                    console.print(f"[yellow]⚠ 第 {batch_start}-{batch_end} 章生成失败，跳过[/yellow]\n")
                
            except Exception as e:
                logger.error(f"生成第 {batch_start}-{batch_end} 章失败: {e}")
                console.print(f"[red]✗ 生成失败: {e}[/red]\n")
                break
        
        # 最终保存
        if all_chapters:
            console.print(f"\n[bold green]✓ 第 {volume_num} 卷细纲生成完成！共 {len(all_chapters)} 章[/bold green]\n")
            return {
                "status": "success",
                "volume_title": f"第 {volume_num} 卷",
                "chapters": all_chapters,
                "total_chapters": len(all_chapters)
            }
        else:
            console.print(f"[yellow]⚠ 未生成任何章节[/yellow]\n")
            return {"status": "failed", "chapters": 0}

    def _get_start_chapter(self, volume_num: int, auto_continue: bool) -> int:
        """获取起始章节号"""
        outline_file = self.project_root / "大纲" / "细纲" / f"卷{volume_num}_细纲.json"
        
        if outline_file.exists() and auto_continue:
            try:
                old_data = json.loads(read_text_file(outline_file))
                existing_chapters = old_data.get("chapters", [])
                if existing_chapters:
                    max_existing = max(ch.get("chapter_num", 0) for ch in existing_chapters)
                    console.print(f"[dim]检测到已有 {max_existing} 章细纲，将从第 {max_existing + 1} 章开始追加[/dim]")
                    return max_existing + 1
            except Exception as e:
                logger.warning(f"加载已有细纲失败: {e}")
        
        return 1

    async def _generate_batch(
        self,
        volume_num: int,
        start_chapter: int,
        end_chapter: int,
        existing_chapters: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """生成一批细纲"""
        # 加载总纲
        master_outline_path = self.project_root / "大纲" / "总纲.md"
        if master_outline_path.exists():
            master_outline = read_text_file(master_outline_path)
        else:
            raise FileNotFoundError(f"未找到总纲文件: {master_outline_path}")
        
        # 构建前情摘要
        prev_summary = self._build_context_summary(existing_chapters)
        
        # 获取世界观规则
        world_rules_text = ""
        if self.world_rules_manager:
            world_rules_text = self.world_rules_manager.get_rules_for_context()
        
        # 获取角色弧光
        character_arcs_text = ""
        if self.character_arc_tracker:
            arcs = self.character_arc_tracker.get_all_arcs()
            if arcs:
                arcs_summary = []
                for name, arc in list(arcs.items())[:5]:  # 最多5个角色
                    if arc.snapshots:
                        last = arc.snapshots[-1]
                        arcs_summary.append(f"{name}({arc.role}): 境界={last.cultivation}, 状态={last.status}, 动机={last.motivation}")
                character_arcs_text = "\n".join(arcs_summary)
        
        # 构建提示词
        prompt = AUTO_OUTLINE_PROMPT.format(
            volume_num=volume_num,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            master_outline=master_outline,
            world_rules=world_rules_text or "（暂无世界观规则）",
            character_arcs=character_arcs_text or "（暂无角色弧光）",
            prev_outline_summary=prev_summary or "（无前情）"
        )
        
        # 调用LLM
        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是专业的网文主编，擅长规划剧情节奏和设计爽点。",
            temperature=0.7,
            max_tokens=8192,
        )
        
        # 解析JSON
        return self._parse_json_response(response.text)

    def _build_context_summary(self, existing_chapters: List[Dict[str, Any]]) -> str:
        """构建前情摘要"""
        if not existing_chapters:
            return ""
        
        # 取最近5章
        recent = existing_chapters[-5:]
        summary_parts = []
        for ch in recent:
            summary_parts.append(
                f"第{ch['chapter_num']}章: {ch.get('plot', '')}，"
                f"冲突: {ch.get('conflict', '')}，"
                f"结尾: {ch.get('hook', '')}"
            )
        
        return "\n".join(summary_parts)

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """解析JSON响应"""
        # 尝试提取JSON
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            json_str = match.group(1)
        else:
            json_str = text
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return None

    def _save_outline(self, volume_num: int, data: Dict[str, Any]):
        """保存细纲"""
        outline_dir = self.project_root / "大纲" / "细纲"
        ensure_directory(outline_dir)
        
        outline_file = outline_dir / f"卷{volume_num}_细纲.json"
        
        # 如果文件已存在，加载旧数据并合并
        if outline_file.exists():
            try:
                old_data = json.loads(read_text_file(outline_file))
                existing_chapters = old_data.get("chapters", [])
                
                # 构建已有章节号集合
                existing_nums = {ch["chapter_num"] for ch in existing_chapters}
                
                # 过滤掉重复章节
                new_chapters = [ch for ch in data["chapters"] if ch["chapter_num"] not in existing_nums]
                
                # 合并
                all_chapters = existing_chapters + new_chapters
                all_chapters.sort(key=lambda x: x.get("chapter_num", 0))
                
                data["chapters"] = all_chapters
                data["volume_title"] = old_data.get("volume_title", data.get("volume_title"))
                
            except Exception as e:
                logger.warning(f"加载旧细纲失败: {e}，将覆盖保存")
        
        atomic_write_json(outline_file, data)
        logger.info(f"细纲已保存: {outline_file} (共 {len(data['chapters'])} 章)")
