"""
Anti-AI 词库与扫描器
职责：
1. 200+ 高风险 AI 词汇库
2. 逐段扫描，命中即标记
3. 提供自动替换建议
"""

import re
from typing import Dict, List, Tuple


# ===== 第1层：高风险词汇库 =====

HIGH_RISK_WORDS = {
    # A. 总结归纳词
    "summary_words": [
        "综合", "总之", "总而言之", "由此可见", "可以看出", "不难发现",
        "归根结底", "说到底", "总体来看", "从这个角度看", "换句话说",
        "简而言之", "概括来说", "可以说", "由此得出", "结论是",
        "最终可知", "总的来说", "总括起来", "整体而言", "总体上", "综上"
    ],
    
    # B. 枚举模板词
    "enum_words": [
        "首先", "其次", "再次", "最后", "第一", "第二", "第三",
        "其一", "其二", "其三", "一方面", "另一方面", "再者",
        "此外", "另外", "同时", "接着", "然后", "随后", "紧接着",
        "最后一步", "下一步", "第一点", "第二点"
    ],
    
    # C. 书面学术腔
    "academic_words": [
        "某种程度上", "本质上", "意义上", "维度上", "层面上",
        "在于", "体现为", "构成了", "形成了", "实现了", "完成了",
        "进行了", "展开了", "推动了", "促进了", "提供了",
        "具备了", "拥有了", "达成了", "呈现出", "表现出",
        "反映出", "蕴含着", "折射出"
    ],
    
    # D. 逻辑连接滥用
    "logic_words": [
        "因此", "因而", "所以", "由于", "然而", "不过", "但是",
        "与此同时", "同样地", "对应地", "相应地", "进一步",
        "更进一步", "从而", "进而", "于是", "结果是", "于是乎",
        "故而", "由此", "相较之下", "反过来说"
    ],
    
    # E. 情绪直述词
    "emotion_words": [
        "非常愤怒", "非常开心", "非常难过", "心中五味杂陈",
        "百感交集", "情绪复杂", "内心震撼", "不由得感慨",
        "感到无奈", "感到痛苦", "感到欣慰", "感到恐惧",
        "深受触动", "心潮起伏", "心情沉重", "心情复杂",
        "心里一暖", "心里一沉", "心中一紧", "不禁一愣",
        "不由一怔", "内心一震"
    ],
    
    # F. 动作套话
    "action_cliches": [
        "皱起眉头", "叹了口气", "深吸一口气", "缓缓开口",
        "沉声说道", "淡淡说道", "冷冷说道", "轻声说道",
        "嘴角上扬", "嘴角抽了抽", "眼神一凝", "目光一闪",
        "身形一滞", "脚步一顿", "浑身一震", "心头一跳",
        "不由后退半步", "猛地转身", "抬手一挥", "缓缓点头",
        "轻轻摇头", "下意识后退"
    ],
    
    # G. 环境套话
    "environment_cliches": [
        "空气仿佛凝固", "气氛骤然紧张", "气压陡然下降",
        "夜色如墨", "月色如水", "寒风刺骨", "四周一片寂静",
        "死一般的寂静", "时间仿佛静止", "空间仿佛扭曲",
        "房间里弥漫着", "唯一的光源", "摇摇欲坠",
        "压抑得让人喘不过气", "沉默像潮水", "空气中充满了",
        "一切都显得", "世界仿佛", "就在这一刻"
    ],
    
    # H. 叙事填充词
    "narrative_fillers": [
        "事实上", "实际上", "某种意义上", "严格来说",
        "客观而言", "主观上", "一般来说", "通常情况下",
        "在这种情况下", "在这个时候", "在此基础上",
        "在这个意义上", "从某种角度", "对于他来说",
        "对她而言", "这意味着", "这说明", "这代表着",
        "这并不奇怪", "并非偶然", "不可否认", "毋庸置疑"
    ],
    
    # I. 抽象空泛词
    "abstract_words": [
        "命运", "成长", "蜕变", "升华", "价值", "意义",
        "抉择", "坚持", "信念", "初心", "希望", "绝望",
        "勇气", "正义", "邪恶", "真实", "虚伪", "复杂",
        "深刻", "宏大", "渺小", "沉重"
    ],
    
    # J. 机械开场/收尾
    "mechanical_open_close": [
        "故事要从", "让我们把视线", "镜头转到",
        "与此同时在另一边", "回到现在", "再说回",
        "这一切都要从", "他并不知道", "命运的齿轮开始转动",
        "新的篇章开始了", "未完待续", "故事才刚刚开始",
        "真正的考验还在后面", "一场风暴即将来临",
        "更大的阴谋正在酝酿", "这只是开始", "答案尚未揭晓",
        "未来会怎样", "谁也不知道"
    ]
}

