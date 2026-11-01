# -*- coding: utf-8 -*-
"""检测 i18n.py 中被截断在单词中间的 PHRASES 键（键在缓存原文中紧跟字母）。"""
import io, sys, re, ast

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

cache = open("scripts/cache/index.html", encoding="utf-8").read()
src = open("scripts/i18n.py", encoding="utf-8").read()

# 提取所有形如 ("...", "...") 的元组第一个字符串
pairs = re.findall(r'\(\s*("(?:[^"\\]|\\.)*")\s*,\s*\n?\s*"(?:[^"\\]|\\.)*"\s*\)', src)
print("total phrase keys:", len(pairs))

count = 0
for raw in pairs:
    try:
        k = ast.literal_eval(raw)
    except Exception:
        continue
    if not k or not k[-1].isalpha():
        continue
    idx = cache.find(k)
    while idx >= 0:
        nxt = cache[idx + len(k): idx + len(k) + 1]
        if nxt.isalpha():
            tail = cache[idx + len(k): idx + len(k) + 260]
            tail = re.sub(r"<[^>]+>", " ", tail)
            tail = re.sub(r"\s+", " ", tail)
            print("KEY_END: ..." + k[-70:])
            print("TAIL   :", tail[:230])
            print()
            count += 1
            break
        idx = cache.find(k, idx + 1)
print("truncated:", count)
