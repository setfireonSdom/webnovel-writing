"""
规划模块
负责生成卷纲和章节细纲
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.console import Console

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from ..data.schemas import ProjectState
from ..utils.file_ops import read_text_file, write_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)
console = Console()

PLAN_VOLUME_PROMPT = """
你是专业的网文主编。请根据以下项目总纲和**前情细纲**，为第 {volume_num} 卷生成**第 {start_chapter} 章到第 {end_chapter} 章**的详细细纲。

## 项目总纲
{master_outline}

## 主角设定
{protagonist_info}

## 前情细纲回顾（必须保持剧情连贯，接续最后的钩子）
{prev_outline_summary}

## 任务
请输出这几章的细纲。

要求：
1. **剧情连贯**：每一章都要有明确的目标和阻碍。
2. **爽点清晰**：每章必须设计至少一个爽点或期待感。
3. **节奏紧凑**：开头要快，迅速切入冲突。
4. **感情线丰富**：请在剧情中巧妙融入主角与不同角色的互动、情感羁绊以及由此带来的成长（修为提升、资源获取、势力壮大等）。
5. **格式要求**：请严格按照 JSON 格式输出。

请输出如下 JSON（只包含这几章）：

```json
{{
  "volume_title": "卷名",
  "chapters": [
    {{
      "chapter_num": {start_chapter},
      "title": "章节标题",
      "plot": "本章剧情概要（发生了什么）",
      "conflict": "本章冲突/阻碍",
      "payoff": "爽点/收获",
      "hook": "结尾悬念/钩子",
      "characters": ["出场角色"],
      "location": "地点"
    }}
  ]
}}
```

