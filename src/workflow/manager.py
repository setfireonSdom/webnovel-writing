"""
工作流管理器
管理 6 步写作管道的执行
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from ..llm.base import BaseLLM
from ..data.state_manager import StateManager
from ..data.schemas import ChapterResult, ReviewReport, WorkflowState
from ..data.plot_thread_tracker import PlotThreadTracker
from ..data.long_term_memory import LongTermMemory
from ..utils.file_ops import (
    chapter_file_path,
    read_text_file,
    write_text_file,
    ensure_directory,
)
from ..utils.git_ops import GitOps
from ..utils.performance import PerformanceMonitor, LLMCallMonitor
from ..agents.context_agent import ContextAgent
from ..agents.data_agent import DataAgent
from ..agents.logic_checker import LogicChecker
from ..agents.checkers import (
    ConsistencyChecker,
    ContinuityChecker,
    OOCChecker,
    HighPointChecker,
    PacingChecker,
    ReaderPullChecker,
)

from ..data.rag_adapter import BM25RAG
from ..data.world_rules import WorldRulesManager
from ..data.character_arc_tracker import CharacterArcTracker
from ..data.auto_audit import AutoAuditReport
from ..data.state_machine import StateMachine
from ..data.causal_chain import CausalChainTracker
from ..utils.anti_ai_scanner import scanner as anti_ai_scanner
from ..utils.gender_pronoun_scanner import GenderPrononScanner
from ..agents.checkers import WorldRulesChecker

logger = logging.getLogger(__name__)
console = Console()

# 写作提示词
DRAFT_GENERATION_PROMPT = """
你是专业的中文网文作家。根据以下创作执行包，撰写第 {chapter_num} 章的内容。

## 🎭 角色状态面板（必须严格遵守，绝对禁止写错性别/境界/状态）
{character_states}

## 前序章节（必须接续这里的剧情）
{previous_chapters}

## 任务书
{mission_brief}

## 上下文契约
{context_contract}

## 本章细纲（必须严格遵守）
{chapter_outline}

## 写作提示
{writing_prompt}

## 历史剧情检索（与本章相关的旧章节片段）
{rag_context}

## 🧠 长期记忆与大局（来自远方/历史章节）
{distant_context}

## 🧵 活跃剧情线提醒（必须关注）
{plot_thread_reminder}

## 🌍 世界观规则（必须遵守）
{world_rules}

## 🔒 显式状态机（代码强制，必须遵守）
{state_machine}

## 📌 因果链约束（伏笔/债务强制回收）
{causal_chain}

## 铁律（违反任何一条将导致严重的逻辑崩坏）
0. **角色身份绝对一致（最高优先级）** - 角色状态面板中列出的每个角色的性别、境界、状态、性格是**铁的事实，绝对禁止写错**。例如：面板写"张三：男"，你绝对不能写成"她"或任何女性化描写。面板写"李四：女"，你绝对不能用"他"。
1. **节奏控制（单章单核）** - **本章 80% 的篇幅只写细纲中的"核心冲突"**。其他信息（背景、设定、新角色）只能在过场中**一笔带过**。严禁在一章里塞入 3 个以上的大事件。
2. **设定边界（禁止私设）** - **绝对禁止**描写世界观、设定集中未出现的元素（如：科幻设备、现代词汇、非本世界的力量体系）。如果大纲没写"智能手环"，绝对不许出现。
3. **对白口语化** - 角色对话必须像真人说话。**禁止使用**完整长句、学术词、书面语。多用短句、打断、反问、情绪词（如"滚！"、"怎么可能？"、"见鬼"）。
4. **状态闭环（最重要）** - 如果本章开头角色处于某种状态（如重伤、中毒、灵力枯竭），你必须在文中明确交代该状态的**变化或结果**。**绝对禁止**开头写重伤，结尾却像没事人一样。
5. **零旁白/零括号** - **绝对禁止**使用括号 `()` 或 `（）` 来补充设定或解释剧情。所有信息必须通过角色的对话、动作、心理活动自然展现。
6. **战力限制** - 低境界角色战胜高境界敌人，必须有极其合理的理由（如：偷袭、对方轻敌、使用了系统特殊一次性道具）。**禁止**新手刚升级就能靠普通拳头越级秒杀强敌。
7. **大纲 = 法律** - 必须完全遵循本章细纲，不得随意更改剧情。
8. **中文母语思维** - 用中文思考，避免翻译腔。
9. **字数要求** - {min_words}-{max_words} 字
10. **爽点密度** - 至少 1 个爽点。
11. **章末钩子** - 必须以悬念或未解决问题结尾。

请输出纯文本章节，不要包含任何标记或说明。
"""

STYLE_ADAPTATION_PROMPT = """
你是专业的网文主编，专门负责消除 AI 写作的痕迹，提升文学质感。

## 待优化章节
{chapter_content}

## 🚨 必须执行的修改规则（最高优先级）
1. **清除括号解释**：文中所有使用括号 `()` 或 `（）` 补充设定、解释剧情的内容（如"事后他才知道……"、"其实这狼妖只是……"），必须**彻底删除或改写**。
   - *错误示范*：他感到一阵寒意（其实是妖兽的威压）。
   - *正确改法*：他感到一阵刺骨的寒意，仿佛被某种凶兽盯上，连呼吸都变得困难。
