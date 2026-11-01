# -*- coding: utf-8 -*-
"""QA: 模拟抓取管道的文本处理, 报告死键与英文残留"""
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

nodes = []
for txt in soup.find_all(string=True):
    s = sanitize_text(str(txt))
    if s and re.search(r"[A-Za-z]", s):
        nodes.append(s)

def pre_phrase(t):
    for rx, rep in i18n.PATTERNS:
        t = rx.sub(rep, t)
    return t

joined = "\n".join(pre_phrase(n) for n in nodes)

dead = [en for en, zh in i18n.PHRASES if en not in joined]
print("=== DEAD PHRASE KEYS:", len(dead))
for d in dead:
    print("  ", d[:110])

WL = set("""SOFR EFFR IORB TGA TGCR BGCR OBFR FHLB FHLBs LPI FSI GEX VIX VIX9D SPY QQQ DIA IWM RSP SMH SOXX GLD USO
GDP RRP ON SRF FIMA CTA CFTC COT ETF OAS HY IG BBB BB CCC EM NFCI ANFCI TIPS WTI AI IT bp bps z vs FOMC GCF USD RMP SOMA
E-mini Nasdaq Russell MaxDD CI Wednesday Thursday Tuesday Friday Monday Saturday Sunday
Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec UTC T-bill T-bills Treasuries Treasury Binance CoinGecko OKX SqueezeMetrics
GitHub Actions FRED DTS H.4.1 Fed NY ICE BofA Cboe SSGA S&P PRATES Calcbench""".split())

print("=== RESIDUAL ENGLISH (translated nodes) ===")
seen = set()
for n in nodes:
    t = i18n.translate_text(n)
    for m in re.finditer(r"[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)*", t):
        g = m.group(0)
        words = g.split()
        bad = [w for w in words if w.strip("'-") not in WL and len(w.strip("'-")) >= 4]
        if not bad:
            continue
        if len(words) >= 2 or len(bad[0].strip("'-")) >= 5:
            key = g
            if key in seen:
                continue
            seen.add(key)
            print("  NODE:", n[:100])
            print("  RES :", g[:160])
            print()
