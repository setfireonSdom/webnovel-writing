"""
自动复盘审计系统 - 每50章自动生成审计报告
职责：
1. 检查隐性矛盾（如"第3章说A怕火，第80章却不怕"）
2. 统计伏笔回收率
3. 分析角色弧光一致性
4. 检查世界观规则变更历史
5. 生成可操作的审计报告
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.file_ops import read_text_file, write_text_file, ensure_directory
from ..data.state_manager import StateManager
from ..data.world_rules import WorldRulesManager
from ..data.character_arc_tracker import CharacterArcTracker
from ..data.plot_thread_tracker import PlotThreadTracker

logger = logging.getLogger(__name__)


class AutoAuditReport:
    """自动审计报告生成器"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.audit_dir = self.webnovel_dir / "audits"
        self.state_manager = StateManager(project_root)
        
        ensure_directory(self.audit_dir)
        
        # 初始化各组件（只读模式）
        try:
            self.world_rules_manager = WorldRulesManager(project_root)
        except:
            self.world_rules_manager = None
        
        try:
            self.character_arc_tracker = CharacterArcTracker(project_root)
        except:
            self.character_arc_tracker = None
        
        try:
            self.plot_threads = PlotThreadTracker(project_root)
        except:
            self.plot_threads = None

    def generate_report(self, chapter_num: Optional[int] = None) -> str:
        """生成审计报告"""
        if chapter_num is None:
            chapter_num = self.state_manager.get_current_chapter()
        
        lines = []
        lines.append(f"# 📊 网文项目自动审计报告")
        lines.append(f"\n**审计章节**: 第 {chapter_num} 章")
        lines.append(f"\n**生成时间**: {datetime.now().isoformat()}")
        lines.append(f"\n---\n")
        
        # 1. 整体健康度评分
        health_score = self._calculate_health_score(chapter_num)
        lines.append(f"## 🎯 整体健康度: {health_score['score']}/100")
        lines.append(f"\n{health_score['emoji']} {health_score['summary']}")
        lines.append("")
        
        # 2. 一致性检查
        lines.append(self._audit_consistency(chapter_num))
        
        # 3. 伏笔回收统计
        if self.plot_threads:
            lines.append(self._audit_plot_threads(chapter_num))
        
        # 4. 角色弧光分析
        if self.character_arc_tracker:
            lines.append(self._audit_character_arcs(chapter_num))
        
        # 5. 世界观规则检查
        if self.world_rules_manager:
            lines.append(self._audit_world_rules(chapter_num))
        
        # 6. 节奏与质量趋势
        lines.append(self._audit_quality_trends(chapter_num))
        
        # 7. 潜在问题与建议
        lines.append(self._generate_recommendations(chapter_num))
        
        report_content = "\n".join(lines)
        
        # 保存报告
        report_file = self.audit_dir / f"audit_chapter_{chapter_num:04d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        write_text_file(report_file, report_content)
        logger.info(f"审计报告已保存: {report_file}")
        
        return report_content

    def _calculate_health_score(self, chapter_num: int) -> Dict[str, Any]:
        """计算整体健康度评分"""
        score = 100
        issues = []
        
        # 1. 检查审查通过率
        state = self.state_manager.load_state()
        review_checkpoints = state.review_checkpoints
        if review_checkpoints:
            recent_checks = review_checkpoints[-10:]  # 最近10次审查
            avg_score = sum(c.get('score', 0) for c in recent_checks) / len(recent_checks)
            if avg_score < 60:
                score -= 20
                issues.append("最近审查平均分低于60分")
            elif avg_score < 70:
                score -= 10
                issues.append("最近审查平均分偏低")
        
        # 2. 检查角色一致性问题
        if self.character_arc_tracker:
            arcs = self.character_arc_tracker.get_all_arcs()
            inconsistent_chars = sum(1 for arc in arcs.values() if not arc.is_consistent)
            if inconsistent_chars > 0:
                score -= inconsistent_chars * 5
                issues.append(f"{inconsistent_chars} 个角色存在一致性问题")
        
        # 3. 检查世界观规则冲突
        if self.world_rules_manager:
            rules_state = self.world_rules_manager.state
            conflicted_rules = sum(1 for r in rules_state.rules if '冲突' in (r.notes or ''))
            if conflicted_rules > 0:
                score -= conflicted_rules * 3
                issues.append(f"{conflicted_rules} 条世界观规则存在冲突")
        
        # 4. 检查未回收伏笔
        if self.plot_threads:
            overdue_threads = [t for t in self.plot_threads.threads
                             if t.status == 'open' and t.created_chapter < chapter_num - 50]
            if len(overdue_threads) > 5:
                score -= 10
                issues.append(f"有 {len(overdue_threads)} 个伏笔超过50章未回收")
        
        # 确定评分等级
        if score >= 90:
            emoji = "✅"
            summary = "项目健康状况优秀，继续保持！"
        elif score >= 75:
            emoji = "👍"
            summary = "项目状况良好，有少量需要注意的问题。"
        elif score >= 60:
            emoji = "⚠️"
            summary = "项目存在一些问题，建议查看下方详细报告。"
        else:
            emoji = "🚨"
            summary = "项目存在较多问题，建议立即进行人工审查和修复。"
        
        return {
            "score": max(0, score),
            "emoji": emoji,
            "summary": summary,
            "issues": issues
        }

    def _audit_consistency(self, chapter_num: int) -> str:
        """审计一致性"""
        lines = ["\n## 🔍 一致性审计"]
        
        # 加载所有审查检查点
        state = self.state_manager.load_state()
        checkpoints = state.review_checkpoints
        
        if not checkpoints:
            lines.append("\n暂无审查数据。")
            return "\n".join(lines)
        
        # 统计各维度表现
        dimension_stats = {}
        for cp in checkpoints:
            if 'dimension_scores' in cp:
                for dim, score in cp['dimension_scores'].items():
                    if dim not in dimension_stats:
                        dimension_stats[dim] = []
                    dimension_stats[dim].append(score)
        
        if dimension_stats:
            lines.append("\n### 各维度平均分（最近20章）")
            for dim, scores in list(dimension_stats.items())[-20:]:
                avg = sum(scores) / len(scores) if scores else 0
                trend = "↑" if len(scores) > 1 and scores[-1] > scores[-2] else "↓" if len(scores) > 1 else "-"
                emoji = "✅" if avg >= 80 else "⚠️" if avg >= 60 else "❌"
                lines.append(f"{emoji} {dim}: {avg:.1f} {trend}")
        
        # 检查严重问题
        critical_issues = [cp for cp in checkpoints 
                          if cp.get('severity_counts', {}).get('critical', 0) > 0]
        if critical_issues:
            lines.append(f"\n### ⚠️ 发现 {len(critical_issues)} 次严重问题")
            for cp in critical_issues[-5:]:  # 最近5次
                lines.append(f"- 第{cp.get('chapter', '?')}章: {cp.get('severity_counts', {}).get('critical', 0)} 个严重问题")
        
        return "\n".join(lines)

    def _audit_plot_threads(self, chapter_num: int) -> str:
        """审计伏笔回收"""
        lines = ["\n## 🧵 伏笔回收审计"]
        
        threads = self.plot_threads.threads
        if not threads:
            lines.append("\n暂无伏笔记录。")
            return "\n".join(lines)
        
        # 统计状态
        total = len(threads)
        resolved = sum(1 for t in threads if t.status == 'resolved')
        open_count = sum(1 for t in threads if t.status == 'open')
        abandoned = sum(1 for t in threads if t.status == 'abandoned')
        overdue = sum(1 for t in threads if t.status == 'open' and t.created_chapter < chapter_num - 50)
        
        recovery_rate = (resolved / total * 100) if total > 0 else 0
        
        lines.append(f"\n### 伏笔统计")
        lines.append(f"- 总伏笔数: {total}")
        lines.append(f"- 已回收: {resolved} ({recovery_rate:.1f}%)")
        lines.append(f"- 活跃中: {open_count}")
        lines.append(f"- 已放弃: {abandoned}")
        lines.append(f"- ⚠️ 超期未回收: {overdue}")
        
        # 超期伏笔详情
        if overdue > 0:
            lines.append(f"\n### 🚨 超期伏笔（超过50章未回收）")
            overdue_threads = [t for t in threads 
                              if t.status == 'open' and t.created_chapter < chapter_num - 50]
            for t in overdue_threads[:10]:  # 最多显示10个
                chapters_overdue = chapter_num - t.created_chapter
                lines.append(f"- [{t.type}] 第{t.created_chapter}章开启: {t.description}")
                lines.append(f"  已持续 {chapters_overdue} 章未回收")
        
        return "\n".join(lines)

    def _audit_character_arcs(self, chapter_num: int) -> str:
        """审计角色弧光"""
        lines = ["\n## 👥 角色弧光审计"]
        
        arcs = self.character_arc_tracker.get_all_arcs()
        if not arcs:
            lines.append("\n暂无角色弧光记录。")
            return "\n".join(lines)
        
        # 统计
        consistent_count = sum(1 for arc in arcs.values() if arc.is_consistent)
        inconsistent_count = len(arcs) - consistent_count
        
        lines.append(f"\n### 角色统计")
        lines.append(f"- 追踪角色数: {len(arcs)}")
        lines.append(f"- ✅ 一致性良好: {consistent_count}")
        lines.append(f"- ❌ 存在问题: {inconsistent_count}")
        
        # 不一致角色详情
        if inconsistent_count > 0:
            lines.append(f"\n### ⚠️ 一致性问题角色")
            for name, arc in arcs.items():
                if not arc.is_consistent and arc.consistency_issues:
                    lines.append(f"\n**{name}**:")
                    for issue in arc.consistency_issues[:3]:  # 最多显示3个问题
                        lines.append(f"- {issue}")
        
        # 角色成长亮点
        lines.append(f"\n### ✨ 角色成长亮点")
        for name, arc in arcs.items():
            if len(arc.power_progression) > 0:
                lines.append(f"\n**{name}** 的能力进展:")
                for pp in arc.power_progression[-3:]:  # 最近3次
                    lines.append(f"- 第{pp['chapter']}章: {pp['old_level']} → {pp['new_level']}")
        
        return "\n".join(lines)

    def _audit_world_rules(self, chapter_num: int) -> str:
        """审计世界观规则"""
        lines = ["\n## 📜 世界观规则审计"]
        
        rules_state = self.world_rules_manager.state
        total_rules = len(rules_state.rules)
        active_rules = sum(1 for r in rules_state.rules if r.is_active)
        
        lines.append(f"\n### 规则统计")
        lines.append(f"- 总规则数: {total_rules}")
        lines.append(f"- 活跃规则: {active_rules}")
        lines.append(f"- 已停用: {total_rules - active_rules}")
        
        # 按类别统计
        by_category = {}
        for rule in rules_state.rules:
            if rule.is_active:
                by_category.setdefault(rule.category, 0)
                by_category[rule.category] += 1
        
        if by_category:
            lines.append(f"\n### 按类别分布")
            for category, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {category}: {count}")
        
        # 冲突规则
        conflicted = [r for r in rules_state.rules if '冲突' in (r.notes or '')]
        if conflicted:
            lines.append(f"\n### ⚠️ 存在冲突的规则")
            for rule in conflicted[:5]:
                lines.append(f"- [{rule.id}] {rule.name}: {rule.notes}")
        
        # 最近变更
        if rules_state.change_log:
            lines.append(f"\n### 最近变更（最近10条）")
            for change in rules_state.change_log[-10:]:
                lines.append(f"- [{change['timestamp'][:10]}] {change['description']}")
        
        return "\n".join(lines)

    def _audit_quality_trends(self, chapter_num: int) -> str:
        """审计质量趋势"""
        lines = ["\n## 📈 质量趋势分析"]
        
        # 加载审查检查点
        state = self.state_manager.load_state()
        checkpoints = state.review_checkpoints
        
        if len(checkpoints) < 5:
            lines.append(f"\n数据不足（需要至少5章数据），当前有 {len(checkpoints)} 章。")
            return "\n".join(lines)
        
        # 计算每10章的平均分趋势
        batch_size = 10
        batches = []
        for i in range(0, len(checkpoints), batch_size):
            batch = checkpoints[i:i+batch_size]
            avg_score = sum(cp.get('score', 0) for cp in batch) / len(batch)
            batches.append({
                'start': batch[0].get('chapter', 0),
                'end': batch[-1].get('chapter', 0),
                'avg_score': avg_score
            })
        
        if len(batches) >= 2:
            lines.append(f"\n### 每{batch_size}章质量趋势")
            for batch in batches:
                trend = "↑" if batches[-1]['avg_score'] > batches[0]['avg_score'] else "↓"
                lines.append(f"- 第{batch['start']}-{batch['end']}章: {batch['avg_score']:.1f}分 {trend}")
            
            # 判断整体趋势
            first_avg = batches[0]['avg_score']
            last_avg = batches[-1]['avg_score']
            if last_avg > first_avg + 5:
                lines.append(f"\n✅ 质量呈上升趋势，进步明显！")
            elif last_avg < first_avg - 5:
                lines.append(f"\n⚠️ 质量呈下降趋势，需要注意。")
            else:
                lines.append(f"\n👍 质量保持稳定。")
        
        # 爽点密度趋势
        cool_points = [cp.get('cool_point_count', 0) for cp in checkpoints if 'cool_point_count' in cp]
        if cool_points:
            recent_avg = sum(cool_points[-10:]) / min(10, len(cool_points))
            lines.append(f"\n### 爽点密度")
            lines.append(f"- 最近10章平均: {recent_avg:.1f} 个/章")
            if recent_avg < 1:
                lines.append(f"- ⚠️ 爽点密度不足，建议每章至少1个爽点")
        
        return "\n".join(lines)

    def _generate_recommendations(self, chapter_num: int) -> str:
        """生成建议"""
        lines = ["\n## 💡 审计建议"]
        
        recommendations = []
        
        # 基于健康度评分的建议
        health = self._calculate_health_score(chapter_num)
        if health['score'] < 60:
            recommendations.append({
                'priority': 'high',
                'item': '建议进行全面人工审查',
                'detail': f'当前健康度仅{health["score"]}分，存在较多问题。'
            })
        
        # 基于伏笔回收的建议
        if self.plot_threads:
            threads = self.plot_threads.threads
            overdue = [t for t in threads if t.status == 'open' and t.chapter_num < chapter_num - 50]
            if len(overdue) > 3:
                recommendations.append({
                    'priority': 'medium',
                    'item': '回收超期伏笔',
                    'detail': f'有{len(overdue)}个伏笔超过50章未回收，建议在后续章节中适当呼应或回收。'
                })
        
        # 基于角色一致性的建议
        if self.character_arc_tracker:
            arcs = self.character_arc_tracker.get_all_arcs()
            inconsistent = [name for name, arc in arcs.items() if not arc.is_consistent]
            if inconsistent:
                recommendations.append({
                    'priority': 'high',
                    'item': '修复角色一致性问题',
                    'detail': f'以下角色存在一致性问题: {", ".join(inconsistent[:3])}'
                })
        
        # 基于世界观规则的建议
        if self.world_rules_manager:
            rules_state = self.world_rules_manager.state
            conflicted = [r for r in rules_state.rules if '冲突' in (r.notes or '')]
            if conflicted:
                recommendations.append({
                    'priority': 'high',
                    'item': '解决世界观规则冲突',
                    'detail': f'有{len(conflicted)}条规则存在冲突，需要人工判断并修正。'
                })
        
        # 输出建议
        if not recommendations:
            lines.append("\n✅ 暂无特别建议，继续保持！")
        else:
            lines.append(f"\n共 {len(recommendations)} 条建议：\n")
            for i, rec in enumerate(recommendations, 1):
                priority_emoji = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(rec['priority'], '⚪')
                
                lines.append(f"{i}. {priority_emoji} **{rec['item']}**")
                lines.append(f"   {rec['detail']}")
                lines.append("")
        
        return "\n".join(lines)
