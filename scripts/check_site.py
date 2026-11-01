# -*- coding: utf-8 -*-
"""扫描 site.json 中所有可见文本的英文残留"""
import io, json, re, sys
from html.parser import HTMLParser

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

class TP(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
    def handle_data(self, d):
        d = d.strip()
        if d:
            self.texts.append(d)

data = json.load(open("app/public/site.json", encoding="utf-8"))

WL = set("""SOFR EFFR IORB TGA TGCR BGCR OBFR FHLB FHLBs LPI FSI GEX VIX VIX9D SPY QQQ DIA IWM RSP SMH SOXX GLD USO
GDP RRP ON SRF FIMA CTA CFTC COT ETF OAS HY IG BBB BB CCC EM NFCI ANFCI TIPS WTI AI IT bp bps z vs FOMC GCF USD RMP SOMA
E-mini Nasdaq Russell MaxDD CI Wednesday Thursday Tuesday Friday Monday Saturday Sunday
Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec UTC T-bill T-bills Treasuries Treasury
S&P EFFR01 IOER IOERs GSCPI fredgraph Calcbench""".split())

CHART_TOKEN_RE = re.compile("\\x00CHART:[^\\x00]+\\x00")

seen = set()
count = 0

def scan(html, where):
    global count
    html = CHART_TOKEN_RE.sub(" ", html)
    p = TP()
    try:
        p.feed(html)
    except Exception:
        return
    for t in p.texts:
        for m in re.finditer(r"[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)*", t):
            g = m.group(0)
            words = [w.strip("'-") for w in g.split()]
            bad = [w for w in words if w not in WL and len(w) >= 4]
            if not bad:
                continue
            if len(words) < 2 and len(bad[0]) < 5:
                continue
            if g in seen:
                continue
            seen.add(g)
            count += 1
            print(f"[{where}] {t[:140]}")
            print(f"    >>> {g[:150]}")

def walk_blocks(blocks, where):
    for b in blocks:
        t = b.get("t") or b.get("type")
        if t == "html":
            scan(b.get("html", ""), where)
        elif t == "cardgrid":
            for c in b.get("cards", []):
                scan(c.get("html", ""), where)
        elif t == "expander":
            scan(b.get("summary", ""), where)
            walk_blocks(b.get("blocks", []), where)
        elif t == "layer":
            scan(b.get("html", ""), where)

for hb in [data.get("headerHtml", "")]:
    scan(hb, "header")
for b in data.get("blocks", []):
    walk_blocks([b], "top")
for sec in data.get("sections", []):
    scan(sec.get("summaryHtml", ""), sec["id"] + "/summary")
    walk_blocks(sec.get("blocks", []), sec["id"])

print("TOTAL:", count)