# 合并所有词
ALL_RISK_WORDS = []
for category, words in HIGH_RISK_WORDS.items():
    ALL_RISK_WORDS.extend(words)


class AntiAIScanner:
    """Anti-AI 扫描器"""
    
    def __init__(self):
        self.risk_words = ALL_RISK_WORDS
        self.word_categories = {
            word: category 
            for category, words in HIGH_RISK_WORDS.items()
            for word in words
        }
        
        # 编译正则表达式
        self.pattern = re.compile(
            '|'.join(re.escape(word) for word in self.risk_words),
            re.UNICODE
        )
    
    def scan_text(self, text: str) -> List[Dict]:
        """扫描文本，返回命中的AI词汇列表"""
        results = []
        
        # 按段落扫描
        paragraphs = text.split('\n')
        for para_idx, paragraph in enumerate(paragraphs):
            matches = self.pattern.finditer(paragraph)
            for match in matches:
                word = match.group()
                results.append({
                    "word": word,
                    "category": self.word_categories.get(word, "unknown"),
                    "paragraph": para_idx + 1,
                    "context": self._get_context(paragraph, match.start(), match.end()),
                    "severity": self._get_severity(word)
                })
        
        return results
    
    def _get_context(self, paragraph: str, start: int, end: int, radius: int = 20) -> str:
        """获取命中词上下文"""
        start = max(0, start - radius)
        end = min(len(paragraph), end + radius)
        return paragraph[start:end]
    
    def _get_severity(self, word: str) -> str:
        """获取风险等级"""
        high_risk = ["首先", "其次", "最后", "综合", "总之", "总而言之",
                     "命运的齿轮开始转动", "故事要从"]
        if word in high_risk:
            return "high"
        return "medium"
    
    def get_report(self, text: str) -> str:
        """生成扫描报告"""
        results = self.scan_text(text)
        
        if not results:
            return "✅ Anti-AI 检查通过，未发现高风险词汇"
        
        lines = [f"⚠️ Anti-AI 检查发现 {len(results)} 处风险："]
        
        # 按严重度排序
        results.sort(key=lambda x: 0 if x["severity"] == "high" else 1)
        
        for r in results[:20]:  # 最多显示20条
            emoji = "🔴" if r["severity"] == "high" else "🟡"
            lines.append(f"{emoji} [{r['category']}] 第{r['paragraph']}段: \"{r['word']}\"")
            lines.append(f"   上下文: ...{r['context']}...")
        
        if len(results) > 20:
            lines.append(f"... 还有 {len(results) - 20} 处未显示")
        
        return "\n".join(lines)
    
    def is_pass(self, text: str, max_high: int = 3, max_total: int = 15) -> Tuple[bool, str]:
        """判断是否通过检查"""
        results = self.scan_text(text)
        
        high_count = sum(1 for r in results if r["severity"] == "high")
        total_count = len(results)
        
        if high_count > max_high:
            return False, f"高风险词汇过多({high_count}>{max_high})"
        if total_count > max_total:
            return False, f"AI词汇总数过多({total_count}>{max_total})"
        
        return True, f"通过（高风险:{high_count}, 总计:{total_count}）"


# 单例
scanner = AntiAIScanner()
