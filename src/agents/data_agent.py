"""
Data Agent - 数据代理
负责实体提取、状态更新、索引构建、章节摘要生成、剧情线追踪
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from ..data.plot_thread_tracker import PlotThreadTracker
from ..data.schemas import Entity, CharacterState
from ..utils.file_ops import (
    atomic_write_json,
    read_text_file,
    write_text_file,
    chapter_file_path,
    ensure_directory,
)
from .base import BaseAgent

from ..data.rag_adapter import BM25RAG

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = """
你是专业的网文数据分析专家。请从章节内容中提取以下实体信息：

## 项目现有实体
{existing_entities}

## 活跃剧情线（请注意是否回收或推进了这些线）
{active_threads}

## 章节内容
{chapter_content}

## 任务
1. 提取本章出现的所有实体（角色、地点、势力、物品等）
2. 标注实体类型
3. 记录实体之间的关系
4. 提取章节关键信息（境界变化、能力使用、重要事件等）
5. 提取角色状态变化（修为、关系、持有物品等）
6. **角色知识状态追踪**：
   - 本章中角色得知了什么新信息？
   - 角色是否隐瞒了某些信息？
   - 角色之间存在哪些信息差？（谁知道什么，谁不知道）
7. **剧情线/伏笔管理**：
   - 是否开启了新的伏笔/悬念？
   - 是否回收了旧的伏笔？
   - 是否推进了正在进行的剧情线？
8. 生成本章剧情摘要（200字内）

请严格按照以下 JSON 格式输出：

```json
{{
  "entities": [
    {{
      "name": "实体名称",
      "entity_type": "character|location|faction|item|ability",
      "description": "描述",
      "attributes": {{}},
      "status": "active|inactive|deceased"
    }}
  ],
  "character_states": [
    {{
      "name": "角色名",
      "gender": "男|女|其他（从上下文判断，不确定则留空）",
      "cultivation": "修为境界",
      "status": "active|injured|deceased|other",
      "personality": "性格特征（如：冷酷、狡猾、热血）",
      "traits": ["特征1", "特征2"],
      "background": "背景故事摘要",
      "relationships": {{"角色名": "关系描述"}},
      "key_items": ["物品1", "物品2"],
      "knowledge": [
        "角色知道的关键信息（如：'知道X是卧底'、'不知道Y已死'、'发现了Z的秘密'）"
      ],
      "aliases": ["别名/称号"],
      "notes": "状态备注"
    }}
  ],
  "chapter_summary": "本章剧情摘要（200字内，说明发生了什么大事）",
  "key_events": ["关键事件1", "关键事件2"],
  "strand_type": "quest|fire|constellation",
  "hook_strength": 75,
  "cool_point_count": 2,
  "plot_threads_update": {{
    "new_threads": [
      {{
        "description": "伏笔描述",
        "type": "foreshadowing|mystery|conflict",
        "priority": "low|medium|high|critical",
        "expected_payoff_chapter": null
      }}
    ],
    "updates": [
      {{
        "thread_id": "thread_xxxx",
        "status": "open|resolved|abandoned",
        "summary": "回收/推进情况说明"
      }}
    ]
  }}
}}
```