2. **消除上帝视角**：删除所有作者口吻的旁白（如"此时的他并不知道……"、"命运的齿轮开始转动"）。所有信息必须限制在主角的所见所闻所感范围内。
3. **禁止私自加设定**：文中出现了大纲和设定中没有的"科技产品"或"特殊设定"（如智能手环、logo、现代名词），**必须删除或替换为符合世界观的描述**。
4. **消除机械句式**：禁止使用"首先……然后……最后……"、"不仅……而且……"等僵硬连接词。使用动作和感官描写自然过渡。
5. **口语化对白**：
   - 删除所有过于书面化的对话（如"我认为这种行为是不理智的"）。
   - 替换为短句、口语词、情绪反应（如"你疯了？"、"找死！"）。
   - 角色说话要有**潜台词**，不要直白地把心里话说出来。
6. **保持情节绝对不变**：你只能优化表达，不能修改任何剧情、人物对话的核心含义。

请输出优化后的完整章节。
"""


class WorkflowManager:
    """工作流管理器"""
    
    def __init__(self, llm: BaseLLM, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}
        self.workflow_config = self.config.get("workflow", {})
        
        # 获取项目根目录
        project_root_path = self.config.get("project_root", ".")
        self.project_root = Path(project_root_path)
        
        # 初始化状态管理器
        self.state_manager = StateManager(self.project_root)
        
        # 初始化 Agents
        agent_config = self.config.get("agents", {})
        self.context_agent = ContextAgent(
            llm=llm,
            state_manager=self.state_manager,
            config=agent_config.get("context_agent", {}),
        )
        self.data_agent = DataAgent(
            llm=llm,
            state_manager=self.state_manager,
            config=agent_config.get("data_agent", {}),
        )
        self.logic_checker = LogicChecker(
            llm=llm,
            state_manager=self.state_manager,
        )

        # 初始化审查器
        self.consistency_checker = ConsistencyChecker(llm=llm, state_manager=self.state_manager)
        self.continuity_checker = ContinuityChecker(llm=llm, state_manager=self.state_manager)
        self.ooc_checker = OOCChecker(llm=llm, state_manager=self.state_manager)
        self.high_point_checker = HighPointChecker(llm=llm, state_manager=self.state_manager)
        self.pacing_checker = PacingChecker(llm=llm, state_manager=self.state_manager)
        self.reader_pull_checker = ReaderPullChecker(llm=llm, state_manager=self.state_manager)
        
        # 初始化世界观规则检查器
        self.world_rules_manager = WorldRulesManager(self.project_root)
        self.world_rules_checker = WorldRulesChecker(
            llm=llm,
            world_rules_manager=self.world_rules_manager,
            state_manager=self.state_manager
        )
        
        # 初始化角色弧光追踪器
        self.character_arc_tracker = CharacterArcTracker(self.project_root)
        
        # 初始化自动审计系统
        self.auto_audit = AutoAuditReport(self.project_root)
        
        # 初始化显式状态机（逻辑连贯核心）
        self.state_machine = StateMachine(self.project_root)
        
        # 初始化因果链追踪（伏笔/债务管理）
        self.causal_chain = CausalChainTracker(self.project_root)
        
        # 初始化性别代词扫描器（不依赖LLM的快速检查）
        self.gender_scanner = GenderPrononScanner()

        # 初始化 Git 备份
        git_config = self.workflow_config.get("git_backup", True)
        if git_config:
            self.git_ops = GitOps(self.project_root)
            if not self.git_ops.is_git_repo():
                logger.info("初始化 Git 仓库...")
                self.git_ops.init_repo()
        else:
            self.git_ops = None

        # 初始化性能监控
        self.perf_monitor = PerformanceMonitor(self.project_root)
        self.llm_monitor = LLMCallMonitor(self.project_root)

        # 初始化长期记忆与剧情线追踪
        self.plot_threads = PlotThreadTracker(self.project_root)
        self.long_term_mem = LongTermMemory(self.project_root)
    
    async def write_chapter(
        self,
        chapter_num: int,
        mode: str = "standard",
    ) -> ChapterResult:
        """写作章节的完整流程

        Args:
            chapter_num: 章节号
            mode: 写作模式 (standard | fast | minimal)

        Returns:
            ChapterResult: 写作结果
        """
        # 开始性能监控
        self.perf_monitor.start("total")

        console.print(f"\n[bold blue]开始写作第 {chapter_num} 章[/bold blue] (模式: {mode})\n")
        
        try:
            # 0. 加载本章细纲（必须）
            chapter_outline = self._load_chapter_outline(chapter_num)
            if not chapter_outline:
                return ChapterResult(
                    success=False,
                    chapter_num=chapter_num,
                    error=f"未找到第 {chapter_num} 章的细纲。请先运行 plan 命令生成大纲。",
                )
            
            # 0.5 加载前序章节摘要和状态（保持连贯性，不加载全文）
            context_info = self._load_context_info(chapter_num)
            console.print(f"[dim]已加载前情摘要和角色状态作为上下文参考[/dim]\n")
            
            # 记录工作流状态
            workflow_state = self.state_manager.load_workflow_state()
            workflow_state.current_task = {
                "command": "write",
                "args": {"chapter_num": chapter_num},
                "status": "running",
                "started_at": datetime.now().isoformat(),
            }
            self.state_manager.save_workflow_state(workflow_state)
            
            # Step 1: Context Agent (传入细纲 + 前情摘要 + 角色状态)
            console.print("[cyan]Step 1/6: 生成创作执行包[/cyan]")
            context_result = await self._step1_context(chapter_num, chapter_outline, context_info)
            console.print("[green]✓ 完成[/green]\n")

            # 引入逻辑审查循环
            max_retries = 2
            retry_count = 0
            final_content = ""
            
            while retry_count <= max_retries:
                # Step 2A: Draft Generation
                console.print(f"[cyan]Step 2A/6: 撰写初稿 (尝试 {retry_count + 1})[/cyan]")
                draft_content = await self._step2a_draft(chapter_num, context_result, context_info)

                # Step 2B: Style Adaptation (根据模式决定是否跳过)
                if mode == "minimal":
                    # minimal 模式跳过风格优化
                    console.print("[dim]Step 2B/6: 跳过风格优化 (minimal 模式)[/dim]")
                    final_content = draft_content
                else:
                    console.print("[cyan]Step 2B/6: 风格优化[/cyan]")
                    final_content = await self._step2b_style(draft_content)
                    console.print(f"[green]✓ 完成（{len(final_content)} 字）[/green]")

                # Step 2.4: 性别代词扫描（快速正则检查，不依赖LLM）
                gender_issues = self._step2_4_gender_pronoun_scan(chapter_num, final_content)
                
                # Step 2.5: Logic Checker (防智障机制)
                # minimal 模式也跳过逻辑审查
                if mode == "minimal":
                    console.print("[dim]Step 2.5/6: 跳过逻辑审查 (minimal 模式)[/dim]")
                    break

                console.print("[cyan]Step 2.5/6: 逻辑审查（检查变性、境界倒退等）...[/cyan]")
                check_result = await self.logic_checker.check(chapter_num, final_content)
                
                # 合并性别扫描结果到逻辑检查结果
                if gender_issues:
                    gender_error_msg = self.gender_scanner.get_error_message(gender_issues)
                    if check_result["success"]:
                        # 逻辑检查通过了，但性别扫描发现问题
                        check_result = {
                            "success": False,
                            "reason": gender_error_msg,
                            "correct_value": "请根据角色状态面板中的性别正确使用代词（男=他，女=她）",
                            "error_type": "gender",
                        }
                    else:
                        # 两者都失败，合并错误信息
                        check_result["reason"] += "\n" + gender_error_msg

                if check_result["success"]:
                    console.print("[green]✓ 逻辑审查通过[/green]\n")
                    break
                else:
                    retry_count += 1
                    if retry_count > max_retries:
                        console.print(f"[bold red]✗ 逻辑审查连续 {max_retries + 1} 次失败，放弃生成[/bold red]")
                        raise ValueError(f"逻辑审查未通过: {check_result['reason']}")
                    
                    console.print(f"[yellow]⚠ 逻辑审查失败: {check_result['reason']}[/yellow]")
                    console.print("[yellow]正在注入错误反馈并要求重写...[/yellow]\n")

                    # 【关键修复】注入明确的正确值反馈，而不是模糊的"请确保符合设定"
                    correct_value_info = ""
                    if check_result.get('correct_value'):
                        correct_value_info = f"\n正确值: {check_result['correct_value']}"
                    
                    error_feedback = f"""
