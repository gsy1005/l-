# -*- coding: utf-8 -*-
"""提取所有翻译后仍含英文残留的唯一文本节点, 输出完整内容供批量翻译"""
import io, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bs4 import BeautifulSoup
import i18n
from scrape_source import sanitize_text

cache = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "index.html"), encoding="utf-8").read()
soup = BeautifulSoup(cache, "lxml")
for tag in soup.find_all(["script", "style"]):
    tag.decompose()

WL = set("""SOFR EFFR IORB TGA TGCR BGCR OBFR FHLB FHLBs LPI FSI GEX VIX VIX9D SPY QQQ DIA IWM RSP SMH SOXX GLD USO
GDP RRP ON SRF FIMA CTA CFTC COT ETF OAS HY IG BBB BB CCC EM NFCI ANFCI TIPS WTI AI IT bp bps z vs FOMC GCF USD RMP SOMA
E-mini Nasdaq Russell MaxDD CI Wednesday Thursday Tuesday Friday Monday Saturday Sunday IOER
Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec UTC T-bill T-bills Treasuries Treasury S&P""".split())

uniq = {}
for txt in soup.find_all(string=True):
    s = sanitize_text(str(txt))
    if not s or not re.search(r"[A-Za-z]", s):
        continue
    t = i18n.translate_text(s)
    bad = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'\-]*", t):
        w = m.group(0).strip("'-")
        if len(w) >= 4 and w not in WL:
            bad.append(w)
    if bad:
        uniq.setdefault(s, t)

print("UNIQUE NODES WITH RESIDUAL:", len(uniq))
print()
for i, (src, dst) in enumerate(sorted(uniq.items(), key=lambda kv: -len(kv[0]))):
    print(f"### {i}")
    print("SRC:", src)
    print("NOW:", dst)
    print()
