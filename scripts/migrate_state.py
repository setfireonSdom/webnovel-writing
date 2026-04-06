#!/usr/bin/env python3
"""
迁移脚本：旧项目 state.json 补充缺失字段

用途：
- 为旧项目补充 CharacterState 的 gender、personality、traits、background、knowledge、aliases 字段
- 为 protagonist dict 补充 gender 字段
- 从设定文件或章节内容中智能推断性别

用法：
    python scripts/migrate_state.py --project /path/to/project
    python scripts/migrate_state.py --project /path/to/project --auto-gender  # 自动推断性别
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.file_ops import read_json, atomic_write_json

logger = logging.getLogger(__name__)


def infer_gender_from_name(name: str) -> str:
    """根据常见中文名推断性别（启发式，准确率约 80%）"""
    # 常见男性字
    male_chars = set("伟刚勇毅俊峰强军平保东文辉力明永健世广志义兴良海山仁波宁贵福生龙元全国胜学祥才发武新利清飞彬富顺信子杰涛昌成康星光天达安岩中茂进林有坚和彪博诚先敬震振壮会思群豪心邦承乐绍功松善厚庆磊民友裕河哲江超浩亮政谦亨奇固之轮翰朗伯宏言若鸣朋斌梁栋维启克伦翔旭鹏泽晨辰士以建家致树炎德行时泰盛雄琛钧冠策腾楠榕风航弘")
    # 常见女性字
    female_chars = set("秀娟英华慧巧美娜静淑惠珠翠雅芝玉萍红娥玲芬芳燕彩春菊兰凤洁梅琳素云莲真环雪荣爱妹霞香月莺媛艳瑞凡佳嘉琼勤珍贞莉桂娣叶璧璐娅琦晶妍茜秋珊莎锦黛青倩婷姣婉娴瑾颖露瑶怡婵雁蓓纨仪荷丹蓉眉君琴蕊薇菁梦岚苑婕馨瑗琰韵融园艺咏卿聪澜纯毓悦昭冰爽琬茗羽希宁欣飘育馥琦妍")
    
    name_only = re.sub(r'[\s\(\)（）]', '', name)
    
    male_count = sum(1 for c in name_only if c in male_chars)
    female_count = sum(1 for c in name_only if c in female_chars)
    
    if male_count > female_count:
        return "男"
    elif female_count > male_count:
        return "女"
    return ""  # 无法判断


def scan_chapters_for_gender_indicators(project_root: Path, character_name: str) -> Dict[str, int]:
    """扫描章节内容，统计角色的性别代词出现次数"""
    male_count = 0
    female_count = 0
    
    chapters_dir = project_root / "正文"
    if not chapters_dir.exists():
        return {"male": 0, "female": 0}
    
    for ch_file in sorted(chapters_dir.glob("*.txt")):
        try:
            content = ch_file.read_text(encoding="utf-8")
            # 查找角色名附近的代词
            # 简单策略：统计全文"他"和"她"的比例（假设主角出现最多）
            if character_name in content:
                male_count += len(re.findall(r'他[们]?', content))
                female_count += len(re.findall(r'她[们]?', content))
        except:
            continue
    
    return {"male": male_count, "female": female_count}


def migrate_character_state(cs_data: Dict[str, Any], auto_gender: bool = False) -> Dict[str, Any]:
    """迁移单个 CharacterState"""
    # 确保所有新字段存在
    defaults = {
        "gender": "",
        "personality": "",
        "traits": [],
        "background": "",
        "knowledge": [],
        "aliases": [],
    }
    
    for key, default_val in defaults.items():
        if key not in cs_data:
            cs_data[key] = default_val
    
    # 自动推断性别
    if auto_gender and not cs_data.get("gender"):
        name = cs_data.get("name", "")
        cs_data["gender"] = infer_gender_from_name(name)
        if cs_data["gender"]:
            logger.info(f"  推断 {name} 性别为: {cs_data['gender']}")
    
    return cs_data


def migrate_state_file(state_path: Path, auto_gender: bool = False) -> bool:
    """迁移单个 state.json 文件"""
    logger.info(f"\n处理: {state_path}")
    
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except Exception as e:
        logger.error(f"  读取失败: {e}")
        return False
    
    modified = False
    
    # 1. 迁移 protagonist dict
    protagonist = state.get("protagonist", {})
    if protagonist and "gender" not in protagonist:
        name = protagonist.get("name", "")
        if auto_gender and name:
            protagonist["gender"] = infer_gender_from_name(name)
            logger.info(f"  推断主角 {name} 性别为: {protagonist['gender']}")
        else:
            protagonist["gender"] = "男"  # 默认
            logger.info(f"  设置主角 {name} 性别为: 男（默认）")
        state["protagonist"] = protagonist
        modified = True
    
    # 2. 迁移 character_states
    character_states = state.get("character_states", [])
    if character_states:
        # 扫描章节获取代词统计（用于推断主角性别）
        protagonist_name = state.get("protagonist", {}).get("name", "")
        gender_indicators = {}
        if auto_gender and protagonist_name:
            gender_indicators = scan_chapters_for_gender_indicators(
                state_path.parent.parent,  # project_root
                protagonist_name
            )
            if gender_indicators["male"] > 0 or gender_indicators["female"] > 0:
                logger.info(f"  章节代词统计 - 他:{gender_indicators['male']} 她:{gender_indicators['female']}")
        
        for i, cs in enumerate(character_states):
            old_cs = dict(cs)
            migrated_cs = migrate_character_state(cs, auto_gender)
            
            # 对主角使用章节扫描结果
            if (auto_gender and cs.get("name") == protagonist_name and 
                not migrated_cs.get("gender") and
                (gender_indicators.get("male", 0) > 0 or gender_indicators.get("female", 0) > 0)):
                if gender_indicators.get("female", 0) > gender_indicators.get("male", 0):
                    migrated_cs["gender"] = "女"
                    logger.info(f"  根据章节内容推断 {protagonist_name} 为女性")
                elif gender_indicators.get("male", 0) > gender_indicators.get("female", 0):
                    migrated_cs["gender"] = "男"
                    logger.info(f"  根据章节内容推断 {protagonist_name} 为男性")
            
            if migrated_cs != old_cs:
                character_states[i] = migrated_cs
                modified = True
        
        state["character_states"] = character_states
    
    # 保存
    if modified:
        backup_path = state_path.with_suffix(".json.bak")
        if not backup_path.exists():
            import shutil
            shutil.copy2(state_path, backup_path)
            logger.info(f"  已备份原文件到 {backup_path}")
        
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.info(f"  ✓ 迁移完成")
    else:
        logger.info(f"  ✓ 已是最新格式，无需迁移")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="迁移旧项目 state.json 到新版格式")
    parser.add_argument("--project", type=str, required=True, help="项目根目录路径")
    parser.add_argument("--auto-gender", action="store_true", help="自动推断角色性别")
    parser.add_argument("--all-webnovel", action="store_true", help="迁移 .webnovel 目录下所有 state.json（用于批量处理）")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"
    )
    
    project_root = Path(args.project)
    if not project_root.exists():
        print(f"错误: 项目路径不存在: {project_root}")
        sys.exit(1)
    
    print(f"=" * 60)
    print(f" Novel-Writer 状态迁移工具")
    print(f"=" * 60)
    print(f"项目路径: {project_root}")
    print(f"自动推断性别: {'是' if args.auto_gender else '否'}")
    print()
    
    state_files = []
    
    if args.all_webnovel:
        # 查找所有 .webnovel/state.json
        for state_file in project_root.rglob(".webnovel/state.json"):
            state_files.append(state_file)
    else:
        # 只处理当前项目
        state_file = project_root / ".webnovel" / "state.json"
        if state_file.exists():
            state_files.append(state_file)
    
    if not state_files:
        print("未找到 state.json 文件")
        sys.exit(0)
    
    success_count = 0
    for sf in state_files:
        if migrate_state_file(sf, args.auto_gender):
            success_count += 1
    
    print(f"\n{'=' * 60}")
    print(f"迁移完成: {success_count}/{len(state_files)} 个文件")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
