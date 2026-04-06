"""
性能监控工具
"""

import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root
        self.timings: Dict[str, float] = {}
        self.start_time: Optional[float] = None
        self.step_start_times: Dict[str, float] = {}

        if project_root:
            self.observability_dir = project_root / ".webnovel" / "observability"
            self.observability_dir.mkdir(parents=True, exist_ok=True)
            self.timing_log_file = self.observability_dir / "performance.jsonl"
        else:
            self.timing_log_file = None

    def start(self, step_name: str):
        """开始计时"""
        self.step_start_times[step_name] = time.time()
        if self.start_time is None:
            self.start_time = self.step_start_times[step_name]
        logger.debug(f"开始: {step_name}")

    def stop(self, step_name: str) -> float:
        """停止计时并记录"""
        if step_name in self.step_start_times:
            elapsed = time.time() - self.step_start_times[step_name]
            self.timings[step_name] = elapsed
            logger.debug(f"完成: {step_name} - {elapsed:.2f}s")
            
            # 记录到文件
            self._log_timing(step_name, elapsed)
            
            del self.step_start_times[step_name]
            return elapsed
        return 0.0

    def _log_timing(self, step_name: str, elapsed: float):
        """记录性能数据到文件"""
        if self.timing_log_file:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "step": step_name,
                "duration_seconds": round(elapsed, 3),
            }
            try:
                with open(self.timing_log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"记录性能数据失败: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """获取性能总结"""
        total_time = sum(self.timings.values())
        return {
            "total_time_seconds": round(total_time, 2),
            "steps": {k: round(v, 2) for k, v in self.timings.items()},
            "step_percentages": {
                k: round((v / total_time * 100) if total_time > 0 else 0, 1)
                for k, v in self.timings.items()
            },
        }

    def print_summary(self, console=None):
        """打印性能总结"""
        summary = self.get_summary()
        
        if console:
            console.print(f"\n[dim]⏱️ 性能总结[/dim]")
            console.print(f"[dim]总耗时: {summary['total_time_seconds']:.2f}s[/dim]")
            for step, duration in summary["steps"].items():
                percentage = summary["step_percentages"][step]
                console.print(f"[dim]  - {step}: {duration}s ({percentage}%)[/dim]")
        else:
            logger.info(f"性能总结 - 总耗时: {summary['total_time_seconds']}s")
            for step, duration in summary["steps"].items():
                percentage = summary["step_percentages"][step]
                logger.info(f"  - {step}: {duration}s ({percentage}%)")


class LLMCallMonitor:
    """LLM 调用监控"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root
        self.call_count = 0
        self.total_tokens = 0
        self.total_cost = 0.0  # 估算成本

        if project_root:
            self.observability_dir = project_root / ".webnovel" / "observability"
            self.observability_dir.mkdir(parents=True, exist_ok=True)
            self.llm_log_file = self.observability_dir / "llm_calls.jsonl"
        else:
            self.llm_log_file = None

    def record_call(self, model: str, prompt_tokens: int, completion_tokens: int, cost: float = 0.0):
        """记录 LLM 调用"""
        self.call_count += 1
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost += cost

        if self.llm_log_file:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": round(cost, 4),
            }
            try:
                with open(self.llm_log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"记录 LLM 调用失败: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """获取 LLM 调用总结"""
        return {
            "call_count": self.call_count,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "avg_tokens_per_call": round(self.total_tokens / self.call_count) if self.call_count > 0 else 0,
        }
