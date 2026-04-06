"""
项目初始化
创建项目骨架文件结构
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.prompt import Prompt

from ..llm.base import BaseLLM
from ..data.schemas import ProjectState, Genre
from ..utils.file_ops import atomic_write_json, ensure_directory, write_text_file

console = Console()


# 项目初始化模板
SETTING_WORLDVIEW_TEMPLATE = """# 世界观设定

## 世界概述
{worldview}

## 社会结构
{social_structure}

## 重要地点
{important_locations}

## 时代背景
{time_period}
"""

SETTING_POWER_SYSTEM_TEMPLATE = """# 力量体系

## 体系类型
{power_type}

## 境界等级
{realms}

## 能力规则
{ability_rules}

## 限制与代价
{limitations}
"""

SETTING_CHARACTERS_TEMPLATE = """# 角色设定

## 主角
- 姓名：{protagonist_name}
- 性别：{protagonist_gender}
- 欲望/目标：{protagonist_desire}
- 缺陷：{protagonist_flaw}
- 性格特点：{protagonist_traits}
- 背景故事：{protagonist_background}
- 金手指/系统：{golden_finger}

## 重要配角
{supporting_characters}

## 反派
{antagonists}
"""

MASTER_OUTLINE_TEMPLATE = """# 总纲

## 书名
{title}

## 题材
{genre}

## 一句话简介
{one_liner}

## 核心冲突
{core_conflict}

## 目标读者
{target_audience}

## 目标字数
{target_scale}

## 主要卖点
{selling_points}

## 故事主线
{main_storyline}

## 世界观
{worldview}

## 力量体系
{power_type}
境界等级：{realms}

## 主角设定
姓名：{protagonist_name}
性别：{protagonist_gender}
欲望/目标：{protagonist_desire}
缺陷：{protagonist_flaw}
性格特点：{protagonist_traits}
背景故事：{protagonist_background}
金手指/系统：{golden_finger}
"""

PROJECT_MEMORY_TEMPLATE = """{{
  "patterns": [],
  "learned_at": [],
  "version": "0.1.0"
}}
"""


class InitProject:
    """项目初始化"""
    
    def __init__(self, llm: BaseLLM, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}
    
    def auto_initialize(self, title: str, genre: str) -> Path:
        """AI 全自动脑补所有设定（无需人工填写）"""
        console.print(f"[bold]\n🤖 AI 全自动初始化项目: {title} ({genre})[/bold]\n")
        console.print("[yellow]⏳ 正在让 AI 脑补所有设定，这可能需要 30-60 秒...[/yellow]\n")
        
        # 让 AI 生成所有设定
        project_info = self._ai_generate_project_info(title, genre)
        
        # 创建目录结构
        project_root = Path.cwd() / title
        self._create_project_structure(project_root)
        
        # 生成配置文件
        self._generate_state_json(project_root, project_info)
        self._generate_workflow_state_json(project_root)
        self._generate_project_memory_json(project_root)
        
        # 生成设定文件
        self._generate_setting_files(project_root, project_info)
        
        # 生成总纲
        self._generate_master_outline(project_root, project_info)
        
        # 生成 .env 示例
        self._generate_env_example(project_root)
        
        console.print(f"\n[bold green]✓ 项目全自动初始化完成！[/bold green]")
        console.print(f"项目路径: {project_root}")
        console.print(f"\n📝 AI 生成的设定摘要:")
        console.print(f"  主角: {project_info.get('protagonist_name', '未知')}")
        console.print(f"  金手指: {project_info.get('golden_finger', '未知')}")
        console.print(f"  境界: {project_info.get('realms', '未知')}")
        console.print(f"\n下一步:")
        console.print(f"  cd {project_root}")
        console.print(f"  novel-writer plan --volume 1 --chapters 100 --auto")
        
        return project_root

    def _ai_generate_project_info(self, title: str, genre: str) -> Dict[str, Any]:
        """使用 AI 自动生成项目信息"""
        prompt = f"""
你是专业的网文主编。请根据书名《{title}》和题材（{genre}），自动生成完整的项目设定。

请严格按照以下 JSON 格式输出，不要有任何解释：