**注意**：
- 确保 JSON 格式合法，不要有多余的解释性文字。
- 内容要具体，不要写空话。
"""


class PlanVolumeAgent:
    """卷纲规划 Agent"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager

    async def execute(self, volume_num: int, num_chapters: int) -> Dict[str, Any]:
        """执行规划任务"""
        console.print(f"[bold]开始规划第 {volume_num} 卷（{num_chapters} 章）细纲...[/bold]")

        # 读取总纲
        project_root = self.state_manager.project_root
        master_outline_path = project_root / "大纲" / "总纲.md"
        if master_outline_path.exists():
            master_outline = read_text_file(master_outline_path)
        else:
            raise FileNotFoundError(f"未找到总纲文件: {master_outline_path}")

        state = self.state_manager.load_state()
        
        # 检查已有细纲，确定起始章节
        start_chapter = 1
        outline_file = project_root / "大纲" / "细纲" / f"卷{volume_num}_细纲.json"
        if outline_file.exists():
            try:
                old_data = json.loads(read_text_file(outline_file))
                existing_chapters = old_data.get("chapters", [])
                if existing_chapters:
                    max_existing = max(ch.get("chapter_num", 0) for ch in existing_chapters)
                    
                    # 【保护锁】：如果用户要求的章节数 <= 已有的最大章节号，说明不需要新增
                    if num_chapters <= max_existing:
                         console.print(f"[green]✓ 第 {volume_num} 卷细纲已存在（已有 {max_existing} 章）。")
                         console.print("[bold yellow]⚠ 保护机制触发：为了防止已有细纲、正文、状态记录出现逻辑冲突，程序【绝不会】自动覆盖或重新生成旧大纲。[/bold yellow]")
                         console.print("如需修改旧大纲，请手动编辑 JSON 文件。")
                         return old_data
                    
                    # 只有当要求的章节更多时，才从断点处开始追加
                    start_chapter = max_existing + 1
                    console.print(f"[yellow]检测到已有 {max_existing} 章细纲，将从第 {start_chapter} 章开始追加[/yellow]")
            except Exception:
                pass # 解析失败则从头开始

        if start_chapter > num_chapters:
            return {"chapters": []}

        all_chapters = []
        batch_size = 3
        
        # 初始化前情摘要变量
        prev_outline_summary = ""
        if outline_file.exists():
            try:
                old_data = json.loads(read_text_file(outline_file))
                existing_chapters = old_data.get("chapters", [])
                if existing_chapters:
                    # 取最后 5 章的细纲作为直接上下文
                    recent_context = existing_chapters[-5:]
                    summary_parts = []
                    for ch in recent_context:
                        summary_parts.append(f"第{ch['chapter_num']}章: {ch.get('plot', '')}，冲突: {ch.get('conflict', '')}，结尾: {ch.get('hook', '')}")
                    prev_outline_summary = "\n".join(summary_parts)
            except Exception:
                pass

        for start in range(start_chapter, num_chapters + 1, batch_size):
            end = min(start + batch_size - 1, num_chapters)
            console.print(f"[cyan]正在生成第 {start}-{end} 章细纲...[/cyan]")

            # 动态更新前情回顾：结合文件里的旧细纲 + 本次刚刚生成的新细纲
            # 这样即使是连续生成 1-50 章，后一批也能看到前一批的内容
            context_summary_parts = prev_outline_summary.split('\n') if prev_outline_summary else []
            
            # 加上本次运行中已生成的章节
            if all_chapters:
                for ch in all_chapters[-5:]: # 取最近 5 章
                    context_summary_parts.append(f"第{ch['chapter_num']}章: {ch.get('plot', '')}，冲突: {ch.get('conflict', '')}，结尾: {ch.get('hook', '')}")
            
            # 重新拼接
            dynamic_summary = "\n".join(context_summary_parts)
            
            prompt = PLAN_VOLUME_PROMPT.format(
                volume_num=volume_num,
                start_chapter=start,
                end_chapter=end,
                master_outline=master_outline,
                protagonist_info=json.dumps(state.protagonist, ensure_ascii=False, indent=2),
                prev_outline_summary=dynamic_summary,
            )

            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是专业的网文主编，擅长规划剧情节奏和设计爽点。",
                temperature=0.7,
                max_tokens=8192,
            )

            # 解析 JSON
            match = re.search(r"```json\s*([\s\S]*?)\s*```", response.text)
            if match:
                json_str = match.group(1)
            else:
                json_str = response.text

            try:
                batch_result = json.loads(json_str)
                all_chapters.extend(batch_result.get("chapters", []))
            except json.JSONDecodeError as e:
                console.print(f"[yellow]第 {start}-{end} 章细纲解析失败，跳过[/yellow]")
        
        result = {
            "volume_title": f"第 {volume_num} 卷",
            "chapters": all_chapters
        }

        # 保存细纲
        self._save_outline(volume_num, result, project_root)
        
        console.print(f"[bold green]✓ 第 {volume_num} 卷细纲生成完毕！共 {len(all_chapters)} 章[/bold green]")
        return result

    def _save_outline(self, volume_num: int, data: Dict[str, Any], project_root: Path):
        """保存细纲到文件（追加模式，不覆盖已有章节）"""
        outline_dir = project_root / "大纲" / "细纲"
        ensure_directory(outline_dir)

        outline_file = outline_dir / f"卷{volume_num}_细纲.json"
        
        # 如果文件已存在，加载旧数据并追加
        existing_data = {"volume_title": data.get("volume_title", f"第 {volume_num} 卷"), "chapters": []}
        if outline_file.exists():
            try:
                old_data = json.loads(read_text_file(outline_file))
                existing_data["volume_title"] = old_data.get("volume_title", existing_data["volume_title"])
                existing_data["chapters"] = old_data.get("chapters", [])
                
                # 去重：如果新章节的 chapter_num 已存在，覆盖旧的
                old_chapter_nums = {ch["chapter_num"] for ch in existing_data["chapters"]}
                for new_ch in data.get("chapters", []):
                    if new_ch["chapter_num"] in old_chapter_nums:
                        # 删除旧的同章节条目
                        existing_data["chapters"] = [ch for ch in existing_data["chapters"] 
                                                     if ch["chapter_num"] != new_ch["chapter_num"]]
                
                # 追加新章节
                existing_data["chapters"].extend(data.get("chapters", []))
                # 按章节号排序
                existing_data["chapters"].sort(key=lambda x: x.get("chapter_num", 0))
            except Exception as e:
                console.print(f"[yellow]⚠ 加载旧细纲失败: {e}，将创建新文件[/yellow]")
        
        atomic_write_json(outline_file, existing_data)
        console.print(f"[green]细纲已保存至: {outline_file} (共 {len(existing_data['chapters'])} 章)[/green]")
