#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行添加角色：在数据仓库对应目录创建 normal-character/<角色名>/
用法： python add.py <gs|sr|zzz> <角色名> [R|R17|R18]
示例： python add.py gs 刻晴 R
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import add_character, CONFIG  # noqa

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python add.py <gs|sr|zzz> <角色名> [R|R17|R18]")
        sys.exit(1)
    g = sys.argv[1]
    name = sys.argv[2]
    rlevel = sys.argv[3] if len(sys.argv) > 3 else "R"
    if g not in CONFIG["games"]:
        print(f"未知游戏: {g}（可选 {list(CONFIG['games'].keys())}）")
        sys.exit(1)
    res = add_character(g, name, rlevel)
    print(json.dumps(res, ensure_ascii=False, indent=2) if False else
          (f"已添加: {res['path']}" if res.get("ok") else f"失败: {res.get('error')}"))
