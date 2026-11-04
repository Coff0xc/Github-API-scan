#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口。扫描实现只在 main_v2.2.py。"""

import sys
from pathlib import Path

import runpy


def main():
    target = Path(__file__).resolve().parent / "main_v2.2.py"
    print(
        f"[deprecated] {Path(__file__).name} 已合并到 main_v2.2.py，参数原样转交。",
        file=sys.stderr,
    )
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