```json
{{
  "target_scale": "100万字",
  "one_liner": "一句话简介",
  "core_conflict": "核心冲突",
  "target_audience": "目标读者",
  "selling_points": "主要卖点",
  "main_storyline": "故事主线",
  "protagonist_name": "主角姓名",
  "protagonist_gender": "主角性别（男/女/其他）",
  "protagonist_desire": "主角欲望/目标",
  "protagonist_flaw": "主角缺陷",
  "protagonist_traits": "性格特点（用、分隔）",
  "protagonist_background": "背景故事",
  "golden_finger": "金手指类型",
  "worldview": "世界概述",
  "power_type": "力量体系类型",
  "realms": "境界等级（用逗号分隔）",
  "social_structure": "社会结构",
  "important_locations": "重要地点",
  "time_period": "时代背景"
}}
```

要求：
1. 设定必须符合{genre}题材的常见套路
2. 金手指要有特色，不能太烂大街
3. 境界体系要完整，至少 6-8 个等级
4. 核心冲突要明确，能支撑 100 万字以上剧情
5. 主角性别要明确
6. **重要**：如果是"都市"、"都市神豪"、"都市生活"等现代都市题材，力量体系必须是**财富等级、商业地位、人脉影响力**等现实体系，**绝对不要**用修仙境界（炼气、筑基、金丹、元婴、化神等）。如果是"仙侠"、"玄幻"、"修仙"等奇幻题材，才可以使用修仙境界。题材和力量体系必须匹配。
"""
        try:
            import re
            import json
            response = self.llm.generate(
                prompt=prompt,
                system_prompt="你是专业的网文主编，擅长设计吸引人的小说设定。",
                temperature=0.8,
                max_tokens=2048,
            )
            
            # 提取 JSON
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                info = json.loads(json_match.group())
                info["title"] = title
                info["genre"] = genre
                return info
            else:
                console.print("[yellow]⚠️ AI 返回格式异常，使用默认设定[/yellow]")
                return self._get_default_info(title, genre)
        except Exception as e:
            console.print(f"[yellow]⚠️ AI 生成失败: {e}，使用默认设定[/yellow]")
            return self._get_default_info(title, genre)
    
    def _get_default_info(self, title: str, genre: str) -> Dict[str, Any]:
        """获取默认设定（备用方案）"""
        # 根据题材动态生成默认力量体系
        genre_lower = genre.lower()
        
        # 都市题材 → 现实体系
        if any(kw in genre_lower for kw in ["都市", "神豪", "商战", "职场", "现代"]):
            power_type = "财富/地位体系"
            realms = "路人,小有资产,千万富豪,亿万富豪,十亿级,百亿级,商业巨擘,财阀"
            worldview = "现代都市背景，表面繁荣平静，暗藏资本博弈"
        # 仙侠/玄幻/修仙 → 修仙境界
        elif any(kw in genre_lower for kw in ["仙侠", "玄幻", "修仙", "修真", "仙侠"]):
            power_type = "修炼体系"
            realms = "炼气,筑基,金丹,元婴,化神,炼虚,合体,大乘,渡劫"
            worldview = "修仙世界，弱肉强食，强者为尊"
        # 历史/架空 → 武力/官职体系
        elif any(kw in genre_lower for kw in ["历史", "架空", "古代"]):
            power_type = "武力/官职体系"
            realms = "平民,武者,武将,将军,王侯,帝王"
            worldview = "古代王朝背景，皇权至上，江湖与朝堂并存"
        # 科幻 → 科技等级
        elif any(kw in genre_lower for kw in ["科幻", "星际", "未来"]):
            power_type = "科技等级"
            realms = "地球文明,行星级文明,恒星级文明,星系级文明,宇宙级文明"
            worldview = "未来星际时代，人类文明已扩张至银河系"
        # 悬疑/惊悚 → 无明确等级
        elif any(kw in genre_lower for kw in ["悬疑", "惊悚", "恐怖", "灵异"]):
            power_type = "灵异能力体系"
            realms = "普通人,开眼,通灵,御鬼,驱魔,天师"
            worldview = "现代都市背景，表面正常，暗藏灵异与超自然力量"
        # 言情 → 情感/社会地位
        elif any(kw in genre_lower for kw in ["言情", "恋爱", "甜宠"]):
            power_type = "社会地位/情感成熟度"
            realms = "陌生人,普通朋友,暧昧对象,恋人,未婚夫妻,夫妻"
            worldview = "现代都市背景，聚焦职场、家庭、情感纠葛"
        # 游戏/电竞 → 段位/等级
        elif any(kw in genre_lower for kw in ["游戏", "电竞", "网游"]):
            power_type = "游戏段位体系"
            realms = "青铜,白银,黄金,铂金,钻石,大师,宗师,最强王者"
            worldview = "现代电竞/网游世界，虚拟与现实的界限模糊"
        # 默认：通用修炼体系
        else:
            power_type = "修炼体系"
            realms = "入门,初阶,中阶,高阶,大师,宗师,巅峰,超脱"
            worldview = "待补充"
        
        return {
            "title": title,
            "genre": genre,
            "target_scale": "100万字",
            "one_liner": f"一部{genre}题材的长篇网文",
            "core_conflict": "待补充",
            "target_audience": "网文读者",
            "selling_points": "待补充",
            "main_storyline": "待补充",
            "protagonist_name": "林晨",
            "protagonist_gender": "男",
            "protagonist_desire": "变强",
            "protagonist_flaw": "过于正直",
            "protagonist_traits": "坚韧、聪明、重情义",
            "protagonist_background": "普通人意外获得机缘",
            "golden_finger": "系统流",
            "worldview": worldview,
            "power_type": power_type,
            "realms": realms,
            "social_structure": "待补充",
            "important_locations": "待补充",
            "time_period": "现代"
        }

    def initialize(self, title: str, genre: str) -> Path:
        """创建项目骨架
        
        Args:
            title: 书名
            genre: 题材
        
        Returns:
            项目根目录路径
        """
        console.print(f"[bold]\n开始初始化项目: {title} ({genre})[/bold]\n")
        
        # 交互式收集信息
        project_info = self._collect_project_info(title, genre)
        
        # 创建目录结构
        project_root = Path.cwd() / title
        self._create_project_structure(project_root)
        
        # 生成配置文件
        self._generate_state_json(project_root, project_info)
        self._generate_workflow_state_json(project_root)
        self._generate_project_memory_json(project_root)
        
        # 生成设定文件
        self._generate_setting_files(project_root, project_info)
        
        # 生成总纲
        self._generate_master_outline(project_root, project_info)
        
        # 生成 .env 示例
        self._generate_env_example(project_root)
        
        console.print(f"\n[bold green]✓ 项目初始化完成！[/bold green]")
        console.print(f"项目路径: {project_root}")
        
        return project_root
    
    def _collect_project_info(self, title: str, genre: str) -> Dict[str, Any]:
        """交互式收集项目信息，用户不填的字段由 AI 自动补全"""
        console.print("[bold]请填写项目信息（直接回车跳过，AI 会自动补全）[/bold]\n")

        info = {
            "title": title,
            "genre": genre,
        }

        # 基础信息
        info["target_scale"] = Prompt.ask("目标字数", default="")
        info["one_liner"] = Prompt.ask("一句话简介", default="")
        info["core_conflict"] = Prompt.ask("核心冲突", default="")
        info["target_audience"] = Prompt.ask("目标读者", default="")
        info["selling_points"] = Prompt.ask("主要卖点", default="")
        info["main_storyline"] = Prompt.ask("故事主线", default="")

        # 主角信息
        console.print("\n[bold]主角设定[/bold]")
        info["protagonist_name"] = Prompt.ask("主角姓名", default="")
        info["protagonist_gender"] = Prompt.ask("主角性别", choices=["男", "女", "其他", ""], default="")
        info["protagonist_desire"] = Prompt.ask("主角欲望/目标", default="")
        info["protagonist_flaw"] = Prompt.ask("主角缺陷", default="")
        info["protagonist_traits"] = Prompt.ask("性格特点（逗号分隔）", default="")
        info["protagonist_background"] = Prompt.ask("背景故事", default="")

        # 金手指
        console.print("\n[bold]金手指/系统[/bold]")
        info["golden_finger"] = Prompt.ask("金手指类型", default="")

        # 世界观
        console.print("\n[bold]世界观[/bold]")
        info["worldview"] = Prompt.ask("世界概述", default="")
        info["power_type"] = Prompt.ask("力量体系类型", default="")
        info["realms"] = Prompt.ask("境界等级（用逗号分隔）", default="")
        info["social_structure"] = Prompt.ask("社会结构", default="")
        info["important_locations"] = Prompt.ask("重要地点", default="")
        info["time_period"] = Prompt.ask("时代背景", default="")

        # 收集用户输入后，用 AI 补全空字段
        console.print("\n[yellow]⏳ 正在让 AI 补全未填写的设定...[/yellow]")
        info = self._ai_fill_missing_fields(title, genre, info)

        return info

    def _ai_fill_missing_fields(self, title: str, genre: str, info: Dict[str, Any]) -> Dict[str, Any]:
        """用 AI 补全用户未填写的空字段"""
        # 找出空字段
        empty_fields = {k: v for k, v in info.items() if not v}
        if not empty_fields:
            return info

        prompt = f"""
