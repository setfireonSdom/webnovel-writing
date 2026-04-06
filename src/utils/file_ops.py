"""
文件操作工具
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict

import filelock
from rich.console import Console

console = Console()


def atomic_write_json(path: Path, data: Dict[str, Any], use_lock: bool = True):
    """原子写入 JSON 文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if use_lock:
        lock_path = path.with_suffix(".lock")
        with filelock.FileLock(str(lock_path)):
            _write_json_impl(path, data)
    else:
        _write_json_impl(path, data)


def _write_json_impl(path: Path, data: Dict[str, Any]):
    temp_path = path.with_suffix(".json.tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.replace(path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise e


def read_json(path: Path) -> Dict[str, Any]:
    """读取 JSON 文件"""
    path = Path(path)
    if not path.exists():
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_directory(path: Path):
    """确保目录存在"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)


def read_text_file(path: Path) -> str:
    """读取文本文件"""
    path = Path(path)
    if not path.exists():
        return ""
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text_file(path: Path, content: str):
    """写入文本文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def chapter_file_path(project_root: Path, chapter_num: int) -> Path:
    """获取章节文件路径"""
    return project_root / "正文" / f"ch{chapter_num:04d}.md"


def find_chapter_file(project_root: Path, chapter_num: int) -> Path:
    """查找章节文件"""
    return chapter_file_path(project_root, chapter_num)
