"""
日志工具
"""

import logging
from pathlib import Path


def setup_logging(project_root: Path, level: int = logging.INFO):
    """设置日志"""
    log_dir = project_root / ".webnovel" / "observability"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "novel_writer.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    
    return logging.getLogger("novel_writer")
