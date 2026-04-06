"""
CLI 主入口
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel

from .utils.config import load_config, resolve_project_root
from .llm.base import create_llm
from .init.project import InitProject
from .workflow.manager import WorkflowManager

console = Console()


def main():
    parser = argparse.ArgumentParser(
        prog="novel-writer",
        description="NovelWriter - 模型无关的网文写作系统",
    )
    parser.add_argument(
        "--project-root",
        help="项目根目录（可选，默认自动检测）",
        type=Path,
    )
    parser.add_argument(
        "--config",
        help="配置文件路径",
        type=Path,
        default=None,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化项目")
    init_parser.add_argument("--title", required=True, help="书名")
    init_parser.add_argument("--genre", required=True, help="题材（如：仙侠、都市、游戏）")
    init_parser.add_argument("--auto", action="store_true", help="AI 全自动脑补所有设定（无需人工填写）")
    
    # plan 命令
    plan_parser = subparsers.add_parser("plan", help="规划大纲")
    plan_parser.add_argument("--volume", type=int, required=True, help="卷号")
    plan_parser.add_argument("--chapters", type=int, required=True, help="本章数")
    plan_parser.add_argument("--auto", action="store_true", help="自动生成模式（批量续写）")
    plan_parser.add_argument("--batch-size", type=int, default=5, help="每批生成章节数（默认5）")

    # check-outline 命令
    check_parser = subparsers.add_parser("check-outline", help="自动检查并修复大纲逻辑漏洞")
    check_parser.add_argument("--volume", type=int, required=True, help="卷号")
    
    # write 命令
    write_parser = subparsers.add_parser("write", help="写作章节")
    write_parser.add_argument("--chapter", type=int, help="章节号（用于单章模式）")
    write_parser.add_argument("--start", type=int, help="起始章节号（用于批量模式）")
    write_parser.add_argument("--end", type=int, help="结束章节号（用于批量模式）")
    write_parser.add_argument(
        "--mode",
        choices=["standard", "fast", "minimal"],
        default="standard",
        help="写作模式",
    )
    
    # review 命令
    review_parser = subparsers.add_parser("review", help="审查章节")
    review_parser.add_argument("--chapter", type=int, required=True, help="章节号")
    review_parser.add_argument(
        "--depth",
        choices=["core", "full"],
        default="core",
        help="审查深度",
    )
    review_parser.add_argument(
        "--fix",
        action="store_true",
        help="自动修复 critical/high 问题并覆盖原文件",
    )
    
    # query 命令
    query_parser = subparsers.add_parser("query", help="查询信息")
    query_parser.add_argument("--type", required=True, help="查询类型")
    query_parser.add_argument("--name", help="查询名称")
    
    # resume 命令
    subparsers.add_parser("resume", help="恢复中断的任务")
    
    # preflight 命令
    subparsers.add_parser("preflight", help="预检环境")

    # dashboard 命令
    dashboard_parser = subparsers.add_parser("dashboard", help="启动可视化面板")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    dashboard_parser.add_argument("--port", type=int, default=8765, help="监听端口")
    dashboard_parser.add_argument("--reload", action="store_true", help="热重载模式")

    args = parser.parse_args()
    
    if not args.command:
        console.print(Panel(
            "[bold blue]NovelWriter v0.1.0[/bold blue]\n\n"
            "模型无关的网文写作系统\n\n"
            "[bold]用法:[/bold]\n"
            "  novel-writer init --title '书名' --genre '题材'\n"
            "  novel-writer plan --volume 1 --chapters 20\n"
            "  novel-writer check-outline --volume 1\n"
            "  novel-writer write --chapter 1\n"
            "  novel-writer review --chapter 1\n"
            "  novel-writer query --type character --name '主角'\n"
            "  novel-writer resume\n"
            "  novel-writer preflight",
            title="欢迎使用 NovelWriter",
        ))
        sys.exit(0)
    
    # 每次执行命令都重新加载 .env 文件
    from .utils.config import _load_env_file
    _load_env_file()
    
    # 加载配置
    config = load_config(args.config)
    
    # 解析项目根目录
    if args.command != "init":
        try:
            project_root = args.project_root or resolve_project_root()
            config["project_root"] = project_root
        except Exception as e:
            console.print(f"[red]错误:[/red] 无法解析项目根目录: {e}")
            sys.exit(1)
    
    # 执行命令
    if args.command == "preflight":
        cmd_preflight(config)
    elif args.command == "init":
        cmd_init(args, config)
    elif args.command == "plan":
        cmd_plan(args, config)
    elif args.command == "check-outline":
        cmd_check_outline(args, config)
    elif args.command == "write":
        cmd_write(args, config)
    elif args.command == "review":
        cmd_review(args, config)
    elif args.command == "resume":
        cmd_resume(config)
    elif args.command == "query":
        cmd_query(args, config)
    elif args.command == "dashboard":
        cmd_dashboard(args, config)


def cmd_preflight(config):
    """预检环境"""
    console.print("[bold]环境预检[/bold]\n")
    
    # 检查配置文件
    config_file = Path("config.yaml")
    if config_file.exists():
        console.print("[green]✓[/green] config.yaml 存在")
    else:
        console.print("[yellow]⚠[/yellow] config.yaml 不存在，将使用默认配置")
    
    # 检查 .env
    env_file = Path(".env")
    if env_file.exists():
        console.print("[green]✓[/green] .env 存在")
    else:
        console.print("[yellow]⚠[/yellow] .env 不存在")
    
    # 检查 LLM 配置
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "qwen")
    console.print(f"[green]✓[/green] LLM 提供商: {provider}")
    
    if provider == "qwen":
        api_key = llm_config.get("api_key", "")
        if api_key and api_key != "${QWEN_API_KEY}":
            console.print("[green]✓[/green] 千问 API Key 已配置")
        else:
            console.print("[red]✗[/red] 千问 API Key 未配置")
    
    console.print("\n[bold green]预检完成[/bold green]")


def cmd_init(args, config):
    """初始化项目"""
    from .llm.base import create_llm

    console.print(f"[bold]初始化项目:[/bold] {args.title} ({args.genre})\n")

    # 创建 LLM 实例
    llm = create_llm(config.get("llm", {}))

    # 初始化项目
    initializer = InitProject(llm=llm, config=config)
    
    # 检查是否使用全自动模式
    if getattr(args, 'auto', False):
        # AI 全自动脑补所有设定
        project_root = initializer.auto_initialize(
            title=args.title,
            genre=args.genre,
        )
    else:
        # 原有的人工交互式收集信息
        project_root = initializer.initialize(
            title=args.title,
            genre=args.genre,
        )

    console.print(f"\n[bold green]项目初始化完成！[/bold green]")
    console.print(f"项目路径: {project_root}")
    if not getattr(args, 'auto', False):
        console.print(f"\n下一步:")
        console.print(f"  cd {project_root}")
        console.print(f"  novel-writer plan --volume 1 --chapters 20")


def cmd_plan(args, config):
    """规划大纲"""
    console.print(f"[bold]规划大纲:[/bold] 第 {args.volume} 卷，{args.chapters} 章\n")

    project_root = config["project_root"]
    master_outline_path = project_root / "大纲" / "总纲.md"

    # 如果总纲不存在，引导用户交互式完善
    if not master_outline_path.exists():
        console.print("[yellow]⚠ 未找到总纲，请先完善总纲后再规划细纲。[/yellow]\n")
        _interactive_fill_master_outline(project_root, config)
        console.print("\n[bold green]总纲已更新！[/bold green] 请重新运行 plan 命令生成细纲。\n")
        return

    # 创建 LLM 实例
    llm = create_llm(config.get("llm", {}))

    # 检查是否使用自动生成模式
    if getattr(args, 'auto', False):
        # 使用自动生成器
        from .plan.auto_outline import AutoOutlineGenerator
        from .data.state_manager import StateManager
        
        state_manager = StateManager(project_root)
        generator = AutoOutlineGenerator(llm=llm, state_manager=state_manager)
        
        batch_size = getattr(args, 'batch_size', 5)
        console.print(f"[cyan]🤖 自动生成模式：每批 {batch_size} 章[/cyan]\n")
        
        import asyncio
        try:
            result = asyncio.run(generator.generate(
                volume_num=args.volume,
                target_chapters=args.chapters,
                batch_size=batch_size,
                auto_continue=True
            ))
            
            if result['status'] == 'success':
                console.print(f"\n[bold green]✓ 自动生成完成！共生成 {result['total_chapters']} 章[/bold green]")
                # 更新 state.json 的总章节数
                state = state_manager.load_state()
                state.progress["total_chapters"] = max(
                    state.progress.get("total_chapters", 0),
                    result['total_chapters']
                )
                state_manager.save_state(state)
            elif result['status'] == 'already_complete':
                console.print(f"\n[bold green]✓ 细纲已存在，无需重复生成[/bold green]")
            else:
                console.print(f"\n[bold red]✗ 自动生成失败[/bold red]")
        except Exception as e:
            console.print(f"\n[bold red]✗ 自动生成失败: {e}[/bold red]")
            import sys
            sys.exit(1)
    else:
        # 使用原有的人工辅助规划
        from .plan.volume_planner import PlanVolumeAgent
        from .data.state_manager import StateManager

        state_manager = StateManager(project_root)
        planner = PlanVolumeAgent(llm=llm, state_manager=state_manager)

        # 执行规划
        import asyncio
        try:
            result = asyncio.run(planner.execute(
                volume_num=args.volume,
                num_chapters=args.chapters,
            ))
            console.print(f"\n[bold green]大纲规划完成！[/bold green]")
            # 更新 state.json 的总章节数
            state = state_manager.load_state()
            state.progress["total_chapters"] = max(
                state.progress.get("total_chapters", 0),
                result.get("num_chapters", args.chapters)
            )
            state_manager.save_state(state)
        except Exception as e:
            console.print(f"\n[bold red]大纲规划失败: {e}[/bold red]")
            import sys
            sys.exit(1)


def cmd_check_outline(args, config):
    """检查并优化大纲逻辑"""
    console.print(f"[bold]🔍 检查大纲:[/bold] 第 {args.volume} 卷\n")
    project_root = config["project_root"]

    # 创建 LLM 和 Agent
    llm = create_llm(config.get("llm", {}))
    from .plan.outline_checker import OutlineChecker
    from .data.state_manager import StateManager

    state_manager = StateManager(project_root)
    checker = OutlineChecker(llm=llm, state_manager=state_manager)

    import asyncio
    try:
        success = asyncio.run(checker.check_and_optimize(volume_num=args.volume))
        if success:
            console.print(f"\n[bold green]✓ 大纲优化完成！现在可以重新写作了[/bold green]")
        else:
            console.print(f"\n[bold yellow]⚠ 优化取消或失败[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]✗ 大纲检查失败: {e}[/bold red]")
        import sys
        sys.exit(1)


def _interactive_fill_master_outline(project_root, config):
    """交互式完善总纲"""
    from src.data.state_manager import StateManager
    from src.utils.file_ops import write_text_file
    from rich.prompt import Prompt

    state_manager = StateManager(project_root)
    state = state_manager.load_state()
    
    console.print("[bold]请完善你的总纲（直接回车可跳过）[/bold]\n")
    
    title = state.project.get("title", "未命名")
    genre = state.project.get("genre", "未知")
    
    one_liner = Prompt.ask("一句话简介（这本书最吸引人的点是什么？）", default="")
    core_conflict = Prompt.ask("核心冲突（主角面临的最大阻碍是什么？）", default="")
    selling_points = Prompt.ask("主要卖点（爽点/金手指/节奏特色）", default="")
    main_storyline = Prompt.ask("故事主线（主角最终要达成什么目标？）", default="")
    
    content = f"""# 总纲

