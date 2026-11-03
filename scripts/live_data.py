# -*- coding: utf-8 -*-
"""
从官方公开接口直接抓取核心流动性指标 → static-dist/live.js
数据源: FRED (圣路易斯联储 fredgraph.csv, 免 key) + 纽约联储 markets API
产出 window.LIVE_DATA, 由页面顶部的"实时快线"横幅渲染
用法: python scripts/live_data.py
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "static-dist")
OUT_JS = os.path.join(OUT_DIR, "live.js")
FLAG = os.path.join(HERE, ".force-rebuild")  # 数据有更新时置位, 供 build_static.py 判断
DEPLOYED_LIVE_JS = "https://gsy1005.github.io/l-/live.js"

# FRED 序列: (序列号, 中文名, 单位, 缩放)
# scale: raw → 显示值; FRED 的 WALCL 单位是百万美元, WRESBAL/WTREGEN/RRPONTSYD 是十亿美元
FRED_SERIES = [
    ("SOFR",        "SOFR 担保隔夜融资", "%", 1),
    ("EFFR",        "EFFR 有效联邦基金", "%", 1),
    ("IORB",        "IORB 准备金利率",   "%", 1),
    ("DGS2",        "2年期美债",         "%", 1),
    ("DGS10",       "10年期美债",        "%", 1),
    ("DGS30",       "30年期美债",        "%", 1),
    ("RRPONTSYD",   "ON RRP 隔夜逆回购", "$B", 1),
    ("WTREGEN",     "TGA 财政部一般账户", "$B", 1),
    ("WRESBAL",     "银行准备金",        "$B", 1),
    ("WALCL",       "美联储总资产",      "$B", 0.001),   # 百万 → 十亿
    ("BAMLC0A0CM",  "投资级债 OAS",      "%", 1),
    ("BAMLH0A0HYM2","高收益债 OAS",      "%", 1),
    ("VIXCLS",      "VIX 波动率",        "",  1),
    ("DTWEXBGS",    "广义美元指数",      "",  1),
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8")


def fred_latest(sid: str):
    """返回 (最新日期, 最新值, 前一期值); 无数据返回 None"""
    csv = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
    rows = []
    for line in csv.strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        v = v.strip()
        if v and v != ".":
            rows.append((d.strip(), float(v)))
    if not rows:
        return None
    prev = rows[-2][1] if len(rows) > 1 else None
    return rows[-1][0], rows[-1][1], prev


def nyfed_latest():
    """纽约联储: TGCR/BGCR 三方回购利率"""
    out = {}
    data = json.loads(fetch("https://markets.newyorkfed.org/api/rates/secured/all/latest.json"))
    for r in data.get("refRates", []):
        t = r.get("type")
        if t in ("TGCR", "BGCR") and r.get("percentRate") is not None:
            out[t] = (r["effectiveDate"], float(r["percentRate"]))
    return out


def fmt(v: float, unit: str) -> str:
    if unit == "$B" and abs(v) >= 1000:
        return f"{v/1000:.2f}T"
    if unit == "%":
        return f"{v:.2f}%"
    return f"{v:.2f}"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = []
    series_cache = {}

    for sid, label, unit, scale in FRED_SERIES:
        try:
            got = fred_latest(sid)
        except Exception as e:
            print(f"[跳过] {sid}: {e}")
            continue
        if not got:
            continue
        date, val, prev = got
        series_cache[sid] = (date, val)
        items.append({
            "k": sid, "label": label, "unit": unit,
            "date": date, "value": round(val * scale, 4),
            "prev": round(prev * scale, 4) if prev is not None else None,
        })
        time.sleep(0.3)  # 礼貌限速

    # SOFR − IORB 利差 (bp), 仪表盘的核心指标
    if "SOFR" in series_cache and "IORB" in series_cache:
        d_s, v_s = series_cache["SOFR"]
        v_i = series_cache["IORB"][1]
        items.insert(0, {
            "k": "SOFR-IORB", "label": "SOFR − IORB 利差", "unit": "bp",
            "date": d_s, "value": round((v_s - v_i) * 100, 1), "prev": None,
        })

    # 纽约联储 TGCR/BGCR
    try:
        ny = nyfed_latest()
        for t, label in (("TGCR", "TGCR 三方回购"), ("BGCR", "BGCR 广义回购")):
            if t in ny:
                d, v = ny[t]
                items.append({"k": t, "label": label, "unit": "%", "date": d, "value": v, "prev": None})
    except Exception as e:
        print("[跳过] 纽约联储:", e)

    payload = {
        "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "items": items,
    }
    js = "window.LIVE_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"

    # 与线上已部署的 live.js 对比, 不同则置重建标志
    changed = True
    try:
        deployed = fetch(DEPLOYED_LIVE_JS + "?t=" + str(int(time.time())))
        changed = deployed != js
    except Exception:
        changed = True
    if changed:
        open(FLAG, "w").write("1")
    elif os.path.exists(FLAG):
        os.remove(FLAG)

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"live.js 输出 {len(items)} 项指标, 数据{'有' if changed else '无'}变化 -> {os.path.abspath(OUT_JS)}")


if __name__ == "__main__":
    main()
