# -*- coding: utf-8 -*-
"""
Dreamina Toolkit - 启动脚本
提供两种启动方式：
  python run.py           → 仅启动 WebSocket 服务（无 UI，适合后台运行）
  python run.py --ui      → 启动 PySide6 图形界面（包含服务 + 控制台）
"""

import argparse
import sys
import os

# 确保使用虚拟环境的包
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")

# 如果当前 Python 不是虚拟环境中的，尝试切换
def ensure_venv():
    """确保在虚拟环境中运行"""
    if sys.prefix.lower() != SCRIPT_DIR.lower():
        # 检查虚拟环境是否存在
        if os.path.exists(VENV_PYTHON):
            print(f"[Info] 检测到需要使用虚拟环境，正在切换...")
            os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])
        else:
            print("[Warning] 虚拟环境不存在，请先初始化:")
            print(f"  cd {SCRIPT_DIR}")
            print("  python -m venv venv")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Dreamina Toolkit - 本地中转服务")
    parser.add_argument("--ui", action="store_true", help="启动 PySide6 图形界面")
    parser.add_argument("--host", default="127.0.0.1", help="WebSocket 服务地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket 服务端口 (默认 8765)")
    args = parser.parse_args()

    if args.ui:
        # 启动 PySide6 图形界面
        from main import main as ui_main
        ui_main()
    else:
        # 仅启动无 UI 的 WebSocket 服务
        from server import run_server
        print(f"[Info] 启动 WebSocket 服务 → ws://{args.host}:{args.port}/ws")
        run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