## 书名
{title}

## 题材
{genre}

## 一句话简介
{one_liner}

## 核心冲突
{core_conflict}

## 目标读者
{state.project.get('target_audience', '网文读者')}

## 目标字数
{state.project.get('target_scale', '100万字')}

## 主要卖点
{selling_points}

## 故事主线
{main_storyline}
"""
    write_text_file(project_root / "大纲" / "总纲.md", content)
    console.print(f"[green]✓ 总纲已保存至 {project_root / '大纲' / '总纲.md'}[/green]")


def cmd_write(args, config):
    """写作章节"""
    
    # 检查参数：批量模式还是单章模式
    if args.start and args.end:
        # 批量模式
        if args.start > args.end:
            console.print("[red]错误: --start 不能大于 --end[/red]")
            return
        
        console.print(f"[bold]批量写作模式:[/bold] 第 {args.start} 章 到 第 {args.end} 章 (模式: {args.mode})\n")
        
        _run_batch_write(args.start, args.end, args.mode, config)
        
    elif args.chapter:
        # 单章模式
        console.print(f"[bold]写作章节:[/bold] 第 {args.chapter} 章 (模式: {args.mode})\n")
        _run_single_write(args.chapter, args.mode, config)
    else:
        console.print("[red]错误: 请指定 --chapter <章节号> 或者 --start <起始> --end <结束>[/red]")


def _run_single_write(chapter_num: int, mode: str, config: Dict[str, Any]):
    """运行单章写作"""
    from .llm.base import create_llm
    from .workflow.manager import WorkflowManager
    
    llm = create_llm(config.get("llm", {}))
    workflow = WorkflowManager(llm=llm, config=config)
    
    import asyncio
    result = asyncio.run(workflow.write_chapter(chapter_num=chapter_num, mode=mode))
    
    if result.success:
        console.print(f"\n[bold green]✓ 第 {chapter_num} 章写作完成！[/bold green]")
    else:
        console.print(f"\n[bold red]✗ 第 {chapter_num} 章写作失败:[/bold red] {result.error}")


def _run_batch_write(start: int, end: int, mode: str, config: Dict[str, Any]):
    """运行批量写作"""
    import asyncio
    from .llm.base import create_llm
    from .workflow.manager import WorkflowManager
    
    llm = create_llm(config.get("llm", {}))
    workflow = WorkflowManager(llm=llm, config=config)
    
    for i in range(start, end + 1):
        console.rule(f"[bold blue]正在处理: 第 {i} 章[/bold blue]")
        result = asyncio.run(workflow.write_chapter(chapter_num=i, mode=mode))
        
        if result.success:
            console.print(f"[green]✓ 第 {i} 章完成[/green]")
        else:
            console.print(f"[red]✗ 第 {i} 章失败: {result.error}[/red]")
            console.print("[bold yellow]批量写作已停止，请检查错误后继续。[/bold yellow]")
            break


def cmd_review(args, config):
    """审查章节"""
    console.print(f"[bold]审查章节:[/bold] 第 {args.chapter} 章 (深度: {args.depth})\n")

    # 创建 LLM 实例
    llm = create_llm(config.get("llm", {}))

    # 创建工作流管理器
    workflow = WorkflowManager(
        llm=llm,
        config=config,
    )

    # 执行审查
    import asyncio
    result = asyncio.run(workflow.review_chapter(
        chapter_num=args.chapter,
        depth=args.depth,
        auto_fix=getattr(args, 'fix', False),
    ))

    console.print(result.to_rich_table())


def cmd_resume(config):
    """恢复中断的任务"""
    console.print("[bold]恢复中断的任务[/bold]\n")

    from .data.state_manager import StateManager
    from pathlib import Path

    project_root = config.get("project_root", ".")
    state_manager = StateManager(Path(project_root))

    # 加载工作流状态
    workflow_state = state_manager.load_workflow_state()

    if workflow_state.current_task is None:
        console.print("[yellow]没有正在进行的任务[/yellow]")
        return

    task = workflow_state.current_task
    console.print(f"[cyan]发现中断的任务:[/cyan] {task.get('command', '未知')}")
    console.print(f"  状态: {task.get('status', '未知')}")
    console.print(f"  参数: {task.get('args', {})}")
    
    if task.get("current_step"):
        console.print(f"  当前步骤: {task['current_step'].get('name', '未知')}")
    
    if task.get("failure_reason"):
        console.print(f"  失败原因: {task.get('failure_reason')}")

    # 询问用户如何处理
    from rich.prompt import Prompt
    
    action = Prompt.ask(
        "如何处理",
        choices=["continue", "restart", "cancel"],
        default="continue",
    )

    if action == "continue":
        console.print("[green]继续任务...（功能开发中）[/green]")
        # TODO: 实现继续逻辑
    elif action == "restart":
        console.print("[yellow]重新开始任务...（功能开发中）[/yellow]")
        # 清除当前任务，允许重新开始
        workflow_state.current_task = None
        state_manager.save_workflow_state(workflow_state)
        console.print("[green]已清除当前任务状态，可以重新执行[/green]")
    elif action == "cancel":
        console.print("[yellow]取消任务[/yellow]")
        workflow_state.current_task = None
        workflow_state.history.append({
            "task_id": f"task_{len(workflow_state.history) + 1:03d}",
            "command": task.get("command", "未知"),
            "status": "cancelled",
            "cancelled_at": datetime.now().isoformat(),
        })
        state_manager.save_workflow_state(workflow_state)
        console.print("[green]任务已取消[/green]")


def cmd_query(args, config):
    """查询信息"""
    query_type = args.type
    query_name = args.name

    console.print(f"[bold]查询信息:[/bold] {query_type}" + (f" - {query_name}" if query_name else "") + "\n")

    from .data.state_manager import StateManager
    from pathlib import Path

    project_root = config.get("project_root", ".")
    state_manager = StateManager(Path(project_root))

    # 加载项目状态
    state = state_manager.load_state()

    if query_type == "character":
        # 查询角色
        if query_name:
            # 查询特定角色
            char_state = next(
                (cs for cs in state.character_states if cs.name == query_name),
                None
            )
            if char_state:
                console.print(f"[bold]角色信息: {char_state.name}[/bold]")
                console.print(f"  境界: {char_state.cultivation}")
                console.print(f"  状态: {char_state.status}")
                console.print(f"  关系: {char_state.relationships}")
                console.print(f"  持有物品: {char_state.key_items}")
                console.print(f"  备注: {char_state.notes}")
            else:
                console.print(f"[yellow]未找到角色: {query_name}[/yellow]")
        else:
            # 列出所有角色
            console.print("[bold]所有角色:[/bold]")
            for cs in state.character_states:
                console.print(f"  - {cs.name}: {cs.cultivation} ({cs.status})")
    
    elif query_type == "progress":
        # 查询进度
        console.print("[bold]项目进度[/bold]")
        console.print(f"  书名: {state.project.get('title', '未命名')}")
        console.print(f"  当前章节: {state.progress.get('current_chapter', 0)}")
        console.print(f"  总章节: {state.progress.get('total_chapters', '未知')}")
        console.print(f"  最后更新: {state.progress.get('last_updated', '未知')}")
    
    elif query_type == "entities":
        # 查询实体
        entities = state_manager.get_entities()
        console.print(f"[bold]实体列表（共 {len(entities)} 个）[/bold]")
        for entity in entities[:20]:  # 只显示前 20 个
            console.print(f"  - {entity.name} ({entity.entity_type})")
        if len(entities) > 20:
            console.print(f"  ... 还有 {len(entities) - 20} 个实体")
    
    elif query_type == "review":
        # 查询审查检查点
        checkpoints = state.review_checkpoints
        console.print(f"[bold]审查检查点（共 {len(checkpoints)} 个）[/bold]")
        for cp in checkpoints[-10:]:  # 只显示最近 10 个
            console.print(f"  - 第 {cp['chapter']} 章: {cp['score']} 分 ({'通过' if cp['passed'] else '未通过'})")
    
    else:
        console.print(f"[yellow]不支持的查询类型: {query_type}[/yellow]")
        console.print("支持的类型: character, progress, entities, review")


def cmd_dashboard(args, config):
    """启动 Dashboard"""
    import subprocess
    import sys
    from pathlib import Path

    project_root = config.get("project_root", ".")
    
    console.print(f"[bold]启动 Dashboard[/bold]")
    console.print(f"项目目录: {project_root}")
    console.print(f"访问地址: http://{args.host}:{args.port}\n")

    # 找到 dashboard 目录
    dashboard_dir = Path(__file__).parent.parent / "dashboard"
    if not dashboard_dir.exists():
        console.print("[red]错误: dashboard 模块不存在[/red]")
        return

    # 启动 dashboard 服务
    cmd = [
        sys.executable, str(dashboard_dir / "server.py"),
        "--project-root", str(project_root),
        "--host", args.host,
        "--port", str(args.port),
    ]

    if args.reload:
        cmd.append("--reload")

    console.print("[green]Dashboard 已启动，按 Ctrl+C 停止[/green]\n")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard 已停止[/yellow]")