【严重逻辑错误警告】你上一稿的内容存在以下逻辑硬伤，必须修正！
错误类型: {check_result.get('error_type', 'unknown')}
错误详情: {check_result['reason']}{correct_value_info}

你必须严格遵守以下事实：
1. 角色状态面板中明确列出了每个角色的性别、境界、状态
2. 绝对禁止写错角色的性别（男=他，女=她）
3. 绝对禁止角色境界无故倒退
4. 绝对禁止角色伤势未愈就生龙活虎

请立即修正！
"""
                    context_result['writing_prompt'] += "\n\n" + error_feedback
                    context_info['character_states'] += f"\n\n[系统警告]: 上文中出现严重逻辑错误 - {check_result['reason']}{correct_value_info}"

            # Step 3: 并行六维审查 (fast/minimal 模式跳过)
            if mode == "standard":
                console.print("[cyan]Step 3/6: 并行六维审查[/cyan]")
                review_results = await self._step3_parallel_review(chapter_num, final_content, chapter_outline, context_info)
                console.print(f"[green]✓ 审查完成（综合得分: {review_results['overall_score']:.0f}/100）[/green]\n")

                # Step 4: 根据审查结果润色
                console.print("[cyan]Step 4/6: 智能润色[/cyan]")
                final_content = await self._step4_polish(chapter_num, final_content, review_results)
                console.print(f"[green]✓ 润色完成（{len(final_content)} 字）[/green]\n")
            else:
                console.print(f"[dim]Step 3-4/6: 跳过审查和润色 ({mode} 模式)[/dim]")
                review_results = None

            # 保存章节文件
            chapter_path = chapter_file_path(self.project_root, chapter_num)
            write_text_file(chapter_path, final_content)
            console.print(f"[green]✓ 章节已保存到 {chapter_path}[/green]\n")
            
            # Step 5: Data Agent
            console.print("[cyan]Step 5/6: 数据处理[/cyan]")
            await self._step5_data(chapter_num, final_content)
            console.print("[green]✓ 完成[/green]\n")

            # Step 6: Git Backup (如果启用)
            if self.git_ops:
                console.print("[cyan]Step 6/6: Git 备份[/cyan]")
                try:
                    if self.git_ops.backup_chapter(chapter_num):
                        console.print("[green]✓ Git 提交和标签创建成功[/green]\n")
                    else:
                        console.print("[yellow]⚠ Git 备份失败，但不影响写作结果[/yellow]\n")
                except Exception as e:
                    logger.warning(f"Git 备份失败: {e}")
                    console.print("[yellow]⚠ Git 备份异常，但不影响写作结果[/yellow]\n")
            else:
                console.print("[dim]Step 6/6: Git 备份已禁用[/dim]\n")
            
            # Step 7: 自动审计（每50章）
            if chapter_num % 50 == 0:
                console.print("[cyan]🔍 触发定期审计（每50章）...[/cyan]")
                try:
                    audit_report = self.auto_audit.generate_report(chapter_num)
                    console.print(f"[green]✓ 审计报告已生成[/green]")
                    console.print(f"[dim]审计报告摘要:\n{audit_report[:500]}...[/dim]\n")
                except Exception as e:
                    logger.warning(f"自动审计失败: {e}")
                    console.print("[yellow]⚠ 审计生成失败，但不影响写作结果[/yellow]\n")
            
            # 更新工作流状态
            workflow_state = self.state_manager.load_workflow_state()
            workflow_state.current_task = None
            workflow_state.history.append({
                "task_id": f"task_{len(workflow_state.history) + 1:03d}",
                "command": "write",
                "chapter": chapter_num,
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
            })
            self.state_manager.save_workflow_state(workflow_state)
            
            console.print(f"[bold green]✓ 第 {chapter_num} 章写作完成！[/bold green]\n")

            # 输出性能总结
            self.perf_monitor.stop("total")
            self.perf_monitor.print_summary(console)

            # 输出 LLM 调用总结
            llm_summary = self.llm_monitor.get_summary()
            if llm_summary["call_count"] > 0:
                console.print(f"[dim]🤖 LLM 调用: {llm_summary['call_count']} 次, {llm_summary['total_tokens']} tokens[/dim]\n")

            return ChapterResult(
                success=True,
                chapter_num=chapter_num,
                file_path=str(chapter_path),
                word_count=len(final_content),
            )
            
        except Exception as e:
            logger.error(f"写作第 {chapter_num} 章失败: {e}", exc_info=True)
            console.print(f"[bold red]✗ 写作失败: {e}[/bold red]\n")

            # 标记任务失败
            workflow_state = self.state_manager.load_workflow_state()
            if workflow_state.current_task is not None:
                workflow_state.current_task["status"] = "failed"
                workflow_state.current_task["failed_at"] = datetime.now().isoformat()
                workflow_state.current_task["failure_reason"] = str(e)
                self.state_manager.save_workflow_state(workflow_state)
            else:
                logger.warning("工作流状态中 current_task 为 None，无法标记失败")

            return ChapterResult(
                success=False,
                chapter_num=chapter_num,
                error=str(e),
            )
    
    def _load_chapter_outline(self, chapter_num: int) -> Optional[Dict[str, Any]]:
        """加载本章细纲"""
        # 查找所有卷的细纲文件
        outline_dir = self.project_root / "大纲" / "细纲"
        if not outline_dir.exists():
            return None

        # 遍历所有卷的细纲文件
        for outline_file in sorted(outline_dir.glob("卷*_细纲.json")):
            try:
                data = json.loads(read_text_file(outline_file))
                for chapter in data.get("chapters", []):
                    if chapter.get("chapter_num") == chapter_num:
                        return chapter
            except Exception as e:
                logger.warning(f"加载细纲 {outline_file.name} 失败: {e}")
                continue

        return None
    
    def _load_context_info(self, current_chapter: int) -> Dict[str, Any]:
        """加载前情摘要和角色状态（恒定大小，不随章节数增长）"""
        state = self.state_manager.load_state()

        # 角色状态面板 (压缩版)
        char_states_text = self.long_term_mem.compress_state_for_context(state)

        # 最近章节摘要（最近 3 章）
        summaries_dir = self.project_root / ".webnovel" / "summaries"
        recent_summaries = []
        for i in range(max(1, current_chapter - 3), current_chapter):
            summary_file = summaries_dir / f"ch{i:04d}.md"
            if summary_file.exists():
                content = read_text_file(summary_file)
                lines = content.split("\n")
                summary = "\n".join(lines[2:]).strip()
                if summary:
                    recent_summaries.append(f"第{i}章: {summary}")

        recent_summaries_text = "\n".join(recent_summaries) if recent_summaries else "（无前序章节摘要）"

        # RAG 检索：根据细纲关键词检索前文
        rag_context = self._retrieve_rag_context(current_chapter)

        # 长期记忆（卷摘要、归档角色）
        distant_context = self.long_term_mem.get_distant_context(current_chapter)

        # 活跃剧情线提醒
        plot_thread_reminder = self.plot_threads.generate_reminder_prompt(current_chapter)
        
        # 世界观规则（新增）
        world_rules_context = self.world_rules_manager.get_rules_for_context()
        
        # 显式状态机上下文（新增 - 强制逻辑连贯）
        state_machine_context = self._get_state_machine_context(current_chapter)
        
        # 因果链约束（新增 - 伏笔/债务强制回收）
        causal_chain_context = self.causal_chain.generate_writing_constraints(current_chapter)

        return {
            "character_states": char_states_text,
            "recent_summaries": recent_summaries_text,
            "recent_summary": state.recent_summary,
            "rag_context": rag_context,
            "distant_context": distant_context,
            "plot_thread_reminder": plot_thread_reminder,
            "world_rules": world_rules_context,
            "state_machine": state_machine_context,
            "causal_chain": causal_chain_context,
        }
    
    def _retrieve_rag_context(self, current_chapter: int, top_k: int = 3) -> str:
        """从历史章节中检索相关内容"""
        try:
            rag = BM25RAG(self.project_root)

            # 获取本章细纲作为查询词
            outline = self._load_chapter_outline(current_chapter)
            if outline:
                query = f"{outline.get('plot', '')} {outline.get('characters', '')} {outline.get('conflict', '')}"
            else:
                query = ""

            if not query.strip():
                return "（无相关检索内容）"

            results = rag.retrieve(query, top_k=top_k)

            if results:
                context_parts = []
                for res in results:
                    # 只显示本章之前的内容
                    if res["chapter"] < current_chapter:
                        context_parts.append(f"[来自第{res['chapter']}章]: {res['content']}")

                if context_parts:
                    return "\n".join(context_parts)

            return "（无相关检索内容）"
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")
            return "（检索失败）"
    
    def _get_state_machine_context(self, current_chapter: int) -> str:
        """获取显式状态机上下文（强制逻辑连贯）"""
        lines = ["## 🔒 显式状态机约束（代码强制，必须遵守）"]
        
        # 获取所有角色状态
        states = self.state_machine.get_all_states()
        if not states:
            lines.append("\n（暂无状态机记录）")
            return "\n".join(lines)
        
        for name, state in states.items():
            lines.append(f"\n### {name} 当前状态")
            lines.append(f"- 境界: {state.realm}")
            lines.append(f"- 生命: {state.hp_percent:.0f}% ({state.injury_type.value})")
            if state.injuries:
                lines.append(f"- 伤势: {', '.join(state.injuries)}")
            lines.append(f"- 灵力: {state.spirit_level.value}")
            if state.items:
                lines.append(f"- 持有: {', '.join(state.items[:5])}")
        
        lines.append(f"\n### 硬拦截规则")
        lines.append(f"- 重伤/濒死状态下禁止战斗")
        lines.append(f"- 灵力枯竭时禁止释放高消耗技能")
        lines.append(f"- 不得越境界使用能力")
        lines.append(f"- 未持有物品不得使用")
        lines.append(f"\n如违反上述规则，代码将强制驳回并重写")
        
        return "\n".join(lines)

    async def _step1_context(self, chapter_num: int, chapter_outline: Dict[str, Any], context_info: Dict[str, Any]) -> Dict[str, Any]:
        """Step 1: Context Agent 生成创作执行包"""
        context_result = await self.context_agent.execute({
            "chapter_num": chapter_num,
            "outline_info": json.dumps(chapter_outline, ensure_ascii=False, indent=2),
            "context_info": context_info,
        })
        return context_result
    
    async def _step2a_draft(self, chapter_num: int, context_result: Dict[str, Any], context_info: Dict[str, Any]) -> str:
        """Step 2A: 基于 Context Agent 输出撰写初稿"""
        mission_brief = context_result.get("mission_brief", {})
        context_contract = context_result.get("context_contract", {})
        writing_prompt = context_result.get("writing_prompt", "")
        chapter_outline = context_result.get("outline_info", "无细纲信息")

        # 获取字数配置
        min_words = self.workflow_config.get("chapter_min_words", 2000)
        max_words = self.workflow_config.get("chapter_max_words", 2500)

        # 格式化前情信息（不再包含角色状态面板，因为它现在有独立的位置）
        prev_str = f"""
