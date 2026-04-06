"""
Dashboard 启动脚本
"""

import argparse
import uvicorn
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="启动 NovelWriter Dashboard")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="项目根目录（默认当前目录）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址（默认 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="监听端口（默认 8765）",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载（开发模式）",
    )

    args = parser.parse_args()

    # 设置项目根目录
    from app import set_project_root
    set_project_root(args.project_root.resolve())

    print(f"\n🚀 NovelWriter Dashboard 启动中...")
    print(f"📁 项目目录: {args.project_root.resolve()}")
    print(f"🌐 访问地址: http://{args.host}:{args.port}")
    print(f"{'🔄 热重载已启用' if args.reload else ''}\n")

    # 启动 Uvicorn
    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
