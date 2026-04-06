#!/usr/bin/env python3
"""
NovelWriter - 模型无关的网文写作系统
CLI 主入口
"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.main import main

if __name__ == "__main__":
    main()
