"""
Git 操作工具
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitOps:
    """Git 操作工具类"""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def _run_git(self, *args: str) -> Optional[str]:
        """执行 Git命令"""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Git 命令失败: {result.stderr}")
                return None
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Git 命令执行失败: {e}")
            return None

    def is_git_repo(self) -> bool:
        """检查是否是 Git 仓库"""
        result = self._run_git("rev-parse", "--git-dir")
        return result is not None

    def init_repo(self) -> bool:
        """初始化 Git 仓库"""
        if self.is_git_repo():
            logger.info("已是 Git 仓库")
            return True

        result = self._run_git("init")
        if result is not None:
            logger.info("Git 仓库初始化成功")
            return True
        return False

    def add_all(self) -> bool:
        """添加所有文件"""
        result = self._run_git("add", "-A")
        return result is not None

    def commit(self, message: str) -> bool:
        """提交更改"""
        result = self._run_git("commit", "-m", message)
        if result is not None:
            logger.info(f"Git 提交成功: {message[:50]}")
        return result is not None

    def create_tag(self, tag_name: str, message: str = "") -> bool:
        """创建标签"""
        cmd = ["tag", "-a", tag_name]
        if message:
            cmd.extend(["-m", message])
        
        result = self._run_git(*cmd)
        if result is not None:
            logger.info(f"Git 标签创建成功: {tag_name}")
        return result is not None

    def get_current_branch(self) -> Optional[str]:
        """获取当前分支"""
        return self._run_git("rev-parse", "--abbrev-ref", "HEAD")

    def get_status(self) -> Optional[str]:
        """获取 Git 状态"""
        return self._run_git("status", "--short")

    def has_uncommitted_changes(self) -> bool:
        """检查是否有未提交的更改"""
        status = self.get_status()
        return status is not None and len(status) > 0

    def backup_chapter(self, chapter_num: int) -> bool:
        """备份章节"""
        if not self.is_git_repo():
            logger.warning("不是 Git 仓库，跳过备份")
            return False

        chapter_file = self.project_root / "正文" / f"ch{chapter_num:04d}.md"
        if not chapter_file.exists():
            logger.warning(f"章节文件不存在: {chapter_file}")
            return False

        # 添加并提交
        if self.add_all():
            commit_msg = f"feat: 完成第 {chapter_num} 章"
            if self.commit(commit_msg):
                # 创建标签
                tag_name = f"chapter-{chapter_num:04d}"
                self.create_tag(tag_name, f"第 {chapter_num} 章完成")
                return True

        return False
