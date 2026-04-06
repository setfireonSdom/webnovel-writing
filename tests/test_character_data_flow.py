"""
角色数据流完整性测试
验证性别、性格、特征等字段从初始化到写作prompt的完整流通
"""

import pytest
from pathlib import Path
from src.data.schemas import CharacterState, ProjectState
from src.data.long_term_memory import LongTermMemory


class TestCharacterDataFlow:
    """角色数据流测试"""

    def test_character_state_has_gender(self):
        """CharacterState 必须包含 gender 字段"""
        cs = CharacterState(
            name="张三",
            gender="男",
            cultivation="炼气三层",
            status="active",
        )
        assert cs.gender == "男"
        assert cs.name == "张三"

    def test_character_state_has_all_fields(self):
        """CharacterState 必须包含所有新增字段"""
        cs = CharacterState(
            name="李四",
            gender="女",
            cultivation="筑基初期",
            status="active",
            personality="冷酷、果断",
            traits=["聪明", "狡猾"],
            background="曾是某大家族的天才少女",
            relationships={"王五": "师兄妹"},
            key_items=["灵剑", "传送符"],
            knowledge=["知道某个秘密"],
            aliases=["冰美人", "剑痴"],
            notes="经脉受过伤",
        )
        assert cs.gender == "女"
        assert cs.personality == "冷酷、果断"
        assert len(cs.traits) == 2
        assert cs.background != ""
        assert len(cs.knowledge) == 1
        assert len(cs.aliases) == 2

    def test_compress_state_for_context_includes_gender(self, tmp_path):
        """compress_state_for_context 必须包含性别信息"""
        # 创建临时项目目录
        webnovel_dir = tmp_path / ".webnovel"
        webnovel_dir.mkdir()
        
        # 创建测试状态
        state = ProjectState(
            protagonist={
                "name": "林晨",
                "gender": "男",
                "desire": "变强",
                "flaw": "过于正直",
            },
            character_states=[
                CharacterState(
                    name="林晨",
                    gender="男",
                    cultivation="炼气三层",
                    status="active",
                    personality="坚韧、聪明",
                ),
                CharacterState(
                    name="苏瑶",
                    gender="女",
                    cultivation="筑基初期",
                    status="active",
                    personality="温柔、善良",
                ),
            ],
        )

        # 创建 LongTermMemory 实例
        ltm = LongTermMemory(tmp_path)
        context = ltm.compress_state_for_context(state)

        # 验证性别信息出现在上下文中
        assert "性别: 男" in context or "男" in context
        assert "苏瑶" in context
        # 女性角色应该能识别性别
        assert "女" in context

    def test_protagonist_initialization_with_gender(self):
        """项目初始化时 protagonist dict 必须包含性别"""
        state = ProjectState(
            project={"title": "测试小说", "genre": "玄幻"},
            protagonist={
                "name": "林晨",
                "gender": "男",  # 必须包含
                "desire": "变强",
                "flaw": "过于正直",
                "traits": "坚韧、聪明",
                "background": "普通人",
                "golden_finger": "系统",
            },
        )
        assert "gender" in state.protagonist
        assert state.protagonist["gender"] == "男"

    def test_character_state_merge_logic(self):
        """验证角色状态合并逻辑：优先从 character_states 取完整信息"""
        # 模拟 state.protagonist 有部分信息
        protagonist_dict = {
            "name": "林晨",
            "gender": "男",
            "desire": "变强",
        }
        
        # character_states 有完整信息
        character_states = [
            CharacterState(
                name="林晨",
                gender="男",
                cultivation="炼气三层",
                status="active",
                personality="坚韧",
            )
        ]
        
        # 查找主角信息
        protagonist_state = None
        for cs in character_states:
            if cs.name == protagonist_dict["name"]:
                protagonist_state = cs
                break
        
        # 应该能找到
        assert protagonist_state is not None
        assert protagonist_state.gender == "男"
        assert protagonist_state.cultivation == "炼气三层"
        
        # 性别获取优先级：character_states > protagonist dict
        gender = protagonist_state.gender if protagonist_state.gender else protagonist_dict.get("gender", "男")
        assert gender == "男"

    def test_character_profile_for_ooc_checker(self):
        """OOC 检查器必须接收到完整的角色档案"""
        state = ProjectState(
            protagonist={
                "name": "林晨",
                "gender": "男",
                "desire": "变强",
                "flaw": "过于正直",
                "golden_finger": "系统",
            },
            character_states=[
                CharacterState(
                    name="林晨",
                    gender="男",
                    cultivation="炼气三层",
                    status="active",
                    personality="坚韧、聪明",
                    background="普通人获得机缘",
                ),
                CharacterState(
                    name="苏瑶",
                    gender="女",
                    cultivation="筑基初期",
                    status="active",
                    personality="温柔",
                ),
            ],
        )
        
        # 模拟 OOC checker 的 _build_character_profiles
        profiles = {}
        for cs in state.character_states:
            profiles[cs.name] = {
                "gender": cs.gender,
                "cultivation": cs.cultivation,
                "status": cs.status,
                "personality": cs.personality,
                "background": cs.background,
            }
        
        # 添加主角
        protagonist = state.protagonist.get("name", "")
        if protagonist and protagonist not in profiles:
            profiles[protagonist] = {}
        profiles[protagonist].update({
            "is_protagonist": True,
            "desire": state.protagonist.get("desire", ""),
            "flaw": state.protagonist.get("flaw", ""),
        })
        if not profiles[protagonist].get("gender"):
            profiles[protagonist]["gender"] = state.protagonist.get("gender", "男")
        
        # 验证林晨的档案完整
        linchen_profile = profiles["林晨"]
        assert linchen_profile["gender"] == "男"
        assert linchen_profile["cultivation"] == "炼气三层"
        assert linchen_profile["personality"] == "坚韧、聪明"
        assert linchen_profile["is_protagonist"] is True
        
        # 验证苏瑶的档案
        suyao_profile = profiles["苏瑶"]
        assert suyao_profile["gender"] == "女"
        assert suyao_profile["cultivation"] == "筑基初期"
