# -*- coding: utf-8 -*-
"""
抓取源站 (vincizh.github.io/market-fragility-dashboard) 并提取为结构化 site.json
- 文本内容: BeautifulSoup 解析为 html/chart 区块
- 图表数据: MFD JSON 对象 + Node 提取 Plotly.newPlot 捕获
- 清洗: 移除官方数据源署名、外链、数据序列代码
输出: app/public/site.json, app/src/source.css
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n

SRC_URL = "https://vincizh.github.io/market-fragility-dashboard"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT_JSON = os.path.join(HERE, "..", "app", "public", "site.json")
OUT_CSS = os.path.join(HERE, "..", "app", "src", "source.css")

CHART_ID_RE = re.compile(r"^(chart-|spark-|cot-chart-|mcc-|fcc-|lfc-|gxc-)")

# ---------- 清洗: 隐藏官方数据源 ----------
SERIES_CODES = (
    "WRESBAL|WTREGEN|WALCL|RRPONTSYD|RPONTSYD|WLCFLPCL|SWPT|H41RESPPALGTRFNWW|WLRRAFOIAL|"
    "TGCRRATE|SOFR99|SOFRVOL|EFFRVOL|DTWEXBGS|THREEFYTP10|BAMLH0A0HYM2|BAMLC0A0CM|BAMLH0A3HYC|"
    "BAMLH0A1HYBB|BAMLC0A3EY|VIXCLS|VXVCLS|DCOILWTICO|OBFR|NFCI|DGS30|DGS10|DGS2|"
    "SPX|VIX9D"  # 注意: SPX 出现在 cot 名称中会被误伤, 下面用更精确的方式
)
# 精确代码(不带 SPX/VIX9D 这种常用词)
CODE_RE = re.compile(r"\b(WRESBAL|WTREGEN|WALCL|RRPONTSYD|RPONTSYD|WLCFLPCL|SWPT|H41RESPPALGTRFNWW|"
                     r"WLRRAFOIAL|TGCRRATE|SOFR99|SOFRVOL|EFFRVOL|DTWEXBGS|THREEFYTP10|BAMLH0A0HYM2|"
                     r"BAMLC0A0CM|BAMLH0A3HYC|BAMLH0A1HYBB|BAMLC0A3EY|VIXCLS|VXVCLS|DCOILWTICO|OBFR|"
                     r"NFCI|DGS30|DGS10|DGS2|WLCFLL|DFF|TASACBW027SBOG)\b")
TOKEN_SUBS = [
    (re.compile(r"\bFRED\b\s*"), ""),
    (re.compile(r"fredgraph\.csv", re.I), ""),
    (re.compile(r"\bPRATES\b"), ""),
    (re.compile(r"H\.4\.1 Table \d+", re.I), "Fed 周报"),
    (re.compile(r"H\.4\.1", re.I), "Fed 周报"),
    (re.compile(r"\bDTS\b"), "财政部日报"),
    (re.compile(r"Daily Treasury Statement", re.I), "财政部每日报表"),
    (re.compile(r"FiscalData", re.I), ""),
    (re.compile(r"TreasuryDirect", re.I), ""),
    (re.compile(r"SqueezeMetrics", re.I), "期权持仓"),
    (re.compile(r"GitHub Actions", re.I), "自动任务"),
    (re.compile(r"stlouisfed\.org", re.I), ""),
    (re.compile(r"newyorkfed\.org", re.I), ""),
    (re.compile(r"federalreserve\.gov", re.I), ""),
    (re.compile(r"\bYahoo Finance\b", re.I), "行情数据"),
    (re.compile(r"\bCboe official\b", re.I), "官方"),
    (re.compile(r"\bCboe\b"), "波动率交易所"),
    (re.compile(r"\bICE BofA\b", re.I), "债券指数"),
    (re.compile(r"\bNY Fed\b", re.I), "纽约联储"),
    (re.compile(r"New York Fed", re.I), "纽约联储"),
    (re.compile(r"\bYahoo\b", re.I), ""),
    (re.compile(r"\^VIX"), "VIX"),
    (re.compile(r"auctions_query"), "拍卖查询"),
    (re.compile(r"upcoming_auctions"), "拍卖日程"),
    (re.compile(r"Fed Fed 周报"), "美联储周报"),
    (re.compile(r"\bBinance\b", re.I), "交易所"),
]


def sanitize_text(t: str) -> str:
    t = CODE_RE.sub("", t)
    for rx, rep in TOKEN_SUBS:
        t = rx.sub(rep, t)
    # 剥离文本节点尾部的 Source:/Sources: 署名 (用户要求隐藏官方数据源)
    t = re.sub(r"\s*Sources?:\s*[^.:]*\.?\s*$", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([·,;。)])", r"\1", t)
    t = re.sub(r"([({\[])\s+", r"\1", t)
    t = re.sub(r"\s+([)}\]])", r"\1", t)
    t = re.sub(r"(·\s*){2,}", "· ", t)
    return t.strip()


def sanitize_node(node: Tag):
    """就地清洗: 展开外链, 删除 Source 段落, 清理文本"""
    for a in node.find_all("a"):
        a.unwrap()
    # 阶段标题: 已有中文 zh 副标时, 去掉前面的英文主标
    for st in node.find_all("span", class_="stage-title"):
        zh = st.find("span", class_="zh")
        if zh:
            for child in list(st.contents):
                if child is zh:
                    break
                child.extract()
    # 删除 <b>Source(s):</b> 到下一个 <br> 之间的内容
    for b in node.find_all("b"):
        if b.get_text(strip=True).lower().rstrip(":") in ("source", "sources", "official sources"):
            sib = b.next_sibling
            b.decompose()
            while sib is not None:
                nxt = sib.next_sibling
                if isinstance(sib, Tag) and sib.name == "br":
                    sib.decompose()
                    break
                sib.extract() if isinstance(sib, Tag) else sib.extract()
                sib = nxt
    for txt in node.find_all(string=True):
        new = i18n.translate_text(sanitize_text(str(txt)))
        if new != str(txt):
            txt.replace_with(new)


def el_html(el: Tag) -> str:
    return "".join(str(c) for c in el.children).strip()


CHART_TOKEN = "\u0000CHART:{}\u0000"


def tokenize_charts(html_str: str) -> str:
    """把空图表容器 div 换成占位 token"""
    def repl(m):
        return CHART_TOKEN.format(m.group(1))
    # 匹配 <div ... id="chart-xxx" ...></div> (空内容)
    return re.sub(
        r'<div[^>]*id="((?:chart-|spark-|cot-chart-|mcc-|fcc-|lfc-|gxc-)[\w-]*)"[^>]*>\s*</div>',
        repl, html_str)


def extract_about(el: Tag):
    d = el.find("details", class_="metric-details")
    if not d:
        return None
    s = d.find("summary")
    body = d.find("div")
    return {"summary": sanitize_text(s.get_text(" ", strip=True)) if s else "说明",
            "html": sanitize_html_node(body) if body else ""}


def sanitize_html_node(el: Tag) -> str:
    if el is None:
        return ""
    import copy
    frag = BeautifulSoup(str(el), "lxml")
    root = frag.body if frag.body else frag
    for r in list(root.children):
        sanitize_node(r) if isinstance(r, Tag) else None
    out = "".join(str(c) for c in root.children)
    out = re.sub(r"</?(div|br)[^>]*>", lambda m: "\n" if m.group(1) in ("div", "br") else "", out)
    return out.strip()


def parse_frag(el: Tag) -> Tag:
    """把元素重新解析为独立 fragment, 返回容器节点"""
    frag = BeautifulSoup(str(el), "lxml")
    return frag.body or frag


def block_html(el: Tag) -> dict:
    root = parse_frag(el)
    # 移除交互控件与脚本
    for sel in ["script", ".mod-head", ".mod-ranges", ".sh-ranges", ".tabs"]:
        for x in root.select(sel):
            x.decompose()
    for child in list(root.children):
        if isinstance(child, Tag):
            sanitize_node(child)
    h = el_html(root)
    # 保留卡片自身外层 class
    outer_class = " ".join(el.get("class") or [])
    h = tokenize_charts(h)
    return {"t": "html", "cls": outer_class, "html": h}


SKIP_CLASSES = ("mod-head", "tabs", "bottom-bar")


def walk(parent: Tag) -> list:
    blocks = []
    for el in parent.children:
        if not isinstance(el, Tag):
            continue
        if el.name == "script":
            continue
        cls = el.get("class") or []
        cset = set(cls)
        if cset & set(SKIP_CLASSES):
            continue
        txt = el.get_text(" ", strip=True)
        # 独立图表容器
        eid = el.get("id", "")
        if eid and CHART_ID_RE.match(eid):
            blocks.append({"t": "chart", "id": eid})
            continue
        # 分组容器: 递归展开
        if cset & {"mod-section", "gex-section", "regime-wrap", "charts-grid", "fp-charts",
                   "mc-grid", "fast-grid", "sig-grid", "lpi-factors", "tab-pane", "mod-body"}:
            if cset & {"mc-grid", "fast-grid", "sig-grid", "lpi-factors"}:
                blocks.append({"t": "cardgrid", "kind": next(iter(cset & {"mc-grid", "fast-grid", "sig-grid", "lpi-factors"})),
                               "cards": [block_html(c) for c in el.children if isinstance(c, Tag)]})
            else:
                blocks.extend(walk(el))
            continue
        if el.name == "details":
            summary = el.find("summary")
            body_blocks = []
            for c in el.children:
                if isinstance(c, Tag) and c.name != "summary":
                    body_blocks.extend(walk(c))
                elif isinstance(c, Tag):
                    pass
            blocks.append({"t": "expander", "summary": i18n.translate_text(sanitize_text(summary.get_text(" ", strip=True))) if summary else "展开",
                           "blocks": body_blocks})
            continue
        if not txt and not el.find(id=CHART_ID_RE):
            continue
        blocks.append(block_html(el))
    return blocks


def main():
    os.makedirs(CACHE, exist_ok=True)
    cache_file = os.path.join(CACHE, "index.html")
    if "--cached" in sys.argv and os.path.exists(cache_file):
        html = open(cache_file, encoding="utf-8").read()
        print("使用缓存页面")
    else:
        req = urllib.request.Request(SRC_URL, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        open(cache_file, "w", encoding="utf-8").write(html)
        print(f"已抓取源站 {len(html)//1024} KB")

    soup = BeautifulSoup(html, "lxml")

    # ---- CSS ----
    style = soup.find("style")
    css = style.string or "" if style else ""
    css = css.replace("http://", "").replace("https://", "")
    os.makedirs(os.path.dirname(OUT_CSS), exist_ok=True)
    open(OUT_CSS, "w", encoding="utf-8").write(css)
    print(f"CSS {len(css)//1024} KB -> {OUT_CSS}")

    # ---- 图表数据: MFD + newPlot 捕获 ----
    i = html.find("var MFD=")
    registry = {}
    if i >= 0:
        j = i + len("var MFD=")
        depth, k, in_str, esc = 0, j, False, False
        while k < len(html):
            ch = html[k]
            if in_str:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
                elif ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: break
            k += 1
        mfd = json.loads(html[j:k+1])
        for group, charts in mfd.items():
            if not isinstance(charts, list):
                continue
            for cd in charts:
                if isinstance(cd, dict) and cd.get("id"):
                    registry[cd["id"]] = {"kind": "mfd", **cd}
        print(f"MFD 图表: {len(registry)}")

    node_out = os.path.join(CACHE, "charts.json")
    subprocess.run(["node", os.path.join(HERE, "extract_charts.js"), cache_file, node_out],
                   check=False, capture_output=True)
    if os.path.exists(node_out):
        cap = json.load(open(node_out, encoding="utf-8"))
        for cid, cdata in cap.items():
            if cid.endswith("@react"):
                continue
            registry[cid] = {"kind": "plotly", "id": cid, **cdata}
        print(f"合并后图表注册表: {len(registry)}")

    # ---- 图表元数据翻译 ----
    for cid, cd in registry.items():
        if isinstance(cd.get("title"), dict):
            t = cd["title"].get("text")
            if t:
                cd["title"]["text"] = i18n.translate_text(str(t))
        else:
            i18n.translate_chart(cd)
        # plotly layout 标题
        lay = cd.get("layout")
        if isinstance(lay, dict) and isinstance(lay.get("title"), dict) and lay["title"].get("text"):
            lay["title"]["text"] = i18n.translate_text(str(lay["title"]["text"]))

    # ---- 页面结构 ----
    def clean_el(el):
        root = parse_frag(el)
        for sel in ["script", ".mod-head", ".mod-ranges", ".sh-ranges", ".tabs"]:
            for x in root.select(sel):
                x.decompose()
        for child in list(root.children):
            if isinstance(child, Tag):
                sanitize_node(child)
        return tokenize_charts(el_html(root))

    body = soup.body
    site = {"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "blocks": [], "sections": [], "charts": registry}

    for el in body.children:
        if not isinstance(el, Tag) or el.name in ("script",):
            continue
        cls = el.get("class") or []
        eid = el.get("id", "")
        if "header" in cls:
            site["headerHtml"] = clean_el(el)
            continue
        if "sec-nav" in cls:
            # 重建导航为中文锚点
            continue
        if eid in ("overview", "sofr-hero") or "what-changed" in cls or "takeaway" in cls:
            site["blocks"].append({"t": "html", "cls": " ".join(cls), "html": clean_el(el)})
            continue
        if "layer-header" in cls:
            site["blocks"].append({"t": "layer", "html": clean_el(el)})
            continue
        if el.name == "details" and eid.startswith("sec-"):
            summary = el.find("summary", class_="sec-sum")
            sbody = el.find("div", class_="sec-body")
            site["sections"].append({
                "id": eid,
                "open": el.has_attr("open"),
                "summaryHtml": clean_el(summary) if summary else eid,
                "blocks": walk(sbody) if sbody else [],
            })
            continue

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(site, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"site.json {os.path.getsize(OUT_JSON)//1024} KB -> {OUT_JSON}")
    print("sections:", [(s["id"], len(s["blocks"])) for s in site["sections"]])


if __name__ == "__main__":
    main()