你是专业的网文主编。用户正在创建一部{genre}题材的小说《{title}》。
用户已经填写了部分设定，请根据已填写的内容和题材特点，补全所有未填写的设定。

## 用户已填写的内容
{json.dumps({k: v for k, v in info.items() if v}, ensure_ascii=False, indent=2)}

## 需要补全的字段
{list(empty_fields.keys())}

请严格按照以下 JSON 格式输出补全后的**全部**字段（包括用户已填写的和你要补全的）：

```json
{{
  "target_scale": "目标字数",
  "one_liner": "一句话简介",
  "core_conflict": "核心冲突",
  "target_audience": "目标读者",
  "selling_points": "主要卖点",
  "main_storyline": "故事主线",
  "protagonist_name": "主角姓名",
  "protagonist_gender": "男/女/其他",
  "protagonist_desire": "主角欲望/目标",
  "protagonist_flaw": "主角缺陷",
  "protagonist_traits": "性格特点",
  "protagonist_background": "背景故事",
  "golden_finger": "金手指类型",
  "worldview": "世界概述",
  "power_type": "力量体系类型",
  "realms": "境界等级（用逗号分隔）",
  "social_structure": "社会结构",
  "important_locations": "重要地点",
  "time_period": "时代背景"
}}
```

要求：
1. 用户已填写的字段**必须原样保留，不得修改**。
2. 未填写的字段请根据题材和用户已填写的内容合理补全。
3. 如果是都市/神豪题材，力量体系必须是财富/地位相关，**绝对不要**用修仙境界。
4. 只输出 JSON，不要有任何解释。
"""
        try:
            response = self.llm.generate(
                prompt=prompt,
                system_prompt="你是专业的网文主编，擅长设计吸引人的小说设定。",
                temperature=0.8,
                max_tokens=2048,
            )

            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                filled_info = json.loads(json_match.group())
                # 合并：AI 补全的 + 用户填写的（用户填写的优先）
                for k, v in info.items():
                    if v:  # 用户填了的，覆盖 AI 的输出
                        filled_info[k] = v
                return filled_info
            else:
                console.print("[yellow]⚠️ AI 补全返回格式异常，使用默认值[/yellow]")
                return self._get_default_info(title, genre)
        except Exception as e:
            console.print(f"[yellow]⚠️ AI 补全失败: {e}，使用默认值[/yellow]")
            return self._get_default_info(title, genre)
    
    def _create_project_structure(self, project_root: Path):
        """创建目录结构"""
        console.print("[cyan]创建目录结构...[/cyan]")
        
        directories = [
            ".webnovel",
            ".webnovel/observability",
            ".webnovel/summaries",
            "设定集",
            "大纲",
            "正文",
        ]
        
        for dir_path in directories:
            ensure_directory(project_root / dir_path)
    
    def _generate_state_json(self, project_root: Path, info: Dict[str, Any]):
        """生成 state.json"""
        console.print("[cyan]生成 state.json...[/cyan]")

        state = ProjectState(
            project={
                "title": info["title"],
                "genre": info["genre"],
                "target_scale": info["target_scale"],
                "one_liner": info.get("one_liner", ""),
                "core_conflict": info.get("core_conflict", ""),
                "target_audience": info.get("target_audience", ""),
            },
            protagonist={
                "name": info["protagonist_name"],
                "gender": info.get("protagonist_gender", "男"),  # 【修复】添加性别
                "desire": info["protagonist_desire"],
                "flaw": info["protagonist_flaw"],
                "traits": info.get("protagonist_traits", ""),
                "background": info.get("protagonist_background", ""),
                "golden_finger": info["golden_finger"],
            },
            world={
                "worldview": info["worldview"],
                "power_type": info["power_type"],
                "realms": [r.strip() for r in info["realms"].split(",")],
            },
            progress={
                "current_chapter": 0,
                "total_chapters": 0,
                "last_updated": datetime.now().isoformat(),
            },
            strands={
                "quest_ratio": 0.60,
                "fire_ratio": 0.25,
                "constellation_ratio": 0.15,
            },
        )

        state_file = project_root / ".webnovel" / "state.json"
        atomic_write_json(state_file, state.model_dump())
    
    def _generate_workflow_state_json(self, project_root: Path):
        """生成 workflow_state.json"""
        console.print("[cyan]生成 workflow_state.json...[/cyan]")
        
        workflow_state = {
            "current_task": None,
            "last_stable_state": None,
            "history": [],
        }
        
        workflow_file = project_root / ".webnovel" / "workflow_state.json"
        atomic_write_json(workflow_file, workflow_state)
    
    def _generate_project_memory_json(self, project_root: Path):
        """生成 project_memory.json"""
        console.print("[cyan]生成 project_memory.json...[/cyan]")
        
        memory_file = project_root / ".webnovel" / "project_memory.json"
        write_text_file(memory_file, PROJECT_MEMORY_TEMPLATE)
    
    def _generate_setting_files(self, project_root: Path, info: Dict[str, Any]):
        """生成设定文件"""
        console.print("[cyan]生成设定文件...[/cyan]")
        
        # 世界观设定
        worldview_content = SETTING_WORLDVIEW_TEMPLATE.format(
            worldview=info["worldview"],
            social_structure="待补充",
            important_locations="待补充",
            time_period="现代",
        )
        write_text_file(
            project_root / "设定集" / "世界观.md",
            worldview_content,
        )
        
        # 力量体系
        power_content = SETTING_POWER_SYSTEM_TEMPLATE.format(
            power_type=info["power_type"],
            realms=info["realms"],
            ability_rules="待补充",
            limitations="待补充",
        )
        write_text_file(
            project_root / "设定集" / "力量体系.md",
            power_content,
        )
        
        # 角色设定
        characters_content = SETTING_CHARACTERS_TEMPLATE.format(
            protagonist_name=info["protagonist_name"],
            protagonist_gender=info.get("protagonist_gender", "男"),  # 【修复】添加性别
            protagonist_desire=info["protagonist_desire"],
            protagonist_flaw=info["protagonist_flaw"],
            protagonist_traits=info.get("protagonist_traits", ""),
            protagonist_background=info.get("protagonist_background", ""),
            golden_finger=info["golden_finger"],
            supporting_characters="待补充",
            antagonists="待补充",
        )
        write_text_file(
            project_root / "设定集" / "角色设定.md",
            characters_content,
        )
    
    def _generate_master_outline(self, project_root: Path, info: Dict[str, Any]):
        """生成总纲"""
        console.print("[cyan]生成总纲...[/cyan]")

        outline_content = MASTER_OUTLINE_TEMPLATE.format(
            title=info["title"],
            genre=info["genre"],
            one_liner=info.get("one_liner", "待补充"),
            core_conflict=info.get("core_conflict", "待补充"),
            target_audience=info.get("target_audience", ""),
            target_scale=info["target_scale"],
            selling_points=info.get("selling_points", "待补充"),
            main_storyline=info.get("main_storyline", "待补充"),
            worldview=info.get("worldview", "待补充"),
            power_type=info.get("power_type", "待补充"),
            realms=info.get("realms", "待补充"),
            protagonist_name=info.get("protagonist_name", "待补充"),
            protagonist_gender=info.get("protagonist_gender", "男"),
            protagonist_desire=info.get("protagonist_desire", "待补充"),
            protagonist_flaw=info.get("protagonist_flaw", "待补充"),
            protagonist_traits=info.get("protagonist_traits", "待补充"),
            protagonist_background=info.get("protagonist_background", "待补充"),
            golden_finger=info.get("golden_finger", "待补充"),
        )

        write_text_file(
            project_root / "大纲" / "总纲.md",
            outline_content,
        )
    
    def _generate_env_example(self, project_root: Path):
        """生成 .env.example"""
        console.print("[cyan]生成 .env.example...[/cyan]")
        
        env_content = """# NovelWriter 环境变量配置
# 复制此文件为 .env 并填入你的配置

# 千问 API 配置（默认）
QWEN_API_KEY=your_api_key_here
QWEN_MODEL=qwen-max

# Ollama 配置（可选）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:72b

# Embedding 模型配置（RAG 系统，可选）
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_api_key_here

# Rerank 模型配置（RAG 系统，可选）
RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_api_key_here

# 项目配置
NOVEL_LLM_PROVIDER=qwen
NOVEL_LLM_TEMPERATURE=0.7
NOVEL_LLM_MAX_TOKENS=4096
NOVEL_WORKFLOW_MODE=standard
NOVEL_REVIEW_DEPTH=core
"""
        env_file = project_root / ".env.example"
        write_text_file(env_file, env_content)
