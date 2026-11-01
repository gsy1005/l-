# -*- coding: utf-8 -*-
"""给定句子前缀, 从源站缓存打印后续完整原文(去标签)"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

cache = open("scripts/cache/index.html", encoding="utf-8").read()

PREFIXES = [
    "Emphasized line is a 5-observation median of non-calendar rea",
    "scarcity or balanc",
    "The strategy overlay leg turns on when the filtered me",
    "it is a confirmat",
    "week ended Wednes",
    "more likely to trade above t",
    "which drains reserves one-for-one, all",
    "rather than bei",
    "A rebuilding TGA moves cash from banks to the Treasury",
    "Repo can also price above IORB for reasons unrelated",
    "is not ris",
    "They rise when dealers need cash to finance T",
    "the pressure is in bilateral dealer-cle",
    "a persistent premium to IORB points to collateral-financing pressure rat",
    "Rising volume with a stable rate is normal mon",
    "Unsecured on: EFFR - IORB at or above 0 bp, or up 2 b",
    "the header shows an inc",
    "When reserves become scarce, banks bid more",
    "A positive and widening gap means cash against",
    "It reflects the dispersion of rates paid by",
    "These absolute levels are a",
    "When SOFR rises but BGCR does not",
]
for p in PREFIXES:
    idx = cache.find(p)
    if idx < 0:
        print("NOT FOUND:", p[:60]); print(); continue
    tail = cache[idx: idx + 700]
    tail = re.sub(r"<[^>]+>", "|", tail)
    tail = re.sub(r"\s+", " ", tail)
    print("PRE:", p[:50])
    print("FULL:", tail[:600])
    print()
