# -*- coding: utf-8 -*-
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
cache = open("scripts/cache/index.html", encoding="utf-8").read()
print("zh spans:", len(re.findall(r'class="zh"', cache)))
pat = re.compile(r'<span class="stage-title">([^<]+)<span class="zh">([^<]+)</span>')
for m in pat.finditer(cache):
    print(repr(m.group(1)), "->", repr(m.group(2)))