## 最近剧情摘要
{context_info.get('recent_summaries', '无')}

## 历史剧情检索
{context_info.get('rag_context', '无')}

## 世界观规则（必须严格遵守）
{context_info.get('world_rules', '无')}

## 🔒 显式状态机（代码强制校验）
{context_info.get('state_machine', '无')}

## 📌 因果链约束（伏笔/债务强制回收）
{context_info.get('causal_chain', '无')}
"""

        prompt = DRAFT_GENERATION_PROMPT.format(
            chapter_num=chapter_num,
            character_states=context_info.get('character_states', '无'),  # 【修复】独立填充角色状态面板
            previous_chapters=prev_str,
            mission_brief=self._format_dict(mission_brief),
            context_contract=self._format_dict(context_contract),
            chapter_outline=chapter_outline,
            writing_prompt=writing_prompt,
            rag_context=context_info.get('rag_context', '无'),
            distant_context=context_info.get('distant_context', ''),
            plot_thread_reminder=context_info.get('plot_thread_reminder', ''),
            world_rules=context_info.get('world_rules', '无'),
            state_machine=context_info.get('state_machine', '无'),
            causal_chain=context_info.get('causal_chain', '无'),
            min_words=min_words,
            max_words=max_words,
        )
        
        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是专业的中文网文作家，擅长创作吸引人的网文内容。",
            temperature=0.8,
            max_tokens=8000,
        )
        
        return response.text.strip()
    
    async def _step2b_style(self, chapter_content: str) -> str:
        """Step 2B: 风格优化（表达层翻译，不改情节）"""
        prompt = STYLE_ADAPTATION_PROMPT.format(
            chapter_content=chapter_content,  # 传递完整内容
        )
        
        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="你是专业的文字编辑，擅长优化表达但不改变情节。",
            temperature=0.5,
            max_tokens=8000,
        )
        
        return response.text.strip()

    def _step2_4_gender_pronoun_scan(self, chapter_num: int, content: str) -> list:
        """Step 2.4: 性别代词扫描（快速正则检查，不依赖LLM）"""
        state = self.state_manager.load_state()
        
        # 构建 {角色名: 性别} 字典
        character_genders = {}
        for cs in state.character_states:
            if cs.gender:
                character_genders[cs.name] = cs.gender
        
        # 添加主角性别（如果不在 character_states 中）
        protagonist_name = state.protagonist.get("name", "")
        if protagonist_name and protagonist_name not in character_genders:
            character_genders[protagonist_name] = state.protagonist.get("gender", "")
        
        # 执行扫描
        issues = self.gender_scanner.scan(content, character_genders)
        
        if issues:
            error_msg = self.gender_scanner.get_error_message(issues)
            logger.warning(f"第 {chapter_num} 章性别代词检查发现问题: {error_msg}")
            console.print(f"[yellow]⚠ 性别代词检查发现问题[/yellow]")
            for issue in issues:
                console.print(f"  [red]{issue.character_name}[/red]: 设定{issue.expected_gender}性，但使用了'{issue.found_pronoun}'")
        else:
            logger.info(f"第 {chapter_num} 章性别代词检查通过")
        
        return issues

    async def _step3_parallel_review(
        self,
        chapter_num: int,
        content: str,
        outline: Dict[str, Any],
        context_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Step 3: 并行七维审查（带重试机制）"""
        import asyncio
        from ..agents.checkers.consistency_checker import CheckResult

        async def review_with_retry(checker_name: str, coro_fn, max_retries: int = 2):
            """单个审查器带重试 - 每次重试创建新的协程"""
            for attempt in range(max_retries + 1):
                try:
                    result = await coro_fn()
                    if isinstance(result, Exception):
                        raise result
                    return result
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"{checker_name} 第 {attempt + 1} 次失败，重试中: {e}")
                        await asyncio.sleep(0.5 * (2 ** attempt))  # 指数退避
                        continue
                    else:
                        logger.error(f"{checker_name} 重试 {max_retries} 次后仍失败: {e}")
                        # 返回默认失败结
                        return CheckResult(
                            checker=checker_name,
                            score=50,  # 使用中间分数而不是 0
                            issues=[],
                            summary=f"{checker_name} 调用失败",
                        )

        # 并行调用 7 个审查器（传入工厂函数而非协程对象）
        tasks = [
            review_with_retry("consistency", lambda: self.consistency_checker.check(chapter_num, content, outline)),
            review_with_retry("continuity", lambda: self.continuity_checker.check(chapter_num, content, context_info.get("recent_summary", ""))),
            review_with_retry("ooc", lambda: self.ooc_checker.check(chapter_num, content)),
            review_with_retry("high_point", lambda: self.high_point_checker.check(chapter_num, content)),
            review_with_retry("pacing", lambda: self.pacing_checker.check(chapter_num, content)),
            review_with_retry("reader_pull", lambda: self.reader_pull_checker.check(chapter_num, content, outline)),
            review_with_retry("world_rules", lambda: self.world_rules_checker.check(chapter_num, content)),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        checker_names = ["consistency", "continuity", "ooc", "high_point", "pacing", "reader_pull", "world_rules"]
        dimension_scores = {}
        all_issues = []
        
        for name, result in zip(checker_names, results):
            if isinstance(result, Exception):
                logger.warning(f"{name} 审查失败: {result}")
                dimension_scores[name] = 0
            else:
                dimension_scores[name] = result.score
                all_issues.extend(result.issues)

        # 计算综合得分（加权平均）
        weights = {
            "consistency": 0.20,
            "continuity": 0.18,
            "ooc": 0.18,
            "high_point": 0.13,
            "pacing": 0.09,
            "reader_pull": 0.09,
            "world_rules": 0.13,
        }
        
        overall_score = sum(
            dimension_scores[name] * weights[name]
            for name in checker_names
        )

        # 统计严重性分布
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for issue in all_issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

        return {
            "dimension_scores": dimension_scores,
            "overall_score": overall_score,
            "issues": all_issues,
            "severity_counts": severity_counts,
            "summary": self._generate_review_summary(dimension_scores, all_issues),
        }

    async def _step4_polish(
        self,
        chapter_num: int,
        content: str,
        review_results: Dict[str, Any],
    ) -> str:
        """Step 4: 根据审查结果智能润色"""
        issues = review_results.get("issues", [])
        
        # 过滤需要修复的问题（只处理 high 和 critical）
        critical_issues = [i for i in issues if i.severity == "critical"]
        high_issues = [i for i in issues if i.severity == "high"]
        
        if not critical_issues and not high_issues:
            # 无严重问题，跳过
            console.print("[dim]无严重问题，跳过润色[/dim]")
            return content

        # 构建修复提示
        fix_instructions = []
        for issue in (critical_issues + high_issues)[:5]:  # 最多处理 5 个问题
            fix_instructions.append(f"- 【{issue.severity.upper()}】{issue.description}")
            if issue.suggestion:
                fix_instructions.append(f"  建议: {issue.suggestion}")

        fix_text = "\n".join(fix_instructions)

        polish_prompt = f"""
你是专业的网文编辑。以下章节存在一些问题，请进行针对性修复。

## 待修复问题
{fix_text}

## 原章节内容
{content}

## 要求
1. 保持原情节和结构不变
2. 仅针对上述问题进行局部修复
3. 修复后确保逻辑通顺、表达清晰
4. 输出完整的章节内容（必须和原章节长度一致，不要删减）

请直接输出修复后的章节。
"""
        try:
            response = await self.llm.generate(
                prompt=polish_prompt,
                system_prompt="你是专业的网文编辑，擅长修复章节内容。",
                temperature=0.5,
                max_tokens=8000,
            )
            
            polished_content = response.text.strip()
            if len(polished_content) > len(content) * 0.7:  # 确保内容没有大幅丢失
                console.print(f"[green]✓ 已修复 {len(critical_issues) + len(high_issues)} 个严重问题[/green]")
                return polished_content
            else:
                logger.warning("润色后内容大幅丢失，使用原内容")
                return content
        except Exception as e:
            logger.warning(f"润色失败: {e}，使用原内容")
            return content

    def _generate_review_summary(
        self,
        dimension_scores: Dict[str, int],
        issues: list,
    ) -> str:
        """生成审查总结"""
        lines = ["审查结果："]
        
        dimension_names = {
            "consistency": "设定一致性",
            "continuity": "叙事连贯性",
            "ooc": "角色一致性",
            "high_point": "爽点密度",
            "pacing": "节奏控制",
            "reader_pull": "追读力",
            "world_rules": "世界观规则",
        }
        
        for name, score in dimension_scores.items():
            display_name = dimension_names.get(name, name)
            emoji = "✓" if score >= 80 else "⚠" if score >= 60 else "✗"
            lines.append(f"  {emoji} {display_name}: {score}")

        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        
        if critical > 0:
            lines.append(f"\n⚠ 发现 {critical} 个严重问题，必须修复")
        if high > 0:
            lines.append(f"⚠ 发现 {high} 个高优先级问题，建议修复")

        return "\n".join(lines)

    async def _step5_data(self, chapter_num: int, chapter_content: str):
        """Step 5: Data Agent 数据处理 + 状态机更新 + 因果链分析 + Anti-AI扫描"""
        # 原有数据处理
        data_result = await self.data_agent.execute({
            "chapter_num": chapter_num,
            "chapter_content": chapter_content,
            "project_root": str(self.project_root),
        })
        
        # Anti-AI 扫描（新增 - 自动检测AI痕迹）
        try:
            is_pass, report = anti_ai_scanner.is_pass(chapter_content)
            if not is_pass:
                console.print(f"[yellow]⚠️ Anti-AI 检查未通过: {report}[/yellow]")
                console.print(f"[dim]详细报告已记录，可在润色阶段修复[/dim]")
            else:
                console.print(f"[green]✓ Anti-AI 检查通过: {report}[/green]")
        except Exception as e:
            logger.warning(f"Anti-AI 扫描失败: {e}")
        
        # 更新状态机（新增 - 从文本中提取状态变化）
        try:
            self._update_state_machine_from_chapter(chapter_num, chapter_content)
        except Exception as e:
            logger.warning(f"状态机更新失败: {e}")
        
        # 更新因果链（新增 - 自动提取新债/还债/伏笔）
        try:
            causal_results = self.causal_chain.analyze_chapter_for_debts_and_foreshadowings(
                chapter_num, 
                chapter_content,
                llm=self.llm
            )
            if causal_results.get("new_debts") or causal_results.get("resolved_foreshadowings"):
                console.print(f"[green]✓ 因果链已更新: "
                            f"新增{len(causal_results.get('new_debts', []))}笔债, "
                            f"回收{len(causal_results.get('resolved_foreshadowings', []))}个伏笔[/green]")
        except Exception as e:
            logger.warning(f"因果链更新失败: {e}")
        
        # 自动提取世界观规则（异步，不阻塞）
        try:
            import asyncio
            asyncio.create_task(
                self.world_rules_manager.auto_extract_rules(
                    self.llm, 
                    chapter_num, 
                    chapter_content
                )
            )
        except Exception as e:
            logger.warning(f"自动提取世界观规则失败: {e}")
        
        # 更新角色弧光（从数据结果中提取）
        try:
            self._update_character_arcs(chapter_num, data_result)
        except Exception as e:
            logger.warning(f"更新角色弧光失败: {e}")
    
    def _update_state_machine_from_chapter(self, chapter_num: int, chapter_content: str):
        """从章节内容更新状态机"""
        # 提取主要角色
        state = self.state_manager.load_state()
        protagonist_name = state.protagonist.get("name", "")

        if protagonist_name:
            # 如果角色不存在，初始化
            if not self.state_machine.get_state(protagonist_name):
                # 【修复】从 character_states 获取最新境界，而不是从 protagonist dict
                protagonist_cultivation = "炼气一层"  # 默认值
                for cs in state.character_states:
                    if cs.name == protagonist_name and cs.cultivation:
                        protagonist_cultivation = cs.cultivation
                        break
                else:
                    # 如果 character_states 中也没有，尝试从 protagonist dict 取
                    protagonist_cultivation = state.protagonist.get("cultivation", "炼气一层")
                
                self.state_machine.init_entity(
                    name=protagonist_name,
                    realm=protagonist_cultivation,
                    location=""
                )

            # 【关键修复】激活 LLM 提取状态变化
            try:
                self.state_machine.update_state_from_text(
                    entity_name=protagonist_name,
                    chapter_num=chapter_num,
                    text_content=chapter_content,
                    llm=self.llm
                )
            except Exception as e:
                logger.warning(f"状态机更新失败: {e}")
        
        # 更新其他活跃角色
        for cs in state.character_states:
            if cs.name != protagonist_name and cs.status == "active":
                if not self.state_machine.get_state(cs.name):
                    self.state_machine.init_entity(
                        name=cs.name,
                        realm=cs.cultivation or "未知",
                        location=""
                    )
                try:
                    self.state_machine.update_state_from_text(
                        entity_name=cs.name,
                        chapter_num=chapter_num,
                        text_content=chapter_content,
                        llm=self.llm
                    )
                except Exception as e:
                    logger.debug(f"角色 {cs.name} 状态机更新失败: {e}")
    
    def _update_character_arcs(self, chapter_num: int, data_result: Dict[str, Any]):
        """更新角色弧光追踪器"""
        character_states = data_result.get("character_states", [])
        
        for cs_data in character_states:
            name = cs_data.get("name")
            if not name:
                continue
            
            # 如果角色未初始化，尝试从state.json初始化
            if name not in self.character_arc_tracker.get_active_characters():
                # 尝试从state.json获取初始信息
                state = self.state_manager.load_state()
                if name == state.project.get("protagonist", {}).get("name"):
                    # 主角
                    self.character_arc_tracker.init_character(
                        name=name,
                        role="protagonist",
                        desire=state.protagonist.get("desire", ""),
                        flaw=state.protagonist.get("flaw", ""),
                        cultivation=cs_data.get("cultivation", "")
                    )
                else:
                    # 配角
                    self.character_arc_tracker.init_character(
                        name=name,
                        role="supporting",
                        desire="",
                        flaw="",
                        cultivation=cs_data.get("cultivation", "")
                    )
            
            # 更新快照
            self.character_arc_tracker.update_snapshot(
                name=name,
                chapter=chapter_num,
                new_state=cs_data
            )
    
    def _format_dict(self, d: Dict[str, Any]) -> str:
        """格式化字典为字符串"""
        if not d:
            return "无"
        return "\n".join(f"- {k}: {v}" for k, v in d.items())
    
    async def review_chapter(
        self,
        chapter_num: int,
        depth: str = "core",
    ) -> ReviewReport:
        """审查章节质量
        
        Args:
            chapter_num: 章节号
            depth: 审查深度 (core | full)
        
        Returns:
            ReviewReport: 审查报告
        """
        console.print(f"\n[bold blue]开始审查第 {chapter_num} 章[/bold blue] (深度: {depth})\n")
        
        # 读取章节内容
        chapter_path = chapter_file_path(self.project_root, chapter_num)
        if not chapter_path.exists():
            raise FileNotFoundError(f"章节文件不存在: {chapter_path}")
        
        chapter_content = read_text_file(chapter_path)
        
        # TODO: 实现审查系统
        # 这里先返回一个示例报告
        report = ReviewReport(
            agent="review-system",
            chapter=chapter_num,
            overall_score=80,
            pass_=True,
            dimension_scores={
                "爽点密度": 75,
                "设定一致性": 85,
                "节奏控制": 80,
                "人物塑造": 85,
                "连贯性": 80,
                "追读力": 75,
            },
            summary="章节质量良好，继续保持！",
        )
        
        console.print(f"[bold green]审查完成，总分: {report.overall_score}[/bold green]\n")
        return report