**注意**：
- 只提取新出现的实体或状态发生变化的实体
- 角色状态必须准确反映本章结尾的情况
- 摘要要包含关键剧情节点
"""


class DataAgent(BaseAgent):
    """数据代理"""

    name = "data-agent"
    description = "实体提取、状态更新、索引构建、章节摘要生成、剧情线追踪"

    def __init__(self, llm: BaseLLM, state_manager: StateManager, config: Dict[str, Any] = None):
        super().__init__(llm, config)
        self.state_manager = state_manager
        # 使用 state_manager 的项目根目录
        project_root = state_manager.project_root
        try:
            self.thread_tracker = PlotThreadTracker(project_root)
        except Exception as e:
            logger.warning(f"初始化剧情线追踪器失败: {e}")
            self.thread_tracker = None

    async def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """执行数据处理任务

        Args:
            input: {
                "chapter_num": 章节号,
                "chapter_content": 章节内容,
                "project_root": 项目根目录,
            }

        Returns:
            {
                "entities": 提取的实体列表,
                "chapter_summary": 章节摘要,
                "key_events": 关键事件,
                "strand_type": 情节线类型,
                "hook_strength": 钩子强度,
                "cool_point_count": 爽点数量,
            }
        """
        chapter_num = input["chapter_num"]
        chapter_content = input["chapter_content"]
        project_root = Path(input.get("project_root", "."))

        # 获取现有实体
        existing_entities = self.state_manager.get_entities()
        entities_str = json.dumps(
            [e.model_dump() for e in existing_entities],
            ensure_ascii=False,
            indent=2,
        )

        # 获取活跃剧情线
        active_threads_str = ""
        if self.thread_tracker:
            active_threads = self.thread_tracker.get_active_threads()
            if active_threads:
                lines = [f"- [{t.type}] {t.description} (ID: {t.id})" for t in active_threads]
                active_threads_str = "\n".join(lines)
            else:
                active_threads_str = "（当前无活跃剧情线）"
        else:
            active_threads_str = "（剧情线追踪器未启用）"

        # 构建提示词
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            existing_entities=entities_str,
            active_threads=active_threads_str,
            chapter_content=chapter_content[:8000],  # 限制长度
        )

        # 调用 LLM 提取实体
        logger.info(f"Data Agent 开始提取第 {chapter_num} 章的实体信息")
        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是专业的网文数据分析助手，擅长从文本中提取结构化信息。",
            temperature=0.3,  # 低温度，提高准确性
            max_tokens=self.max_tokens,
        )

        # 解析响应
        result = self.parse_response(response.text)

        # 更新项目状态
        await self._update_state(chapter_num, result, project_root)

        # 建立 RAG 索引
        self._index_rag(chapter_num, chapter_content, project_root)
        
        # 更新剧情线
        self._update_plot_threads(chapter_num, result.get("plot_threads_update", {}))

        logger.info(f"Data Agent 完成第 {chapter_num} 章的数据处理")
        return result

    def _update_plot_threads(self, chapter_num: int, update_data: Dict[str, Any]):
        """更新剧情线状态"""
        if not self.thread_tracker or not update_data:
            return

        # 添加新剧情线
        for new_thread in update_data.get("new_threads", []):
            self.thread_tracker.add_thread(
                chapter_num=chapter_num,
                description=new_thread.get("description", ""),
                p_type=new_thread.get("type", "foreshadowing"),
                priority=new_thread.get("priority", "medium"),
                expected_payoff_chapter=new_thread.get("expected_payoff_chapter"),
            )

        # 更新现有剧情线
        for upd in update_data.get("updates", []):
            thread_id = upd.get("thread_id")
            status = upd.get("status")
            summary = upd.get("summary", "")
            
            # AI 可能返回 ID 或描述来匹配，这里尝试 ID 匹配
            if thread_id and thread_id in self.thread_tracker.threads:
                self.thread_tracker.update_thread(
                    thread_id=thread_id,
                    chapter_num=chapter_num,
                    status=status if status else None,
                    summary=summary,
                )
            else:
                # 如果没有 ID，尝试通过描述模糊匹配（这里简化为不处理，要求 AI 必须返回 ID）
                logger.warning(f"未找到剧情线 ID: {thread_id}，跳过更新")
    
    def _index_rag(self, chapter_num: int, content: str, project_root: Path):
        """建立 RAG 索引"""
        try:
            rag = BM25RAG(project_root)
            rag.add_chapter(chapter_num, content)
            logger.info(f"第 {chapter_num} 章 RAG 索引建立完成")
        except Exception as e:
            logger.warning(f"建立 RAG 索引失败: {e}")
    
    async def _update_state(self, chapter_num: int, result: Dict[str, Any], project_root: Path):
        """更新项目状态（批量保存，避免多次读写）"""
        state = self.state_manager.load_state()

        # 收集所有待更新的实体
        entities_data = result.get("entities", [])
        entities_to_add = []
        for entity_data in entities_data:
            entity = Entity(
                name=entity_data["name"],
                entity_type=entity_data["entity_type"],
                description=entity_data.get("description", ""),
                attributes=entity_data.get("attributes", {}),
                first_appearance_chapter=chapter_num,
                last_appearance_chapter=chapter_num,
                status=entity_data.get("status", "active"),
            )
            entities_to_add.append(entity)

        # 批量添加实体（避免每次 add_entity 都保存一次）
        if entities_to_add:
            existing_entities = state.entities.setdefault("all", [])
            for entity in entities_to_add:
                entity_dict = entity.model_dump()
                # 检查是否已存在
                found = False
                for i, e in enumerate(existing_entities):
                    if e.get("name") == entity.name and e.get("entity_type") == entity.entity_type:
                        existing_entities[i] = entity_dict
                        found = True
                        break
                if not found:
                    existing_entities.append(entity_dict)

        # 更新角色状态快照
        character_states_data = result.get("character_states", [])
        if character_states_data:
            for cs_data in character_states_data:
                cs = CharacterState(
                    name=cs_data["name"],
                    gender=cs_data.get("gender", ""),  # 【修复】添加性别
                    cultivation=cs_data.get("cultivation", ""),
                    status=cs_data.get("status", "active"),
                    personality=cs_data.get("personality", ""),  # 【修复】添加性格
                    traits=cs_data.get("traits", []),  # 【修复】添加特征
                    background=cs_data.get("background", ""),  # 【修复】添加背景
                    relationships=cs_data.get("relationships", {}),
                    key_items=cs_data.get("key_items", []),
                    knowledge=cs_data.get("knowledge", []),  # 【修复】添加知识
                    aliases=cs_data.get("aliases", []),  # 【修复】添加别名
                    notes=cs_data.get("notes", ""),
                )
                # 合并或追加
                existing_idx = None
                for i, existing_cs in enumerate(state.character_states):
                    if existing_cs.name == cs.name:
                        existing_idx = i
                        break

                if existing_idx is not None:
                    # 【修复】合并而非完全替换，保留未更新的字段
                    existing_cs = state.character_states[existing_idx]
                    # 只更新非空值
                    if cs.gender:
                        existing_cs.gender = cs.gender
                    if cs.cultivation:
                        existing_cs.cultivation = cs.cultivation
                    if cs.status != "active":
                        existing_cs.status = cs.status
                    if cs.personality:
                        existing_cs.personality = cs.personality
                    if cs.traits:
                        existing_cs.traits = cs.traits
                    if cs.background:
                        existing_cs.background = cs.background
                    if cs.relationships:
                        existing_cs.relationships.update(cs.relationships)
                    if cs.key_items:
                        existing_cs.key_items = cs.key_items
                    if cs.knowledge:
                        existing_cs.knowledge = cs.knowledge
                    if cs.aliases:
                        existing_cs.aliases = cs.aliases
                    if cs.notes:
                        existing_cs.notes = cs.notes
                else:
                    state.character_states.append(cs)

        # 更新最近剧情摘要
        chapter_summary = result.get("chapter_summary", "")
        state.recent_summary = chapter_summary

        # 保存章节摘要
        summary_dir = project_root / ".webnovel" / "summaries"
        ensure_directory(summary_dir)
        summary_file = summary_dir / f"ch{chapter_num:04d}.md"
        write_text_file(summary_file, f"# 第 {chapter_num} 章摘要\n\n{chapter_summary}\n")

        # 更新进度
        state.progress["current_chapter"] = chapter_num
        state.progress["last_updated"] = datetime.now().isoformat()

        # 更新阅读力数据
        state.reading_power.update({
            "last_chapter": chapter_num,
            "hook_strength": result.get("hook_strength", 0),
            "cool_point_count": result.get("cool_point_count", 0),
            "updated_at": datetime.now().isoformat(),
        })

        # 一次性保存所有状态变更
        self.state_manager.save_state(state)
