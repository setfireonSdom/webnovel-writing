"""
性别代词扫描器 - 不依赖 LLM 的快速硬性检查
职责：扫描章节内容，检测角色性别代词是否与其设定性别一致
原理：正则匹配角色名附近的"他/她"，与设定性别对比
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class GenderIssue:
    """性别代词问题"""
    character_name: str
    expected_gender: str  # 设定性别
    found_pronoun: str   # 发现的代词（他/她）
    pronoun_count: int   # 出现次数
    location_hint: str   # 大致位置
    severity: str = "critical"  # 固定为 critical


class GenderPronounScanner:
    """
    性别代词扫描器 - 纯正则实现，不依赖 LLM
    
    工作原理：
    1. 对每个已知角色，在文本中查找其名字附近 50 字范围内的代词
    2. 统计"他"和"她"的出现次数
    3. 如果角色设定为"男"但"她"出现次数 > "他"，标记为 critical
    4. 如果角色设定为"女"但"他"出现次数 > "她"，标记为 critical
    """
    
    # 男性代词
    MALE_PRONOUNS = ["他", "他们"]
    # 女性代词
    FEMALE_PRONOUNS = ["她", "她们"]
    # 扫描窗口（角色名前后多少字）
    WINDOW_SIZE = 80
    
    def __init__(self):
        self.issues: List[GenderIssue] = []
    
    def scan(
        self,
        content: str,
        character_genders: Dict[str, str],
    ) -> List[GenderIssue]:
        """
        扫描章节内容
        
        Args:
            content: 章节文本
            character_genders: {角色名: 性别} 字典，性别为"男"/"女"/""
        
        Returns:
            性别代词问题列表
        """
        self.issues = []
        
        for char_name, expected_gender in character_genders.items():
            if not expected_gender or expected_gender not in ("男", "女"):
                # 不知道性别，跳过
                continue
            
            # 在角色名附近扫描代词
            male_count, female_count = self._count_pronouns_near_name(content, char_name)
            
            # 判断是否存在矛盾
            if expected_gender == "男" and female_count > male_count and female_count >= 3:
                # 男性角色，但"她"出现更多（至少3次才判定，避免误判）
                self.issues.append(GenderIssue(
                    character_name=char_name,
                    expected_gender="男",
                    found_pronoun="她",
                    pronoun_count=female_count,
                    location_hint=f"在'{char_name}'附近发现{female_count}次'她'，{male_count}次'他'",
                    severity="critical",
                ))
            elif expected_gender == "女" and male_count > female_count and male_count >= 3:
                # 女性角色，但"他"出现更多
                self.issues.append(GenderIssue(
                    character_name=char_name,
                    expected_gender="女",
                    found_pronoun="他",
                    pronoun_count=male_count,
                    location_hint=f"在'{char_name}'附近发现{male_count}次'他'，{female_count}次'她'",
                    severity="critical",
                ))
        
        return self.issues
    
    def _count_pronouns_near_name(self, content: str, name: str) -> tuple[int, int]:
        """
        在角色名附近统计代词出现次数

        Returns:
            (male_count, female_count)
        """
        male_count = 0
        female_count = 0

        # 追踪已统计过的代词位置，避免重叠窗口重复计数
        counted_male_positions: set[int] = set()
        counted_female_positions: set[int] = set()

        # 查找所有角色名出现的位置
        name_pattern = re.escape(name)
        name_matches = list(re.finditer(name_pattern, content))

        for name_match in name_matches:
            start = max(0, name_match.start() - self.WINDOW_SIZE)
            end = min(len(content), name_match.end() + self.WINDOW_SIZE)
            window = content[start:end]
            window_start_offset = start  # 窗口在原文中的起始位置

            # 统计代词（排除角色名本身包含代词的情况）
            for pronoun in self.MALE_PRONOUNS:
                for pron_match in re.finditer(re.escape(pronoun), window):
                    # 计算在原文中的绝对位置
                    abs_pos = window_start_offset + pron_match.start()
                    # 去重：如果这个位置已经统计过，跳过
                    if abs_pos not in counted_male_positions:
                        counted_male_positions.add(abs_pos)
                        male_count += 1

            for pronoun in self.FEMALE_PRONOUNS:
                for pron_match in re.finditer(re.escape(pronoun), window):
                    # 计算在原文中的绝对位置
                    abs_pos = window_start_offset + pron_match.start()
                    # 去重：如果这个位置已经统计过，跳过
                    if abs_pos not in counted_female_positions:
                        counted_female_positions.add(abs_pos)
                        female_count += 1

        return male_count, female_count
    
    def get_error_message(self, issues: List[GenderIssue] = None) -> str:
        """生成人类可读的错误信息"""
        if issues is None:
            issues = self.issues
        if not issues:
            return ""
        
        lines = ["【性别代词错误】以下角色的性别代词与设定矛盾："]
        for issue in issues:
            correct_pronoun = "他" if issue.expected_gender == "男" else "她"
            lines.append(
                f"- {issue.character_name} 设定为{issue.expected_gender}性（应使用'{correct_pronoun}'），"
                f"但文中使用了'{issue.found_pronoun}'（{issue.location_hint}）"
            )
        return "\n".join(lines)
